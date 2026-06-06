---
name: stock-research
description: For each watched stock in the 監視-* tabs, deep-research the market environment and the stock from many angles over repeated loops, then write the values yfinance cannot give (industry-average PER/PBR, an average target price, a theoretical price) and a Claude-synthesized per-stock verdict into the watchlist's Track B columns. Manual, owner-only run.
argument-hint: "(no args; processes every row that has a ticker in every watchlist tab)"
---

For each watched stock (a candidate the owner does **not** yet hold), web-research
it deeply and write the analysis Track A cannot produce. Track A (yfinance) already
fills price, PER/PBR, dividend yield, market cap, EPS history/YoY, consensus targets,
analyst count, and rating. This skill adds the **web-research** values and an
opinionated verdict. It is a **manually launched, owner-only skill**.

(Repo files are in English; the sheet — tab names, headers, data — stays in
Japanese. Tab names like `監視-JP` / `監視-US` are sheet identifiers, kept as-is.)

## Target tabs and columns

- Processed tabs: every tab of `type: watchlist` in `config.yaml` (currently
  `監視-JP`, `監視-US`). The holdings tab (`保有銘柄`) is handled by the separate
  **holdings-review** skill, not this one.
- Columns are resolved by **header name**, not position (see `sheet.py`), so a
  column move in the sheet does not break this skill.
- Inputs read for each stock (role → header label):
  - `my_target` 購入検討株価 — the price the owner is considering buying at.
  - Track A figures: `current_price` 現在株価, `per` PER, `pbr` PBR,
    `dividend_yield` 配当利回り, `market_cap` 時価総額, `eps_ttm` EPS(TTM),
    `eps_yoy_latest`/`eps_yoy_prev` EPS前年比, `target_mean`/`target_high`/
    `target_low` 合意目標, `num_analysts` アナリスト数, `rating` レーティング.
  - The existing Track B values (to update): `industry_per`, `industry_pbr`,
    `avg_target`, `theoretical`, `analysis_comment`.
- **Only these five roles may be written** (`research_io.py write` refuses any other):
  - `industry_per` 業界PER — industry-average PER (single number).
  - `industry_pbr` 業界PBR — industry-average PBR (single number).
  - `avg_target` 平均目標株価 — an average analyst/own target price (single number).
  - `theoretical` 理論株価 — a theoretical fair price (single number).
  - `analysis_comment` AI分析コメント — Claude's synthesized per-stock verdict.

## What the analysis comment must be

`AI分析コメント` is **Claude's own opinionated verdict**, not a restatement of the
researched numbers. In Japanese, it should:

1. **Open with a stance** on whether this is worth buying at/around the owner's
   購入検討株価 (buy now / wait / pass — your honest call).
2. **Use the figures as evidence**: current price vs. the owner's 購入検討株価 and
   vs. consensus targets, PER/PBR vs. the industry averages you researched, EPS
   trend, dividend, and the market/sector backdrop.
3. **Name the key risks** and **what to watch** (a concrete trigger to revisit).
4. **Record the research date** in the text (there is no separate date column).

## Discipline (strict)

- **Loop, don't one-shot.** Research each stock **repeatedly, from multiple angles**
  — by ticker (code) and by company name, across market/macro, sector, company
  fundamentals, news/catalysts, and valuation — before writing. Cross-check, change
  the angle, reconcile contradictions, and only then synthesize.
- **Latest information only**: reference the most recent primary sources/reporting
  as of the time of research. Do not rely on memory or stale cache.
- **No fabrication**: never invent an industry PER/PBR, a target, a theoretical
  price, or an event. If a number cannot be confirmed, **leave it blank** (do not
  send that role) and say so in the comment rather than guessing. Source URLs are
  not stored in the sheet; summarize the basis/reasoning in the comment instead.
- `industry_per` / `industry_pbr` / `avg_target` / `theoretical` are each a **single
  number**, not a list.
- **Public-repo discipline**: this skill's output is handled only transiently in the
  local Claude session. Never leave tickers/prices/PII in committed files or public
  logs (see the repo-root `CLAUDE.md`). Reporting prints counts only.

## Authentication

Same as Track A. Since this runs locally, set the environment variable (from the
repo root):

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/sa-key.json"
```

`research_io.py` references the repo-root `sheet.py` / `config.yaml`.

## Procedure

### 1. Fetch the watched stocks

```bash
.venv/bin/python .claude/skills/stock-research/research_io.py read-rows
```

A JSON array is returned. Each element: `tab` (which watchlist tab), `row`
(1-based), `ticker` (yfinance format), and `fields` (the role→value inputs above).
A row whose Track B values are already filled is an **update with the latest
information**, not a new entry.

### 2. Deep-research one stock at a time (WebSearch), looping

For each stock, loop through several passes before writing anything: macro/market,
sector/theme, company fundamentals & catalysts, valuation. Re-search from a
different angle, reconcile, repeat until the picture is stable.

### 3. Write

Pass results as JSON via stdin, using the `tab` and `row` from step 1. Send only the
roles you confirmed; omit any you could not confirm (leave them blank).

```bash
echo '{"writes":[
  {"tab":"監視-JP","row":2,"fields":{
     "industry_per":15.2,"industry_pbr":1.1,
     "avg_target":3200,"theoretical":3500,
     "analysis_comment":"<verdict + reasoning + research date>"}}
]}' | .venv/bin/python .claude/skills/stock-research/research_io.py write
```

### 4. Report

Report only the number of stocks commented on (no tickers/prices). If anything
could not be confirmed and was therefore left blank/hedged, state that.

## What not to do

- Writing any role other than the five Track B roles (`research_io.py write` refuses it).
- One-shotting the research, or restating figures instead of forming a judgment.
- Fabricating an industry PER/PBR, target, theoretical price, or event you could
  not confirm — leave it blank instead.
