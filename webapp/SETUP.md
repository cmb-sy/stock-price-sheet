# webapp — owner-only sheet editor (Google Apps Script)

A standalone Apps Script **web app** that shows the spreadsheet and lets you edit the
**manual columns** from a browser (incl. mobile). It opens the sheet by ID and runs
**as the accessing user** (`executeAs: USER_ACCESSING`), so it needs **no
service-account key** — but each allowed account must have the sheet shared with it.
Track A (yfinance) and Track B (Claude) columns are read-only and the server refuses to
write them.

Files (managed with `clasp`, Google's Apps Script CLI):

- `appsscript.json` — manifest. `executeAs: USER_ACCESSING`, `access: ANYONE`; access
  is then narrowed in code to an allowlist (see below), so each visitor runs as
  themselves and `Session.getActiveUser().getEmail()` can be checked. Scopes:
  `spreadsheets` + `userinfo.email`.
- `Code.gs` — server: `getRows` (read, display-formatted), `saveRow` (writes only
  whitelisted manual headers; refuses read-only columns). Every data call passes
  through `_guard()`, which rejects non-allowlisted users.
- `index.html` — client: tab switch → table (all columns) → per-row edit form
  (manual fields only) → save.

The allowlist (emails) is **not committed** — it lives in a Script Property named
`ALLOWED_EMAILS` (comma-separated), set in the Apps Script editor. `.clasp.json` (the
scriptId linkage) is **gitignored** — it stays local. No tickers, prices, PII, or keys
live in any committed file here (only generic header/tab labels and the spreadsheet_id,
which is already public-safe in `config.yaml`).

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
clasp create --type standalone --title "stock-price-sheet"
# clasp create overwrites appsscript.json with a default — restore THIS repo's
# version so executeAs/access/scopes are preserved:
git checkout -- appsscript.json
clasp push --force                  # uploads Code.gs, index.html, appsscript.json
```

`clasp create` writes a local `.clasp.json` with the new scriptId — it is gitignored.

## Set the allowlist

In the Apps Script editor → **Project Settings → Script Properties**, add a property:

- key: `ALLOWED_EMAILS`
- value: comma-separated emails allowed to use the app (e.g. `a@example.com,b@example.com`)

Share the spreadsheet (Editor) with each of those accounts — with `USER_ACCESSING`
the app acts as the visitor, so each must be able to open the sheet.

## Deploy as a web app

```bash
clasp deploy --description "v1"
```

Then open the Apps Script editor (`clasp open`) → **Deploy → Manage deployments** and
confirm: **Execute as = User accessing the web app**, **Who has access = Anyone**
(the in-code allowlist is what actually restricts access). Copy the web app URL
(`.../exec`). The first open will prompt you to authorize the `spreadsheets` +
`userinfo.email` scopes.

## Update later

```bash
cd webapp
clasp push --force
clasp deploy --description "vN"     # or redeploy the existing deployment in the UI
```

## Notes

- Numeric manual fields (購入検討株価/目標売却株価/取得株価/取得株数) are stored as
  numbers so the sheet's number format applies; names/reasons/tickers stay text.
- The editable manual columns per tab are defined by `MANUAL_HEADERS` in `Code.gs`
  (holdings: 銘柄名/目標売却株価/取得株価/取得株数/株主優待/購入理由/Ticker;
  watchlist: 銘柄名/購入検討株価/購入検討理由/Ticker). Everything else is read-only.
