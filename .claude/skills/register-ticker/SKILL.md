---
name: register-ticker
description: Resolve the yfinance ticker for watchlist rows the owner registered by name (a 銘柄名 with no Ticker yet, added from the web app). Propose candidate tickers from the yfinance search API, let the OWNER pick one (never auto-pick), then write the chosen Ticker so Track A can fill the rest. Manual, owner-only run.
argument-hint: "(no args; processes every watchlist row that has a name but no ticker)"
---

The owner registers a stock by **name** from the web app — this creates a name-only row
(a `銘柄名` with an empty `Ticker`) in a watchlist tab. This skill turns that name into a
yfinance ticker: it **proposes candidates**, the **owner chooses**, and only the chosen
`Ticker` is written. After that, Track A fills the metric columns on its next run and
**stock-research** can fill the Track B columns. This is a **manually launched,
owner-only skill**.

(Repo files are in English; the sheet — tab names, headers, data — stays in Japanese.
Tab names like `監視-JP` / `監視-US` are sheet identifiers, kept as-is.)

## Target tabs and columns

- Processed tabs: every tab of `type: watchlist` in `config.yaml` (currently `監視-JP`,
  `監視-US`). The holdings tab is out of scope.
- Columns are resolved by **header name**, not position (see `sheet.py`).
- Read: `name` 銘柄名 (the registered name) — only rows where `name` is non-empty and
  `ticker` Ticker is empty are processed.
- **Only the `Ticker` column may be written** (`register_io.py write-ticker` refuses any
  other column). No metric or comment column is touched.

## Discipline (strict)

- **Never auto-pick.** The yfinance search is ambiguous for Japanese names (multiple
  listings, ADRs, similarly named firms). Always present the candidates and let the
  **owner choose**. If nothing matches, leave the row's Ticker empty and report it — do
  **not** guess.
- **Confirm the market.** A name on `監視-JP` should resolve to a Japanese listing
  (`####.T`); on `監視-US` to a US listing (`AAPL`). Prefer the candidate whose exchange
  matches the tab; if the only matches are on the wrong market, surface that to the owner
  rather than writing a mismatched ticker.
- **Latest information**: if the search candidates are unclear, cross-check the company
  with WebSearch (official name, listing venue, ticker) before presenting — but the pick
  is still the owner's.
- **Secret-handling discipline**: output is handled only transiently in the local Claude
  session. Never leave tickers, names, or PII in committed files or run logs (see the
  repo-root `CLAUDE.md`). Reporting prints counts only.

## Authentication

Same as Track A. Since this runs locally, set the environment variable (from the repo
root):

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/sa-key.json"
```

`register_io.py` references the repo-root `sheet.py` / `config.yaml`.

## Procedure

### 1. List the rows waiting for a ticker

```bash
.venv/bin/python .claude/skills/register-ticker/register_io.py read-pending
```

Returns `[{tab, row, name}, ...]` — each watchlist row that has a `銘柄名` but no
`Ticker`. If empty, there is nothing to do.

### 2. Propose candidates for each name

For each pending row, query the yfinance search API:

```bash
.venv/bin/python .claude/skills/register-ticker/register_io.py search "<the 銘柄名>"
```

Returns `[{symbol, name, exchange, type}, ...]` (up to 8). Filter to the tab's market
(JP listings for `監視-JP`, US for `監視-US`), drop non-equity types, and if the result
is ambiguous, cross-check with WebSearch. **Present the shortlist to the owner and ask
which one** (symbol + company name + exchange). Do not proceed on a guess.

### 3. Write the chosen ticker

After the owner picks, write only the `Ticker` for that `tab` / `row`:

```bash
echo '{"writes":[
  {"tab":"監視-JP","row":7,"ticker":"7203.T"}
]}' | .venv/bin/python .claude/skills/register-ticker/register_io.py write-ticker
```

### 4. Report and hand off

Report only how many tickers were written and how many rows were left unresolved (no
tickers/prices in the summary beyond what the owner already chose). Remind the owner
that Track A will fill the metric columns on its next run, and that **stock-research**
can then fill the Track B analysis columns.

## What not to do

- Writing any column other than `Ticker` (`register_io.py write-ticker` refuses it).
- Auto-selecting a candidate, or writing a ticker the owner did not confirm.
- Writing a ticker whose market does not match the tab (JP vs US).
- Inventing a ticker when the search returns nothing — leave it empty and report it.
