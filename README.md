# stock-price-sheet

Keeps a private Google Sheet of your **stock holdings** up to date, and lets Claude
write you a personalized advisory comment on each position. Prices and dividends are
fetched with [yfinance](https://github.com/ranaroussi/yfinance), so both Japanese
(`7203.T`) and US (`AAPL`) tickers work. No machine of your own needs to be running —
GitHub's runners do the automatic part.

## How it works

The repo processes two kinds of tab, both listed in `config.yaml`'s `tabs`:

- **holdings** (`保有銘柄`) — stocks you actually hold.
- **watchlist** (`監視-JP`, `監視-US`) — stocks you are evaluating but don't hold yet.

The `売買履歴` (trade history) tab is left untouched.

Two tracks feed every processed tab:

- **Track A — automatic (`update_prices.py`).** A scheduled workflow
  (`.github/workflows/update-prices.yml`) reads the tickers from each tab's `Ticker`
  column and writes back yfinance-native values (no scraping, no AI):
  - *holdings*: `現在株価` (current price), `配当利回り` (dividend yield, a percent
    number), `配当金` (total annual dividend = per-share dividend × your `取得株数`).
  - *watchlist*: a richer set — price, PER/PBR, dividend yield, market cap
    (normalised to 億円, FX-converted to JPY), EPS (TTM), EPS YoY, rating, next
    earnings date, a kabutan URL built from the ticker, and a write timestamp.
- **Track B — manual (Claude skills).** Two skills do the web research yfinance can't:
  - `.claude/skills/holdings-review` — for each holding, deep-researches over repeated
    loops, weighs it against **your own** `購入理由` / `短中長期` / `目標売却株価`, and
    writes a personalized verdict into `AIコメント`.
  - `.claude/skills/stock-research` — for each watched stock, researches the values
    yfinance can't give (the industry/theme, industry PER/PBR, an analyst-consensus
    target price, a theoretical price) and writes those plus a synthesized verdict
    (`AI分析コメント`).

Columns are mapped by **header name**, not by position (see each tab's `columns` map
in `config.yaml`), so adding or moving a column in the sheet does not break anything;
only renaming or removing a header does.

## Setup

### 1. Prepare the Google Sheet

- Have the tabs your `config.yaml` lists. Out of the box: `保有銘柄` (holdings),
  `監視-JP` and `監視-US` (watchlists). Row 1 of each holds the Japanese header labels
  from that tab's `columns` map. The order does not matter — the code finds each
  column by its label.
- Put your tickers in each tab's `Ticker` column, in **yfinance format**:
  - Japan (Tokyo): `7203.T`, `9984.T`, ...
  - US: `AAPL`, `MSFT`, ...
- Fill the manual columns yourself. Track A fills the price/metric columns; the
  holdings-review skill fills `AIコメント` (holdings) and stock-research fills the
  Track B columns (watchlists). Rows with no ticker are skipped.

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
# edit config.yaml: set your spreadsheet_id. The `tabs` list (each tab's name,
# type, and role -> Japanese header label map) is pre-filled for the
# 保有銘柄 / 監視-JP / 監視-US layout.
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

Track B is two Claude Code skills. Open this repo in Claude Code and run the one you
need; each does looped live web research with the latest sources and never fabricates
values (anything unconfirmed is left blank / hedged in the text):

- **`.claude/skills/holdings-review/`** — for the holdings tab. Reads each holding
  (your purchase reason, horizon, target sell price, plus the Track A figures) and
  writes a personalized advisory comment into `AIコメント`.
- **`.claude/skills/stock-research/`** — for the watchlist tabs. Researches the
  values yfinance can't give (the industry/theme, industry PER/PBR, an
  analyst-consensus target price, a theoretical price) and writes them plus a
  synthesized verdict into `AI分析コメント`.

See each skill's `SKILL.md` and the project `CLAUDE.md` for the research discipline.

If you edit the sheet's structure (rename/remove a header, rename a tab), run the
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
