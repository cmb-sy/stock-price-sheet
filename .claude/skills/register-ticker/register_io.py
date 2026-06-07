#!/usr/bin/env python3
"""I/O helper for the register-ticker skill. LOCAL / MANUAL use only.

The owner registers a stock by name from the web app (a name-only row, no Ticker, in a
watchlist tab). This skill resolves that name to a yfinance ticker: it proposes
candidates from the yfinance search API, the HUMAN picks one, and only then is the
Ticker written back. Track A then fills the metric columns on its next run.

Subcommands:
  read-pending  Print JSON of every watchlist row that has a 銘柄名 but NO Ticker yet
                (the rows waiting for a ticker), as [{tab,row,name}, ...].
  search        Read a query string from argv (or stdin) and print yfinance search
                candidates as [{symbol,name,exchange,type}, ...]. Used to PROPOSE
                tickers to the human; it never auto-picks.
  write-ticker  Read {"writes": [{"tab","row","ticker"}, ...]} from stdin and batch-
                write each ticker into the Ticker column ONLY. No other column is
                touched; a non-Ticker target is refused.

This output is consumed by Claude locally during a manual run. It is never committed
and must not be piped into the repo or into Actions logs.

Columns are resolved by header name (see sheet.py), so a column move in the sheet does
not misdirect a read or write.

Credentials: set GOOGLE_APPLICATION_CREDENTIALS (path to the local SA key) or
GCP_SA_KEY (JSON string), same as Track A.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root holds sheet.py: .claude/skills/register-ticker/ -> parents[3].
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sheet import (  # noqa: E402
    get_client,
    index_to_col,
    load_config,
    open_spreadsheet,
    resolve_columns,
    watchlist_tabs,
)

WRITE_ROLE = "ticker"
MAX_CANDIDATES = 8


def _cell(row: list[str], col_idx: int) -> str:
    i = col_idx - 1
    return row[i] if 0 <= i < len(row) else ""


def read_pending(cfg: dict, ss) -> None:
    out = []
    for tab in watchlist_tabs(cfg):
        try:
            ws = ss.worksheet(tab["tab"])
        except Exception:
            print(f"  worksheet not found, skipped: {tab['tab']}", file=sys.stderr)
            continue
        header = ws.row_values(int(cfg["header_rows"]))
        cols = resolve_columns(header, tab["columns"], required={"ticker", "name"})
        values = ws.get_all_values()
        for r in range(int(cfg["header_rows"]), len(values)):
            row = values[r]
            name = _cell(row, cols["name"]).strip()
            ticker = _cell(row, cols["ticker"]).strip()
            if name and not ticker:
                out.append({"tab": tab["tab"], "row": r + 1, "name": name})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def search(query: str) -> None:
    import yfinance as yf

    quotes = []
    try:
        quotes = yf.Search(query, max_results=MAX_CANDIDATES).quotes or []
    except Exception as e:
        print(f"search failed: {e}", file=sys.stderr)
    out = []
    for q in quotes:
        out.append(
            {
                "symbol": q.get("symbol", ""),
                "name": q.get("longname") or q.get("shortname") or "",
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
            }
        )
    print(json.dumps(out, ensure_ascii=False, indent=2))


def write_ticker(cfg: dict, ss) -> None:
    payload = json.load(sys.stdin)
    writes = payload.get("writes", [])
    by_tab: dict[str, list] = {}
    for w in writes:
        by_tab.setdefault(w["tab"], []).append(w)

    tab_by_name = {t["tab"]: t for t in watchlist_tabs(cfg)}
    total = 0
    for tab_name, tab_writes in by_tab.items():
        tab = tab_by_name.get(tab_name)
        if tab is None:
            sys.exit(f"unknown or non-watchlist tab: {tab_name!r}")
        ws = ss.worksheet(tab_name)
        header = ws.row_values(int(cfg["header_rows"]))
        cols = resolve_columns(header, tab["columns"], required={"ticker"})
        col_letter = index_to_col(cols[WRITE_ROLE])
        updates = []
        for w in tab_writes:
            ticker = str(w["ticker"]).strip()
            if not ticker:
                sys.exit("refusing to write an empty ticker")
            updates.append(
                {"range": f"{col_letter}{int(w['row'])}", "values": [[ticker]]}
            )
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
            total += len(updates)
    print(f"wrote {total} ticker(s)")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("read-pending", "search", "write-ticker"):
        sys.exit("usage: register_io.py [read-pending|search <query>|write-ticker]")
    if cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read().strip()
        if not query:
            sys.exit("search needs a query (argv or stdin)")
        search(query)
        return 0
    cfg = load_config()
    ss = open_spreadsheet(cfg, get_client())
    if cmd == "read-pending":
        read_pending(cfg, ss)
    else:
        write_ticker(cfg, ss)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
