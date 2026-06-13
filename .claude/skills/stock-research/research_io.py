#!/usr/bin/env python3
# Copyright (c) 2026 cmb-sy. All Rights Reserved. Proprietary; see LICENSE.
"""I/O helper for the stock-research skill (Track B for watchlist tabs). LOCAL /
MANUAL use only.

Subcommands:
  read-rows   Print JSON of every watched stock (a row with a ticker) across all
              watchlist tabs, with the owner's 購入検討株価 and 購入検討理由, the
              Track A figures (price, PER/PBR, dividend yield, market cap in 億円,
              EPS, EPS YoY, rating, next earnings date), and the existing Track B
              values, so
              the skill can decide what to (re)write.
  write       Read {"writes": [{"tab","row","fields":{role:value,...}}, ...]} from
              stdin and batch-write per tab. Only the Track B roles below are
              writable; any other role is refused.

Track B roles this skill may write:
  theme (業界やテーマ) · industry_per (業界PER) · industry_pbr (業界PBR) ·
  analyst_target (アナリスト予想株価) · theoretical (理論株価) ·
  analysis_comment (AI分析コメント) · target_* (機関別目標株価 8列) ·
  ai_dip_target (AI予想押し目) ·
  ai_recheck (AI再評価) — manual trigger flag the skill clears (writes "") on
  successful processing of a row; never set to a non-empty value by the skill

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

# Repo root holds sheet.py: .claude/skills/stock-research/ -> parents[3].
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sheet import (  # noqa: E402
    cell,
    index_to_col,
    iter_watchlist_sheets,
    open_configured,
    resolve_columns,
    watchlist_tabs,
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
# Roles surfaced to the skill for each watched stock (read-only synthesis context).
READ_ROLES = (
    "name",
    "theme",
    "my_target",
    "consider_reason",
    "current_price",
    "per",
    "pbr",
    "industry_per",
    "industry_pbr",
    "dividend_yield",
    "market_cap",
    "eps_ttm",
    "eps_yoy_latest",
    "rating",
    "analyst_target",
    "theoretical",
    "next_earnings",
    "analysis_comment",
    "ai_dip_target",
    "ai_recheck",
) + TARGET_ROLES
# The only roles this skill may write. ai_recheck is a manual trigger flag the
# skill MUST clear (write "") on each row it processes; the skill never writes a
# non-empty ai_recheck value.
WRITE_ROLES = (
    "theme",
    "industry_per",
    "industry_pbr",
    "analyst_target",
    "theoretical",
    "analysis_comment",
    "ai_dip_target",
    "ai_recheck",
) + TARGET_ROLES


def read_rows(cfg: dict, ss) -> None:
    out = []
    for tab, cols, values in iter_watchlist_sheets(cfg, ss, required={"ticker"}):
        for r in range(int(cfg["header_rows"]), len(values)):
            row = values[r]
            ticker = cell(row, cols["ticker"]).strip()
            if not ticker:
                continue
            out.append(
                {
                    "tab": tab["tab"],
                    "row": r + 1,  # 1-based sheet row
                    "ticker": ticker,
                    "fields": {
                        role: cell(row, cols[role]) for role in READ_ROLES if role in cols
                    },
                }
            )
    print(json.dumps(out, ensure_ascii=False, indent=2))


def write(cfg: dict, ss) -> None:
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
        updates = []
        for w in tab_writes:
            row_num = int(w["row"])
            for role, val in (w.get("fields") or {}).items():
                if role not in WRITE_ROLES:
                    sys.exit(f"refusing to write a non-Track-B role: {role!r}")
                if role not in cols:
                    sys.exit(f"role {role!r} has no column in tab {tab_name!r}")
                updates.append(
                    {"range": f"{index_to_col(cols[role])}{row_num}", "values": [[val]]}
                )
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
            total += len(updates)
    print(f"wrote {total} value(s)")


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
