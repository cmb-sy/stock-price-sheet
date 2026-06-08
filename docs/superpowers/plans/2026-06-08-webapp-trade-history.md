# 売買履歴（Trade History）Webアプリ入力・編集機能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** オーナーの過去の売買記録と理由を Web アプリから入力・編集できる「売買履歴」タブを追加し、将来 AI が分析できる取引台帳を整える。

**Architecture:** 既存の Apps Script webapp（`webapp/Code.gs` バックエンド + `webapp/index.html` SPA + `webapp/sortlib.html` インライン純関数パーシャル）に、保有/監視の二値モデルとは異なる第3のタブ種別「売買履歴」を `isHistoryTab()` による限定分岐で追加する。バックエンドはタブ自動作成と `deleteRow` の identity 一般化（同一銘柄の複数取引でも誤削除しない）を行う。

**Tech Stack:** Google Apps Script（`.gs` server）, HtmlService テンプレート（`<?!= include() ?>`）, Vanilla JS（ES5 互換、`var`/`function`）, Node `node:test`/`node:vm`（sortlib 純関数の単体テスト）, Python `unittest`（価格エンジン回帰）。

---

## 検証モデル（重要 — このプロジェクト固有の制約）

この webapp はローカルで完全には実行できない（clasp/ブラウザ無し環境）。したがって本計画の検証は以下の多層構成を取る。各実装タスクで「失敗するテスト → 実装 → green」の古典的 TDD が成立するのは **純関数を抽出する Task 3 のみ**。それ以外のタスクは Apps Script ランタイム/DOM に依存するため、ローカル検証は **構文チェック + 静的レビュー**、ランタイム確証は **デプロイ後のオーナー手動チェック** に委ねる。これは推測ではなく、このプロジェクトで確立済みの検証方針である。

- **Node 単体テスト（runnable）**: `webapp/sortlib.html` の純関数のみ。`node --test tests/webapp/test_sortlib.mjs`。
- **構文チェック**:
  - `Code.gs`: `node --check` は `.gs` 拡張子を拒否するため、一時 `.js` にコピーしてチェック。
  - `index.html`: 配信ドキュメントを再構成（`<?!= include('sortlib'); ?>` を `sortlib.html` 本体でインライン化 → 全 `<script>` 本文を連結 → 一時 `.js` に書き出し → `node --check`）。
- **Python 回帰**: `.venv/bin/python -m unittest discover -s tests`（既存26件）。売買履歴は `config.yaml` 非対象なので価格エンジンに影響しないことを確認。
- **静的 adversarial レビュー**: 安全クリティカルな `deleteRow` の identity 一般化を、同一銘柄2取引のシナリオでコード上トレースして誤削除拒否を確認（Task 9）。
- **オーナー手動チェック**: デプロイ後のブラウザ動作確認（Task 9）。

---

## File Structure

| ファイル | 役割 | 本計画での変更 |
|----------|------|----------------|
| `webapp/Code.gs` | サーバ（タブ解決・読み書き・削除ガード） | TABS 追加・`HISTORY_*` 定数・`_sheet` 自動作成・`deleteRow` identity 一般化 |
| `webapp/sortlib.html` | DOM/google 非依存の純関数（単体テスト対象の単一ソース） | `isPositiveNumberStr` 追加 |
| `webapp/index.html` | SPA（描画・編集 UI・ソート） | `isHistoryTab` 分岐群・select 入力・売買区分バッジ・日付ソート・新規追加/削除 identity・バリデーション・CSS |
| `tests/webapp/test_sortlib.mjs` | sortlib 単体テスト | `isPositiveNumberStr` のテスト追加 |

---

## Task 1: Code.gs — 売買履歴タブの登録とオンデマンド自動作成

**Files:**
- Modify: `webapp/Code.gs:27`（TABS）, `webapp/Code.gs:35-39`（MANUAL_HEADERS）, `webapp/Code.gs:81-86`（_sheet）

- [ ] **Step 1: TABS の末尾に売買履歴を追加**

`webapp/Code.gs:27` を置換:

```javascript
var TABS = ['保有銘柄', '監視-JP', '監視-US', '売買履歴'];
```

末尾に追加する理由: `index.html` の `state.holdingsTab = tabs[0]`（= 保有銘柄）が先頭である前提に依存しているため、先頭を変えると holdings 判定が壊れる。

- [ ] **Step 2: MANUAL_HEADERS に売買履歴の編集可能列を追加**

`webapp/Code.gs:35-39` の `MANUAL_HEADERS` を置換:

```javascript
var MANUAL_HEADERS = {
  '保有銘柄': ['銘柄名', '想定保有期間', '目標売却株価', '取得株価', '取得株数', '株主優待', '購入理由', 'Ticker'],
  '監視-JP': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker'],
  '監視-US': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker'],
  '売買履歴': ['日付', '銘柄名', 'Ticker', '売買区分', '約定単価', '株数', '理由']
};
```

`AI分析コメント` は MANUAL_HEADERS に **含めない**（= 読み取り専用。`_resolveManualCol` が書き込みを拒否する）。

- [ ] **Step 3: 売買履歴の正規ヘッダ定数を追加**

`webapp/Code.gs:39`（MANUAL_HEADERS の閉じ括弧）の直後に追加:

```javascript

// 売買履歴タブはオーナーが手動作成しなくてよいよう、初回アクセス時に自動生成する
// （_sheet 参照）。下記はその正規ヘッダ行（順序固定）。末尾の AI分析コメントは
// 読み取り専用（MANUAL_HEADERS 非掲載）で、将来の Track B スキル用に確保する。
// 汎用ラベルのみ — ティッカー/価格/PII は一切含めない。
var HISTORY_TAB = '売買履歴';
var HISTORY_HEADERS = ['日付', '銘柄名', 'Ticker', '売買区分', '約定単価', '株数', '理由', 'AI分析コメント'];
```

- [ ] **Step 4: _sheet を自動作成対応に書き換え**

`webapp/Code.gs:81-86` の `_sheet` を置換:

```javascript
function _sheet(tabName) {
  if (TABS.indexOf(tabName) < 0) throw new Error('不明なタブです');
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName(tabName);
  if (!sh) {
    // 売買履歴タブのみ、無ければ正規ヘッダ付きで自動作成する（冪等: 既存タブは
    // 上書きしない）。他タブが無いのは従来どおりエラー。単一オーナー運用のため
    // 競合作成の懸念は実質ない。
    if (tabName !== HISTORY_TAB) throw new Error('タブが見つかりません');
    sh = ss.insertSheet(HISTORY_TAB);
    sh.getRange(HEADER_ROW, 1, 1, HISTORY_HEADERS.length).setValues([HISTORY_HEADERS]);
  }
  return sh;
}
```

- [ ] **Step 5: Code.gs の構文チェック**

Run:
```bash
cp webapp/Code.gs /tmp/th_code.js && node --check /tmp/th_code.js && echo "Code.gs OK"
```
Expected: `Code.gs OK`（構文エラーなし）

- [ ] **Step 6: Commit**

```bash
git add webapp/Code.gs
git commit -m "feat(webapp): register 売買履歴 tab and auto-create it on first read

保有銘柄を先頭に保ったまま TABS 末尾へ追加し holdings 判定を不変に保つ。
オーナーが手動でタブを作らなくても初回アクセスで正規ヘッダ付き生成。"
```

---

## Task 2: Code.gs — deleteRow の identity を全 editable 列へ一般化（誤削除バグ修正）

**背景:** 現状の `deleteRow(tabName, rowNum, expected)` は `expected = {ticker, name}` で行を同定する。売買履歴は同一銘柄を複数回取引するため Ticker+銘柄名 では一意にならず、行シフト時に誤った行を削除し得る。`expected` を「全 editable 列の表示値マップ」に一般化する。

**Files:**
- Modify: `webapp/Code.gs:205-229`（deleteRow）

- [ ] **Step 1: deleteRow を書き換え**

`webapp/Code.gs:205-229` の `deleteRow` 全体を置換:

```javascript
function deleteRow(tabName, rowNum, expected) {
  _guard();
  var manual = MANUAL_HEADERS[tabName] || [];
  var sh = _sheet(tabName);
  rowNum = parseInt(rowNum, 10);
  if (!(rowNum > HEADER_ROW)) throw new Error('無効な行番号です');
  if (rowNum > sh.getLastRow()) throw new Error('行が存在しません');

  // Staleness guard: クライアントは見ていた行の editable 列の表示値を expected として
  // 送る。サーバは今の行を読み直し、全 expected 値が一致しなければ削除を拒否する。
  // これにより Track A/B や別セッションの行挿入/削除で行がずれていても、古い行番号で
  // 誤って削除しない。{ticker,name} から一般化した理由: 取引台帳は同じ ticker+name が
  // 複数行に現れるため、identity は全 editable 列のタプルでないと一意にならない。
  // セルの値はログ・戻り値に一切含めない（PII/ティッカー保護）。
  var keys = expected ? Object.keys(expected) : [];
  if (!keys.length) throw new Error('削除対象の identity がありません');
  var headerRow = _headerRow(sh);
  var cur = sh.getRange(rowNum, 1, 1, sh.getLastColumn()).getDisplayValues()[0];
  for (var i = 0; i < keys.length; i++) {
    var label = keys[i];
    // editable（manual）列のみが identity キーとして有効。機械更新列は我々の知らぬ間に
    // 変わり得るので削除判定に使わない（クライアントは editable 列のみ送る想定）。
    if (manual.indexOf(label) < 0) throw new Error('削除 identity が不正です');
    var col = headerRow.indexOf(label);
    var curVal = col >= 0 ? String(cur[col] || '').trim() : '';
    var expVal = String(expected[label] == null ? '' : expected[label]).trim();
    if (curVal !== expVal) {
      throw new Error('行の内容が変わっています。再読み込みしてください');
    }
  }

  sh.deleteRow(rowNum);
  return true;
}
```

ヘッダに存在しないキーは `curVal = ''` として突き合わせる（実値と一致しなければミスマッチ → 安全側に削除拒否）。設計どおりミスマッチ経路に一本化している。

- [ ] **Step 2: Code.gs の構文チェック**

Run:
```bash
cp webapp/Code.gs /tmp/th_code.js && node --check /tmp/th_code.js && echo "Code.gs OK"
```
Expected: `Code.gs OK`

- [ ] **Step 3: Commit**

```bash
git add webapp/Code.gs
git commit -m "fix(webapp): generalize deleteRow identity to all editable columns

取引台帳は同じ ticker+name が複数行に現れ {ticker,name} では一意にならない。
行シフト時の誤削除を防ぐため identity を全 editable 列の表示値タプルに一般化。"
```

---

## Task 3: sortlib.html — 正の数バリデータ `isPositiveNumberStr`（TDD）

**目的:** 約定単価/株数の「正の数」検証を、DOM 非依存の純関数として `sortlib.html` に置き、Node で単体テストする（このプロジェクトで唯一ローカル実行可能な red-green TDD タスク）。`index.html` 側の `numericFieldError`（Task 7）がこれを使う。既存の `parseNum` は表示/計算用の寛容なパーサで役割が異なるため、検証専用の本関数を別に持つ。

**Files:**
- Modify: `webapp/sortlib.html:39`（sortRows の後、`</script>` の前）
- Test: `tests/webapp/test_sortlib.mjs`

- [ ] **Step 1: 失敗するテストを追加**

`tests/webapp/test_sortlib.mjs` の `const { ratingRank, compareKeys, sortRows } = ctx;` を以下に置換:

```javascript
const { ratingRank, compareKeys, sortRows, isPositiveNumberStr } = ctx;
```

ファイル末尾（最後の `});` の後）に追加:

```javascript

test('isPositiveNumberStr: positive numbers (incl. comma/yen formatting) are valid', () => {
  assert.equal(isPositiveNumberStr('1200'), true);
  assert.equal(isPositiveNumberStr('1,200'), true);
  assert.equal(isPositiveNumberStr('¥1,200'), true);
  assert.equal(isPositiveNumberStr('12.5'), true);
  assert.equal(isPositiveNumberStr(1200), true);
});

test('isPositiveNumberStr: zero, negative, empty, and non-numeric are invalid', () => {
  assert.equal(isPositiveNumberStr('0'), false);
  assert.equal(isPositiveNumberStr('-5'), false);
  assert.equal(isPositiveNumberStr(''), false);
  assert.equal(isPositiveNumberStr('   '), false);
  assert.equal(isPositiveNumberStr('abc'), false);
  assert.equal(isPositiveNumberStr('-'), false);
  assert.equal(isPositiveNumberStr('.'), false);
  assert.equal(isPositiveNumberStr(null), false);
  assert.equal(isPositiveNumberStr(undefined), false);
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run:
```bash
node --test tests/webapp/test_sortlib.mjs
```
Expected: FAIL（`isPositiveNumberStr is not a function` 系で新規2テストが落ちる。既存5テストは pass）

- [ ] **Step 3: 最小実装を追加**

`webapp/sortlib.html:39`（`sortRows` 関数の閉じ `}` の後、`</script>`(40行目) の前）に追加:

```javascript

  // 文字列/数値が「正の数」かを判定する検証専用述語（DOM/google 非依存）。カンマや
  // ¥ などの装飾を除去して解釈し、空・非数値・0・負数は false。約定単価/株数の入力
  // バリデーションに使う（index.html の numericFieldError）。表示/計算用の寛容な
  // parseNum とは役割が異なるため別関数として持つ。
  function isPositiveNumberStr(v) {
    var s = String(v == null ? '' : v).replace(/[^0-9.\-]/g, '');
    if (s === '' || s === '-' || s === '.') return false;
    var n = parseFloat(s);
    return !isNaN(n) && n > 0;
  }
```

- [ ] **Step 4: テストを実行して green を確認**

Run:
```bash
node --test tests/webapp/test_sortlib.mjs
```
Expected: PASS（7テスト全て pass）

- [ ] **Step 5: Commit**

```bash
git add webapp/sortlib.html tests/webapp/test_sortlib.mjs
git commit -m "feat(webapp): add isPositiveNumberStr pure validator with unit tests

約定単価/株数の正数バリデーションを DOM 非依存の純関数として sortlib に置き
Node でテスト可能にする。index.html の入力検証から再利用する。"
```

---

## Task 4: index.html — 売買履歴の定数・NOTES・select 入力・CSS

**Files:**
- Modify: `webapp/index.html:331-345`（NOTES/LONG_EDIT/HELP）, 直後に履歴定数ブロック追加, `webapp/index.html:584-591`（fieldHtml）, `webapp/index.html:89-91`（.pill CSS）, `webapp/index.html:224-228`（.fld input CSS）

- [ ] **Step 1: NOTES に「理由」を追加**

`webapp/index.html:331-336` の `NOTES` を置換:

```javascript
  var NOTES = [
    { label: '購入検討理由', man: true },
    { label: '購入理由',     man: true },
    { label: '理由',         man: true },
    { label: 'AIコメント',   man: false, ai: true },
    { label: 'AI分析コメント', man: false, ai: true }
  ];
```

- [ ] **Step 2: LONG_EDIT に「理由」を追加**

`webapp/index.html:337` を置換:

```javascript
  var LONG_EDIT = ['購入検討理由', '購入理由', '理由'];
```

- [ ] **Step 3: HELP に売買履歴の項目ヘルプを追加**

`webapp/index.html:339-345` の `HELP` を置換:

```javascript
  var HELP = {
    '銘柄名': '正式名称', 'Ticker': 'yfinance 形式（例 7203.T, AAPL）',
    '購入検討株価': '狙う購入価格', '購入検討理由': '検討の根拠をメモ',
    '目標売却株価': '売却の目標価格', '取得株価': '購入時の株価', '取得株数': '保有株数',
    '想定保有期間': '短期 / 中期 / 長期 など', '株主優待': '優待の内容',
    '購入理由': '購入の根拠をメモ',
    '日付': '取引日（例 2026-06-08）', '売買区分': '買い / 売り',
    '約定単価': '約定した1株の価格', '株数': '約定した株数',
    '理由': '売買の根拠をメモ（AI 分析の材料）'
  };
```

- [ ] **Step 4: 売買履歴の定数ブロックを追加**

`webapp/index.html:345`（HELP の閉じ `};`）の直後、`// Client-only "glossary" tab.`（347行目）の前に追加:

```javascript

  // ---- trade-history (売買履歴) tab ----
  // 保有でも監視でもない第3のタブ種別 = 取引台帳。以降の分岐は isHistoryTab() で切替。
  var HISTORY_TAB = '売買履歴';
  var BUY_SELL = '売買区分';
  function isHistoryTab() { return state.tab === HISTORY_TAB; }
  // 列挙型 editable フィールドの <select> 選択肢（label -> options）。
  var SELECT_OPTS = { '売買区分': ['買い', '売り'] };
  // 入力時に「正の数」を要求する editable 列（Task 7 の numericFieldError が使用）。
  var POSITIVE_NUM_FIELDS = ['約定単価', '株数'];
```

`isHistoryTab` は実行時にしか呼ばれず、その時点で `state`（410行目で宣言）は初期化済みなので定義順の問題はない。

- [ ] **Step 5: fieldHtml を select 対応に書き換え**

`webapp/index.html:584-591` の `fieldHtml` を置換:

```javascript
  function fieldHtml(label, val, required) {
    var help = HELP[label] ? '<div class="help">' + esc(HELP[label]) + '</div>' : '';
    var req = required ? ' <span class="req">*</span>' : '';
    var lab = '<label>✎ ' + esc(label) + req + '</label>' + help;
    if (SELECT_OPTS[label]) {
      var cur = String(val == null ? '' : val).trim();
      var opts = '<option value=""></option>' + SELECT_OPTS[label].map(function (o) {
        return '<option value="' + esc(o) + '"' + (o === cur ? ' selected' : '') +
          '>' + esc(o) + '</option>';
      }).join('');
      return lab + '<select data-h="' + esc(label) + '">' + opts + '</select>';
    }
    var isLong = LONG_EDIT.indexOf(label) >= 0;
    return lab + (isLong
      ? '<textarea data-h="' + esc(label) + '">' + esc(val) + '</textarea>'
      : '<input data-h="' + esc(label) + '" value="' + esc(val) + '">');
  }
```

`<select>` も `data-h` を持つので、保存時の `document.querySelectorAll('[data-h]')` 収集にそのまま乗る（`el.value` が選択値）。

- [ ] **Step 6: .pill.buy / .pill.sell の CSS を追加**

`webapp/index.html:91`（`.pill.watch { ... }`）の直後に追加:

```css
    .pill.buy { background: #e7f6ef; color: var(--pos); }
    .pill.sell { background: #fdecea; color: var(--neg); }
```

- [ ] **Step 7: .fld の select スタイルを追加**

`webapp/index.html:224-228` を置換:

```css
    .fld input, .fld textarea, .fld select { width: 100%; padding: 11px 12px;
      border: 1px solid var(--line); border-radius: 12px; font: inherit; font-size: 15px;
      background: #fafafa; transition: .15s; }
    .fld input:focus, .fld textarea:focus, .fld select:focus { outline: none;
      border-color: var(--accent); background: #fff; box-shadow: 0 0 0 3px var(--accent-soft); }
```

- [ ] **Step 8: index.html 配信JSの構文チェック**

Run:
```bash
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK"
```
Expected: `index.html served JS OK`

- [ ] **Step 9: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): add trade-history constants, 理由 note, select field, CSS

isHistoryTab/SELECT_OPTS/POSITIVE_NUM_FIELDS を導入し、理由を長文ノート化、
fieldHtml に select 対応、売買区分バッジと select のスタイルを追加。"
```

---

## Task 5: index.html — カードの売買区分バッジとチップ抑制

**Files:**
- Modify: `webapp/index.html:786-799`（render のピル生成）, `webapp/index.html:651-662`（columnMetrics）

- [ ] **Step 1: render のカード冒頭でピルをタブ種別ごとに分岐**

`webapp/index.html:786-799` を確認すると、`state.view.forEach(function (row, idx) {` の中で `var c = '<div class="card">...` の直前に `name/ticker/price/stamp/ch` を組み立てている。`webapp/index.html:793-799` の以下のブロック:

```javascript
      var ch = firstChar(name || ticker || '?');
      var c = '<div class="card"><div class="card-top">';
      c += '<div class="avatar">' + esc(ch) + '</div>';
      c += '<div class="top-mid"><div class="name-row">' +
        '<span class="name">' + esc(name || '(名称未設定)') + '</span>' +
        '<span class="pill' + (isHoldings ? '' : ' watch') + '">' +
        (isHoldings ? '保有' : '監視') + '</span></div>';
```

を次に置換:

```javascript
      var ch = firstChar(name || ticker || '?');
      // ピル: 保有/監視は種別ラベル、売買履歴は売買区分（買い=緑 / 売り=赤）。
      var pillCls, pillTxt;
      if (isHistoryTab()) {
        var bs = byLabel[BUY_SELL] ?
          String(byLabel[BUY_SELL].val == null ? '' : byLabel[BUY_SELL].val).trim() : '';
        pillTxt = bs || '—';
        pillCls = bs === '売り' ? ' sell' : ' buy';
      } else {
        pillTxt = isHoldings ? '保有' : '監視';
        pillCls = isHoldings ? '' : ' watch';
      }
      var c = '<div class="card"><div class="card-top">';
      c += '<div class="avatar">' + esc(ch) + '</div>';
      c += '<div class="top-mid"><div class="name-row">' +
        '<span class="name">' + esc(name || '(名称未設定)') + '</span>' +
        '<span class="pill' + pillCls + '">' + esc(pillTxt) + '</span></div>';
```

- [ ] **Step 2: columnMetrics で売買履歴の売買区分チップを抑制**

`webapp/index.html:656` の `if (SUPPRESS[label] || noteOf(label)) return;` の直後に1行追加:

```javascript
      if (isHistoryTab() && label === BUY_SELL) return; // バッジで表示するのでチップ重複を抑止
```

（日付/約定単価/株数 はチップとして表示され、理由は NOTES に回り、Ticker/銘柄名 は ROLE 扱いで除外される。追加抑制が要るのは 売買区分 のみ。）

- [ ] **Step 3: index.html 配信JSの構文チェック**

Run:
```bash
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK"
```
Expected: `index.html served JS OK`

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): render 売買区分 badge and suppress its chip on history cards

履歴カードのピルを保有/監視ラベルから売買区分（買い=緑/売り=赤）に分岐し、
本文側の売買区分チップ重複を抑止。"
```

---

## Task 6: index.html — ソート（シート順廃止・全タブ既定キー・売買履歴の候補/日付キー）

**Files:**
- Modify: `webapp/index.html:556-567`（load）, `webapp/index.html:709-722`（sortOptions）, `webapp/index.html:726-753`（sortValue）

**背景:** ユーザー要望により「シート順」（未ソート）選択肢を全タブから廃止する。これにより `sortKey=null`（未ソート）状態が選択肢に対応しなくなるため、各タブが load 時に必ず既定キーで整列するようにする。既定は **売買履歴=日付降順**（新しい取引が上）、**保有/監視=銘柄名昇順**（中立で決定的・ソート候補の先頭と一致）。

- [ ] **Step 1: 全タブで load 時に既定ソートキーを適用する**

`webapp/index.html:559-562` の load 成功ハンドラ:

```javascript
    google.script.run.withSuccessHandler(function (data) {
      state.headers = data.headers; state.rows = data.rows;
      buildSortUI();
      render();
```

を次に置換:

```javascript
    google.script.run.withSuccessHandler(function (data) {
      state.headers = data.headers; state.rows = data.rows;
      // シート順（未ソート）選択肢を廃止したため、各タブは必ず既定キーで整列させる。
      // 売買履歴は日付降順（新しい取引が上）、保有/監視は銘柄名昇順（中立で決定的）。
      // selectTab が sortKey=null にリセットするので、タブ切替ごとにこの既定が適用される。
      // ユーザーが他キーを選んだ後の再読込（load 再実行）ではその選択を尊重する。
      if (!state.sortKey) {
        var ds = isHistoryTab() ? { key: '日付', dir: 'desc' } : { key: ROLE.name, dir: 'asc' };
        state.sortKey = ds.key; state.sortDir = ds.dir;
      }
      buildSortUI();
      render();
```

- [ ] **Step 2: sortOptions からシート順を廃止し売買履歴分岐を追加**

`webapp/index.html:709-722` の `sortOptions` を置換（先頭の `{ key: '', label: 'シート順' }` を削除し、空配列から開始する）:

```javascript
  function sortOptions() {
    var present = {};
    state.headers.forEach(function (h) { present[h.label] = 1; });
    var opts = [];
    if (isHistoryTab()) {
      ['日付', '約定単価', '株数', ROLE.name].forEach(function (l) {
        if (present[l]) opts.push({ key: l, label: l });
      });
      return opts;
    }
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
```

- [ ] **Step 3: sortValue に日付ケースを追加**

`webapp/index.html:748-751` の `case ROLE.updated:` ブロックと `default:` の間に日付ケースを追加する。`webapp/index.html:748-752`:

```javascript
      case ROLE.updated: { var raw = byLabel[ROLE.updated] ?
        String(byLabel[ROLE.updated].val || '') : '';
        var d = Date.parse(raw.replace(/\//g, '-')); return isNaN(d) ? null : d; }
      default: return num(key);
    }
  }
```

を次に置換:

```javascript
      case ROLE.updated: { var raw = byLabel[ROLE.updated] ?
        String(byLabel[ROLE.updated].val || '') : '';
        var d = Date.parse(raw.replace(/\//g, '-')); return isNaN(d) ? null : d; }
      case '日付': { var draw = byLabel['日付'] ?
        String(byLabel['日付'].val || '') : '';
        var dd = Date.parse(draw.replace(/\//g, '-')); return isNaN(dd) ? null : dd; }
      default: return num(key);
    }
  }
```

約定単価/株数 は `default: return num(key);`（parseNum）で数値ソートされる。

- [ ] **Step 4: index.html 配信JSの構文チェック + sortlib 回帰**

Run:
```bash
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK" && node --test tests/webapp/test_sortlib.mjs
```
Expected: `index.html served JS OK` + sortlib 7テスト全 pass

- [ ] **Step 5: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): add trade-history sort (date/price/shares/name, date-desc default)

売買履歴のソート候補と日付キー(Date.parse)を追加し、既定を日付降順に。"
```

---

## Task 7: index.html — 新規追加の売買履歴分岐とバリデーション

**Files:**
- Modify: `webapp/index.html:929-949`（openAdd）, `webapp/index.html:962-973`（saveNew）, `webapp/index.html:975-986`（save）, `webapp/index.html:961`（closeSheet の後に numericFieldError 追加）

- [ ] **Step 1: openAdd を売買履歴対応に書き換え**

`webapp/index.html:929-949` の `openAdd` を置換:

```javascript
  function openAdd() {
    state.editing = 'new'; state.original = {};
    state.required = isHistoryTab()
      ? ['日付', ROLE.name, BUY_SELL, '約定単価', '株数']
      : [ROLE.name];
    $('eyebrow').textContent = '新規登録';
    var addLabel = isHistoryTab() ? ' <small>に取引を追加</small>' : ' <small>に銘柄を追加</small>';
    $('sheetTitle').innerHTML = esc(state.tab) + addLabel;
    $('dangerZone').style.display = 'none';
    var form = $('formFields'); form.innerHTML = '';
    state.headers.forEach(function (h) {
      if (!h.editable) return;
      // 売買履歴は Ticker を手入力する（自動解決しない）。他タブは register-ticker
      // スキルが後で埋めるため Ticker 入力を隠す。
      if (h.label === ROLE.ticker && !isHistoryTab()) return;
      var wrap = document.createElement('div');
      wrap.className = 'fld';
      wrap.innerHTML = fieldHtml(h.label, '', state.required.indexOf(h.label) >= 0);
      form.appendChild(wrap);
      state.original[h.label] = '';
    });
    var ro = $('roFields');
    if (isHistoryTab()) {
      ro.innerHTML = ''; ro.style.display = 'none';
    } else {
      ro.innerHTML = '<div class="h">Ticker はあとで自動解決します</div>' +
        '<div class="note-line">register-ticker スキルが候補を提示 → 選択 → 自動更新されます。</div>';
      ro.style.display = 'block';
    }
    refreshProgress();
    openSheet();
  }
```

必須マークを `state.required.indexOf(h.label) >= 0` で付与するため、保有/監視（required=[銘柄名]）でも従来どおり銘柄名だけに `*` が付く（後方互換）。

- [ ] **Step 2: numericFieldError ヘルパを追加**

`webapp/index.html:960`（`closeSheet` 関数の閉じ `}`）の直後に追加:

```javascript

  // POSITIVE_NUM_FIELDS のうち入力されているものが正の数か検証する。最初に違反した
  // フィールドのエラーメッセージを返す（無ければ null）。判定は sortlib の純関数
  // isPositiveNumberStr に委譲（Node でテスト済み）。
  function numericFieldError(fields) {
    for (var i = 0; i < POSITIVE_NUM_FIELDS.length; i++) {
      var f = POSITIVE_NUM_FIELDS[i];
      if (fields[f] == null || String(fields[f]).trim() === '') continue;
      if (!isPositiveNumberStr(fields[f])) return f + 'は正の数を入力してください';
    }
    return null;
  }
```

- [ ] **Step 3: saveNew を必須+数値バリデーションに一般化**

`webapp/index.html:962-973` の `saveNew` を置換:

```javascript
  function saveNew() {
    var fields = {};
    [].forEach.call(document.querySelectorAll('[data-h]'), function (el) {
      if (String(el.value).trim()) fields[el.getAttribute('data-h')] = el.value;
    });
    // 必須項目チェック（タブごとに state.required を openAdd で設定済み）。
    for (var i = 0; i < state.required.length; i++) {
      var rq = state.required[i];
      if (!fields[rq] || !String(fields[rq]).trim()) {
        toast(rq + 'を入力してください'); return;
      }
    }
    // 数値項目（約定単価/株数）は正の数であること。
    var numErr = numericFieldError(fields);
    if (numErr) { toast(numErr); return; }
    runSave('追加中…', '追加しました', '追加に失敗: ', function (runner) {
      runner.addRow(state.tab, fields);
    });
  }
```

- [ ] **Step 4: save（編集モード）にも数値バリデーションを追加**

`webapp/index.html:975-986` の `save` を置換:

```javascript
  function save() {
    if (state.editing === 'new') { saveNew(); return; }
    var changed = {};
    [].forEach.call(document.querySelectorAll('[data-h]'), function (el) {
      var h = el.getAttribute('data-h');
      if (el.value !== state.original[h]) changed[h] = el.value;
    });
    if (Object.keys(changed).length === 0) { closeSheet(); return; }
    var numErr = numericFieldError(changed);
    if (numErr) { toast(numErr); return; }
    runSave('保存中…', '保存しました', '保存に失敗: ', function (runner) {
      runner.saveRow(state.tab, state.editing, changed);
    });
  }
```

- [ ] **Step 5: index.html 配信JSの構文チェック**

Run:
```bash
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK"
```
Expected: `index.html served JS OK`

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): trade-history add flow with required + positive-number validation

売買履歴の新規追加で Ticker を手入力に含め登録注記を消し、必須項目を
[日付,銘柄名,売買区分,約定単価,株数]に。約定単価/株数は追加・編集とも正数を要求。"
```

---

## Task 8: index.html — 削除 identity の一般化とラベル

**Files:**
- Modify: `webapp/index.html:989-995`（resetDelete）, `webapp/index.html:996-1015`（onDeleteClick）

- [ ] **Step 1: resetDelete のラベルをタブ種別で分岐**

`webapp/index.html:989-995` の `resetDelete` を置換:

```javascript
  function resetDelete() {
    delConfirm = false;
    var b = $('deleteBtn');
    b.disabled = false;
    b.classList.remove('confirm');
    b.textContent = isHistoryTab() ? 'この取引を削除' : 'この銘柄を削除';
  }
```

- [ ] **Step 2: onDeleteClick の ident を全 editable 列に一般化**

`webapp/index.html:996-1015` の `onDeleteClick` を置換:

```javascript
  function onDeleteClick() {
    var b = $('deleteBtn');
    if (!delConfirm) { // 1st tap: arm confirmation
      delConfirm = true;
      b.classList.add('confirm');
      b.textContent = 'この操作は取り消せません — 削除する';
      return;
    }
    // 2nd tap: execute. Identity = openEdit 時にキャプチャした全 editable 列の
    // CURRENT シート値（state.original。ライブ入力ではない）なので、サーバが読み直す
    // 値と一致する。取引台帳は同じ ticker+name が複数行に現れるため、全 editable 列の
    // タプルでないと一意に同定できない。
    var tab = state.tab, rowNum = state.editing;
    var ident = {};
    Object.keys(state.original).forEach(function (k) {
      ident[k] = state.original[k] == null ? '' : state.original[k];
    });
    b.disabled = true; b.classList.remove('confirm'); b.textContent = '削除中…';
    google.script.run.withSuccessHandler(function () {
      closeSheet(); toast('削除しました'); load();
    }).withFailureHandler(function (e) {
      closeSheet(); toast('削除に失敗: ' + errMsg(e)); load();
    }).deleteRow(tab, rowNum, ident);
  }
```

`state.original` は openEdit で editable 列のみ（`h.editable` のもの）について現在のシート表示値で埋まる（`webapp/index.html:912-916`）。サーバ側はキーごとに manual 列であることを検証し、表示値を trim 比較する（Task 2）。

- [ ] **Step 3: index.html 配信JSの構文チェック**

Run:
```bash
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK"
```
Expected: `index.html served JS OK`

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "fix(webapp): send full editable-column identity on delete; history delete label

onDeleteClick の identity を ticker+name から全 editable 列のコピーに一般化し、
Task 2 のサーバ側一般化と対応。履歴タブの削除ラベルを「この取引を削除」に。"
```

---

## Task 9: 統合検証と本番デプロイゲート

**目的:** 全変更を横断的に検証し、安全クリティカルな削除ガードを静的に突き、回帰が無いことを確認した上で、ユーザー確認の下で本番デプロイ（`webapp/**` push）する。

**Files:** （変更なし。検証とゲートのみ）

- [ ] **Step 1: 全構文チェック + 全自動テスト**

Run:
```bash
cp webapp/Code.gs /tmp/th_code.js && node --check /tmp/th_code.js && echo "Code.gs OK"
node -e '
const fs=require("fs");
let html=fs.readFileSync("webapp/index.html","utf8");
const sort=fs.readFileSync("webapp/sortlib.html","utf8");
html=html.replace(/<\?!=\s*include\(.sortlib.\);?\s*\?>/, sort);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join("\n;\n");
fs.writeFileSync("/tmp/th_index.js", scripts);
' && node --check /tmp/th_index.js && echo "index.html served JS OK"
node --test tests/webapp/test_sortlib.mjs
.venv/bin/python -m unittest discover -s tests
```
Expected: `Code.gs OK` / `index.html served JS OK` / sortlib 7テスト pass / Python 26テスト pass。Python が green = 売買履歴を `config.yaml` に追加していない（価格エンジン非影響）ことの確認も兼ねる。

- [ ] **Step 2: config.yaml に売買履歴が混入していないことを確認**

Run:
```bash
grep -n "売買履歴" config.yaml || echo "config.yaml に売買履歴なし（期待どおり）"
```
Expected: `config.yaml に売買履歴なし（期待どおり）`

- [ ] **Step 3: 削除ガードの adversarial 静的レビュー（同一銘柄2取引）**

ランタイム実行はデプロイ無しに不可のため、コード上で次のシナリオをトレースして確認する（結果を文章で記録する）:

シナリオ: 売買履歴に同一銘柄の2取引がある。
- 行A: 日付=2026-01-10, 銘柄名=サンプル, Ticker=7203.T, 売買区分=買い, 約定単価=2000, 株数=100, 理由=…
- 行B: 日付=2026-03-20, 銘柄名=サンプル, Ticker=7203.T, 売買区分=売り, 約定単価=2500, 株数=100, 理由=…

確認項目:
1. クライアント（onDeleteClick, Task 8）は行Aを開いた `state.original` の全 editable 列（日付/銘柄名/Ticker/売買区分/約定単価/株数/理由）を `ident` として送る。行Aと行Bは少なくとも日付・売買区分・約定単価が異なるので `ident` は一意。
2. 行Bが先頭に挿入される等で行Aの行番号がずれた場合、サーバ（deleteRow, Task 2）は `rowNum` の現在値を読み直し、`ident['日付']`(=2026-01-10) と現在値(行Bがずれ込めば 2026-03-20)が不一致 → `行の内容が変わっています。再読み込みしてください` を throw し、誤削除しない。
3. `expected` が空（旧クライアント等）なら `削除対象の identity がありません` で拒否。
4. `deleteRow` は成功時 `true` のみ返し、セル値をログ/戻り値に含めない（PII/ティッカー保護）。

旧 `{ticker,name}` 実装ではこの2行は ticker/name が同一のため identity が衝突し誤削除し得たが、一般化により防止される——をコード参照（`webapp/Code.gs` deleteRow, `webapp/index.html` onDeleteClick）で確認する。

- [ ] **Step 4: 差分の最終目視レビュー**

Run:
```bash
git log --oneline origin/main..HEAD
git diff origin/main..HEAD -- webapp/ | head -400
```
確認: コミットされた `webapp/Code.gs` / `index.html` / `sortlib.html` に実ティッカー・価格・PII・allowlist email が含まれていないこと（汎用例 7203.T/AAPL のみ）。`config.yaml` に変更が無いこと。

- [ ] **Step 5: 本番デプロイゲート（ユーザー確認 → push）**

`webapp/**` を含むコミットを `origin/main` に push すると `deploy-webapp.yml` が本番 clasp デプロイをトリガーする。**push 前に必ずユーザーへ確認を取る**（subagent はここで push しない。オーケストレーターが finishing-a-development-branch 経由でゲートする）。

確認後の push:
```bash
git push origin main
```
Push 後、Actions のデプロイ run が success になることを確認する（ジョブ名/番号のみ確認。ログにセル値は出さない設計）。

- [ ] **Step 6: オーナー手動ブラウザチェックリスト（デプロイ後）**

オーナーが /exec アプリで確認:
1. 「売買履歴」タブが自動作成され、正規ヘッダ（日付/銘柄名/Ticker/売買区分/約定単価/株数/理由/AI分析コメント）で生成される。
2. 取引を追加できる（買い・売り両方。Ticker 手入力欄が出る。約定単価/株数に 0 や負・非数値を入れると保存拒否され、必須欠落も拒否される）。
3. 既存取引を編集できる（理由は textarea、売買区分は select）。
4. カードのバッジが売買区分（買い=緑/売り=赤）で表示され、本文に売買区分チップが重複しない。
5. ソートが日付降順を既定に、約定単価/株数/銘柄名でも並べ替えできる。ソートのプルダウンに「シート順」が無い。
6. 同一銘柄の2取引のうち片方を削除でき、削除ボタンが「この取引を削除」と表示される。
7. AI分析コメントが編集 UI に現れない（読み取り専用）。
8. 既存の保有銘柄/監視/用語解説タブの表示・編集・削除がリグレッション無し。**ソートは仕様変更**: 全タブで「シート順」選択肢が消え、保有/監視はタブを開くと既定で銘柄名昇順に整列する（プルダウンと実データが一致する＝未ソート状態が残らない）。

---

## Self-Review

**1. Spec coverage（設計書の各要件 → タスク対応）:**
- データモデル（列構成・型・必須・MANUAL_HEADERS） → Task 1（MANUAL_HEADERS, HISTORY_HEADERS）。
- config.yaml 非追加 → Task 9 Step 2 で明示確認（コードでは config.yaml を一切触らない）。
- TABS 末尾追加（holdings 先頭維持） → Task 1 Step 1。
- _sheet 自動作成（冪等） → Task 1 Step 4。
- deleteRow identity 一般化（空拒否・true のみ・非掲載キーはミスマッチ） → Task 2。
- HISTORY_TAB/isHistoryTab/SELECT_OPTS → Task 4。
- 売買区分バッジ + チップ抑制 → Task 5。
- 理由 NOTES + LONG_EDIT → Task 4。
- 履歴チップ（日付/約定単価/株数） → Task 5（抑制ロジック）+ 既存 columnMetrics が日付/約定単価/株数 をチップ化。
- sortOptions 履歴分岐 + sortValue 日付 + 既定降順 → Task 6。
- fieldHtml select → Task 4。
- openAdd 履歴分岐（Ticker 含む・注記非表示・required） → Task 7。
- saveNew/save 必須+数値>0 一般化 → Task 7（isPositiveNumberStr は Task 3）。
- 削除 ident 全 editable 列 + ラベル → Task 8。
- 検証（構文/sortlib/python/adversarial/browser） → Task 9。
- セキュリティ/PII（汎用ラベルのみ・セル値非ログ・push ゲート） → Task 2 コメント, Task 9 Step 4-5。
- Non-goals（AI スキル本体/集計/手数料列/CSV/AI分析コメント編集不可） → 計画に含めず（YAGNI 遵守）。AI分析コメント編集不可は Task 1（MANUAL_HEADERS 非掲載）で担保。

ギャップ: なし。

**2. Placeholder scan:** TBD/TODO/「適切に」「ハンドリングを追加」等の曖昧表現なし。全コード手順に実コードを記載。OK。

**3. Type consistency:**
- `HISTORY_TAB`/`BUY_SELL`/`POSITIVE_NUM_FIELDS`/`SELECT_OPTS`/`isHistoryTab` は Task 4 で定義し、Task 5-8 で同名参照。
- `isPositiveNumberStr` は Task 3（sortlib）で定義し Task 7（numericFieldError）で参照。実行時は include で先にインライン化されるため定義済み。
- `numericFieldError` は Task 7 Step 2 で定義し、同 Task の saveNew/save で参照。
- サーバ `deleteRow(tabName,rowNum,expected)` の `expected` 形（label→表示値マップ）と、クライアント `onDeleteClick` の `ident` 形（state.original の全 editable 列）が一致。
- `HISTORY_HEADERS`（AI分析コメント込み8列）と `MANUAL_HEADERS['売買履歴']`（7列、AI分析コメント除外）の関係が整合。
整合性 OK。
