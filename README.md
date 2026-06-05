# stock-price-sheet

Periodically writes the latest stock prices into a Google Sheet, on a GitHub
Actions schedule. Prices are fetched with [yfinance](https://github.com/ranaroussi/yfinance),
so both Japanese (`7203.T`) and US (`AAPL`) tickers work reliably. No machine of
your own needs to be running — GitHub's runners do the work.

## How it works

1. A scheduled workflow (`.github/workflows/update-prices.yml`) runs during
   market hours.
2. `update_prices.py` reads tickers from a configured column of your sheet.
3. It fetches each latest price via yfinance.
4. It writes the price (and an update timestamp) back into the sheet via the
   Google Sheets API.

## Setup

### 1. Prepare the Google Sheet

- Put your tickers in one column, in **yfinance format**:
  - Japan (Tokyo): `7203.T`, `9984.T`, ...
  - US: `AAPL`, `MSFT`, ...
- Leave a column for the price and (optionally) one for the update timestamp.

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
# edit config.yaml with your spreadsheet_id, worksheet name, and column letters
git add config.yaml && git commit -m "configure sheet mapping" && git push
```

`config.yaml` must be committed so the Actions runner can read it. It contains
no secrets — the `spreadsheet_id` is just the ID from the sheet URL.

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
