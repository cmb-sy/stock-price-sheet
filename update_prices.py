#!/usr/bin/env python3
"""Track A: fetch yfinance values for every holding (a row with a ticker) in the
保有銘柄 tab and write them back to the Google Sheet. Designed to run on a GitHub
Actions schedule, but also runnable locally for testing.

Privacy: this repo is PUBLIC and Actions logs are world-readable. Never print
ticker symbols, names, or prices — only row numbers and aggregate counts. See
CLAUDE.md.

Track A writes exactly three columns, all derived from yfinance natively (no
scraping, no AI):
  現在株価   = currentPrice
  配当利回り = dividendYield      (a percent number, e.g. 2.34, not a fraction)
  配当金     = dividendRate * 取得株数  (total annual dividend received)
It never touches the manual columns or the AI-comment column. Columns are
resolved by header name (see sheet.py), so a column move does not misdirect a write.
"""
from __future__ import annotations

import argparse
import sys

import yfinance as yf

from sheet import get_client, index_to_col, load_config, open_spreadsheet, resolve_columns

# yfinance fields Track A writes, keyed by the logical role (config `columns`).
WRITE_ROLES = ("current_price", "dividend_yield", "dividend_amount")


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
    field and may be empty); 'N/A' only is handled by the caller for a missing rate.
    """
    r = _to_float(rate)
    s = _to_float(shares)
    if r is None:
        return "N/A"
    if s is None or s == 0:
        return ""
    return round(r * s, 2)


def fetch_holding(symbol: str, shares: object) -> dict | None:
    """Return {role: value} for the three Track A columns, or None on total failure."""
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


def update_holdings(ws, cols: dict[str, int], dry_run: bool) -> tuple[int, int]:
    """Fetch + write the holdings tab. Returns (n_ok, n_na)."""
    values = ws.get_all_values()
    header_rows = 1
    ticker_idx0 = cols["ticker"] - 1
    shares_idx0 = (cols.get("shares") or 0) - 1
    write_cols = {role: cols[role] for role in WRITE_ROLES if role in cols}
    updates: list[dict] = []
    n_ok = n_na = 0
    for r in range(header_rows, len(values)):
        row = values[r]
        symbol = (row[ticker_idx0] if ticker_idx0 < len(row) else "").strip()
        if not symbol:
            continue
        row_num = r + 1
        shares = row[shares_idx0] if 0 <= shares_idx0 < len(row) else None
        result = fetch_holding(symbol, shares)
        if result is None:
            n_na += 1
            print(f"  fetch failed at row {row_num}", file=sys.stderr)
            continue
        for role, col_idx in write_cols.items():
            cell = f"{index_to_col(col_idx)}{row_num}"
            updates.append({"range": cell, "values": [[result[role]]]})
        n_ok += 1

    if updates and not dry_run:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return n_ok, n_na


def main() -> int:
    parser = argparse.ArgumentParser(description="Track A holdings price/dividend updater")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and resolve columns but do not write to the sheet",
    )
    args = parser.parse_args()

    cfg = load_config()
    ss = open_spreadsheet(cfg, get_client())
    try:
        ws = ss.worksheet(cfg["holdings_tab"])
    except Exception:
        sys.exit(f"holdings tab not found: {cfg['holdings_tab']}")

    header = ws.row_values(int(cfg["header_rows"]))
    cols = resolve_columns(header, cfg["columns"], required={"ticker"})

    n_ok, n_na = update_holdings(ws, cols, args.dry_run)
    mode = " (dry-run, nothing written)" if args.dry_run else ""
    print(f"Done: {n_ok} updated, {n_na} N/A{mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
