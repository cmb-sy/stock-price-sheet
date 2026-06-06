# webapp — owner-only sheet editor (Google Apps Script)

A standalone Apps Script **web app** that shows the spreadsheet and lets you edit the
**manual columns** from a browser (incl. mobile). It opens the sheet by ID and runs
**as you** (the deploying owner), so it needs **no service-account key**. Track A
(yfinance) and Track B (Claude) columns are read-only and the server refuses to write
them.

Files (managed with `clasp`, Google's Apps Script CLI):

- `appsscript.json` — manifest. `executeAs: USER_DEPLOYING`, `access: MYSELF`
  (only you can open it), scope limited to `spreadsheets`.
- `Code.gs` — server: `getRows` (read, display-formatted), `saveRow` (writes only
  whitelisted manual headers; refuses read-only columns).
- `index.html` — client: tab switch → table (all columns) → per-row edit form
  (manual fields only) → save.

`.clasp.json` (the scriptId linkage) is **gitignored** — it stays local. No tickers,
prices, PII, or keys live in any committed file here (only generic header/tab labels
and the spreadsheet_id, which is already public-safe in `config.yaml`).

## One-time setup

```bash
npm install -g @google/clasp        # install the CLI (Node 18+; repo has Node 20)
clasp login                         # opens a browser; log in as the sheet's owner
```

Also enable the Apps Script API once at:
<https://script.google.com/home/usersettings> → "Apps Script API" → On.

## Create the project and push

```bash
cd webapp
clasp create --type webapp --title "stock-price-sheet"
# If clasp asks about overwriting appsscript.json, keep THIS repo's version
# (answer no / restore it with: git checkout -- appsscript.json).
clasp push                          # uploads Code.gs, index.html, appsscript.json
```

`clasp create` writes a local `.clasp.json` with the new scriptId — it is gitignored.

## Deploy as a web app

```bash
clasp deploy --description "v1"
```

Then open the Apps Script editor (`clasp open`) → **Deploy → Manage deployments** and
confirm: **Execute as = Me**, **Who has access = Only myself**. Copy the web app URL
(`.../exec`). The first open will prompt you to authorize the `spreadsheets` scope.

## Update later

```bash
cd webapp
clasp push
clasp deploy --description "vN"     # or redeploy the existing deployment in the UI
```

## Notes

- Numeric manual fields (購入検討株価/目標売却株価/取得株価/取得株数) are stored as
  numbers so the sheet's number format applies; names/reasons/tickers stay text.
- Editing 取得日 from the web stores it as text; for a true date value, edit it in the
  sheet directly. (v1 scope.)
- Adding brand-new rows is not in v1 — add a ticker row in the sheet, then it appears
  here for editing.
