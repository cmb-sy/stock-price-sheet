/**
 * stock-price-sheet — owner-only manual editor (Apps Script web app).
 *
 * A standalone web app that opens the spreadsheet by ID and runs AS THE DEPLOYING
 * OWNER (see appsscript.json: executeAs USER_DEPLOYING, access MYSELF). It needs no
 * service-account key. This file intentionally contains ONLY generic header labels,
 * tab names, and the spreadsheet_id (the same public-safe value as config.yaml) —
 * never tickers, prices, or PII. Do not log cell values.
 *
 * It exposes the sheet for VIEWING (all columns) and for EDITING the manual columns
 * only. Track A (yfinance) and Track B (Claude skills) columns are read-only and the
 * server refuses to write them.
 */

// Same ID as config.yaml's spreadsheet_id (safe to publish; access is granted by
// sheet sharing, not by this ID). Keep in sync if the sheet ever changes.
var SPREADSHEET_ID = '1JkQ25PnxflO86axqflNw1HgAHAMVN4dyiQkj1mmFYgE';
var HEADER_ROW = 1;
var TABS = ['保有銘柄', '監視-JP', '監視-US'];

// Manual columns the UI may edit, per tab. Everything else is read-only. Mirrors
// the manual roles in config.yaml / CLAUDE.md; labels are generic, no tickers/PII.
var MANUAL_HEADERS = {
  '保有銘柄': ['銘柄名', '取得日', '短中長期', '目標売却株価', '取得株価', '取得株数', '購入理由', 'Ticker'],
  '監視-JP': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker'],
  '監視-US': ['銘柄名', '購入検討株価', '購入検討理由', 'Ticker']
};

function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('Stock Sheet')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function _sheet(tabName) {
  if (TABS.indexOf(tabName) < 0) throw new Error('unknown tab');
  var sh = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(tabName);
  if (!sh) throw new Error('tab not found');
  return sh;
}

function getTabs() {
  return TABS;
}

/**
 * Returns { headers: [{label, editable}], rows: [{row, cells}] } for a tab.
 * cells are DISPLAY values (formatted: 億円 / thousands / decimals) so the table
 * reads nicely. Rows without a Ticker are skipped, matching Track A/B behavior.
 */
function getRows(tabName) {
  var sh = _sheet(tabName);
  var values = sh.getDataRange().getDisplayValues();
  if (values.length < HEADER_ROW) return { headers: [], rows: [] };
  var headerRow = values[HEADER_ROW - 1];
  var manual = MANUAL_HEADERS[tabName] || [];
  var headers = headerRow.map(function (h) {
    return { label: h, editable: manual.indexOf(h) >= 0 };
  });
  var tickerIdx = headerRow.indexOf('Ticker');
  var rows = [];
  for (var r = HEADER_ROW; r < values.length; r++) {
    var cells = values[r];
    if (tickerIdx >= 0 && !String(cells[tickerIdx] || '').trim()) continue;
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
  var manual = MANUAL_HEADERS[tabName] || [];
  var sh = _sheet(tabName);
  var headerRow = sh.getRange(HEADER_ROW, 1, 1, sh.getLastColumn()).getValues()[0];
  rowNum = parseInt(rowNum, 10);
  if (!(rowNum > HEADER_ROW)) throw new Error('invalid row');

  var written = 0;
  for (var label in fields) {
    if (!Object.prototype.hasOwnProperty.call(fields, label)) continue;
    if (manual.indexOf(label) < 0) {
      throw new Error('refusing to write a non-manual (read-only) column');
    }
    var col = headerRow.indexOf(label);
    if (col < 0) throw new Error('header not found in tab');
    sh.getRange(rowNum, col + 1).setValue(_coerce(fields[label]));
    written++;
  }
  return written;
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
