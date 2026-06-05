# stock-price-sheet

Periodically writes the latest stock prices into a Google Sheet, on a GitHub
Actions schedule. Prices are fetched with [yfinance](https://github.com/ranaroussi/yfinance),
so both Japanese (`7203.T`) and US (`AAPL`) tickers work reliably. No machine of
your own needs to be running — GitHub's runners do the work.

## How it works

Two tracks feed the sheet:

- **Track A — automatic (this script, `update_prices.py`).** A scheduled workflow
  (`.github/workflows/update-prices.yml`) runs `update_prices.py`, which reads the
  tickers from the last column (`AG`) of each watchlist tab and writes back the
  yfinance-native fields listed in `config.yaml` (price, PER/PBR, dividend yield,
  52-week range, EPS, consensus analyst targets, rating) plus values it can derive
  (3-month max volume, the last four years of annual EPS, and EPS year-over-year)
  and an update timestamp. It fetches only what yfinance provides — no scraping, no AI.
- **Track B — manual (Claude skill, `.claude/skills/stock-research`).** For things
  yfinance can't give (industry-average PER/PBR, per-institution target prices,
  theoretical price, rating-change news, a synthesized analysis comment), a Claude
  skill does live web research, on demand, and writes the result with source URLs.
  It processes every row that has a ticker (no monitor flag).

The sheet has four tabs: `保有銘柄` (holdings), `監視-JP`, and `監視-US` (watchlists,
all sharing one 33-column layout), plus `売買履歴` (a manual trade-journal tab the
scripts never touch). The Japanese stock name lives in column `A` (manual), and the
yfinance ticker in the last column `AG` (manual).

## Setup

### 1. Prepare the Google Sheet

- Create three watchlist tabs named exactly `保有銘柄`, `監視-JP`, and `監視-US`,
  plus a `売買履歴` tab. (Tab names and headers are in Japanese; the repository
  references them by these literal names.)
- In each watchlist tab, put your tickers in the **last column (`AG`)**, in
  **yfinance format**:
  - Japan (Tokyo): `7203.T`, `9984.T`, ...
  - US: `AAPL`, `MSFT`, ...
- Column `A` is the stock name (manual, Japanese). Track A fills the
  yfinance-native and derived columns (`B`–`D`, `G`–`X`); columns `E`/`F`
  (industry-average PER/PBR) and `Y`–`AD` are filled by Track B; `AE` (your
  target price) and `AF` (memo) are yours to edit. There is no monitor flag —
  Track B researches every row that has a ticker.
- The `売買履歴` tab is a free-form trade journal (date / ticker / buy-sell /
  shares / price / your reason / a difficulty note) — no script writes to it.

### 2. Create a Google service account

1. Open the [Google Cloud Console](https://console.cloud.google.com/), create
   (or pick) a project.
2. Enable the **Google Sheets API** for that project.
3. Create a **service account**, then create a **JSON key** for it and download
   the file.
4. Copy the service account's email (looks like
   `name@project.iam.gserviceaccount.com`).

### 3. Share the sheet with the service account

- In the Google Sheet, click **Share** and add the service account email with
  **Editor** access. (Without this, the script cannot write.)

### 4. Add the key as a GitHub Actions secret

- Repo → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `GCP_SA_KEY`
- Value: the entire contents of the downloaded JSON key file.

### 5. Configure the sheet mapping

```bash
cp config.example.yaml config.yaml
# edit config.yaml: set your spreadsheet_id. The watchlists list, ticker_column,
# the yfinance `fields` map, and the derived/updated columns are pre-filled for
# the 保有銘柄 / 監視-JP / 監視-US tabs.
git add config.yaml && git commit -m "configure sheet mapping" && git push
```

`config.yaml` must be committed so the Actions runner can read it. It contains
no secrets and no tickers — the `spreadsheet_id` is just the ID from the sheet URL.

### 6. Run it

- Go to the **Actions** tab, select **Update stock prices**, and click
  **Run workflow** (`workflow_dispatch`) to test immediately.
- After that, it runs automatically on the schedule.

## Local testing

```bash
pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
python update_prices.py
```

## Track B (manual research with Claude)

Track B is a Claude Code skill at `.claude/skills/stock-research/`. Open this repo
in Claude Code and run the skill; it reads every row that has a ticker, does live
web research with the latest available sources, and writes industry-average
PER/PBR, per-institution targets, a theoretical price, catalyst/rating news,
source URLs, and a synthesized analysis comment — never fabricating values, always
citing sources. See that skill's `SKILL.md` and the project `CLAUDE.md` for the
research discipline.

## Caveats

- **Timing is approximate.** GitHub Actions scheduled runs are commonly delayed
  10-30+ minutes and can be skipped under load. This is fine for a watchlist,
  not for real-time trading.
- **Schedule is UTC.** The cron in the workflow targets JP (00:00-06:00 UTC) and
  US (13:00-21:00 UTC) market hours, Mon-Fri. Adjust if your markets differ.
- **Auto-disable.** GitHub disables scheduled workflows after 60 days without a
  commit to the repo. Push something occasionally, or re-enable from the Actions
  tab.
- **Minutes.** Public repos get unlimited Actions minutes; private repos draw
  from the free monthly allowance and may incur cost at high frequency.
- **Tickers must be yfinance format** (`7203.T`, not `TYO:7203`).
