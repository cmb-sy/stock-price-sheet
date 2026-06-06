# stock-price-sheet

Keeps a private Google Sheet of your **stock holdings** up to date, and lets Claude
write you a personalized advisory comment on each position. Prices and dividends are
fetched with [yfinance](https://github.com/ranaroussi/yfinance), so both Japanese
(`7203.T`) and US (`AAPL`) tickers work. No machine of your own needs to be running —
GitHub's runners do the automatic part.

## How it works

The sheet has two tabs; this repo works on the **`保有銘柄`** (holdings) tab. The
`売買履歴` (trade history) tab is left untouched.

Two tracks feed the holdings tab:

- **Track A — automatic (`update_prices.py`).** A scheduled workflow
  (`.github/workflows/update-prices.yml`) reads the tickers from the `Ticker` column
  and writes back three yfinance-native values: `現在株価` (current price),
  `配当利回り` (dividend yield, a percent number), and `配当金` (total annual dividend
  = per-share dividend × your `取得株数`). It fetches only what yfinance provides — no
  scraping, no AI.
- **Track B — manual (`.claude/skills/holdings-review`).** A Claude skill that, for
  each holding, deep-researches the market and the stock over repeated loops, weighs
  it against **your own** purchase reason (`購入理由`), horizon (`短中長期`), and target
  sell price (`目標売却株価`), and writes a personalized comment into the `AIコメント`
  column — telling you whether your original thesis still holds and what to watch.

Columns are mapped by **header name**, not by position (see `config.yaml`'s `columns`
map), so adding or moving a column in the sheet does not break anything; only renaming
or removing a header does.

## Setup

### 1. Prepare the Google Sheet

- Have a tab named exactly `保有銘柄`. Row 1 holds the Japanese header labels listed
  in `config.yaml` (銘柄名, 取得日, 短中長期, 目標売却株価, 現在株価, 取得株価, 取得株数,
  配当利回り, 配当金, 購入理由, AIコメント, Ticker). The order does not matter — the
  code finds each column by its label.
- Put your tickers in the `Ticker` column, in **yfinance format**:
  - Japan (Tokyo): `7203.T`, `9984.T`, ...
  - US: `AAPL`, `MSFT`, ...
- Fill the manual columns yourself (銘柄名, 取得日, 短中長期, 目標売却株価, 取得株価,
  取得株数, 購入理由). Track A fills 現在株価 / 配当利回り / 配当金; the holdings-review
  skill fills AIコメント. Rows with no ticker are skipped.

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
# edit config.yaml: set your spreadsheet_id. holdings_tab and the columns map
# (role -> Japanese header label) are pre-filled for the 保有銘柄 layout.
git add config.yaml && git commit -m "configure sheet mapping" && git push
```

`config.yaml` must be committed so the Actions runner can read it. It contains no
secrets and no tickers — the `spreadsheet_id` is just the ID from the sheet URL.

### 6. Run it

- Go to the **Actions** tab, select **Update stock prices**, and click
  **Run workflow** (`workflow_dispatch`) to test immediately.
- After that, it runs automatically on the schedule.

## Local testing

```bash
pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
python update_prices.py --dry-run   # fetch + resolve columns, write nothing
python update_prices.py             # actually write
python -m unittest discover -s tests
```

## Track B (manual research with Claude)

Track B is a Claude Code skill at `.claude/skills/holdings-review/`. Open this repo in
Claude Code and run the skill; it reads each holding (your purchase reason, horizon,
target sell price, plus the Track A figures), does looped live web research with the
latest sources, and writes a personalized advisory comment into `AIコメント` — never
fabricating values (anything unconfirmed is hedged in the text). See that skill's
`SKILL.md` and the project `CLAUDE.md` for the research discipline.

If you edit the sheet's structure (rename/remove a header, rename the tab), run the
`sheet-sync` skill to reconcile `config.yaml`.

## Caveats

- **Timing is approximate.** GitHub Actions scheduled runs are commonly delayed
  10-30+ minutes and can be skipped under load. Fine for holdings tracking, not for
  real-time trading.
- **Schedule is UTC.** The workflow runs twice a day on weekdays — 06:00 UTC
  (15:00 JST, after the Tokyo close) and 22:00 UTC (07:00 JST, after the US close).
  Adjust the cron if your markets differ.
- **Auto-disable.** GitHub disables scheduled workflows after 60 days without a
  commit to the repo. Push something occasionally, or re-enable from the Actions tab.
- **Tickers must be yfinance format** (`7203.T`, not `TYO:7203`).
- **Dividend currency.** 配当金 is in the stock's own currency (JPY for `*.T`, USD for
  US tickers), so a mixed-market holdings tab mixes currencies in that column — same
  as 現在株価.
