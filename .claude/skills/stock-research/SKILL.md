---
name: stock-research
description: For each watched stock in the 監視-* tabs, deep-research the market environment and the stock from many angles over repeated loops, then write the values yfinance cannot give (the industry/theme, industry-average PER/PBR, an analyst-consensus target price, a theoretical price, per-institution analyst target prices) and a Claude-synthesized per-stock verdict into the watchlist's Track B columns. Manual, owner-only run.
argument-hint: "(no args; processes every row that has a ticker in every watchlist tab)"
---

For each watched stock (a candidate the owner does **not** yet hold), web-research
it deeply and write the analysis Track A cannot produce. Track A (yfinance) already
fills price, the YTD-low gap (年初来安値との乖離率), PER/PBR, market cap, EPS (TTM),
EPS YoY, rating, the next earnings date, and the kabutan URL. This skill adds the
**web-research** values and an opinionated verdict. It is a **manually launched,
owner-only skill**.

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
    `industry_pbr`, `analyst_target`, `theoretical`, `analysis_comment`, and the
    eight `target_*` per-institution target prices.
- **Only these Track B roles may be written** (`research_io.py write` refuses any other):
  - `theme` 業界やテーマ — the industry/theme the stock belongs to (short label).
  - `industry_per` 業界PER — industry-average PER (single number).
  - `industry_pbr` 業界PBR — industry-average PBR (single number).
  - `analyst_target` アナリスト予想株価 — analyst-consensus target price (single number).
  - `theoretical` 理論株価 — a theoretical fair price (single number).
  - `analysis_comment` AI分析コメント — Claude's synthesized per-stock verdict.
  - `target_nomura` 目標株価（野村） · `target_daiwa` 目標株価（大和） ·
    `target_smbc_nikko` 目標株価（SMBC日興） · `target_mizuho` 目標株価（みずほ） ·
    `target_mumss` 目標株価（三菱UFJMS） · `target_gs` 目標株価（GS） ·
    `target_ms` 目標株価（モルガンS） · `target_jpm` 目標株価（JPM） —
    per-institution analyst target prices (see the rules below).
  - `ai_dip_target` AI予想押し目 — Claude's own dip-buy level (see the rules below).

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

## AI-predicted dip-buy level (AI予想押し目)

`AI予想押し目` is **Claude's own judgment** of the price at which a pullback becomes
a reasonable entry — not a researched fact and not anyone's published target.

- Derive it from a combination of: recent support levels, the YTD low (Track A's
  年初来安値との乖離率 gives the distance), pullback depth typical for the name's
  volatility, and a valuation floor (PER/PBR vs. the industry averages you
  researched).
- **Cell format: price only** — `¥2,400` for JP stocks, `$150` for US stocks. No
  date, no words, no range. The one-paragraph basis for the level goes in
  `AI分析コメント`, not in the cell (terse-cell rule).
- If no meaningful level can be set (e.g. a fresh IPO with no trading history, or
  data too thin to defend any floor), write `なし` (one word). Never fabricate a
  level you cannot justify in the comment.

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
   (アナリスト予想株価), PER/PBR vs. the industry averages, EPS trend & YoY, dividend,
   the YTD-low gap (年初来安値との乖離率), and the market/sector backdrop as evidence.
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
     "target_nomura":"¥3,400 (2026/4)","target_gs":"なし",
     "analysis_comment":"<verdict + reasoning + research date>"}}
]}' | .venv/bin/python .claude/skills/stock-research/research_io.py write
```

### 4. Report

Report only the number of stocks commented on (no tickers/prices). If anything
could not be confirmed and was therefore filled with a reason text instead of a
number, state that.

## What not to do

- Writing any role other than the allowed Track B roles (`research_io.py write` refuses it).
- One-shotting the research, or restating figures instead of forming a judgment.
- Fabricating a theme, industry PER/PBR, target, theoretical price, or event you
  could not confirm — write a minimal reason word in that cell instead.
- Filling a `target_*` cell with a rating older than one year, a consensus-derived
  guess, or a sentence — the only valid values are `¥/$ price (YYYY/M)` or `なし`.
