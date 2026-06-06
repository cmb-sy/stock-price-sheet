---
name: sheet-sync
description: Detect drift between the live Google Sheet layout (tab names, columns, headers) and the repo's config.yaml / Track A / holdings-review / stock-research, then reconcile config and flag code changes. Use after the sheet layout is edited (columns added/moved/renamed, tabs renamed) or when GitHub Actions fails with a grid/range or "header not found" error.
argument-hint: "(no args)"
---

The mapping is by **header name** (see `sheet.py` `resolve_columns`), so moving a
column no longer silently misdirects writes — instead, *renaming or removing* a
header makes its role fail to resolve. This skill detects that and reconciles
`config.yaml` (and flags any code follow-ups).

(Repo files are in English; the sheet stays in Japanese. Tab names like
`保有銘柄` / `監視-JP` are sheet identifiers, kept as-is.)

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

Returns `{"sheet": [{title, rows, cols, header}, ...], "config": {header_rows,
tabs}}`. The `header` array is the row-1 labels in column order (index 0 = column
A). `config.tabs` is the list of `{tab, type, columns}` definitions.

### 2. Check that every configured role resolves

`config.yaml` `tabs` lists each processed tab with `type` (`holdings` or
`watchlist`) and a `columns` map (role → exact header label). For each tab, find the
matching live worksheet by `tab` name, then confirm each label appears in that
worksheet's `header` array.

**holdings tab roles** (e.g. `保有銘柄`):

| role              | header label | owner / role                                  |
|-------------------|--------------|-----------------------------------------------|
| `ticker`          | Ticker       | manual; rows without it are skipped (required)|
| `name`            | 銘柄名        | manual                                        |
| `shares`          | 取得株数      | manual; × dividendRate for 配当金             |
| `current_price`   | 現在株価      | Track A: currentPrice                          |
| `dividend_yield`  | 配当利回り    | Track A: dividendYield (percent)               |
| `dividend_amount` | 配当金        | Track A: dividendRate × 取得株数              |
| `horizon`         | 短中長期      | manual; holdings-review input                  |
| `target_sell`     | 目標売却株価  | manual; holdings-review input                  |
| `purchase_reason` | 購入理由      | manual; holdings-review input                  |
| `ai_comment`      | AIコメント    | holdings-review writes this (only)             |

**watchlist tab roles** (e.g. `監視-JP`, `監視-US`):

| role              | header label       | owner / role                          |
|-------------------|--------------------|---------------------------------------|
| `name`            | 銘柄名             | manual                                |
| `kabutan_url`     | かぶたんURL        | Track A: built from the ticker        |
| `theme`           | 業界やテーマ       | Track B (stock-research)              |
| `my_target`       | 購入検討株価       | manual                                |
| `consider_reason` | 購入検討理由       | manual; stock-research input          |
| `current_price`   | 現在株価           | Track A: currentPrice                 |
| `per`             | PER                | Track A: trailingPE                   |
| `industry_per`    | 業界PER            | Track B (stock-research)              |
| `pbr`             | PBR                | Track A: priceToBook                  |
| `industry_pbr`    | 業界PBR            | Track B (stock-research)              |
| `dividend_yield`  | 配当利回り         | Track A: dividendYield (percent)      |
| `market_cap`      | 時価総額           | Track A: marketCap                    |
| `eps_ttm`         | 現在EPS            | Track A: trailingEps                  |
| `eps_yoy_latest`  | 年間EPS前年比（%） | Track A: computed from income_stmt    |
| `rating`          | レーティング       | Track A: recommendationKey            |
| `analyst_target`  | アナリスト予想株価 | Track B (stock-research)              |
| `theoretical`     | 理論株価           | Track B (stock-research)              |
| `next_earnings`   | 次回決算日         | Track A: ticker.calendar Earnings Date|
| `analysis_comment`| AI分析コメント     | Track B (stock-research) writes this  |
| `ticker`          | Ticker             | manual; required                      |
| `updated`         | 更新時刻           | Track A: write timestamp              |

A header in the sheet not in the relevant table is **unknown**: do not guess its
owner — list it in the report and ask the user how it should be filled.

### 3. Detect drift

- **Tab drift**: a configured `tab` no longer exists, or was renamed.
- **Header drift**: a configured label that no longer matches any header in its tab
  (renamed or removed) — Track A / the skill will fail to resolve it.
- **New headers**: present in the sheet but not in `columns` (may need new code).
- **Required-role hazard**: the `ticker` label missing means that tab aborts.

(Because mapping is by name, a column that simply *moved* needs no change — that is
the point of this design.)

### 4. Reconcile

- **config-only changes** (safe to apply): update the affected tab's `columns`
  labels (or its `tab` name) so every role points at the header label that now
  carries its meaning. For watchlist tabs that share the `_watchlist_columns` YAML
  anchor, edit the anchor once. Keep `config.example.yaml` in sync.
- **code follow-ups** (cannot be auto-applied — list them): a new header that needs
  logic that does not exist yet (e.g. a new Track A computed value yfinance cannot
  derive), or a removed role still referenced in `update_prices.py` /
  `research_io.py`. Enumerate each as an explicit follow-up; do not silently drop it.

Do not invent data and do not touch data rows — this skill only edits config/docs.

### 5. Report

Summarize: tabs/headers that drifted, the config edits made, and the code follow-ups
that still need a human/Claude implementation pass. Use header labels only — never
tickers, prices, or row data.
