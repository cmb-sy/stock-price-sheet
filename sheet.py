"""Shared Google Sheets auth/config helpers for Track A (update_prices.py) and
Track B (.claude/skills/stock-research/research_io.py).

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
    required = ["spreadsheet_id", "watchlists", "ticker_column", "fields"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        sys.exit(f"config.yaml is missing required keys: {missing}")
    cfg.setdefault("header_rows", 1)
    cfg.setdefault("updated_column", "")
    cfg.setdefault("timezone", "Asia/Tokyo")
    cfg.setdefault("name_column", "A")
    cfg.setdefault("eps_history_columns", [])
    cfg.setdefault("eps_yoy_columns", {})
    cfg.setdefault("volume_3mo_max_column", "")
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


def col_to_index(letter: str) -> int:
    """Convert a spreadsheet column letter to a 1-based index (A->1, AA->27)."""
    letter = str(letter).strip().upper()
    if not letter:
        sys.exit("Empty column letter in config.yaml")
    idx = 0
    for ch in letter:
        if not ("A" <= ch <= "Z"):
            sys.exit(f"Invalid column letter: {letter!r}")
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def open_spreadsheet(cfg: dict, client: gspread.Client) -> gspread.Spreadsheet:
    return client.open_by_key(cfg["spreadsheet_id"])
