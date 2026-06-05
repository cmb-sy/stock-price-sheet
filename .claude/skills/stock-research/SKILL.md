---
name: stock-research
description: Deep-research watched/held stocks on the web and write industry-average PER/PBR, an average analyst target price, a theoretical price, and a Claude-synthesized analysis comment to the sheet (Track B, manual run)
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
  `AG`). The stock name is column A (Japanese, manual). Column C is the manual "my
  target price", placed next to B (current price) — never written by either track.
- **Only Track B columns may be written** (`research_io.py write` blocks other columns):
  - `F` industry PER / `G` industry PBR
  - `Z` average target price (single value) / `AA` theoretical price (single value)
    / `AD` Track B fetch date / `AE` analysis comment (Claude-synthesized prose)
- `AB` and `AC` are unused (no catalyst-news or source-URL column); `write` refuses them.

## Discipline (strict)

- **Latest information only**: reference the most recent primary sources/reporting
  as of the time of research. Do not rely on memory or stale cache. Record the fetch
  date for each value (column AD).
- **No fabrication**: do not fill industry averages, target prices, or theoretical
  prices in by guessing. If you cannot confirm a value, leave it blank or mark it
  "unknown". (Source URLs are not recorded in the sheet; summarize the basis in the
  AE analysis comment instead.)
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

- **F industry PER / G industry PBR**: the average PER/PBR of the industry (sector)
  the stock belongs to. Use a consistent basis (e.g. the JPX sector weighted average)
  and write a **single number**. Not obtainable from yfinance, so always confirm on
  the web. Leave blank if unconfirmed.
- **Z average target price**: collect target prices per brokerage/research firm, then
  write the **single simple mean** of the figures you found (one number, not a list).
  Leave blank if none found.
- **AA theoretical price**: a **single** theoretical/fair price. If a source gives
  multiple bases (PER/PBR), write their average. Leave blank if unconfirmed.
- **AD Track B fetch date**: the research date (`date +%F`).
- **AE analysis comment**: **Claude's own analytical assessment** — an opinionated
  judgment, not a restatement of the figures — synthesized from the research findings
  combined with the Track A fundamentals (B current price and D–X: PER/PBR/dividend/
  market cap/volume/52-week range/EPS history & YoY/analyst consensus, etc.). Lead with
  a one-line verdict, then reason through the valuation level (including vs. the industry
  average), the average target (Z) vs. the current price (upside/downside) and the
  theoretical price (AA), recent catalysts (earnings, guidance revisions, rating changes
  — woven into the text, since there is no separate news column), and key risks, then
  close with a clear stance. Use the figures as evidence for the view; do not merely
  list them. Overwrite any existing comment with the latest information.

Researching by both ticker (stock code) and company name improves accuracy.

### 3. Write

Pass the research results as JSON via stdin. Use the `row`/`tab` from step 1:

```bash
echo '{"writes":[
  {"tab":"保有銘柄","row":2,"col":"F","value":"12.3"},
  {"tab":"保有銘柄","row":2,"col":"G","value":"1.1"},
  {"tab":"保有銘柄","row":2,"col":"Z","value":"6900"},
  {"tab":"保有銘柄","row":2,"col":"AA","value":"6500"},
  {"tab":"保有銘柄","row":2,"col":"AD","value":"2026-06-05"},
  {"tab":"保有銘柄","row":2,"col":"AE","value":"<Claude-synthesized analysis comment>"}
]}' | .venv/bin/python .claude/skills/stock-research/research_io.py write
```

(Replace `value` with the actual research results. The figures above are format
examples, not real data. F/G/Z/AA are plain numbers — the sheet's display formats add
the thousands separators / decimals.)

### 4. Report

Report only the number of rows processed (no tickers/prices). If any field was left
blank because it could not be confirmed, state that explicitly.

## What not to do

- Writing to Track A's automatic columns (B, D–E, H–Y among the config target columns),
  A (stock name), C (my target price), AF (memo), AG (Ticker), or the `売買履歴` tab.
- Writing to the now-unused `AB`/`AC` columns (`research_io.py write` refuses them).
- Writing a per-institution list to `Z`, or multiple basis prices to `AA` (one number each).
- Fabricating a value you could not confirm (leave it blank instead).
