# stock-price-sheet — instructions for Claude / contributors

This repository is **public**. Both committed content and GitHub Actions run logs
are visible to anyone. Follow the rules below strictly.

(The repository's files are written in English. The Google Sheet itself — tab
names, headers, and data — stays in Japanese; the tab-name literals such as
`保有銘柄` in this repo are sheet identifiers and are intentionally kept as-is.)

## Never include PII or held tickers (top priority)

- Never include the owner's PII (name, email, address, phone number, etc.) in any
  code, config, commit message, README, documentation, or log.
- Never put the tickers the owner actually holds anywhere in the repo. The real
  tickers exist **only in the private Google Sheet and are never committed**.
- Ticker examples in docs or code must be generic format-illustration examples
  (`7203.T`, `AAPL`, etc.). Do not use the owner's real holdings as examples.
- Do not write the owner's real held tickers as a literal in any file in the repo
  (code, config, README, docs, anything under `.claude/skills/`, sample or seed
  scripts) — not even as an "example". Real tickers live **only in the sheet's
  Ticker column**.
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

The sheet has two tabs. The system processes **`保有銘柄`** (holdings); `売買履歴`
(trade history) is **not** read or written by any code path here.

### 保有銘柄 (holdings)

Columns are mapped by **header name** (the row-1 label), not by position — see the
`columns` map in `config.yaml`. Inserting or moving a column does not break the
mapping; only renaming/removing a header does. The headers and their owners:

| Header       | Owner               | Source / meaning                                    |
|--------------|---------------------|-----------------------------------------------------|
| 銘柄名       | manual              | stock name (Japanese)                               |
| 取得日       | manual              | acquisition date                                    |
| 短中長期     | manual              | holding horizon (short/mid/long) — AI-comment input |
| 目標売却株価 | manual              | target sell price — AI-comment input                |
| 現在株価     | **Track A**         | yfinance `currentPrice`                             |
| 取得株価     | manual              | acquisition price                                   |
| 取得株数     | manual              | shares held (used to compute 配当金)                |
| 配当利回り   | **Track A**         | yfinance `dividendYield` (a percent number, e.g. 2.34) |
| 配当金       | **Track A**         | `dividendRate` × 取得株数 = total annual dividend   |
| 購入理由     | manual              | purchase reason (the thesis) — AI-comment input     |
| AIコメント   | **holdings-review** | Claude's personalized per-holding comment           |
| Ticker       | manual              | yfinance format (`7203.T`, `AAPL`); rows without it are skipped |

- **Track A** (`update_prices.py`, GitHub Actions, automatic): writes only
  `現在株価`, `配当利回り`, and `配当金`, all derived from yfinance natively (no
  scraping, no AI). 配当金 = per-share `dividendRate` × the manual 取得株数 (blank when
  取得株数 is empty). Targets every row that has a ticker.
- **holdings-review** (`.claude/skills/holdings-review`, run manually by Claude):
  for each holding, deep-researches the market and the stock over **repeated loops**,
  judges it against the owner's own 購入理由 / 短中長期 / 目標売却株価, and writes a
  personalized advisory comment to **`AIコメント`** (the only column it writes). It
  does **not** consult 売買履歴.
- Manual columns (銘柄名, 取得日, 短中長期, 目標売却株価, 取得株価, 取得株数, 購入理由,
  Ticker) are human-edited; neither code path overwrites them.
- Numeric columns already have display formats (thousands separators, `%`, etc.).
  Write raw numbers and percent values as numbers (e.g. `2.34` for 2.34%); let the
  cell format handle grouping and the `%` sign.

### Column mapping discipline (header-name based)

The mapping lives in `config.yaml` `columns` as {role → exact Japanese header label}
and is resolved at runtime by `sheet.py` `resolve_columns`. If the sheet's headers
are renamed/removed, a role will fail to resolve (Track A aborts on a missing
`ticker`; the `sheet-sync` skill reconciles the labels). Do not reintroduce
positional (A/B/C) column constants.

## holdings-review (AI comment) discipline

- When researching, always reference **the latest information as of the time of
  research**. Do not rely on memory or stale cache; confirm the latest primary
  sources/reporting.
- **Loop, don't one-shot**: research each holding repeatedly from multiple angles
  (macro/market, sector, company fundamentals/catalysts, valuation) before forming a
  judgment.
- **Never fabricate** prices, figures, or events. If something cannot be confirmed,
  hedge it in the comment text rather than guessing.
- The comment is a **personalized verdict addressed to the owner**: it must engage
  with their specific 購入理由 / 短中長期 / 目標売却株価 (is the thesis still intact,
  given the latest facts and their horizon?), use the figures as evidence, name the
  key risks and what to watch, and close with a stance. There is **no fetch-date
  column** — record the research date inside the comment text.
- The skill's output is handled only transiently in the local Claude session. Never
  leave tickers, prices, or PII **in committed files or public logs (Actions, etc.)**
  (handling them transiently for research is fine).

## Notes

- Tickers use yfinance format (`7203.T`, `AAPL`; not `TYO:7203`).
- Local run: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json python update_prices.py`
  (`--dry-run` fetches and resolves columns without writing).
- Access to the spreadsheet is granted by "sharing the sheet with the service
  account's email" (not via a GCP IAM role). The service account can access only
  the shared sheet, not the owner's entire Drive.
