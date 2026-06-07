# Web アプリ: 行削除機能 + 指標ソート機能 設計書

- 作成日: 2026-06-08
- 対象: `webapp/Code.gs`（バックエンド） / `webapp/index.html`（フロントエンド SPA）
- ステータス: 設計承認済み（ユーザー承認 2026-06-08）

## 1. 背景と目的

Apps Script 製の owner 専用エディタ（保有・監視シートの閲覧/手動列編集）に、次の 2 機能を追加する。

1. **行削除** — アプリ上で行を削除すると、source of truth である Google Sheet の該当行も削除される。
2. **指標ソート** — 各種指標で銘柄カードを並び替えできる。

削除はシート行を物理削除する**不可逆操作**であり、かつ Track A（yfinance）/ Track B（Claude skills）が同じシートを並行更新する。よって**行の同定（identity）・認可・確認 UI**の安全設計を最優先とする。

## 2. 前提・制約（実装前検証）

- Apps Script は `executeAs USER_ACCESSING`、認可は `ALLOWED_EMAILS` Script Property の allowlist（`_guard()`）。削除も同じ `_guard()` を通す。
- 列は**ヘッダ名**で解決する（位置では解決しない）。`Code.gs` / `config.yaml` 共通の規約。
- 行の同定: `getRows` は 1-based のシート行 `row` をキーに返す。書き込み後は必ず `load()`（全リフレッシュ）で行番号を再同期する。
- 数値フォーマット契約: セルは生のソート可能な数値を保持し、表示のみ整形。`parseNum()` が表示文字列 → 数値に変換する。
- `webapp/**` を main に push すると `deploy-webapp.yml` 経由で本番 clasp デプロイが走る（paths filter: `webapp/**`）。push はユーザー確認後に行う。
- `<!DOCTYPE html>` は `index.html` の 1 行目を維持する。
- PUBLIC リポジトリ。実ティッカー/価格/PII/allowlist email をコード・コミット・ログに出さない。`Code.gs` はセル値をログ出力しない。

## 3. 機能 1: 行削除

### 3.1 バックエンド（`webapp/Code.gs`）

新規関数 `deleteRow(tabName, rowNum, expected)` を追加する。

```
function deleteRow(tabName, rowNum, expected) {
  _guard();
  var sh = _sheet(tabName);                 // TABS 検証込み
  rowNum = parseInt(rowNum, 10);
  if (!(rowNum > HEADER_ROW)) throw new Error('無効な行番号です');
  if (rowNum > sh.getLastRow()) throw new Error('行が存在しません');

  // 行の同定: 現在の Ticker / 銘柄名 を表示値で読み、呼び出し元が見ていた値と一致するか検証
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
  return true;   // セル値は返さない・ログしない
}
```

設計判断:

- **staleness ガード**: Track A/B やユーザーの他セッションが並行して行を挿入/削除すると `rowNum` がずれ得る。削除直前にサーバ側で現在の Ticker + 銘柄名を読み、フロントが削除対象として見ていた `expected` と照合。不一致なら削除せず例外を投げ、フロントは再読み込みする。これにより「ずれた行を誤って消す」事故を防ぐ。
- **同定キー**: Ticker + 銘柄名の組。ティッカー未解決の name-only 行（register-ticker 待ち）も削除可能にするため、両方を比較対象にする（Ticker 空なら空同士で一致）。
- **戻り値**: `true` のみ。セル内容は返さない・ログしない（PII/ティッカー漏洩防止）。
- **認可**: 既存 `_guard()` を流用。allowlist 外は例外。
- **範囲制約**: `rowNum > HEADER_ROW` かつ `rowNum <= getLastRow()` を初回パスで検証（境界値含む）。

### 3.2 フロントエンド（`webapp/index.html`）

削除 UI は**編集ボトムシート内のみ**に置く（新規登録モード `editing === 'new'` のときは非表示）。

- `.actions`（[キャンセル][保存]）の下に区切り線を挟み、「この銘柄を削除」ボタン（`--neg` 配色）を配置。
- **2 段階インライン確認**: 1 回目タップで文言が `この操作は取り消せません [削除する]` に変化。`削除する` を押すと実行。誤タップでの即削除を防ぐ。
- 実行時: `deleteRow(state.tab, state.editing, { ticker, name })` を呼ぶ。`ticker` / `name` は `openEdit` 時に取り込んだ**シート現在値** = `state.original['Ticker']` / `state.original['銘柄名']` を使う（フォームで未保存編集中の入力値ではなく、サーバが読むシート値と一致させるため。Ticker・銘柄名はいずれも編集可能列なので `state.original` に必ず含まれる）。
- 成功: `closeSheet()` + トースト「削除しました」+ `load()`（行番号再同期）。
- 失敗: トーストにサーバのエラーメッセージ（例: 行の内容が変わっています…）+ `load()` で最新化。
- 既存 `runSave()` と同様の busy/disable パターンを削除ボタンにも適用し、二重送信を防ぐ。

## 4. 機能 2: 指標ソート

### 4.1 方針: クライアントサイド表示のみ

シートは一切変更しない（並び替えはシートに書き戻さない）。`state.rows`（シート順）は保持し、ソートは**コピー** `state.view` に対して行う。

- `render()` / カードの `data-i` / `openEdit(idx)` / 削除は `state.view[idx]` を参照する。
- 各 view 要素は元の `row.row`（シート行番号）を保持するので、**削除の同定は正しいまま**。
- ソートはタブ切替でリセットし、`load()` 後に再適用する。

### 4.2 状態とフロー

- `state` に `sortKey`（指標ラベル, 既定 `null` = シート順）と `sortDir`（`'desc'`/`'asc'`, 既定 `'desc'`）を追加。
- `applySort()`: `state.rows` を浅いコピーし、`sortKey` が `null` ならシート順、それ以外は指標値で比較して `state.view` を生成する。
- 呼び出し位置は **`render()` 冒頭の 1 箇所**に統一する（view は常に `rows + sortKey/sortDir` から導出される単一の経路）。`load()` の成功ハンドラもソート UI 操作も、最終的に `render()` を呼べばよい。
- `load()` 成功ハンドラ: `state.rows` 設定 → `render()`（内部で `applySort()`）。
- ソート UI 操作（select 変更・方向トグル）: `sortKey` / `sortDir` を更新 → `render()`。
- タブ切替（`switchTab`）: `sortKey = null; sortDir = 'desc'` にリセット。

### 4.3 UI

- `.meta`（`#count` / `#hint` の行）に、ソート用 `<select>`（指標選択）+ 方向トグルボタン（↓ desc / ↑ asc）を追加。
- 既定の選択肢は「シート順」。データタブ（保有/監視）のみ表示。用語解説タブ（クライアント専用）では非表示。
- `<select>` の変更・方向トグルで `applySort()` → `render()` を呼ぶ。

### 4.4 ソート対象指標（タブ別に厳選）

共通（全データタブ）:
- 銘柄名（テキスト・あいうえお/アルファベット順）, 現在株価, 年初来安値との乖離率, PER, PBR, 配当利回り, 時価総額, 現在 EPS, 年間 EPS 前年比, 更新時刻

保有銘柄タブに追加（client 派生指標を含む）:
- 評価額, 評価損益額, 評価損益率, 目標との乖離率

監視タブ（JP/US）に追加:
- 購入検討との乖離率, 予想乖離率, アナリスト予想株価, 理論株価, レーティング

メニューは現在のタブに存在する指標のみ動的に出す（ヘッダにない指標は出さない）。

### 4.5 比較ロジック

- 数値指標: `parseNum(表示値)` で数値化して比較。派生指標（評価額/評価損益等）は `derivedMetrics` と同じ計算で値を得る。
- **非数値セル（確認不可 / 赤字 / 空）は常に末尾に沈める**（昇順・降順いずれでも）。`parseNum` が `null` を返すものは「値なし」として最後尾。
- テキスト指標（銘柄名）: `localeCompare`。空は末尾。
- レーティング: 文字列をランクにマップして数値比較。
  - `strong_buy=5, buy=4, hold=3, underperform=2, sell=1`（ユーザー承認済み。マップ外/空は値なし扱いで末尾）。

## 5. 変更ファイルと影響範囲

| ファイル | 変更内容 |
|---|---|
| `webapp/Code.gs` | `deleteRow(tabName, rowNum, expected)` を新規追加。既存関数は変更なし。 |
| `webapp/index.html` | sort 用 state + `applySort()`、`render()`/`openEdit()` を `state.view` 参照に、`.meta` にソート UI、編集シートに削除 UI とハンドラ、関連 CSS。 |

- `<!DOCTYPE html>` 1 行目維持。
- 列はヘッダ名解決のため、列移動が起きても削除/ソートは破綻しない。

## 6. テスト・検証方針

- Apps Script コードは既存 unittest の対象外。純粋ロジック（ソート比較・非数値の末尾沈め・レーティングランク）は Node があれば切り出して単体検証する。
- adversarial probe（最低 1 つ）:
  - **行ずれ**: `deleteRow` に古い `rowNum` + 一致しない `expected` を渡し、削除されず例外になることを確認（誤削除防止の核）。
  - 境界値: `rowNum === HEADER_ROW` / `rowNum > getLastRow()` で拒否されること。
  - ソート: 非数値セル混在で常に末尾、方向切替の対称性。
- owner による実ブラウザ確認（golden path + 削除キャンセル + 行ずれ時の再読み込み）。
- push 前にユーザー確認（本番デプロイが走るため）。

## 7. 非対象（YAGNI）

- 複数行一括削除、undo、ゴミ箱。
- シートへのソート書き戻し（永続ソート）。
- 複合キーソート（第 2 ソートキー）。
