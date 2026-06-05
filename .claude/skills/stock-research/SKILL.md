---
name: stock-research
description: Deep-research watched/held stocks on the web and write industry-average PER/PBR, per-institution targets, theoretical price, catalysts, and a synthesized analysis comment to the sheet (Track B, manual run)
argument-hint: "[--tab 保有銘柄|監視-JP|監視-US] (default: every stock in every tab)"
---

For each stock in the sheet, web-research the information yfinance cannot provide
and write/update it in the Track B columns. This is a **manually launched skill**.
It never touches the columns Track A (`update_prices.py`) fills automatically.

(Repo files are in English; the sheet — tab names, headers, data — stays in
Japanese. Tab names like `保有銘柄` below are sheet identifiers, kept as-is.)

## Target tabs and columns

- Processed tabs: `保有銘柄`, `監視-JP`, `監視-US` (`watchlists` in `config.yaml`).
  `売買履歴` is excluded.
- The ticker column is the last column (`ticker_column` in `config.yaml`, currently
  `AG`). The stock name is column A (Japanese, manual).
- **Only Track B columns may be written** (`research_io.py write` blocks other columns):
  - `E` industry PER / `F` industry PBR
  - `Y` per-institution targets / `Z` theoretical price / `AA` catalyst/rating news
    / `AB` source URLs / `AC` Track B fetch date / `AD` analysis comment

## Discipline (strict)

- **Latest information only**: reference the most recent primary sources/reporting
  as of the time of research. Do not rely on memory or stale cache. Record the fetch
  date for each value (column AC).
- **No fabrication**: do not fill industry averages, target prices, ratings,
  theoretical prices, or catalysts in by guessing. If you cannot confirm a value,
  leave it blank or mark it "unknown", and always attach a source URL (column AB).
- **Public-repo discipline**: this skill's output is handled only transiently in the
  local Claude session. Do not leave tickers/prices in committed files or public logs
  (see the repo-root `CLAUDE.md`).

## Authentication

Same as Track A. Since this runs locally, set the environment variable (from the
repo root):

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/sa-key.json"
```

`research_io.py` references the repo-root `sheet.py` / `config.yaml`.

## Procedure

### 1. Fetch the target rows

```bash
.venv/bin/python .claude/skills/stock-research/research_io.py read-rows
```

A JSON array is returned. Each element: `tab`, `row` (1-based), `ticker` (yfinance
format), `name` (Japanese), `current` (current values of each Track B column). A row
whose `current` is already filled should be treated as an **update with the latest
information, not a new entry**.

### 2. Deep-research one stock at a time (WebSearch)

For each stock, research **repeatedly from multiple angles**. Do not stop at one
search; change the angle and cross-check:

- **E industry PER / F industry PBR**: the average PER/PBR of the industry (sector)
  the stock belongs to. State the source (the outlet publishing the industry average,
  and the date). Not obtainable from yfinance, so always confirm on the web.
- **Y per-institution targets**: target prices per brokerage/research firm (e.g.
  "<company> target price <brokerage>"). Pair the institution name with the figure;
  list multiple if available.
- **Z theoretical price**: a theoretical/fair price from a reliable source. State the
  source. Leave blank if unconfirmed.
- **AA catalyst/rating news**: recent earnings, guidance revisions, rating changes,
  orders/new products, and other share-price catalysts. Concise, with dates.
- **AB source URLs**: the basis URLs for E/F/Y/Z/AA and AD. Multiple allowed.
- **AC Track B fetch date**: the research date (`date +%F`).
- **AD analysis comment**: a synthesis combining the above with the Track A
  fundamentals (columns B–W: price/PER/PBR/dividend/market cap/volume/52-week
  range/EPS history & YoY/analyst consensus, etc.). Summarize the valuation level
  (including vs. the industry average), upside/downside targets, key catalysts, and
  risks. Overwrite any existing comment with the latest information.

Researching by both ticker (stock code) and company name improves accuracy.

### 3. Write

Pass the research results as JSON via stdin. Use the `row`/`tab` from step 1:

```bash
echo '{"writes":[
  {"tab":"保有銘柄","row":2,"col":"E","value":"12.3 (industry avg, source: ... 2026-06)"},
  {"tab":"保有銘柄","row":2,"col":"F","value":"1.1 (industry avg, source: ...)"},
  {"tab":"保有銘柄","row":2,"col":"Y","value":"Broker A 7000 / Broker B 6800 (as of 2026-06)"},
  {"tab":"保有銘柄","row":2,"col":"Z","value":"theoretical price 6500 (source: ...)"},
  {"tab":"保有銘柄","row":2,"col":"AA","value":"2026Q1 op. income +12%, upward revision (2026-05-xx)"},
  {"tab":"保有銘柄","row":2,"col":"AB","value":"https://... ; https://..."},
  {"tab":"保有銘柄","row":2,"col":"AC","value":"2026-06-05"},
  {"tab":"保有銘柄","row":2,"col":"AD","value":"<synthesized analysis comment>"}
]}' | .venv/bin/python .claude/skills/stock-research/research_io.py write
```

(Replace `value` with the actual research results. The figures and names above are
format examples, not real data.)

### 4. Report

Report only the number of rows processed (no tickers/prices). If any field was left
blank because it could not be confirmed, state that explicitly.

## What not to do

- Writing to Track A's automatic columns (B–D, G–X among the config target columns),
  A (stock name), AE (my target price), AF (memo), AG (Ticker), or the `売買履歴` tab.
- Writing any number without a source.
