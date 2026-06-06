# stock-price-sheet — instructions for Claude / contributors

This repository is **public**. Both committed content and GitHub Actions run logs
are visible to anyone. Follow the rules below strictly.

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

## Logging constraints (public = logs are public too)

- Never print ticker symbols, prices, or PII to stdout/stderr. Actions logs are
  world-readable.
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
| manual      | 銘柄名, 購入検討株価, メモ, Ticker                                   |
| **Track A** | 現在株価, PER, PBR, 配当利回り, 時価総額, 3ヶ月最大出来高, 52週高値, 52週安値, EPS(TTM), EPS実績(当期/1期前/2期前/3期前), EPS前年比(直近)%, EPS前年比(前期)%, 合意目標(平均/高/安), アナリスト数, レーティング, 更新時刻 |
| **Track B** | 業界PER, 業界PBR, 平均目標株価, 理論株価, AI分析コメント            |

Track A derives EPS history from `income_stmt`, EPS YoY from it, 3ヶ月最大出来高 from
`history("3mo")`, and the rest from `Ticker.info`. Industry PER/PBR, the
target/theoretical prices, and the verdict are **not** available from yfinance, so
Track A never touches the Track B columns. Track B = the **stock-research** skill.

### Shared rules

- Both tracks target **every row that has a ticker**; no-ticker rows are skipped.
- Manual columns are human-edited; neither code path overwrites them.
- Numeric columns already have display formats (thousands separators, `%`, etc.).
  Write raw numbers and percent values as numbers (e.g. `2.34` for 2.34%); let the
  cell format handle grouping and the `%` sign.

## Track B (Claude skills) discipline

Two manual, owner-only skills do the web research Track A cannot:
**holdings-review** (holdings tab → `AIコメント`) and **stock-research** (watchlist
tabs → 業界PER/業界PBR/平均目標株価/理論株価/AI分析コメント). Both follow:

- When researching, always reference **the latest information as of the time of
  research**. Do not rely on memory or stale cache; confirm the latest primary
  sources/reporting.
- **Loop, don't one-shot**: research each stock repeatedly from multiple angles
  (macro/market, sector, company fundamentals/catalysts, valuation) before forming a
  judgment.
- **Never fabricate** prices, figures, targets, or events. If something cannot be
  confirmed, leave that value blank and hedge it in the comment text rather than
  guessing.
- The comment is an **opinionated verdict**, not a restatement of the figures —
  use the figures as evidence, name the key risks and what to watch, close with a
  stance. holdings-review engages the owner's 購入理由 / 短中長期 / 目標売却株価;
  stock-research weighs the watch candidate against the owner's 購入検討株価. There is
  **no fetch-date column** — record the research date inside the comment text.
- The skills' output is handled only transiently in the local Claude session. Never
  leave tickers, prices, or PII **in committed files or public logs (Actions, etc.)**
  (handling them transiently for research is fine).

## Notes

- Tickers use yfinance format (`7203.T`, `AAPL`; not `TYO:7203`).
- Local run: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json python update_prices.py`
  (`--dry-run` fetches and resolves columns without writing).
- Access to the spreadsheet is granted by "sharing the sheet with the service
  account's email" (not via a GCP IAM role). The service account can access only
  the shared sheet, not the owner's entire Drive.
