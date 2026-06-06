# stock-price-sheet — instructions for Claude / contributors

This repository is **private**, but treat committed content and GitHub Actions run
logs as if they could leak (collaborators, accidental visibility flips, log
forwarding). The PII / ticker / secret rules below are **defense-in-depth and must
be followed strictly regardless of visibility** — never weaken them on the grounds
that the repo is private.

(The repository's files are written in English. The Google Sheet itself — tab
names, headers, and data — stays in Japanese; the tab-name literals such as
`保有銘柄` in this repo are sheet identifiers and are intentionally kept as-is.)

## Never include PII or held tickers (top priority)

- Never include the owner's PII (name, email, address, phone number, etc.) in any
  code, config, commit message, README, documentation, or log.
- Never put the tickers the owner actually holds **or watches** anywhere in the
  repo. The real tickers exist **only in the private Google Sheet and are never
  committed**.
- Ticker examples in docs or code must be generic format-illustration examples
  (`7203.T`, `AAPL`, etc.). Do not use the owner's real holdings/watchlist as examples.
- Do not write the owner's real held/watched tickers as a literal in any file in the
  repo (code, config, README, docs, anything under `.claude/skills/`, sample or seed
  scripts) — not even as an "example". Real tickers live **only in each tab's Ticker
  column**.
- If a setup/seed script that contains tickers is needed, keep and run it outside
  the repo (e.g. `/tmp`) and never commit it.

## Logging constraints (treat logs as potentially exposed)

- Never print ticker symbols, prices, or PII to stdout/stderr. Treat Actions logs as
  potentially readable beyond yourself.
- Debug output must be limited to information that cannot identify a stock (row
  numbers, counts, etc.).
- `update_prices.py` is designed to log only aggregate counts, never names or
  prices. Do not regress this property.

## Handling secrets

- The service-account JSON key is injected only via the GitHub secret `GCP_SA_KEY`.
  Never commit it (already gitignored: `*.json`).
- `config.yaml` contains only the `spreadsheet_id` (an ID that is safe to publish)
  and the column mapping (generic Japanese header labels). Never put tickers, PII,
  or keys in it.

## Data layout (the sheet)

The sheet has two **tab types**, both listed in `config.yaml`'s `tabs`:

- `type: holdings` — stocks the owner actually holds. Currently the **`保有銘柄`** tab.
- `type: watchlist` — stocks the owner is watching (not yet held). Currently
  **`監視-JP`** and **`監視-US`** (same layout, shared via a YAML anchor).

`売買履歴` (trade history) is **not** read or written by any code path here.

Columns are mapped by **header name** (the row-1 label), not by position — each
tab's `columns` map is {role → exact Japanese header label}, resolved at runtime by
`sheet.py` `resolve_columns`. Inserting or moving a column does not break the
mapping; only renaming/removing a header does (then the role fails to resolve;
Track A aborts on a missing `ticker`, and the `sheet-sync` skill reconciles labels).
**Do not reintroduce positional (A/B/C) column constants.**

### holdings tab (保有銘柄)

| Header       | Owner               | Source / meaning                                    |
|--------------|---------------------|-----------------------------------------------------|
| 銘柄名       | manual              | stock name (Japanese)                               |
| 取得日       | manual              | acquisition date                                    |
| 短中長期     | manual              | holding horizon — holdings-review input             |
| 目標売却株価 | manual              | target sell price — holdings-review input           |
| 現在株価     | **Track A**         | yfinance `currentPrice`                             |
| 取得株価     | manual              | acquisition price                                   |
| 取得株数     | manual              | shares held (used to compute 配当金)                |
| 配当利回り   | **Track A**         | yfinance `dividendYield` (a percent number, e.g. 2.34) |
| 配当金       | **Track A**         | `dividendRate` × 取得株数 = total annual dividend   |
| 購入理由     | manual              | purchase reason (the thesis) — holdings-review input |
| AIコメント   | **holdings-review** | Claude's personalized per-holding comment           |
| Ticker       | manual              | yfinance format; rows without it are skipped        |

Track A writes only `現在株価` / `配当利回り` / `配当金` here. Track B = the
**holdings-review** skill writes only `AIコメント`.

### watchlist tabs (監視-JP / 監視-US)

A richer layout (the owner is evaluating whether to buy). Roles → headers:

| Owner       | Headers                                                              |
|-------------|---------------------------------------------------------------------|
| manual      | 銘柄名, 購入検討株価, 購入検討理由, Ticker                           |
| **Track A** | かぶたんURL, 現在株価, PER, PBR, 配当利回り, 時価総額, 現在EPS, 年間EPS前年比（%）, レーティング, 次回決算日, 更新時刻 |
| **Track B** | 業界やテーマ, 業界PER, 業界PBR, アナリスト予想株価, 理論株価, AI分析コメント |

Track A derives the EPS YoY % from `income_stmt` annual EPS, 次回決算日 from
`Ticker.calendar` ("Earnings Date"), かぶたんURL from the ticker string (no fetch),
時価総額 by normalising `Ticker.info` `marketCap` to **億円** (FX-converted to JPY
for non-JPY listings; unit unified across JP and US tabs), and the rest verbatim
from `Ticker.info`. The theme, industry PER/PBR, the analyst/
theoretical prices, and the verdict are **not** available from yfinance, so Track A
never touches the Track B columns. Track B = the **stock-research** skill, whose
`AIコメント`/`AI分析コメント` also judges whether the owner's 購入検討理由 still
holds and whether the 購入検討株価 is a reasonable entry price.

### Shared rules

- Both tracks target **every row that has a ticker**; no-ticker rows are skipped.
- Manual columns are human-edited; neither code path overwrites them.
- Numeric columns carry Google Sheets **number formats** (cells keep raw, sortable
  numbers; only the display is styled): ratios (PER/PBR/業界PER/業界PBR) → `0.00`;
  percent magnitudes (配当利回り/年間EPS前年比） → `0.00"%"` (value is already the
  percent magnitude, e.g. `2.34` = 2.34%, so do **not** use a PERCENT format); EPS →
  `#,##0.00`; prices → `#,##0` on JP tabs / `#,##0.00` on US tabs and the holdings
  tab; 時価総額 → `#,##0"億円"`. Write raw numbers (and percent values as their
  magnitude, e.g. `2.34`); let the cell format handle grouping, decimals, and units.
  Reapply via the one-off `/tmp/apply_formats.py` (resolves columns by header, so
  column moves don't matter); it is never committed.

## Track B (Claude skills) discipline

Two manual, owner-only skills do the web research Track A cannot:
**holdings-review** (holdings tab → `AIコメント`) and **stock-research** (watchlist
tabs → 業界やテーマ/業界PER/業界PBR/アナリスト予想株価/理論株価/AI分析コメント). Both follow:

- When researching, always reference **the latest information as of the time of
  research**. Do not rely on memory or stale cache; confirm the latest primary
  sources/reporting.
- **Loop, don't one-shot**: research each stock repeatedly from multiple angles
  (macro/market, sector, company fundamentals/catalysts, valuation) before forming a
  judgment.
- **Never fabricate** prices, figures, targets, or events. If a number cannot be
  confirmed, do not guess a figure — instead write a **minimal reason word** in that
  cell (one or two words only, e.g. "赤字" / "確認不可"; never a sentence, no date —
  the research date lives in the comment), and elaborate/hedge in the comment. A
  reason word is the fallback for an unconfirmable value; an empty cell or a
  fabricated number is not.
- The comment is an **opinionated verdict**, not a restatement of the figures —
  use the figures as evidence, name the key risks and what to watch, close with a
  stance. holdings-review engages the owner's 購入理由 / 短中長期 / 目標売却株価;
  stock-research weighs the watch candidate against the owner's 購入検討株価. There is
  **no fetch-date column** — record the research date inside the comment text.
- The skills' output is handled only transiently in the local Claude session. Never
  leave tickers, prices, or PII **in committed files or run logs (Actions, etc.)**
  (handling them transiently for research is fine).

## Notes

- Tickers use yfinance format (`7203.T`, `AAPL`; not `TYO:7203`).
- Local run: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json python update_prices.py`
  (`--dry-run` fetches and resolves columns without writing).
- Access to the spreadsheet is granted by "sharing the sheet with the service
  account's email" (not via a GCP IAM role). The service account can access only
  the shared sheet, not the owner's entire Drive.
