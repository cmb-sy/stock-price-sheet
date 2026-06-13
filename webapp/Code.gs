/**
 * stock-price-sheet — owner-only manual editor (Apps Script web app).
 *
 * A standalone web app that opens the spreadsheet by ID and runs AS THE ACCESSING
 * USER (see appsscript.json: executeAs USER_ACCESSING, access ANYONE — access is then
 * narrowed in code to the ALLOWED_EMAILS allowlist below). It needs no
 * service-account key. This file intentionally contains ONLY generic header labels,
 * tab names, and the spreadsheet_id (the same public-safe value as config.yaml) —
 * never tickers, prices, or PII. Do not log cell values.
 *
 * It exposes the sheet for VIEWING (all columns) and for EDITING the manual columns
 * only. Track A (yfinance) and Track B (Claude skills) columns are read-only and the
 * server refuses to write them.
 *
 * Access is restricted to an allowlist of accounts. The allowlist (emails) lives in a
 * Script Property named ALLOWED_EMAILS (comma-separated), set in the Apps Script editor
 * — NEVER hard-coded here, so this committed file stays free of personal emails (PII).
 * With executeAs USER_ACCESSING each visitor runs as themselves, so getActiveUser()
 * reliably yields their email for the allowlist check and the sheet must be shared with
 * each allowed account.
 */

// Same ID as config.yaml's spreadsheet_id (safe to publish; access is granted by
// sheet sharing, not by this ID). Keep in sync if the sheet ever changes.
var SPREADSHEET_ID = '1JkQ25PnxflO86axqflNw1HgAHAMVN4dyiQkj1mmFYgE';
var HEADER_ROW = 1;
var TABS = ['保有銘柄', '監視-JP', '監視-US', '売買履歴'];

// Header labels looked up by name (a column move does not break these).
var LABEL_TICKER = 'Ticker';
var LABEL_NAME = '銘柄名';

// Manual columns the UI may edit, per tab. Everything else is read-only. Mirrors
// the manual roles in config.yaml / CLAUDE.md; labels are generic, no tickers/PII.
var MANUAL_HEADERS = {
  '保有銘柄': ['銘柄名', '目標売却株価', '取得株価', '取得株数', '株主優待', '購入理由', 'Ticker', 'ナンピン検討株価', 'ナンピン検討株数', 'カテゴリ', 'AI再評価'],
  '監視-JP': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker', 'カテゴリ', 'AI再評価'],
  '監視-US': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker', 'カテゴリ', 'AI再評価'],
  '売買履歴': ['日付', '銘柄名', 'Ticker', '売買区分', '約定単価', '株数', '理由']
};

// 売買履歴タブはオーナーが手動作成しなくてよいよう、初回アクセス時に自動生成する
// （_sheet 参照）。下記はその正規ヘッダ行（順序固定）。末尾の AI分析コメントは
// 読み取り専用（MANUAL_HEADERS 非掲載）で、将来の Track B スキル用に確保する。
// 汎用ラベルのみ — ティッカー/価格/PII は一切含めない。
var HISTORY_TAB = '売買履歴';
var HISTORY_HEADERS = ['日付', '銘柄名', 'Ticker', '売買区分', '約定単価', '株数', '理由', 'AI分析コメント'];

// Allowlist (emails) is stored in the ALLOWED_EMAILS Script Property, comma-separated,
// so personal emails never live in this committed file.
function _allowedEmails() {
  var raw = PropertiesService.getScriptProperties().getProperty('ALLOWED_EMAILS') || '';
  return raw.split(',').map(function (s) { return s.trim().toLowerCase(); }).filter(String);
}

function _isAllowed() {
  var me = (Session.getActiveUser().getEmail() || '').toLowerCase();
  return !!me && _allowedEmails().indexOf(me) >= 0;
}

// Throw on every data call from a non-allowlisted user, so no data leaks even if the
// page HTML somehow loads.
function _guard() {
  if (!_isAllowed()) throw new Error('アクセス権がありません');
}

function doGet(e) {
  if (!_isAllowed()) {
    return HtmlService.createHtmlOutput(
      '<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;' +
      'padding:48px 24px;text-align:center;color:#374151">' +
      '<div style="font-size:32px">🔒</div>' +
      '<h2 style="margin:12px 0 4px">アクセス権がありません</h2>' +
      '<p style="color:#6b7280;font-size:14px">このアプリは許可されたアカウントのみ利用できます。</p>' +
      '</div>'
    ).setTitle('アクセス権なし');
  }
  // URL パラメータ（?view=detail&tab=…&row=…）を INIT としてページに注入する。
  // tab は TABS 照合・row は整数化・view はホワイトリストで、すべて安全な値に正規化
  // してから埋め込む（生のクエリ文字列は決して HTML に入れない）。
  var p = (e && e.parameter) || {};
  var t = HtmlService.createTemplateFromFile('index');
  t.initJson = JSON.stringify({
    view: p.view === 'detail' ? 'detail' : 'list',
    tab: TABS.indexOf(p.tab) >= 0 ? p.tab : '',
    row: parseInt(p.row, 10) > 0 ? parseInt(p.row, 10) : 0,
    execUrl: ScriptApp.getService().getUrl()
  });
  return t.evaluate()
    .setTitle('保有・監視シート')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// Inlines another project file (e.g. sortlib.html) into a templated page via
// <?!= include('name'); ?>. Returns the file's raw content (no escaping).
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

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

// The tab's header row (row HEADER_ROW), as raw cell values.
function _headerRow(sh) {
  return sh.getRange(HEADER_ROW, 1, 1, sh.getLastColumn()).getValues()[0];
}

// Resolve a manual header label to its 0-based column index, refusing labels that
// are not editable for this tab or not present in the header.
function _resolveManualCol(manual, headerRow, label) {
  if (manual.indexOf(label) < 0) {
    throw new Error('編集不可（自動更新）列のため書き込みできません');
  }
  var col = headerRow.indexOf(label);
  if (col < 0) throw new Error('ヘッダが見つかりません: ' + label);
  return col;
}

function getTabs() {
  _guard();
  return TABS;
}

/**
 * Returns { headers: [{label, editable}], rows: [{row, cells}] } for a tab.
 * cells are DISPLAY values (formatted: 億円 / thousands / decimals) so the table
 * reads nicely. Rows without a Ticker are skipped, matching Track A/B behavior.
 */
function getRows(tabName) {
  _guard();
  var sh = _sheet(tabName);
  var values = sh.getDataRange().getDisplayValues();
  if (values.length < HEADER_ROW) return { headers: [], rows: [] };
  var headerRow = values[HEADER_ROW - 1];
  var manual = MANUAL_HEADERS[tabName] || [];
  var headers = headerRow.map(function (h) {
    return { label: h, editable: manual.indexOf(h) >= 0 };
  });
  var tickerIdx = headerRow.indexOf(LABEL_TICKER);
  var nameIdx = headerRow.indexOf(LABEL_NAME);
  var rows = [];
  for (var r = HEADER_ROW; r < values.length; r++) {
    var cells = values[r];
    // Show a row that has a Ticker OR a 銘柄名. A name-only row is a stock the owner
    // just registered (ticker not yet resolved); it must appear so it is editable and
    // visible to the register-ticker skill. Fully blank trailing rows stay hidden.
    var hasTicker = tickerIdx >= 0 && String(cells[tickerIdx] || '').trim();
    var hasName = nameIdx >= 0 && String(cells[nameIdx] || '').trim();
    if (!hasTicker && !hasName) continue;
    rows.push({ row: r + 1, cells: cells });
  }
  return { headers: headers, rows: rows };
}

/**
 * Writes the given manual fields to one row. fields = { "<header>": "<value>" }.
 * Only manual headers for this tab are accepted; any other header is refused so
 * machine-written (Track A/B) columns can never be clobbered from the web. Numeric-
 * looking values are stored as numbers (commas stripped) so cell formats apply;
 * everything else (names, dates, tickers, reasons) is stored as text. Returns the
 * count of cells written.
 */
function saveRow(tabName, rowNum, fields) {
  _guard();
  var manual = MANUAL_HEADERS[tabName] || [];
  var sh = _sheet(tabName);
  var headerRow = _headerRow(sh);
  rowNum = parseInt(rowNum, 10);
  if (!(rowNum > HEADER_ROW)) throw new Error('無効な行番号です');

  var written = 0;
  for (var label in fields) {
    if (!Object.prototype.hasOwnProperty.call(fields, label)) continue;
    var col = _resolveManualCol(manual, headerRow, label);
    sh.getRange(rowNum, col + 1).setValue(_coerce(fields[label]));
    written++;
  }
  return written;
}

/**
 * Appends a new row to a tab, writing only the given manual fields. fields =
 * { "<header>": "<value>" }. Used by the "register a stock" flow: the owner enters a
 * 銘柄名 (and optionally 購入検討株価 / 購入検討理由); the Ticker is left blank and is
 * resolved later by the register-ticker skill (yfinance search + human pick). Only
 * manual headers are accepted; 銘柄名 is required so the row is identifiable. Returns
 * the new 1-based row number.
 */
function addRow(tabName, fields) {
  _guard();
  var manual = MANUAL_HEADERS[tabName] || [];
  var sh = _sheet(tabName);
  var headerRow = _headerRow(sh);
  var rowArr = [];
  for (var i = 0; i < headerRow.length; i++) rowArr.push('');

  var any = false;
  for (var label in fields) {
    if (!Object.prototype.hasOwnProperty.call(fields, label)) continue;
    var col = _resolveManualCol(manual, headerRow, label);
    rowArr[col] = _coerce(fields[label]);
    any = true;
  }
  if (!any) throw new Error('登録する値がありません');

  var nameCol = headerRow.indexOf(LABEL_NAME);
  if (nameCol < 0 || !String(rowArr[nameCol]).trim()) throw new Error('銘柄名は必須です');

  sh.appendRow(rowArr);
  return sh.getLastRow();
}

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

// Numbers (incl. comma-grouped) -> Number so the cell's number format applies.
// Tickers (7203.T, AAPL), dates, names, and reasons keep their text form.
function _coerce(v) {
  var s = String(v == null ? '' : v).trim();
  if (s !== '' && /^-?[0-9][0-9,]*(\.[0-9]+)?$/.test(s)) {
    var n = Number(s.replace(/,/g, ''));
    if (!isNaN(n)) return n;
  }
  return v;
}
