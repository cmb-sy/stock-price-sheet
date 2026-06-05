# stock-price-sheet — instructions for Claude / contributors

This repository is **public**. Both committed content and GitHub Actions run logs
are visible to anyone. Follow the rules below strictly.

(The repository's files are written in English. The Google Sheet itself — tab
names, headers, and data — stays in Japanese; the tab-name literals such as
`保有銘柄` in this repo are sheet identifiers and are intentionally kept as-is.)

## Never include PII or held tickers (top priority)

- Never include the owner's PII (name, email, address, phone number, etc.) in any
  code, config, commit message, README, documentation, or log.
- Never put the tickers the owner actually holds/watches anywhere in the repo. The
  real tickers exist **only in the private Google Sheet and are never committed**.
- Ticker examples in docs or code must be generic format-illustration examples
  (`7203.T`, `AAPL`, etc.). Do not use the owner's real holdings as examples.
- Do not write the owner's real held/watched tickers as a literal in any file in
  the repo (code, config, README, docs, anything under `.claude/skills/`, sample
  or seed scripts) — not even as an "example". Real tickers live **only in the
  sheet's Ticker column (the last column, AG)**.
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
- `config.yaml` contains only the `spreadsheet_id` (an ID that is safe to publish).
  Never put tickers, PII, or keys in it.

## Data layout (two tracks / the sheet)

- The sheet has 4 tabs: `保有銘柄`, `監視-JP`, `監視-US` (watchlists; one shared
  33-column layout, A–AG) and `売買履歴`. `watchlists` in `config.yaml` are the
  processed tabs.
- Column layout (A–AG): A stock name (manual, Japanese) / B current price / C PER /
  D PBR / E industry PER / F industry PBR / G dividend yield / H market cap /
  I 3-month max volume / J 52-week high / K 52-week low / L EPS (TTM) /
  M–P actual EPS (latest–3 FY ago) / Q,R EPS YoY (latest/prev)% /
  S–U consensus target (mean/high/low) / V number of analysts / W rating /
  X Track A update time / Y per-institution targets / Z theoretical price /
  AA catalyst/rating news / AB source URLs / AC Track B fetch date /
  AD analysis comment / AE my target price (manual) / AF memo (manual) /
  AG Ticker (manual, last column, yfinance format).
- **Track A** (`update_prices.py`, GitHub Actions, automatic): writes only values
  yfinance returns natively plus values derived from them (3-month max volume, EPS
  history, EPS YoY). No over-fetching, no AI inference. The columns it writes are
  limited to `config.yaml`'s `fields` plus the computed columns (I, M–R, X).
  Industry PER/PBR (E/F) is not available from yfinance, so Track A never touches it.
- **Track B** (`.claude/skills/stock-research`, run manually by Claude): web-researches
  the values yfinance can't give (industry-average PER/PBR, per-institution target
  prices, theoretical price, catalyst/rating news, synthesized analysis) and writes
  them to columns E/F/Y–AD. It targets **every row that has a ticker** (the monitor
  flag has been removed).
- Column A (stock name), AE (my target price), AF (memo), AG (Ticker), and the
  entire `売買履歴` tab are human-edited areas. Tracks A/B never overwrite them.
- Numeric columns already have display formats (thousands separators, e.g. 1,000).
  Write raw numbers; let the format handle the grouping.
- See the comments in `config.yaml` for the full column definitions.

## Track B (web research) discipline

- When researching prices, metrics, target prices, or catalysts, always reference
  **the latest information as of the time of research**. Do not rely on memory or
  stale cache; confirm the latest primary sources/reporting.
- **Never fabricate** numbers, target prices, ratings, or catalysts. Leave
  unconfirmed values blank or mark them "unknown"; never fill them in by guessing.
- Every written value must be accompanied by a **source URL (column AB) and fetch
  date (column AC)**.
- The **analysis comment (column AD)** is a synthesis of repeated research from
  multiple angles. If a comment already exists, update it with the latest information.
- The skill's output is handled only transiently in the local Claude session. Never
  leave tickers, prices, or PII **in committed files or public logs (Actions, etc.)**
  (handling them transiently for research is fine).

## Notes

- Tickers use yfinance format (`7203.T`, `AAPL`; not `TYO:7203`).
- Local run: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json python update_prices.py`
- Access to the spreadsheet is granted by "sharing the sheet with the service
  account's email" (not via a GCP IAM role). The service account can access only
  the shared sheet, not the owner's entire Drive.
