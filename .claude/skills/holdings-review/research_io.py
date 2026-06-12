#!/usr/bin/env python3
# Copyright (c) 2026 cmb-sy. All Rights Reserved. Proprietary; see LICENSE.
"""I/O helper for the holdings-review skill. LOCAL / MANUAL use only.

Subcommands:
  read-rows   Print JSON of every holding (a row with a ticker) in the 保有銘柄
              tab, with the owner's inputs (想定保有期間, 目標売却株価, 購入理由), the
              Track A figures (現在株価, 配当利回り, 配当金), and the current
              AIコメント, so the skill can decide what to (re)write.
  write       Read {"writes": [{"row","fields":{role:value,...}}, ...]} from stdin
              and batch-write (USER_ENTERED). Only the Track B roles below are
              writable; any other role is refused.

Track B roles this skill may write:
  ai_comment (AIコメント) · target_* (機関別目標株価 8列) ·
  ai_nampin_price (AIのおすすめナンピン株価) · ai_nampin_shares (AIのおすすめナンピン株数)

This output is consumed by Claude locally during a manual run. It is never
committed and must not be piped into the repo or into Actions logs.

Columns are resolved by header name (see sheet.py), so a column move in the sheet
does not misdirect a read or write.

Credentials: set GOOGLE_APPLICATION_CREDENTIALS (path to the local SA key) or
GCP_SA_KEY (JSON string), same as Track A.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root holds sheet.py: .claude/skills/holdings-review/ -> parents[3].
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sheet import (  # noqa: E402
    cell,
    holdings_tabs,
    index_to_col,
    open_configured,
    resolve_columns,
)

# Per-institution analyst target-price roles (Track B web research, 8 columns).
TARGET_ROLES = (
    "target_nomura",
    "target_daiwa",
    "target_smbc_nikko",
    "target_mizuho",
    "target_mumss",
    "target_gs",
    "target_ms",
    "target_jpm",
)
# Roles surfaced to the skill for each holding (read-only context for the comment).
READ_ROLES = (
    "name",
    "horizon",
    "target_sell",
    "current_price",
    "acquire_price",
    "shares",
    "dividend_yield",
    "dividend_amount",
    "purchase_reason",
    "ai_comment",
    "nampin_price",
    "nampin_shares",
    "ai_nampin_price",
    "ai_nampin_shares",
) + TARGET_ROLES
# The only roles this skill may write.
WRITE_ROLES = ("ai_comment", "ai_nampin_price", "ai_nampin_shares") + TARGET_ROLES


def _holdings_tab(cfg: dict) -> dict:
    tabs = holdings_tabs(cfg)
    if not tabs:
        sys.exit("config.yaml has no tab of type 'holdings' for holdings-review")
    return tabs[0]


def read_rows(cfg: dict, ss) -> None:
    tab = _holdings_tab(cfg)
    ws = ss.worksheet(tab["tab"])
    header = ws.row_values(int(cfg["header_rows"]))
    cols = resolve_columns(header, tab["columns"], required={"ticker"})
    values = ws.get_all_values()
    out = []
    for r in range(int(cfg["header_rows"]), len(values)):
        row = values[r]
        ticker = cell(row, cols["ticker"]).strip()
        if not ticker:
            continue
        out.append(
            {
                "row": r + 1,  # 1-based sheet row
                "ticker": ticker,
                "fields": {
                    role: cell(row, cols[role])
                    for role in READ_ROLES
                    if role in cols
                },
            }
        )
    print(json.dumps(out, ensure_ascii=False, indent=2))


def write(cfg: dict, ss) -> None:
    payload = json.load(sys.stdin)
    writes = payload.get("writes", [])
    tab = _holdings_tab(cfg)
    ws = ss.worksheet(tab["tab"])
    header = ws.row_values(int(cfg["header_rows"]))
    cols = resolve_columns(header, tab["columns"], required={"ticker"})
    updates = []
    for w in writes:
        row_num = int(w["row"])
        if "value" in w or "col" in w or not isinstance(w.get("fields"), dict):
            sys.exit(
                'each write must be {"row", "fields": {role: value}}; '
                'the legacy {"row", "value"} form is not accepted'
            )
        for role, val in w["fields"].items():
            if role not in WRITE_ROLES:
                sys.exit(f"refusing to write a non-Track-B role: {role!r}")
            if role not in cols:
                sys.exit(f"role {role!r} has no column in tab {tab['tab']!r}")
            updates.append(
                {"range": f"{index_to_col(cols[role])}{row_num}", "values": [[val]]}
            )
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"wrote {len(updates)} value(s)")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("read-rows", "write"):
        sys.exit("usage: research_io.py [read-rows|write]")
    cfg, ss = open_configured()
    if sys.argv[1] == "read-rows":
        read_rows(cfg, ss)
    else:
        write(cfg, ss)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
