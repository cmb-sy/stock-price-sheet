"""Shared Google Sheets auth/config helpers for Track A (update_prices.py) and
the holdings-review skill (.claude/skills/holdings-review/research_io.py).

Columns are resolved by HEADER NAME (the row-1 label), never by fixed position,
so adding/moving a column in the sheet does not silently break the mapping.

Auth: provide service-account credentials via either
  - GCP_SA_KEY                    : the JSON key contents as a string (CI), or
  - GOOGLE_APPLICATION_CREDENTIALS : path to the JSON key file (local).
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import gspread
import yaml
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CONFIG_PATH = Path(__file__).with_name("config.yaml")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"config.yaml not found at {CONFIG_PATH}. "
            "Copy config.example.yaml to config.yaml and fill it in."
        )
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    required = ["spreadsheet_id", "tabs"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        sys.exit(f"config.yaml is missing required keys: {missing}")
    tabs = cfg["tabs"]
    if not isinstance(tabs, list) or not tabs:
        sys.exit("config.yaml `tabs` must be a non-empty list of tab definitions")
    for t in tabs:
        if not isinstance(t, dict) or not t.get("tab") or not t.get("type"):
            sys.exit("each entry in `tabs` needs a `tab` name and a `type`")
        if t["type"] not in ("holdings", "watchlist"):
            sys.exit(f"unknown tab type {t['type']!r} (use 'holdings' or 'watchlist')")
        cols = t.get("columns")
        if not isinstance(cols, dict) or "ticker" not in cols:
            sys.exit(f"tab {t['tab']!r} `columns` must be a map that includes a `ticker` label")
    cfg.setdefault("header_rows", 1)
    cfg.setdefault("timezone", "Asia/Tokyo")
    return cfg


def holdings_tabs(cfg: dict) -> list[dict]:
    """Tab definitions of type 'holdings' (the holdings-review skill's targets)."""
    return [t for t in cfg["tabs"] if t.get("type") == "holdings"]


def watchlist_tabs(cfg: dict) -> list[dict]:
    """Tab definitions of type 'watchlist' (the stock-research skill's targets)."""
    return [t for t in cfg["tabs"] if t.get("type") == "watchlist"]


def get_client() -> gspread.Client:
    raw = os.environ.get("GCP_SA_KEY")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not path:
            sys.exit(
                "No credentials. Set GCP_SA_KEY (JSON string) or "
                "GOOGLE_APPLICATION_CREDENTIALS (path to JSON key)."
            )
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)


def open_spreadsheet(cfg: dict, client: gspread.Client) -> gspread.Spreadsheet:
    return client.open_by_key(cfg["spreadsheet_id"])


def open_configured() -> tuple[dict, gspread.Spreadsheet]:
    """Load config and open the spreadsheet in one step, returning (cfg, ss)."""
    cfg = load_config()
    return cfg, open_spreadsheet(cfg, get_client())


def cell(row: list[str], col_idx: int) -> str:
    """Value at a 1-based column index, or '' if the index is out of range."""
    i = col_idx - 1
    return row[i] if 0 <= i < len(row) else ""


def index_to_col(index: int) -> str:
    """Convert a 1-based column index to a spreadsheet letter (1->A, 27->AA)."""
    if index < 1:
        sys.exit(f"Invalid column index: {index!r}")
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def resolve_columns(
    header: list[str], label_map: dict[str, str], *, required: set[str] | None = None
) -> dict[str, int]:
    """Map each logical role to a 1-based column index by matching header labels.

    `header` is the row-1 label list (index 0 = column A). `label_map` is
    {role: exact header label}. Roles whose label is absent from the header are
    omitted from the result, unless listed in `required`, in which case a missing
    label is a fatal error (this is what catches layout drift early).
    """
    pos: dict[str, int] = {}
    for i, label in enumerate(header, start=1):
        key = str(label).strip()
        if key and key not in pos:  # first occurrence wins on duplicate labels
            pos[key] = i
    resolved: dict[str, int] = {}
    missing: list[str] = []
    for role, label in label_map.items():
        idx = pos.get(str(label).strip())
        if idx is not None:
            resolved[role] = idx
        elif required and role in required:
            missing.append(f"{role}={label!r}")
    if missing:
        sys.exit(
            "header labels not found in the sheet (layout drift?): "
            + ", ".join(missing)
        )
    return resolved


def iter_watchlist_sheets(
    cfg: dict, ss, required: set[str] | None = None
) -> Iterator[tuple[dict, dict[str, int], list[list[str]]]]:
    """Yield (tab_def, resolved_cols, all_values) for each watchlist tab.

    A tab whose worksheet is missing is skipped with a stderr note (row/tab only,
    never cell values). `required` is forwarded to resolve_columns.
    """
    for tab in watchlist_tabs(cfg):
        try:
            ws = ss.worksheet(tab["tab"])
        except Exception:
            print(f"  worksheet not found, skipped: {tab['tab']}", file=sys.stderr)
            continue
        header = ws.row_values(int(cfg["header_rows"]))
        cols = resolve_columns(header, tab["columns"], required=required)
        values = ws.get_all_values()
        yield tab, cols, values
