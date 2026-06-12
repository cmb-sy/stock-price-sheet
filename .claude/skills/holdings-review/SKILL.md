---
name: holdings-review
description: For each holding in the 保有銘柄 tab, deep-research the market environment and the stock from many angles over repeated loops, weigh it against the owner's own purchase reason / target sell price, and write a personalized advisory comment addressed to the owner into the AIコメント column, per-institution analyst target prices into the 目標株価（…） columns, and an AI-recommended averaging-down price into the AIのおすすめナンピン株価 column. Manual, owner-only run.
argument-hint: "(no args; processes every row in 保有銘柄 that has a ticker)"
---

For each holding, write the owner a candid, personalized comment: given **why they
bought it (購入理由)** and **their target sell price (目標売却株価)**, is the
original thesis still intact, and what should they watch or do now? This is a
**manually launched, owner-only skill**. It writes **only** the `AIコメント`
column, the eight per-institution `目標株価（…）` columns, and the AI
averaging-down column (`AIのおすすめナンピン株価`); it never touches the manual
columns or Track A's columns.

(Repo files are in English; the sheet — tab names, headers, data — stays in
Japanese. The tab name `保有銘柄` below is a sheet identifier, kept as-is.)

## Target tab and columns

- Processed tab: `保有銘柄` (the tab of `type: holdings` in `config.yaml`'s `tabs`).
- Columns are resolved by **header name**, not position (see `sheet.py`), so a
  column move in the sheet does not break this skill.
- Inputs read for each holding (role → header label):
  - `purchase_reason` 購入理由 — the owner's reason for buying (the thesis to test).
  - `target_sell` 目標売却株価 — the price at which the owner intends to sell.
  - `acquire_price` 取得株価 / `shares` 取得株数 — the owner's cost basis (read
    only; the basis for the averaging-down math below).
  - `nampin_price` ナンピン検討株価 / `nampin_shares` ナンピン検討株数 — the
    averaging-down price/share count the owner is considering (optional; manual).
    If filled, evaluate their plan in the comment.
  - Track A figures: `current_price` 現在株価, `dividend_yield` 配当利回り,
    `dividend_amount` 配当金.
  - `ai_comment` AIコメント — the existing comment (if any) to update.
  - The existing AI averaging-down value (to update): `ai_nampin_price`
    AIのおすすめナンピン株価.
  - The existing per-institution targets (to update): `target_nomura` 目標株価（野村） ·
    `target_daiwa` 目標株価（大和） · `target_smbc_nikko` 目標株価（SMBC日興） ·
    `target_mizuho` 目標株価（みずほ） · `target_mumss` 目標株価（三菱UFJMS） ·
    `target_gs` 目標株価（GS） · `target_ms` 目標株価（モルガンS） ·
    `target_jpm` 目標株価（JPM）.
- **Only `ai_comment`, the eight `target_*` roles and `ai_nampin_price` may be
  written** (`research_io.py write` refuses any other role). 売買履歴 is **not**
  consulted by this skill.

## Per-institution target prices (機関別目標株価)

Per-institution targets are **not available from any API**; they come only from
public rating coverage. Generic web searches mostly surface consensus numbers and
miss the per-institution tables, so follow this procedure — do not stop at `なし`
until the primary source below has actually been checked.

**JP stocks — primary source (check FIRST, usually sufficient):**

1. Fetch `https://www.kabuka.jp.net/rating/<4桁コード>.html` (code without `.T`,
   e.g. `7203`). It is a per-stock history table: 発表日 / 証券会社 /
   レーティング / 目標株価（変更前 → 変更後）. Use the **post-change** (right
   side) figure of the latest entry per institution within the last year.
2. Institution-name mapping (the site abbreviates):
   野村 → `target_nomura` · 大和 → `target_daiwa` · SMBC日興/日興 →
   `target_smbc_nikko` · みずほ → `target_mizuho` · 三菱UFJMS/三菱UFJ
   モルガン・スタンレー → `target_mumss` · GS/ゴールドマン → `target_gs` ·
   モルガンS/モルガン・スタンレー(MUFG) → `target_ms` · JPM/JPモルガン →
   `target_jpm`. Caution: 三菱UFJMS (`target_mumss`) and モルガンS (`target_ms`)
   are **different entities** — never merge them.
3. Fallback / cross-check only if step 1 has no table for the stock:
   トレーダーズウェブ 注目レーティング (traders.co.jp), みんかぶ, かぶたん
   ニュース, or WebSearch `「<銘柄名 or コード> 目標株価 <機関名>」`.

**US stocks — primary source:**

1. Fetch `https://www.marketbeat.com/stocks/<EXCHANGE>/<TICKER>/price-target/`
   (e.g. `NASDAQ/AAPL`; `/forecast/` also works). Table columns: Report Date /
   Brokerage / Rating / Price Target.
2. Of our 8 institutions only Goldman Sachs (`target_gs`), Morgan Stanley
   (`target_ms`) and JPMorgan Chase & Co. (`target_jpm`) typically appear; the
   5 Japanese brokers rarely publish US coverage, so `なし` is normally correct
   for those — but GS/MS/JPM `なし` on a large-cap is suspicious: re-check via
   WebSearch `"<TICKER> price target Goldman Sachs"` (or benzinga.com) before
   writing it.

**Rules (unchanged):**

- **Freshness**: adopt a rating only if it was published **within the last year**.
  If an institution has multiple ratings inside that window, use the **latest**.
- **Cell format**: target price + announcement month, e.g. `¥2,400 (2026/5)` for
  JP stocks, `$150 (2026/5)` for US stocks.
- **No qualifying rating** (none found after the procedure above, or only older
  than a year): write `なし` (one word; never a sentence, never a fabricated
  number, never leave it empty).
- The no-fabrication rule applies in full: if you cannot confirm an institution's
  target from a public source, it is `なし` — do not infer one from a consensus
  (consensus/平均 figures are never an institution's number).

## AI-recommended averaging-down level (AIのおすすめナンピン株価)

This cell is **Claude's own judgment** of a reasonable averaging-down (ナンピン)
entry price for an existing position — not a researched fact and not anyone's
published number.

- `ai_nampin_price`: derive from recent support levels, the YTD low, volatility-
  typical pullback depth, and a valuation floor. The level must be **below the
  owner's 取得株価 and at or below the 現在株価** — a price that cannot lower the
  average cost is not an averaging-down level. **Cell format: price only**
  (`¥2,400` / `$150`). No date, no words, no range.
- If averaging down is not advisable (thesis impaired, downtrend likely to
  continue, position already oversized), write `なし` (one word). Never fabricate
  a level you cannot justify.
- The one-paragraph basis (and, if the owner filled ナンピン検討株価/株数, an
  assessment of *their* plan) goes in `AIコメント`, not in the cell
  (terse-cell rule).

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
   (earnings, guidance, sector/macro shifts), and the market environment. Spell out
   the reasoning, don't just list figures.
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
  購入理由 / 目標売却株価, not read like a stock-screener blurb.
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
picture is stable. Then judge it **through the lens of the owner's thesis**.

### 3. Write

Pass results as JSON via stdin, using the `row` from step 1. Each write carries a
`fields` object of role→value (only `ai_comment`, `target_*` and
`ai_nampin_price` are accepted).

```bash
echo '{"writes":[
  {"row":2,"fields":{
     "ai_comment":"<personalized comment to the owner, incl. research date>",
     "target_nomura":"¥3,400 (2026/4)","target_gs":"なし",
     "ai_nampin_price":"¥2,400"}},
  {"row":3,"fields":{"ai_comment":"<...>"}}
]}' | .venv/bin/python .claude/skills/holdings-review/research_io.py write
```

### 4. Report

Report only the number of holdings commented on (no tickers/prices). If anything
could not be confirmed and was therefore hedged in the comment, state that.

## What not to do

- Writing to any column other than `AIコメント`, the eight `目標株価（…）` columns
  and `AIのおすすめナンピン株価` (`research_io.py write` refuses it).
- Writing the owner's manual ナンピン検討株価 / ナンピン検討株数 cells.
- An `ai_nampin_price` at or above the 取得株価 — recompute or write `なし`.
- One-shotting the research, or restating figures instead of forming a judgment.
- Ignoring the owner's 購入理由 / 目標売却株価 — the comment must be about *their*
  position, not a generic take.
- Fabricating a value or event you could not confirm.
- Filling a `target_*` cell with a rating older than one year, a consensus-derived
  guess, or a sentence — the only valid values are `¥/$ price (YYYY/M)` or `なし`.
