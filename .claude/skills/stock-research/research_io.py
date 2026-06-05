#!/usr/bin/env python3
"""Track B I/O helper for the stock-research skill. LOCAL / MANUAL use only.

Subcommands:
  read-rows   Print JSON of every watchlist row that has a ticker, with the
              ticker, Japanese name, and current Track B column values, so the
              skill can decide what to (re)search and update.
  write       Read {"writes": [{"tab","row","col","value"}, ...]} from stdin and
              batch-write each value (USER_ENTERED). Only Track B columns may be
              written (industry PER/PBR + the research block Y-AD); anything else
              is refused.

This output is consumed by Claude locally during a manual run. It is never
committed and must not be piped into the repo or into public Actions logs.

Credentials: set GOOGLE_APPLICATION_CREDENTIALS (path to the local SA key) or
GCP_SA_KEY (JSON string), same as Track A.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root holds sheet.py: .claude/skills/stock-research/ -> parents[3].
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sheet import col_to_index, get_client, load_config, open_spreadsheet  # noqa: E402

# Track B columns this helper is allowed to surface and write.
TRACK_B_COLS = {
    "E": "industry PER",
    "F": "industry PBR",
    "Y": "per-institution targets",
    "Z": "theoretical price",
    "AA": "catalyst/rating news",
    "AB": "source URLs",
    "AC": "Track B fetch date",
    "AD": "analysis comment",
}


def _cell(values: list[list[str]], row_idx: int, col_letter: str) -> str:
    i = col_to_index(col_letter) - 1
    row = values[row_idx] if row_idx < len(values) else []
    return row[i] if i < len(row) else ""


def read_rows(cfg: dict, ss) -> None:
    header_rows = int(cfg["header_rows"])
    ticker_col = cfg["ticker_column"]
    name_col = cfg["name_column"]
    out = []
    for tab in cfg["watchlists"]:
        try:
            ws = ss.worksheet(tab)
        except Exception:
            continue
        values = ws.get_all_values()
        for r in range(header_rows, len(values)):
            ticker = _cell(values, r, ticker_col).strip()
            if not ticker:
                continue
            out.append(
                {
                    "tab": tab,
                    "row": r + 1,  # 1-based sheet row
                    "ticker": ticker,
                    "name": _cell(values, r, name_col),
                    "current": {c: _cell(values, r, c) for c in TRACK_B_COLS},
                }
            )
    print(json.dumps(out, ensure_ascii=False, indent=2))


def write(cfg: dict, ss) -> None:
    payload = json.load(sys.stdin)
    writes = payload.get("writes", [])
    by_tab: dict[str, list[dict]] = {}
    for w in writes:
        col = str(w["col"]).strip().upper()
        if col not in TRACK_B_COLS:
            sys.exit(f"refusing to write non-Track-B column: {col}")
        by_tab.setdefault(w["tab"], []).append(
            {"range": f"{col}{int(w['row'])}", "values": [[w["value"]]]}
        )
    n = 0
    for tab, updates in by_tab.items():
        ss.worksheet(tab).batch_update(updates, value_input_option="USER_ENTERED")
        n += len(updates)
    print(f"wrote {n} cell(s) across {len(by_tab)} tab(s)")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("read-rows", "write"):
        sys.exit("usage: research_io.py [read-rows|write]")
    cfg = load_config()
    ss = open_spreadsheet(cfg, get_client())
    if sys.argv[1] == "read-rows":
        read_rows(cfg, ss)
    else:
        write(cfg, ss)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
