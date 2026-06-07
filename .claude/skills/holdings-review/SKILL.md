---
name: holdings-review
description: For each holding in the 保有銘柄 tab, deep-research the market environment and the stock from many angles over repeated loops, weigh it against the owner's own purchase reason / horizon / target sell price, and write a personalized advisory comment addressed to the owner into the AIコメント column. Manual, owner-only run.
argument-hint: "(no args; processes every row in 保有銘柄 that has a ticker)"
---

For each holding, write the owner a candid, personalized comment: given **why they
bought it (購入理由)**, **their horizon (想定保有期間)**, and **their target sell price
(目標売却株価)**, is the original thesis still intact, and what should they watch or
do now? This is a **manually launched, owner-only skill**. It writes **only** the
`AIコメント` column; it never touches the manual columns or Track A's columns.

(Repo files are in English; the sheet — tab names, headers, data — stays in
Japanese. The tab name `保有銘柄` below is a sheet identifier, kept as-is.)

## Target tab and columns

- Processed tab: `保有銘柄` (the tab of `type: holdings` in `config.yaml`'s `tabs`).
- Columns are resolved by **header name**, not position (see `sheet.py`), so a
  column move in the sheet does not break this skill.
- Inputs read for each holding (role → header label):
  - `purchase_reason` 購入理由 — the owner's reason for buying (the thesis to test).
  - `horizon` 想定保有期間 — the intended holding horizon (short / mid / long).
  - `target_sell` 目標売却株価 — the price at which the owner intends to sell.
  - Track A figures: `current_price` 現在株価, `dividend_yield` 配当利回り,
    `dividend_amount` 配当金.
  - `ai_comment` AIコメント — the existing comment (if any) to update.
- **Only `AIコメント` may be written** (`research_io.py write` refuses any other
  column). 売買履歴 is **not** consulted by this skill.

## What the comment must be

A candid, **substantial, structured** letter to the owner, in Japanese (目安
**500〜900 字**) — long enough to genuinely advise, not a one-liner. Use **short
paragraphs with clear breaks** (the web app renders line breaks), ideally in this
order, each as its own paragraph:

1. **結論（スタンス）**: open with a verdict tied to *their* thesis — does the 購入理由
   still hold given the latest facts? **継続保有 / 買い増し / 一部利確 / 見直し** — your
   honest call, in one or two sentences.
2. **根拠（現状評価）**: the body. Weave in the current price vs. their 目標売却株価
   (remaining upside/downside to their own target), the dividend yield/amount, valuation
   (research PER/PBR yourself — they are not on the holdings tab), recent catalysts
   (earnings, guidance, sector/macro shifts), and the market environment — calibrated to
   their **horizon** (a short-term and a long-term holder get different advice from the
   same facts). Spell out the reasoning, don't just list figures.
3. **リスク・注目点**: name the key risks and **what to watch** next — a concrete
   trigger to revisit (e.g. the next earnings, a guidance/rate event).
4. **まとめ**: close with a clear stance and the level/condition that would change it.

Finally, **record the research date** in the text (there is no separate date column).
Depth over brevity, but **never pad with fabrication** — if a fact is unconfirmed, say
so plainly rather than inventing detail to hit a length.

## Discipline (strict)

- **Loop, don't one-shot.** Research each stock **repeatedly, from multiple angles**,
  over several passes — by ticker (code) and by company name, across market/macro,
  sector, company fundamentals, news/catalysts, and valuation. Cross-check, change the
  angle, and only then synthesize. Take the time to be right rather than fast.
- **Latest information only**: reference the most recent primary sources/reporting as
  of the time of research. Do not rely on memory or stale cache.
- **No fabrication**: never invent prices, figures, or events. If something cannot be
  confirmed, say so in the comment rather than guessing. Source URLs are not stored in
  the sheet; summarize the basis/reasoning in the comment instead.
- **Personalized, not generic**: the comment must engage with the owner's specific
  購入理由 / 想定保有期間 / 目標売却株価, not read like a stock-screener blurb.
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

### 1. Fetch the holdings

```bash
.venv/bin/python .claude/skills/holdings-review/research_io.py read-rows
```

A JSON array is returned. Each element: `row` (1-based), `ticker` (yfinance format),
and `fields` (the role→value inputs above). A row whose `ai_comment` is already filled
should be treated as an **update with the latest information, not a new entry**.

### 2. Deep-research one holding at a time (WebSearch), looping

For each holding, loop through several research passes before writing anything:

- **Macro / market**: the overall market regime, rates, FX, risk sentiment relevant
  to this stock's market (JP/US).
- **Sector / theme**: the industry trend and where this company sits within it.
- **Company fundamentals & catalysts**: latest earnings, guidance, dividend changes,
  ratings, notable news.
- **Valuation**: current price vs. the owner's 目標売却株価 and vs. peers.

Re-search from a different angle, reconcile contradictions, and repeat until the
picture is stable. Then judge it **through the lens of the owner's thesis and horizon**.

### 3. Write

Pass results as JSON via stdin, using the `row` from step 1. Only `value` (the comment
text) is needed; the column is always `AIコメント`.

```bash
echo '{"writes":[
  {"row":2,"value":"<personalized comment to the owner, incl. research date>"},
  {"row":3,"value":"<...>"}
]}' | .venv/bin/python .claude/skills/holdings-review/research_io.py write
```

### 4. Report

Report only the number of holdings commented on (no tickers/prices). If anything
could not be confirmed and was therefore hedged in the comment, state that.

## What not to do

- Writing to any column other than `AIコメント` (`research_io.py write` refuses it).
- One-shotting the research, or restating figures instead of forming a judgment.
- Ignoring the owner's 購入理由 / 想定保有期間 / 目標売却株価 — the comment must be about
  *their* position, not a generic take.
- Fabricating a value or event you could not confirm.
