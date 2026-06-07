#!/usr/bin/env python3
"""Track A: fetch yfinance values for every ticker row in each configured tab and
write them back to the Google Sheet. Designed to run on a GitHub Actions schedule,
but also runnable locally for testing.

Privacy: treat Actions logs as potentially exposed (the repo is private, but this
is defense-in-depth). Never print ticker symbols, names, or prices — only tab names
(generic identifiers), row numbers, and aggregate counts. See CLAUDE.md.

Two tab types (config.yaml `tabs[].type`):
  holdings  -> 現在株価 = currentPrice, 配当利回り = dividendYield (a percent
               number, e.g. 2.34), 配当金 = dividendRate * 取得株数, and the derived
               年初来安値との乖離率 = (現在株価 - 年初来安値)/年初来安値*100.
  watchlist -> the yfinance metric set (price, PER/PBR, dividend yield, EPS TTM,
               EPS YoY, rating), market cap normalised to 億円 (JPY, FX-converted),
               the next earnings date, the kabutan URL derived from the ticker, the
               derived 年初来安値との乖離率, and a write timestamp.

Track A writes only the roles it owns; the manual columns and the Track B columns
(theme, industry PER/PBR, analyst/theoretical price, AI comments) are never touched.
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
# Every role Track A writes into a holdings tab. All are produced by fetch_holding
# (現在株価/配当利回り/配当金 from Ticker.info, plus the derived 年初来安値との乖離率).
HOLDINGS_WRITE_ROLES = (
    "current_price",
    "dividend_yield",
    "dividend_amount",
    "ytd_low_gap_pct",
)

# --- watchlist tab ----------------------------------------------------------
# role -> yfinance Ticker.info field (written verbatim, "N/A" when absent).
WATCHLIST_INFO_FIELDS = {
    "current_price": "currentPrice",
    "per": "trailingPE",
    "pbr": "priceToBook",
    "dividend_yield": "dividendYield",
    "eps_ttm": "trailingEps",
    "rating": "recommendationKey",
}
# Derived (not raw Ticker.info): EPS YoY from income_stmt annual EPS, next earnings
# date from ticker.calendar, the kabutan URL built from the ticker string, the market
# cap normalised to 億円 (JPY, FX-converted; see _market_cap_oku), and the gap vs the
# year-to-date low (現在株価 vs the YTD Low minimum).
WATCHLIST_DERIVED_ROLES = (
    "eps_yoy_latest",
    "next_earnings",
    "kabutan_url",
    "market_cap",
    "ytd_low_gap_pct",
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


def _ratio(new: object, base: object) -> object:
    """(new - base) / base * 100, rounded. 'N/A' if either side is non-numeric or
    base == 0 (never a fabricated number)."""
    n = _to_float(new)
    b = _to_float(base)
    if n is None or b is None or b == 0:
        return "N/A"
    return round((n - b) / b * 100, 2)


def _ytd_low(ticker: "yf.Ticker") -> float | None:
    """Lowest intraday Low since the start of the year, from ticker.history(ytd).
    None when history is unavailable, so callers degrade to 'N/A'."""
    try:
        hist = ticker.history(period="ytd")
        if hist is not None and not hist.empty:
            lows = hist["Low"].dropna()
            if not lows.empty:
                return float(lows.min())
    except Exception:
        pass
    return None


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


def _next_earnings(ticker: "yf.Ticker") -> object:
    """Next earnings date (YYYY-MM-DD) from ticker.calendar; soonest upcoming if
    several are listed, else the soonest available. 'N/A' when unknown."""
    try:
        cal = ticker.calendar or {}
        raw = cal.get("Earnings Date")
        if raw is None:
            return "N/A"
        dates = raw if isinstance(raw, (list, tuple)) else [raw]
        dates = [d for d in dates if hasattr(d, "isoformat")]
        if not dates:
            return "N/A"
        today = datetime.now().date()
        upcoming = sorted(d for d in dates if d >= today)
        chosen = upcoming[0] if upcoming else sorted(dates)[0]
        return chosen.isoformat()
    except Exception:
        return "N/A"


def _kabutan_url(symbol: str) -> str:
    """Kabutan stock-page URL derived from the yfinance ticker. Tokyo tickers
    (suffix .T) map to kabutan.jp by numeric code; everything else to the US site."""
    s = symbol.strip()
    if s.upper().endswith(".T"):
        return f"https://kabutan.jp/stock/?code={s[:-2]}"
    return f"https://us.kabutan.jp/stocks/{s.upper()}"


# Per-run cache of {currency -> JPY rate}; one network hit per foreign currency.
_FX_CACHE: dict[str, float | None] = {}


def _fx_to_jpy(currency: object) -> float | None:
    """Spot rate to convert `currency` into JPY (1.0 for JPY/unknown-as-JPY).

    Returns None if a foreign rate cannot be fetched, so callers degrade to 'N/A'
    rather than reporting a wrong number. Cached per run."""
    cur = str(currency or "").upper()
    if cur in ("", "JPY"):
        return 1.0
    if cur in _FX_CACHE:
        return _FX_CACHE[cur]
    rate: float | None = None
    try:
        hist = yf.Ticker(f"{cur}JPY=X").history(period="5d")
        if hist is not None and not hist.empty:
            rate = float(hist["Close"].dropna().iloc[-1])
    except Exception:
        rate = None
    _FX_CACHE[cur] = rate
    return rate


def _market_cap_oku(info: dict) -> object:
    """Market cap expressed in 億円 (JPY hundred-millions), as an integer.

    yfinance reports marketCap in the listing currency (USD for US tickers); it is
    FX-converted to JPY and divided by 1e8. 'N/A' when the cap is missing or the FX
    rate is unavailable (never a fabricated figure)."""
    cap = _to_float(info.get("marketCap"))
    if cap is None:
        return "N/A"
    rate = _fx_to_jpy(info.get("currency"))
    if rate is None:
        return "N/A"
    return round(cap * rate / 1e8)


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
    """Return {role: value} for the holdings Track A columns, or None on failure."""
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
            "ytd_low_gap_pct": _ratio(price, _ytd_low(ticker)),
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
        if not info.get("currentPrice"):
            try:
                hist = ticker.history(period="5d")
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

        if "eps_yoy_latest" in roles:
            eps = _annual_eps(ticker, 2)
            out["eps_yoy_latest"] = _yoy(eps[0], eps[1])

        if "next_earnings" in roles:
            out["next_earnings"] = _next_earnings(ticker)

        if "kabutan_url" in roles:
            out["kabutan_url"] = _kabutan_url(symbol)

        if "market_cap" in roles:
            out["market_cap"] = _market_cap_oku(info)

        if "ytd_low_gap_pct" in roles:
            out["ytd_low_gap_pct"] = _ratio(price, _ytd_low(ticker))

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


def _cell_by_role(row: list[str], cols: dict[str, int], role: str) -> object:
    """Value of a role's cell in this row, or None if the role/column is absent."""
    i = (cols.get(role) or 0) - 1
    return row[i] if 0 <= i < len(row) else None


def update_holdings(ws, cols: dict[str, int], header_rows: int, dry_run: bool) -> tuple[int, int]:
    values = ws.get_all_values()
    ticker_idx0 = cols["ticker"] - 1
    write_cols = {role: cols[role] for role in HOLDINGS_WRITE_ROLES if role in cols}
    updates: list[dict] = []
    n_ok = n_na = 0
    for row_num, row, symbol in _ticker_rows(values, ticker_idx0, header_rows):
        shares = _cell_by_role(row, cols, "shares")
        result = fetch_holding(symbol, shares)
        if result is None:
            n_na += 1
            print(f"  fetch failed at row {row_num}", file=sys.stderr)
            continue
        for role, col_idx in write_cols.items():
            if role in result:
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
    for row_num, row, symbol in _ticker_rows(values, ticker_idx0, header_rows):
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
