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
    required = ["spreadsheet_id", "holdings_tab", "columns"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        sys.exit(f"config.yaml is missing required keys: {missing}")
    cols = cfg["columns"]
    if not isinstance(cols, dict) or "ticker" not in cols:
        sys.exit("config.yaml `columns` must be a map that includes a `ticker` label")
    cfg.setdefault("header_rows", 1)
    cfg.setdefault("timezone", "Asia/Tokyo")
    return cfg


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
