#!/usr/bin/env python3
"""Track A: fetch yfinance-native + derived fields for every ticker in each
watchlist tab and write them back to the Google Sheet. Designed to run on a
GitHub Actions schedule, but also runnable locally for testing.

Privacy: this repo is PUBLIC and Actions logs are world-readable. Never print
ticker symbols, names, or prices — only worksheet/row numbers and aggregate
counts. See CLAUDE.md.

Track A writes ONLY the columns declared in config.yaml (the `fields` map plus
the derived columns: volume_3mo_max, EPS history, EPS YoY, and the timestamp).
It never touches the Track B / manual columns.
"""
from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf

from sheet import col_to_index, get_client, load_config, open_spreadsheet


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


def _yoy(new, old):
    if new is None or old is None or old == 0:
        return "N/A"
    return round((new - old) / abs(old) * 100, 1)


def fetch_row(symbol: str, cfg: dict) -> dict | None:
    """Return {column_letter: value} for one ticker, or None on total failure."""
    want_vol = bool(cfg["volume_3mo_max_column"])
    want_eps_hist = bool(cfg["eps_history_columns"])
    want_eps_yoy = bool(cfg["eps_yoy_columns"])
    try:
        ticker = yf.Ticker(symbol)
        try:
            info = dict(ticker.info or {})
        except Exception:
            info = {}

        hist = None
        if want_vol or not info.get("currentPrice"):
            try:
                hist = ticker.history(period="3mo")
            except Exception:
                hist = None

        price = info.get("currentPrice")
        if not price:
            try:
                price = ticker.fast_info["last_price"]
            except Exception:
                price = None
        if not price and hist is not None and not hist.empty:
            price = float(hist["Close"].iloc[-1])
        if price:
            info["currentPrice"] = round(float(price), 4)

        if not info:
            return None

        row: dict[str, object] = {
            col: (info.get(name) if info.get(name) is not None else "N/A")
            for name, col in cfg["fields"].items()
        }

        if want_vol:
            v: object = "N/A"
            if hist is not None and not hist.empty and "Volume" in hist.columns:
                try:
                    mx = int(hist["Volume"].max())
                    v = mx if mx > 0 else "N/A"
                except Exception:
                    v = "N/A"
            row[cfg["volume_3mo_max_column"]] = v

        if want_eps_hist or want_eps_yoy:
            eps = _annual_eps(ticker, 4)
            if want_eps_hist:
                for i, col in enumerate(cfg["eps_history_columns"]):
                    val = eps[i] if i < len(eps) else None
                    row[col] = val if val is not None else "N/A"
            if want_eps_yoy:
                ec = cfg["eps_yoy_columns"]
                if ec.get("latest"):
                    row[ec["latest"]] = _yoy(eps[0], eps[1])
                if ec.get("prev"):
                    row[ec["prev"]] = _yoy(eps[1], eps[2])

        return row
    except Exception:  # noqa: BLE001 - logged by row, never by symbol
        return None


def update_worksheet(ws, cfg: dict, now: str) -> tuple[int, int]:
    """Fetch + write one worksheet. Returns (n_ok, n_na)."""
    header_rows = int(cfg["header_rows"])
    tickers = ws.col_values(col_to_index(cfg["ticker_column"]))
    updates: list[dict] = []
    n_ok = n_na = 0
    for offset, raw_symbol in enumerate(tickers[header_rows:]):
        symbol = raw_symbol.strip()
        if not symbol:
            continue
        row_num = header_rows + offset + 1  # 1-based sheet row
        row = fetch_row(symbol, cfg)
        if row is None:
            n_na += 1
            print(f"  fetch failed at {ws.title} row {row_num}", file=sys.stderr)
            continue
        for col, val in row.items():
            updates.append({"range": f"{col}{row_num}", "values": [[val]]})
        if cfg["updated_column"]:
            updates.append({"range": f"{cfg['updated_column']}{row_num}", "values": [[now]]})
        n_ok += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return n_ok, n_na


def main() -> int:
    cfg = load_config()
    client = get_client()
    ss = open_spreadsheet(cfg, client)

    tz = cfg["timezone"]
    now = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")

    grand_ok = grand_na = 0
    for tab in cfg["watchlists"]:
        try:
            ws = ss.worksheet(tab)
        except Exception:
            print(f"  worksheet not found, skipped: {tab}", file=sys.stderr)
            continue
        n_ok, n_na = update_worksheet(ws, cfg, now)
        print(f"[{tab}] {n_ok} updated, {n_na} N/A")
        grand_ok += n_ok
        grand_na += n_na

    print(f"Done: {grand_ok} updated, {grand_na} N/A at {now} ({tz})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
