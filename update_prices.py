#!/usr/bin/env python3
"""Track A: fetch yfinance values for every ticker row in each configured tab and
write them back to the Google Sheet. Designed to run on a GitHub Actions schedule,
but also runnable locally for testing.

Privacy: this repo is PUBLIC and Actions logs are world-readable. Never print
ticker symbols, names, or prices — only tab names (generic identifiers), row
numbers, and aggregate counts. See CLAUDE.md.

Two tab types (config.yaml `tabs[].type`):
  holdings  -> 現在株価 = currentPrice, 配当利回り = dividendYield (a percent
               number, e.g. 2.34), 配当金 = dividendRate * 取得株数.
  watchlist -> the rich yfinance metric set (price, PER/PBR, dividend yield,
               market cap, 3-month max volume, 52-week high/low, EPS TTM, EPS
               history + YoY, consensus targets, analyst count, rating) plus a
               write timestamp.

Track A writes only the roles it owns; the manual columns and the Track B columns
(industry PER/PBR, target/theoretical price, AI comments) are never touched.
Columns are resolved by header name (see sheet.py), so a column move does not
misdirect a write.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf

from sheet import (
    get_client,
    index_to_col,
    load_config,
    open_spreadsheet,
    resolve_columns,
)

# --- holdings tab -----------------------------------------------------------
HOLDINGS_WRITE_ROLES = ("current_price", "dividend_yield", "dividend_amount")

# --- watchlist tab ----------------------------------------------------------
# role -> yfinance Ticker.info field (written verbatim, "N/A" when absent).
WATCHLIST_INFO_FIELDS = {
    "current_price": "currentPrice",
    "per": "trailingPE",
    "pbr": "priceToBook",
    "dividend_yield": "dividendYield",
    "market_cap": "marketCap",
    "wk52_high": "fiftyTwoWeekHigh",
    "wk52_low": "fiftyTwoWeekLow",
    "eps_ttm": "trailingEps",
    "target_mean": "targetMeanPrice",
    "target_high": "targetHighPrice",
    "target_low": "targetLowPrice",
    "num_analysts": "numberOfAnalystOpinions",
    "rating": "recommendationKey",
}
WATCHLIST_EPS_ROLES = ("eps_fy0", "eps_fy1", "eps_fy2", "eps_fy3")
WATCHLIST_DERIVED_ROLES = (
    "vol_3mo_max",
    *WATCHLIST_EPS_ROLES,
    "eps_yoy_latest",
    "eps_yoy_prev",
)
# Every role Track A may write into a watchlist tab (used to gate by what the tab
# actually has a column for).
WATCHLIST_WRITE_ROLES = (
    *WATCHLIST_INFO_FIELDS.keys(),
    *WATCHLIST_DERIVED_ROLES,
)


def _to_float(value: object) -> float | None:
    """Parse a sheet/info value to float; '1,000' -> 1000.0, blank/garbage -> None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _round(value: object, ndigits: int = 2) -> object:
    f = _to_float(value)
    return round(f, ndigits) if f is not None else "N/A"


def _dividend_total(rate: object, shares: object) -> object:
    """Total annual dividend = per-share dividendRate * shares held.

    Blank ('') when shares is missing/zero (the holding's share count is a manual
    field and may be empty); 'N/A' when the per-share rate is missing.
    """
    r = _to_float(rate)
    s = _to_float(shares)
    if r is None:
        return "N/A"
    if s is None or s == 0:
        return ""
    return round(r * s, 2)


def _annual_eps(ticker: "yf.Ticker", n: int) -> list:
    """Up to n most-recent annual EPS values (newest first), None-padded."""
    try:
        ist = ticker.income_stmt
        if ist is None:
            return [None] * n
        for rowname in ("Diluted EPS", "Basic EPS"):
            if rowname in ist.index:
                out = []
                for v in ist.loc[rowname].values:  # columns are newest-first
                    try:
                        fv = float(v)
                        out.append(None if fv != fv else round(fv, 2))  # NaN -> None
                    except Exception:
                        out.append(None)
                return (out + [None] * n)[:n]
    except Exception:
        pass
    return [None] * n


def _yoy(new: object, old: object) -> object:
    if new is None or old is None or old == 0:
        return "N/A"
    return round((new - old) / abs(old) * 100, 1)


def _resolve_price(ticker: "yf.Ticker", info: dict, hist) -> float | None:
    price = info.get("currentPrice")
    if not price:
        try:
            price = ticker.fast_info["last_price"]
        except Exception:
            price = None
    if not price and hist is not None and not hist.empty:
        try:
            price = float(hist["Close"].dropna().iloc[-1])
        except Exception:
            price = None
    return float(price) if price else None


def fetch_holding(symbol: str, shares: object) -> dict | None:
    """Return {role: value} for the three holdings Track A columns, or None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        try:
            info = dict(ticker.info or {})
        except Exception:
            info = {}

        price = info.get("currentPrice")
        if not price:
            try:
                price = ticker.fast_info["last_price"]
            except Exception:
                price = None
        if not price:
            try:
                hist = ticker.history(period="5d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].dropna().iloc[-1])
            except Exception:
                price = None
        if not price and not info:
            return None

        return {
            "current_price": _round(price) if price else "N/A",
            "dividend_yield": _round(info.get("dividendYield")),
            "dividend_amount": _dividend_total(info.get("dividendRate"), shares),
        }
    except Exception:  # noqa: BLE001 - logged by row, never by symbol
        return None


def fetch_watchlist(symbol: str, roles: set[str]) -> dict | None:
    """Return {role: value} for the watchlist Track A columns present in `roles`,
    or None on total failure. Only fetches the data the requested roles need."""
    try:
        ticker = yf.Ticker(symbol)
        try:
            info = dict(ticker.info or {})
        except Exception:
            info = {}

        hist = None
        if "vol_3mo_max" in roles or not info.get("currentPrice"):
            try:
                hist = ticker.history(period="3mo")
            except Exception:
                hist = None

        price = _resolve_price(ticker, info, hist)
        if price:
            info["currentPrice"] = round(price, 4)
        if not info and price is None:
            return None

        out: dict[str, object] = {}
        for role, field in WATCHLIST_INFO_FIELDS.items():
            if role in roles:
                v = info.get(field)
                out[role] = v if v is not None else "N/A"

        if "vol_3mo_max" in roles:
            v: object = "N/A"
            if hist is not None and not hist.empty and "Volume" in hist.columns:
                try:
                    mx = int(hist["Volume"].max())
                    v = mx if mx > 0 else "N/A"
                except Exception:
                    v = "N/A"
            out["vol_3mo_max"] = v

        if roles & {*WATCHLIST_EPS_ROLES, "eps_yoy_latest", "eps_yoy_prev"}:
            eps = _annual_eps(ticker, 4)
            for i, role in enumerate(WATCHLIST_EPS_ROLES):
                if role in roles:
                    out[role] = eps[i] if eps[i] is not None else "N/A"
            if "eps_yoy_latest" in roles:
                out["eps_yoy_latest"] = _yoy(eps[0], eps[1])
            if "eps_yoy_prev" in roles:
                out["eps_yoy_prev"] = _yoy(eps[1], eps[2])

        return out
    except Exception:  # noqa: BLE001 - logged by row, never by symbol
        return None


def _ticker_rows(values: list[list[str]], ticker_idx0: int, header_rows: int):
    """Yield (row_num, row, symbol) for each data row that has a ticker."""
    for r in range(header_rows, len(values)):
        row = values[r]
        symbol = (row[ticker_idx0] if ticker_idx0 < len(row) else "").strip()
        if symbol:
            yield r + 1, row, symbol


def update_holdings(ws, cols: dict[str, int], header_rows: int, dry_run: bool) -> tuple[int, int]:
    values = ws.get_all_values()
    ticker_idx0 = cols["ticker"] - 1
    shares_idx0 = (cols.get("shares") or 0) - 1
    write_cols = {role: cols[role] for role in HOLDINGS_WRITE_ROLES if role in cols}
    updates: list[dict] = []
    n_ok = n_na = 0
    for row_num, row, symbol in _ticker_rows(values, ticker_idx0, header_rows):
        shares = row[shares_idx0] if 0 <= shares_idx0 < len(row) else None
        result = fetch_holding(symbol, shares)
        if result is None:
            n_na += 1
            print(f"  fetch failed at row {row_num}", file=sys.stderr)
            continue
        for role, col_idx in write_cols.items():
            updates.append({"range": f"{index_to_col(col_idx)}{row_num}", "values": [[result[role]]]})
        n_ok += 1
    if updates and not dry_run:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return n_ok, n_na


def update_watchlist(ws, cols: dict[str, int], header_rows: int, now: str, dry_run: bool) -> tuple[int, int]:
    values = ws.get_all_values()
    ticker_idx0 = cols["ticker"] - 1
    roles = {role for role in WATCHLIST_WRITE_ROLES if role in cols}
    updates: list[dict] = []
    n_ok = n_na = 0
    for row_num, _row, symbol in _ticker_rows(values, ticker_idx0, header_rows):
        result = fetch_watchlist(symbol, roles)
        if result is None:
            n_na += 1
            print(f"  fetch failed at row {row_num}", file=sys.stderr)
            continue
        for role, val in result.items():
            if role in cols:
                updates.append({"range": f"{index_to_col(cols[role])}{row_num}", "values": [[val]]})
        if "updated" in cols:
            updates.append({"range": f"{index_to_col(cols['updated'])}{row_num}", "values": [[now]]})
        n_ok += 1
    if updates and not dry_run:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return n_ok, n_na


def main() -> int:
    parser = argparse.ArgumentParser(description="Track A price/metric updater")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and resolve columns but do not write to the sheet",
    )
    args = parser.parse_args()

    cfg = load_config()
    ss = open_spreadsheet(cfg, get_client())
    header_rows = int(cfg["header_rows"])
    tz = cfg["timezone"]
    now = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")

    grand_ok = grand_na = 0
    for t in cfg["tabs"]:
        try:
            ws = ss.worksheet(t["tab"])
        except Exception:
            print(f"  worksheet not found, skipped: {t['tab']}", file=sys.stderr)
            continue
        header = ws.row_values(header_rows)
        cols = resolve_columns(header, t["columns"], required={"ticker"})
        if t["type"] == "holdings":
            n_ok, n_na = update_holdings(ws, cols, header_rows, args.dry_run)
        else:
            n_ok, n_na = update_watchlist(ws, cols, header_rows, now, args.dry_run)
        print(f"[{t['tab']}] {n_ok} updated, {n_na} N/A")
        grand_ok += n_ok
        grand_na += n_na

    mode = " (dry-run, nothing written)" if args.dry_run else ""
    print(f"Done: {grand_ok} updated, {grand_na} N/A at {now} ({tz}){mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
