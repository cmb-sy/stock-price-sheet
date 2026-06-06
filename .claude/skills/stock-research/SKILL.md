---
name: stock-research
description: For each watched stock in the 監視-* tabs, deep-research the market environment and the stock from many angles over repeated loops, then write the values yfinance cannot give (the industry/theme, industry-average PER/PBR, an analyst-consensus target price, a theoretical price) and a Claude-synthesized per-stock verdict into the watchlist's Track B columns. Manual, owner-only run.
argument-hint: "(no args; processes every row that has a ticker in every watchlist tab)"
---

For each watched stock (a candidate the owner does **not** yet hold), web-research
it deeply and write the analysis Track A cannot produce. Track A (yfinance) already
fills price, PER/PBR, market cap, 3-month max volume, 52-week high/low, EPS (TTM),
EPS YoY, rating, and the next earnings date. This skill adds the **web-research**
values and an opinionated verdict. It is a **manually launched, owner-only skill**.

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
  - `consider_reason` 購入検討理由 — the owner's reason for considering it (the
    thesis to test, as in holdings-review's 購入理由).
  - Track A figures: `current_price` 現在株価, `per` PER, `pbr` PBR,
    `dividend_yield` 配当利回り, `market_cap` 時価総額（億円・円換算済み）, `eps_ttm` 現在EPS,
    `eps_yoy_latest` 年間EPS前年比（%）, `rating` レーティング,
    `next_earnings` 次回決算日.
  - The existing Track B values (to update): `theme`, `industry_per`,
    `industry_pbr`, `analyst_target`, `theoretical`, `analysis_comment`.
- **Only these six roles may be written** (`research_io.py write` refuses any other):
  - `theme` 業界やテーマ — the industry/theme the stock belongs to (short label).
  - `industry_per` 業界PER — industry-average PER (single number).
  - `industry_pbr` 業界PBR — industry-average PBR (single number).
  - `analyst_target` アナリスト予想株価 — analyst-consensus target price (single number).
  - `theoretical` 理論株価 — a theoretical fair price (single number).
  - `analysis_comment` AI分析コメント — Claude's synthesized per-stock verdict.

## What the analysis comment must be

`AI分析コメント` is **Claude's own opinionated verdict**, not a restatement of the
researched numbers. Write it in Japanese as a **substantial, structured analysis**
(目安 **500〜900 字**) — long enough to actually justify the call, not a one-liner.
Use **short paragraphs with clear breaks** (the web app renders line breaks), ideally
in this order, each as its own paragraph:

1. **結論（スタンス）**: open with whether this is worth buying at/around the owner's
   購入検討株価 — **買い / 押し目待ち / 様子見 / 見送り** — in one or two sentences.
2. **根拠（バリュエーション＆ファンダ）**: the body of the analysis. Test the owner's
   購入検討理由 — does it still hold given the latest facts? — and judge whether the
   購入検討株価 is a *reasonable entry price* (too high / about right / room to wait),
   using current price, your researched fair value (理論株価) and analyst target
   (アナリスト予想株価), PER/PBR vs. the industry averages, PEG, EPS trend & YoY,
   dividend, 52-week range position, and the market/sector backdrop as evidence.
   Spell out the reasoning, don't just list figures.
3. **リスク・注目点**: name the key risks and **what to watch** — a concrete trigger
   to revisit (e.g. the 次回決算日, a guidance or rate event).
4. **まとめ**: close by restating the stance and the price level/condition that would
   change it.

Finally, **record the research date** in the text (there is no separate date column).
Depth over brevity, but **never pad with fabrication** — if a fact is unconfirmed, say
so plainly rather than inventing detail to hit a length.

## Discipline (strict)

- **Loop, don't one-shot.** Research each stock **repeatedly, from multiple angles**
  — by ticker (code) and by company name, across market/macro, sector, company
  fundamentals, news/catalysts, and valuation — before writing. Cross-check, change
  the angle, reconcile contradictions, and only then synthesize.
- **Latest information only**: reference the most recent primary sources/reporting
  as of the time of research. Do not rely on memory or stale cache.
- **No fabrication**: never invent an industry PER/PBR, a target, a theoretical
  price, or an event. If a number cannot be confirmed, **do not guess a figure** —
  instead write a **minimal reason word** in that cell (one or two words only, e.g.
  "赤字" / "確認不可"; **never a sentence, no date** — the research date goes in the
  comment), and elaborate/hedge in the comment. Never leave the cell empty; a reason
  word is the fallback, a fabricated number never is. Source URLs are not stored in
  the sheet; summarize the basis/reasoning in the comment instead.
- `industry_per` / `industry_pbr` / `analyst_target` / `theoretical` are each a
  **single number** when confirmable, or a **minimal reason word** when not (never a
  fabricated number). `theme` is a short text label.
- **Secret-handling discipline**: this skill's output is handled only transiently in
  the local Claude session. The repo is private, but never regress that boundary —
  never leave tickers/prices/PII in committed files or run logs (see the repo-root
  `CLAUDE.md`). Reporting prints counts only.

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

Pass results as JSON via stdin, using the `tab` and `row` from step 1. For a role you
could not confirm, send a minimal reason word instead of a number (never omit it,
never fabricate a figure).

```bash
echo '{"writes":[
  {"tab":"監視-JP","row":2,"fields":{
     "theme":"<industry/theme>","industry_per":15.2,"industry_pbr":1.1,
     "analyst_target":3200,"theoretical":3500,
     "analysis_comment":"<verdict + reasoning + research date>"}}
]}' | .venv/bin/python .claude/skills/stock-research/research_io.py write
```

### 4. Report

Report only the number of stocks commented on (no tickers/prices). If anything
could not be confirmed and was therefore filled with a reason text instead of a
number, state that.

## What not to do

- Writing any role other than the six Track B roles (`research_io.py write` refuses it).
- One-shotting the research, or restating figures instead of forming a judgment.
- Fabricating a theme, industry PER/PBR, target, theoretical price, or event you
  could not confirm — write a minimal reason word in that cell instead.
