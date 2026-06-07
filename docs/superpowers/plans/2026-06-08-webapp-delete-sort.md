# Web アプリ 行削除 + 指標ソート 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** owner 専用 Apps Script Web アプリに、シート行を物理削除する行削除機能（誤削除を防ぐサーバ側同定ガード付き）と、指標によるクライアント表示ソートを追加する。

**Architecture:** 決定的な並び替えロジックを依存ゼロの純関数として `webapp/sortlib.html` に切り出し、HtmlService テンプレートで `index.html` に include する。この純関数だけ Node で自動テストする（Apps Script サーバ関数と DOM 配線は clasp が無くローカル実行不可のため、owner のブラウザ手動検証で担保）。ソートはシートを変更せず `state.rows`（シート順）のコピー `state.view` に対して行い、行の同定 `row.row` を保持するので削除の正確性が崩れない。削除はサーバ側で現在の Ticker+銘柄名 を `expected` と照合し、不一致なら削除を拒否する。

**Tech Stack:** Google Apps Script (Code.gs / HtmlService templating), 単一ファイル SPA (index.html, vanilla JS), Node v20 (`node --test` + `node:vm` でローカル単体テスト), 既存 Python unittest（回帰確認用）。

**設計書:** `docs/superpowers/specs/2026-06-08-webapp-delete-sort-design.md`

---

## File Structure

| ファイル | 役割 | 変更 |
|---|---|---|
| `webapp/sortlib.html` | 純粋ソートロジック（`RATING_RANK` / `ratingRank` / `compareKeys` / `sortRows`）。ブラウザにも Node テストにも単一ソースとして供給。DOM・google.* 非依存。 | Create |
| `tests/webapp/test_sortlib.mjs` | `sortlib.html` の `<script>` 本体を `node:vm` で評価し純関数を検証。 | Create |
| `webapp/Code.gs` | `include()` 追加、`doGet` をテンプレート評価に変更、`deleteRow()` 追加。 | Modify |
| `webapp/index.html` | sortlib を include、ソート state/ロジック、`render`/`openEdit` を `state.view` 参照に、`.meta` のソート UI、編集シートの削除 UI とハンドラ、関連 CSS。 | Modify |

**制約（実装前検証 / 不変条件）:**
- `<!DOCTYPE html>` は `index.html` 1 行目を維持。
- 列はヘッダ名で解決（位置で解決しない）。ヘッダラベルは `config.yaml` 準拠（下記タスクのコードは実ラベルに一致済み）。
- PUBLIC リポジトリ。ティッカー/価格/PII/allowlist email をコード・コミット・ログに出さない。`Code.gs` はセル値をログ出力しない（`deleteRow` は `true` のみ返す）。
- `webapp/**` を push すると本番 clasp デプロイ（`deploy-webapp.yml`）が走る。**push は Task 6 の owner 検証後にユーザー確認を取ってから**。各タスクの commit はローカルに留める。

---

## Task 1: 純粋ソートロジック `sortlib.html` + Node 単体テスト（TDD）

**Files:**
- Create: `tests/webapp/test_sortlib.mjs`
- Create: `webapp/sortlib.html`

- [ ] **Step 1: 失敗するテストを書く**

Create `tests/webapp/test_sortlib.mjs`:

```javascript
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';

// sortlib.html は <script> でラップされた純関数群。本体を取り出し vm で評価して
// 関数を取得する（ブラウザでもこの同じ script が読み込まれる = 単一ソース）。
const file = fileURLToPath(new URL('../../webapp/sortlib.html', import.meta.url));
const html = readFileSync(file, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(m, 'sortlib.html must contain a <script> block');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(m[1], ctx);
const { ratingRank, compareKeys, sortRows } = ctx;

test('ratingRank maps rating strings to ranks, else null', () => {
  assert.equal(ratingRank('strong_buy'), 5);
  assert.equal(ratingRank('Strong Buy'), 5); // space/hyphen -> underscore, lowercased
  assert.equal(ratingRank('strong-buy'), 5);
  assert.equal(ratingRank('buy'), 4);
  assert.equal(ratingRank('hold'), 3);
  assert.equal(ratingRank('underperform'), 2);
  assert.equal(ratingRank('sell'), 1);
  assert.equal(ratingRank(''), null);
  assert.equal(ratingRank('確認不可'), null);
  assert.equal(ratingRank(null), null);
});

test('compareKeys: numbers honor direction', () => {
  assert.ok(compareKeys(1, 2, 'asc') < 0);
  assert.ok(compareKeys(2, 1, 'asc') > 0);
  assert.ok(compareKeys(1, 2, 'desc') > 0);
  assert.equal(compareKeys(5, 5, 'asc'), 0);
});

test('compareKeys: null/empty always sink to bottom regardless of direction', () => {
  assert.equal(compareKeys(null, 5, 'asc'), 1);
  assert.equal(compareKeys(5, null, 'asc'), -1);
  assert.equal(compareKeys(null, 5, 'desc'), 1);   // still sinks, not flipped
  assert.equal(compareKeys(5, null, 'desc'), -1);
  assert.equal(compareKeys('', 5, 'asc'), 1);
  assert.equal(compareKeys(null, null, 'asc'), 0);
});

test('compareKeys: strings use locale compare', () => {
  assert.ok(compareKeys('あ', 'い', 'asc') < 0);
  assert.ok(compareKeys('あ', 'い', 'desc') > 0);
});

test('sortRows: desc/asc order with nulls last, input untouched, stable', () => {
  const rows = [{ v: 3, id: 'a' }, { v: null, id: 'b' }, { v: 1, id: 'c' },
                { v: 2, id: 'd' }, { v: 1, id: 'e' }];
  const getKey = (r) => r.v;

  const desc = sortRows(rows, getKey, 'desc');
  assert.deepEqual(desc.map((r) => r.id), ['a', 'd', 'c', 'e', 'b']); // 3,2,1,1,null; 1s stable

  const asc = sortRows(rows, getKey, 'asc');
  assert.deepEqual(asc.map((r) => r.id), ['c', 'e', 'd', 'a', 'b']);  // 1,1,2,3,null; 1s stable

  // input array not mutated
  assert.deepEqual(rows.map((r) => r.id), ['a', 'b', 'c', 'd', 'e']);
});
```

- [ ] **Step 2: テストを実行し、失敗を確認**

Run: `node --test tests/webapp/test_sortlib.mjs`
Expected: FAIL（`webapp/sortlib.html` が無いため `readFileSync` が ENOENT で throw）

- [ ] **Step 3: `sortlib.html` を実装**

Create `webapp/sortlib.html`:

```html
<script>
  // Pure, dependency-free sort helpers (no DOM, no google.*). Single source of truth:
  // this same <script> is included into index.html via HtmlService templating, and is
  // unit-tested from Node (tests/webapp/test_sortlib.mjs) by evaluating this body.
  // Declared with `function`/`var` so they become globals in both the browser and the
  // Node vm context.
  var RATING_RANK = { strong_buy: 5, buy: 4, hold: 3, underperform: 2, sell: 1 };

  // Analyst rating display string -> rank (1..5), or null when unknown/empty.
  function ratingRank(v) {
    var k = String(v == null ? '' : v).trim().toLowerCase().replace(/[ \-]/g, '_');
    return Object.prototype.hasOwnProperty.call(RATING_RANK, k) ? RATING_RANK[k] : null;
  }

  // Compare two prepared keys (number | string | null/''). null/'' ALWAYS sink to the
  // bottom in both directions; otherwise numbers compare numerically, strings by ja
  // locale, and `dir` ('asc'|'desc') flips only the non-null comparison.
  function compareKeys(a, b, dir) {
    var aNull = (a === null || a === undefined || a === '');
    var bNull = (b === null || b === undefined || b === '');
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    var cmp;
    if (typeof a === 'number' && typeof b === 'number') cmp = a - b;
    else cmp = String(a).localeCompare(String(b), 'ja');
    return dir === 'asc' ? cmp : -cmp;
  }

  // Stable sort of `rows` by `getKey(row)` in `dir`. Returns a NEW array; input is not
  // mutated (sorts an index array and ties break on original position).
  function sortRows(rows, getKey, dir) {
    var idx = rows.map(function (_, i) { return i; });
    idx.sort(function (i, j) {
      var c = compareKeys(getKey(rows[i]), getKey(rows[j]), dir);
      return c !== 0 ? c : i - j;
    });
    return idx.map(function (i) { return rows[i]; });
  }
</script>
```

- [ ] **Step 4: テストを実行し、合格を確認**

Run: `node --test tests/webapp/test_sortlib.mjs`
Expected: PASS（5 tests passed）

- [ ] **Step 5: コミット**

```bash
git add webapp/sortlib.html tests/webapp/test_sortlib.mjs
git commit -m "feat(webapp): 純粋ソートロジック sortlib を追加（Node 単体テスト付き）

並び替えの決定的部分（rating ランク化・null 末尾沈め・方向）を依存ゼロの
純関数に切り出し、ブラウザと Node テストで単一ソースとして共有する。"
```

---

## Task 2: `Code.gs` — `include()` + テンプレート評価 + `deleteRow()`

サーバ関数は clasp/実シートが必要でローカル自動テスト不可。実装の正しさは Task 6 の owner ブラウザ検証（特に行ずれ adversarial probe）で担保する。

**Files:**
- Modify: `webapp/Code.gs`（`doGet` 内 70-72 行付近、ファイル末尾 201 行付近）

- [ ] **Step 1: `doGet` の許可ブランチをテンプレート評価に変更**

`webapp/Code.gs` の以下を置換:

```javascript
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('保有・監視シート')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
```

を:

```javascript
  return HtmlService.createTemplateFromFile('index').evaluate()
    .setTitle('保有・監視シート')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
```

（拒否ブランチの `createHtmlOutput(...)` は変更しない。）

- [ ] **Step 2: `include()` ヘルパーを追加**

`webapp/Code.gs` の `function _sheet(tabName) {` の直前に追加:

```javascript
// Inlines another project file (e.g. sortlib.html) into a templated page via
// <?!= include('name'); ?>. Returns the file's raw content (no escaping).
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}
```

- [ ] **Step 3: `deleteRow()` を追加**

`webapp/Code.gs` の `function _coerce(v) {` の直前（`addRow` の後）に追加:

```javascript
/**
 * Deletes one row from a tab. Guards against deleting the wrong row when the sheet
 * shifted under the client (Track A/B or another session inserting/removing rows):
 * reads the row's CURRENT Ticker + 銘柄名 (display values) and refuses unless they
 * match `expected` = { ticker, name } that the client was looking at. Returns true on
 * success. Never returns or logs cell values (PII/ticker safety).
 */
function deleteRow(tabName, rowNum, expected) {
  _guard();
  var sh = _sheet(tabName);
  rowNum = parseInt(rowNum, 10);
  if (!(rowNum > HEADER_ROW)) throw new Error('無効な行番号です');
  if (rowNum > sh.getLastRow()) throw new Error('行が存在しません');

  var headerRow = _headerRow(sh);
  var tickerIdx = headerRow.indexOf(LABEL_TICKER);
  var nameIdx = headerRow.indexOf(LABEL_NAME);
  var cur = sh.getRange(rowNum, 1, 1, sh.getLastColumn()).getDisplayValues()[0];
  var curTicker = tickerIdx >= 0 ? String(cur[tickerIdx] || '').trim() : '';
  var curName = nameIdx >= 0 ? String(cur[nameIdx] || '').trim() : '';
  var expTicker = String((expected && expected.ticker) || '').trim();
  var expName = String((expected && expected.name) || '').trim();
  if (curTicker !== expTicker || curName !== expName) {
    throw new Error('行の内容が変わっています。再読み込みしてください');
  }

  sh.deleteRow(rowNum);
  return true;
}
```

- [ ] **Step 4: 構文確認（ローカルで実行可能な範囲）**

Run: `node --check webapp/Code.gs`
Expected: 出力なし・終了コード 0（構文エラーが無い）。
※ Apps Script の実行時挙動はローカル検証不可。Task 6 のブラウザ検証で担保する。

- [ ] **Step 5: コミット**

```bash
git add webapp/Code.gs
git commit -m "feat(webapp): deleteRow を追加し index をテンプレート化

deleteRow は削除直前に現在の Ticker+銘柄名 を expected と照合し、シートが
ずれていた場合は削除を拒否（誤削除防止）。戻り値は true のみでセル値は返さない。
include() と doGet のテンプレート評価で sortlib.html を取り込めるようにする。"
```

---

## Task 3: `index.html` — sortlib include + ソート state/ロジック + `state.view` 参照化

DOM/インライン JS はローカル自動テスト不可。Task 6 のブラウザ検証で担保する。

**Files:**
- Modify: `webapp/index.html`（287 行付近 / 382-383 行 / 669-680 行 / 796 行）

- [ ] **Step 1: メイン `<script>` の直前で sortlib を include**

`webapp/index.html` の `<script>`（メインスクリプト開始、287 行付近）の直前に追加:

```html
  <?!= include('sortlib'); ?>
```

（結果として sortlib の `<script>` がメインスクリプトより前に出力され、`ratingRank`/`compareKeys`/`sortRows` が先に定義される。）

- [ ] **Step 2: state にソート用フィールドを追加**

以下を置換:

```javascript
  var state = { tab: null, headers: [], rows: [], editing: null, original: {},
    holdingsTab: null, required: [], noteText: {} };
```

を:

```javascript
  var state = { tab: null, headers: [], rows: [], view: [], editing: null,
    original: {}, holdingsTab: null, required: [], noteText: {},
    sortKey: null, sortDir: 'desc' };
```

- [ ] **Step 3: ソートのカタログ・値取得・適用ロジックを追加**

`function render() {`（669 行付近）の直前に追加:

```javascript
  // Curated sortable columns. A header-based option appears only if its label is
  // present in the current tab's headers; derived options appear per tab type. Order
  // here is the menu order.
  var SORT_NUM = ['現在株価', '年初来安値との乖離率', 'PER', 'PBR', '配当利回り',
    '時価総額', '現在EPS', '年間EPS前年比（%）', 'アナリスト予想株価', '理論株価'];
  var HOLDINGS_DERIVED = ['評価額', '評価損益額', '評価損益率', '目標との乖離率'];
  var WATCH_DERIVED = ['購入検討との乖離率', '予想乖離率'];

  function sortOptions() {
    var present = {};
    state.headers.forEach(function (h) { present[h.label] = 1; });
    var opts = [{ key: '', label: 'シート順' }];
    if (present[ROLE.name]) opts.push({ key: ROLE.name, label: ROLE.name });
    SORT_NUM.forEach(function (l) { if (present[l]) opts.push({ key: l, label: l }); });
    if (present['レーティング']) opts.push({ key: 'レーティング', label: 'レーティング' });
    var isH = state.tab === state.holdingsTab;
    (isH ? HOLDINGS_DERIVED : WATCH_DERIVED).forEach(function (l) {
      opts.push({ key: l, label: l });
    });
    if (present[ROLE.updated]) opts.push({ key: ROLE.updated, label: ROLE.updated });
    return opts;
  }

  // Sortable value for one row under `key`: number | string | null. null sinks (see
  // compareKeys). Mirrors derivedMetrics formulas; division guards drop 0 denominators.
  function sortValue(row, key) {
    var byLabel = byLabelOf(state.headers, row.cells);
    function num(l) { return byLabel[l] ? parseNum(byLabel[l].val) : null; }
    var cur = num(ROLE.price);
    switch (key) {
      case '評価額': { var s = num(DERIVE.shares);
        return (cur != null && s != null) ? cur * s : null; }
      case '評価損益額': { var a = num(DERIVE.acquire), s2 = num(DERIVE.shares);
        return (cur != null && a != null && s2 != null) ? (cur - a) * s2 : null; }
      case '評価損益率': { var a2 = num(DERIVE.acquire);
        return (cur != null && a2) ? (cur - a2) / a2 * 100 : null; }
      case '目標との乖離率': { var t = num(DERIVE.targetSell);
        return (cur != null && t) ? (cur - t) / t * 100 : null; }
      case '購入検討との乖離率': { var my = num(DERIVE.myTarget);
        return (cur != null && my) ? (cur - my) / my * 100 : null; }
      case '予想乖離率': { var an = num(DERIVE.analyst);
        return (cur != null && an != null && cur) ? (an - cur) / cur * 100 : null; }
      case ROLE.name: { var nm = byLabel[ROLE.name] ?
        String(byLabel[ROLE.name].val == null ? '' : byLabel[ROLE.name].val).trim() : '';
        return nm || null; }
      case 'レーティング': return byLabel['レーティング'] ?
        ratingRank(byLabel['レーティング'].val) : null;
      case ROLE.updated: { var raw = byLabel[ROLE.updated] ?
        String(byLabel[ROLE.updated].val || '') : '';
        var d = Date.parse(raw.replace(/\//g, '-')); return isNaN(d) ? null : d; }
      default: return num(key);
    }
  }

  function applySort() {
    state.view = state.sortKey
      ? sortRows(state.rows, function (r) { return sortValue(r, state.sortKey); },
          state.sortDir)
      : state.rows.slice();
  }
```

- [ ] **Step 4: `render()` を `state.view` ベースに変更**

`render()` 冒頭の以下:

```javascript
  function render() {
    var H = state.headers;
    state.noteText = {};
    if (!state.rows.length) {
      $('list').innerHTML = '<div class="empty"><div class="ico">🗂️</div>' +
        '<div>表示できる銘柄がありません</div></div>';
      return;
    }
    var isHoldings = state.tab === state.holdingsTab;
    var out = isHoldings ? portfolioHtml() : '';

    state.rows.forEach(function (row, idx) {
```

を:

```javascript
  function render() {
    var H = state.headers;
    state.noteText = {};
    if (!state.rows.length) {
      $('list').innerHTML = '<div class="empty"><div class="ico">🗂️</div>' +
        '<div>表示できる銘柄がありません</div></div>';
      return;
    }
    applySort();
    var isHoldings = state.tab === state.holdingsTab;
    var out = isHoldings ? portfolioHtml() : '';

    state.view.forEach(function (row, idx) {
```

（`portfolioHtml()` は `state.rows` 集計のままで正しい。ソートは表示順のみに影響する。）

- [ ] **Step 5: `openEdit()` を `state.view` 参照に変更**

`function openEdit(idx) {` の以下:

```javascript
    var row = state.rows[idx];
```

を:

```javascript
    var row = state.view[idx];
```

- [ ] **Step 6: 構文確認**

Run: `node --check webapp/index.html`
Expected: HTML なので `node --check` は構文エラーを出す可能性がある（HTML 全体は JS ではない）。**このステップは実行せず**、Step 7 のブラウザ検証（Task 6）に委ねる。代わりにインライン JS の括弧対応を目視確認する。

※ 注: `node --check` は HTML ファイルに使えない。index.html の JS 検証は Task 6 のブラウザ実機で行う。

- [ ] **Step 7: コミット**

```bash
git add webapp/index.html
git commit -m "feat(webapp): 表示ソートの state/ロジックを追加し view 参照化

state.rows（シート順）を保持し、ソートはコピー state.view に対して実施。
render/openEdit を view 参照に変更（row.row は保持されるため削除の同定は不変）。"
```

---

## Task 4: `index.html` — ソート UI（select + 方向トグル）+ 配線 + CSS

**Files:**
- Modify: `webapp/index.html`（261 行 `.meta` / `selectTab` 449 行付近 / `load` 528 行付近 / イベント配線 883 行付近 / `<style>` 内）

- [ ] **Step 1: `.meta` にソート UI コンテナを追加**

以下を置換:

```html
    <div class="meta"><span id="count"></span><span id="hint"></span></div>
```

を:

```html
    <div class="meta"><span id="count"></span><span id="hint"></span>
      <span class="sortbox" id="sortbox" style="display:none">
        <span class="sort-ico">⇅</span>
        <select id="sortSel" aria-label="並び替える指標"></select>
        <button id="sortDir" class="dirbtn" type="button"
          aria-label="昇順と降順を切り替え">↓</button>
      </span>
    </div>
```

- [ ] **Step 2: `selectTab` でソートをリセットし、用語解説タブでは UI を隠す**

`function selectTab(tab, btn) {` の以下:

```javascript
  function selectTab(tab, btn) {
    if (state.tab === tab) return;
    state.tab = tab;
    [].forEach.call(document.querySelectorAll('.seg'), function (e) { e.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    $('addFab').classList.remove('show');
    if (tab === GLOSSARY_TAB) { renderGlossary(); return; }
    load();
  }
```

を:

```javascript
  function selectTab(tab, btn) {
    if (state.tab === tab) return;
    state.tab = tab;
    state.sortKey = null; state.sortDir = 'desc';
    [].forEach.call(document.querySelectorAll('.seg'), function (e) { e.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    $('addFab').classList.remove('show');
    if (tab === GLOSSARY_TAB) { $('sortbox').style.display = 'none'; renderGlossary(); return; }
    load();
  }
```

- [ ] **Step 3: `load()` 成功時にソート UI を構築・表示**

`function load() {` の成功ハンドラ:

```javascript
    google.script.run.withSuccessHandler(function (data) {
      state.headers = data.headers; state.rows = data.rows;
      render();
      $('count').textContent = data.rows.length + ' 銘柄';
      $('hint').textContent = '✎ は編集できる項目';
      $('addFab').classList.toggle('show', state.tab !== state.holdingsTab);
    }).withFailureHandler(fail).getRows(state.tab);
```

を:

```javascript
    google.script.run.withSuccessHandler(function (data) {
      state.headers = data.headers; state.rows = data.rows;
      buildSortUI();
      render();
      $('count').textContent = data.rows.length + ' 銘柄';
      $('hint').textContent = '✎ は編集できる項目';
      $('addFab').classList.toggle('show', state.tab !== state.holdingsTab);
    }).withFailureHandler(fail).getRows(state.tab);
```

- [ ] **Step 4: `buildSortUI()` を追加**

`function applySort() { ... }`（Task 3 Step 3 で追加）の直後に追加:

```javascript
  function buildSortUI() {
    var sel = $('sortSel');
    sel.innerHTML = sortOptions().map(function (o) {
      return '<option value="' + esc(o.key) + '">' + esc(o.label) + '</option>';
    }).join('');
    sel.value = state.sortKey || '';
    $('sortDir').textContent = state.sortDir === 'asc' ? '↑' : '↓';
    $('sortbox').style.display = '';
  }
```

- [ ] **Step 5: select / 方向トグルを配線**

イベント配線ブロック（`$('cancelBtn').onclick = closeSheet;` の付近、883 行付近）に追加:

```javascript
  $('sortSel').onchange = function () { state.sortKey = this.value || null; render(); };
  $('sortDir').onclick = function () {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    this.textContent = state.sortDir === 'asc' ? '↑' : '↓';
    render();
  };
```

- [ ] **Step 6: CSS を追加**

`<style>` 内、`.meta` ルールの近くに追加（既存 `.meta` の定義は変更しない）:

```css
    .sortbox { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; }
    .sort-ico { color: #9ca3af; font-size: 13px; }
    .sortbox select { font: inherit; font-size: 13px; color: #374151;
      background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
      padding: 4px 8px; max-width: 46vw; }
    .dirbtn { font: inherit; font-size: 14px; line-height: 1; color: #374151;
      background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
      padding: 5px 9px; cursor: pointer; }
    .dirbtn:active { background: #f3f4f6; }
```

- [ ] **Step 7: コミット**

```bash
git add webapp/index.html
git commit -m "feat(webapp): 指標ソート UI（指標選択＋昇降トグル）を追加

.meta にタブ別の厳選指標プルダウンと方向トグルを配置。データタブのみ表示し、
タブ切替でシート順にリセット。"
```

---

## Task 5: `index.html` — 削除 UI（2 段階確認）+ ハンドラ + CSS

**Files:**
- Modify: `webapp/index.html`（`.actions` 278-281 行 / `openEdit` 816 行付近 / `openAdd` 837 行付近 / `closeSheet` 846 行付近 / イベント配線 / `<style>`）

- [ ] **Step 1: 編集シートに削除ゾーンを追加**

以下（`.actions` ブロック）:

```html
    <div class="actions">
      <button class="btn" id="cancelBtn">キャンセル</button>
      <button class="btn primary" id="saveBtn">保存<span class="kbd">⌘⏎</span></button>
    </div>
  </div>
```

を:

```html
    <div class="actions">
      <button class="btn" id="cancelBtn">キャンセル</button>
      <button class="btn primary" id="saveBtn">保存<span class="kbd">⌘⏎</span></button>
    </div>
    <div class="danger" id="dangerZone">
      <div class="danger-div"></div>
      <button class="btn del" id="deleteBtn" type="button">この銘柄を削除</button>
    </div>
  </div>
```

- [ ] **Step 2: 削除の状態リセットと実行ハンドラを追加**

`function save() { ... }` の直後（876 行付近）に追加:

```javascript
  var delConfirm = false;
  function resetDelete() {
    delConfirm = false;
    var b = $('deleteBtn');
    b.disabled = false;
    b.classList.remove('confirm');
    b.textContent = 'この銘柄を削除';
  }
  function onDeleteClick() {
    var b = $('deleteBtn');
    if (!delConfirm) { // 1st tap: arm confirmation
      delConfirm = true;
      b.classList.add('confirm');
      b.textContent = 'この操作は取り消せません — 削除する';
      return;
    }
    // 2nd tap: execute. Identity = the sheet's CURRENT values captured at openEdit
    // (state.original), NOT live input, so it matches what the server re-reads.
    var tab = state.tab, rowNum = state.editing;
    var ident = { ticker: state.original[ROLE.ticker] || '',
                  name: state.original[ROLE.name] || '' };
    b.disabled = true; b.textContent = '削除中…';
    google.script.run.withSuccessHandler(function () {
      resetDelete(); closeSheet(); toast('削除しました'); load();
    }).withFailureHandler(function (e) {
      resetDelete(); closeSheet(); toast('削除に失敗: ' + errMsg(e)); load();
    }).deleteRow(tab, rowNum, ident);
  }
```

- [ ] **Step 3: `openEdit` で削除ゾーンを表示しリセット**

`function openEdit(idx) {` 内、`buildReference(byLabel);` の直前に追加:

```javascript
    $('dangerZone').style.display = 'block';
    resetDelete();
```

- [ ] **Step 4: `openAdd` で削除ゾーンを隠す**

`function openAdd() {` 内、`var form = $('formFields'); form.innerHTML = '';` の直前に追加:

```javascript
    $('dangerZone').style.display = 'none';
```

- [ ] **Step 5: `closeSheet` で削除確認をリセット**

`function closeSheet() {` の以下:

```javascript
  function closeSheet() {
    $('scrim').classList.remove('open'); $('sheet').classList.remove('open');
    $('formFields').removeEventListener('input', refreshProgress);
    state.editing = null;
  }
```

を:

```javascript
  function closeSheet() {
    $('scrim').classList.remove('open'); $('sheet').classList.remove('open');
    $('formFields').removeEventListener('input', refreshProgress);
    resetDelete();
    state.editing = null;
  }
```

- [ ] **Step 6: 削除ボタンを配線**

イベント配線ブロック（`$('saveBtn').onclick = save;` の付近）に追加:

```javascript
  $('deleteBtn').onclick = onDeleteClick;
```

- [ ] **Step 7: CSS を追加**

`<style>` 内、`.actions` ルールの近くに追加:

```css
    .danger { margin-top: 4px; }
    .danger-div { height: 1px; background: #f0f0f0; margin: 4px 0 12px; }
    .btn.del { width: 100%; color: var(--neg); border: 1px solid #f3c0c0;
      background: #fff; }
    .btn.del:active { background: #fff5f5; }
    .btn.del.confirm { color: #fff; background: var(--neg); border-color: var(--neg); }
    .btn.del:disabled { opacity: .6; }
```

- [ ] **Step 8: コミット**

```bash
git add webapp/index.html
git commit -m "feat(webapp): 行削除 UI（2 段階確認）とハンドラを追加

編集シート内に削除ボタンを配置し、1 回目タップで確認状態に切替、2 回目で
deleteRow を呼ぶ。同定値は state.original（シート現在値）を送る。新規登録
モードでは非表示。成功/失敗いずれも load() で再同期する。"
```

---

## Task 6: 検証（自動 + owner ブラウザ）+ push ゲート

**Files:**
- 変更なし（検証のみ）

- [ ] **Step 1: Node 単体テスト（ソートロジック）**

Run: `node --test tests/webapp/test_sortlib.mjs`
Expected: PASS（5 tests）

- [ ] **Step 2: 既存 Python テストの回帰確認**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: 26 tests OK（webapp 変更は Python に影響しないことを確認）

- [ ] **Step 3: Code.gs 構文確認**

Run: `node --check webapp/Code.gs`
Expected: 終了コード 0（出力なし）

- [ ] **Step 4: owner ブラウザ手動検証チェックリスト**

ローカルに clasp が無いため、検証は owner が clasp/デプロイ環境（またはテスト用デプロイ）で実施する。以下を確認:

- golden path（ソート）: 各データタブで指標を選択 → カードが即時に並び替わる。方向トグルで昇降が反転する。「シート順」で元の順序に戻る。
- null 末尾: 値が「確認不可」「赤字」「空」の銘柄は、昇順・降順いずれでも常に末尾に並ぶ。
- タブ切替: タブを変えるとソートが「シート順」にリセットされ、プルダウンの選択肢がそのタブの指標に切り替わる。用語解説タブではソート UI が消える。
- golden path（削除）: 銘柄カードの「編集」→「この銘柄を削除」→「削除する」で、Google Sheet の**該当行が消える**。アプリのリストからも消える。
- 削除の同定（ソート併用）: ソートで並び替えた状態で削除しても、**選んだ銘柄＝シート上で消える行が一致**する（行ずれが起きない）。
- 2 段階確認: 1 回目タップでは削除されず文言が変わるだけ。シートを閉じて再度開くと「この銘柄を削除」に戻っている（誤タップ防止）。
- 新規登録モード: 「銘柄を追加」FAB から開いたシートには削除ボタンが出ない。

- [ ] **Step 5: adversarial probe（行ずれ＝誤削除防止の核）**

owner が以下を実施:

1. アプリで監視タブの 1 銘柄の「編集」を開く（シートは開いたまま）。
2. その状態で Google Sheet 側で同じ行の 銘柄名 を直接書き換える（または上に 1 行挿入して行をずらす）。
3. アプリで「この銘柄を削除」→「削除する」を押す。
4. Expected: 「削除に失敗: 行の内容が変わっています。再読み込みしてください」とトーストが出て**何も削除されない**。その後リストが再読み込みされる。

境界値（任意・コードレビューで確認可）: `deleteRow` は `rowNum <= HEADER_ROW` と `rowNum > getLastRow()` を例外で弾く。

- [ ] **Step 6: push ゲート（本番デプロイ）**

全自動テスト PASS かつ owner ブラウザ検証 OK を確認後、**ユーザーに push の可否を確認する**。承認後のみ:

```bash
git push origin main
```

`webapp/**` の push で `deploy-webapp.yml` が本番 clasp デプロイを実行する。push 前に `git log --oneline` で Task 1-5 の 5 コミットが揃っていることを確認する。

---

## Self-Review

**1. Spec coverage（設計書の各要件 → タスク対応）:**
- 削除バックエンド `deleteRow`（範囲制約・staleness ガード・true のみ返す・認可）→ Task 2 Step 3 ✓
- 削除フロント（編集シート内のみ・新規時非表示・2 段階確認・成功/失敗で load）→ Task 5 ✓
- ソート（クライアント表示のみ・state.view コピー・row.row 保持・render/openEdit/削除が view 参照）→ Task 3 ✓
- ソート UI（.meta に select+方向・データタブのみ・タブ切替でリセット・load 後再適用）→ Task 4 ✓
- 厳選指標（共通＋保有派生＋監視派生、ヘッダ存在で動的フィルタ）→ Task 3 Step 3（`SORT_NUM`/`HOLDINGS_DERIVED`/`WATCH_DERIVED`/`sortOptions`）✓
- 非数値セルは末尾沈め → Task 1（`compareKeys` null 分岐）+ Task 3（`sortValue` が null 返却）✓
- レーティングランク `strong_buy=5..sell=1` → Task 1（`RATING_RANK`/`ratingRank`）✓
- `<!DOCTYPE html>` 1 行目維持 → どのタスクも 1 行目を変更しない（include は `<script>` 直前に挿入）✓
- セル値ログ/返却なし → Task 2 `deleteRow` は true のみ ✓
- push は owner 検証後にゲート → Task 6 Step 6 ✓
- 非対象（一括削除/undo/永続ソート/複合キー）→ 計画に含めず ✓

**2. Placeholder scan:** 「TBD/TODO/後で」「適切なエラー処理を追加」等は無し。各コードステップは実コードを含む。✓

**3. Type/signature consistency:**
- `sortRows(rows, getKey, dir)` / `compareKeys(a,b,dir)` / `ratingRank(v)` — Task 1 定義と Task 3 呼び出しで一致 ✓
- `applySort` は引数なし・`state.view` を更新。`render`/`openEdit` は `state.view[idx]` を参照 ✓
- `deleteRow(tabName, rowNum, expected)`（Code.gs）と呼び出し `deleteRow(tab, rowNum, ident)`（index.html）でシグネチャ一致。`ident = {ticker, name}` と `expected.{ticker,name}` 一致 ✓
- `buildSortUI`/`sortOptions`/`sortValue`/`resetDelete`/`onDeleteClick` — 定義箇所と配線箇所で名称一致 ✓
- ヘッダラベルは `config.yaml` 実値（`年間EPS前年比（%）`、`現在EPS`、`アナリスト予想株価` 等）に一致 ✓

**既知の検証限界（正直な明示）:** Apps Script サーバ関数（`deleteRow`/`doGet` テンプレート化）と index.html の DOM 配線はローカルに clasp が無く自動テスト不可。これらは Task 6 の owner ブラウザ検証（特に Step 5 の行ずれ probe）で担保する。自動テストは Task 1 の純粋ソートロジックに限定される。
