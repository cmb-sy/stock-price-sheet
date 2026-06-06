---
name: sheet-sync
description: Detect drift between the live Google Sheet layout (tab names, columns, headers) and the repo's config.yaml / Track A / holdings-review skill, then reconcile config and flag code changes. Use after the sheet layout is edited (columns added/moved/renamed, tabs renamed) or when GitHub Actions fails with a grid/range or "header not found" error.
argument-hint: "(no args)"
---

The mapping is by **header name** (see `sheet.py` `resolve_columns`), so moving a
column no longer silently misdirects writes — instead, *renaming or removing* a
header makes its role fail to resolve. This skill detects that and reconciles
`config.yaml` (and flags any code follow-ups).

(Repo files are in English; the sheet stays in Japanese. Tab names like `保有銘柄`
are sheet identifiers, kept as-is.)

## Privacy

`layout_io.py` emits only structural metadata (tab names, dimensions, header
labels). Header labels are generic column names and contain no tickers/prices/PII.
Do not read or print any data rows. Never write this output into committed files or
public logs.

## Authentication

Same as Track A. From the repo root:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/sa-key.json"
```

## Procedure

### 1. Read the live layout + current config

```bash
.venv/bin/python .claude/skills/sheet-sync/layout_io.py read-layout
```

Returns `{"sheet": [{title, rows, cols, header}, ...], "config": {holdings_tab,
header_rows, columns}}`. The `header` array is the row-1 labels in column order
(index 0 = column A).

### 2. Check that every configured role resolves

`config.yaml` `columns` maps each logical role to an exact header label. For the
`holdings_tab`, confirm each label below appears in that tab's `header` array.

| config role       | header label | owner / role                                  |
|-------------------|--------------|-----------------------------------------------|
| `ticker`          | Ticker       | manual; rows without it are skipped (required)|
| `name`            | 銘柄名        | manual stock name                             |
| `shares`          | 取得株数      | manual; multiplied by dividendRate for 配当金 |
| `current_price`   | 現在株価      | Track A: yfinance currentPrice                |
| `dividend_yield`  | 配当利回り    | Track A: yfinance dividendYield (percent)     |
| `dividend_amount` | 配当金        | Track A: dividendRate * 取得株数              |
| `horizon`         | 短中長期      | manual; holdings-review input                 |
| `target_sell`     | 目標売却株価  | manual; holdings-review input                 |
| `purchase_reason` | 購入理由      | manual; holdings-review input                 |
| `ai_comment`      | AIコメント    | holdings-review writes this (only)            |

A header in the sheet not in this table is **unknown**: do not guess its owner —
list it in the report and ask the user how it should be filled.

### 3. Detect drift

- **Tab drift**: `holdings_tab` no longer exists, or was renamed.
- **Header drift**: a configured label that no longer matches any header (it was
  renamed or removed) — Track A / the skill will fail to resolve it.
- **New headers**: present in the sheet but not in `columns` (may need new code).
- **Required-role hazard**: the `ticker` label missing means Track A aborts.

(Because mapping is by name, a column that simply *moved* needs no change — that is
the point of this design.)

### 4. Reconcile

- **config-only changes** (safe to apply): update `columns` labels (and
  `holdings_tab`) so every role points at the header label that now carries its
  meaning. Update the layout comment block in `config.yaml` to match. Keep
  `config.example.yaml` in sync.
- **code follow-ups** (cannot be auto-applied — list them): a new header that needs
  logic that does not exist yet (e.g. a new Track A computed value yfinance cannot
  derive), or a removed role still referenced in `update_prices.py` /
  `research_io.py`. Enumerate each as an explicit follow-up; do not silently drop it.

Do not invent data and do not touch data rows — this skill only edits config/docs.

### 5. Report

Summarize: tabs/headers that drifted, the config edits made, and the code follow-ups
that still need a human/Claude implementation pass. Use header labels only — never
tickers, prices, or row data.
