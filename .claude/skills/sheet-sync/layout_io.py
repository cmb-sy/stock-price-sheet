#!/usr/bin/env python3
# Copyright (c) 2026 cmb-sy. All Rights Reserved. Proprietary; see LICENSE.
"""Layout I/O helper for the sheet-sync skill. LOCAL / MANUAL use only.

Subcommand:
  read-layout   Print JSON describing every worksheet's name, dimensions, and
                header row, plus the column mapping config.yaml currently expects,
                so the skill can detect drift between the live sheet and the repo
                config/code.

Only structural metadata is emitted: tab names, row/column counts, and header-row
labels. Header labels are generic Japanese column names (銘柄名, 現在株価, ...) and
contain no tickers, prices, or PII, so this output is safe to view. It still must
not be piped into committed files or Actions logs.

Credentials: set GOOGLE_APPLICATION_CREDENTIALS (path to the local SA key) or
GCP_SA_KEY (JSON string), same as Track A.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root holds sheet.py: .claude/skills/sheet-sync/ -> parents[3].
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sheet import open_configured  # noqa: E402


def read_layout(cfg: dict, ss) -> None:
    header_rows = int(cfg.get("header_rows", 1))
    tabs = []
    for ws in ss.worksheets():
        header = ws.row_values(header_rows) if header_rows else []
        tabs.append(
            {
                "title": ws.title,
                "rows": ws.row_count,
                "cols": ws.col_count,
                "header": header,
            }
        )
    config_view = {
        "header_rows": cfg.get("header_rows"),
        "tabs": cfg.get("tabs"),
    }
    print(
        json.dumps({"sheet": tabs, "config": config_view}, ensure_ascii=False, indent=2)
    )


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] != "read-layout":
        sys.exit("usage: layout_io.py read-layout")
    cfg, ss = open_configured()
    read_layout(cfg, ss)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
