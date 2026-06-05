#!/usr/bin/env python3
"""Fetch latest stock prices with yfinance and write them into a Google Sheet.

Reads ticker symbols (yfinance format, e.g. 7203.T / AAPL) from a configured
column, fetches the latest price for each, and writes the price plus an update
timestamp back to configured columns. Designed to run on a GitHub Actions
schedule, but also runnable locally for testing.

Auth: provide the service-account credentials via either
  - GCP_SA_KEY                  : the JSON key contents as a string (CI), or
  - GOOGLE_APPLICATION_CREDENTIALS : path to the JSON key file (local).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
import yaml
import yfinance as yf
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
    required = ["spreadsheet_id", "worksheet", "ticker_column", "price_column"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        sys.exit(f"config.yaml is missing required keys: {missing}")
    cfg.setdefault("header_rows", 1)
    cfg.setdefault("updated_column", "")
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


def fetch_price(symbol: str) -> float | None:
    """Return the latest price for a yfinance symbol, or None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        try:
            price = ticker.fast_info["last_price"]
            if price:
                return round(float(price), 4)
        except Exception:
            pass
        hist = ticker.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:  # noqa: BLE001 - treat as N/A; caller logs by row, not symbol
        pass
    return None


def main() -> int:
    cfg = load_config()
    client = get_client()
    worksheet = client.open_by_key(cfg["spreadsheet_id"]).worksheet(cfg["worksheet"])

    header_rows = int(cfg["header_rows"])
    tickers = worksheet.col_values(col_to_index(cfg["ticker_column"]))
    now = datetime.now(ZoneInfo(cfg["timezone"])).strftime("%Y-%m-%d %H:%M")

    updates: list[dict] = []
    n_ok = n_na = 0
    for offset, raw_symbol in enumerate(tickers[header_rows:]):
        symbol = raw_symbol.strip()
        if not symbol:
            continue
        row = header_rows + offset + 1  # 1-based sheet row
        price = fetch_price(symbol)
        if price is None:
            n_na += 1
            cell_value: object = "N/A"
            # Public repo: never log the symbol/price (Actions logs are world-readable).
            print(f"  fetch failed at row {row}", file=sys.stderr)
        else:
            n_ok += 1
            cell_value = price
        updates.append({"range": f"{cfg['price_column']}{row}", "values": [[cell_value]]})
        if cfg["updated_column"]:
            updates.append({"range": f"{cfg['updated_column']}{row}", "values": [[now]]})

    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"Done: {n_ok} updated, {n_na} N/A at {now} ({cfg['timezone']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
