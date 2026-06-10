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
const { ratingRank, compareKeys, sortRows, isPositiveNumberStr,
        parseNum, ledgerPositions, reconcileHolding } = ctx;

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

test('isPositiveNumberStr: malformed-but-positive typos are rejected', () => {
  assert.equal(isPositiveNumberStr('1.2.3'), false);
  assert.equal(isPositiveNumberStr('1-2'), false);
  assert.equal(isPositiveNumberStr('1.'), false);
  assert.equal(isPositiveNumberStr('.5'), false);
  assert.equal(isPositiveNumberStr('12a'), false);
});

test('parseNum: lenient display-string parsing', () => {
  assert.equal(parseNum('¥1,200'), 1200);
  assert.equal(parseNum('3,584'), 3584);
  assert.equal(parseNum('12.3%'), 12.3);
  assert.equal(parseNum('-5'), -5);
  assert.equal(parseNum('abc'), null);
  assert.equal(parseNum(''), null);
  assert.equal(parseNum(null), null);
});

// ---- ledgerPositions / reconcileHolding ----

const H = ['日付', '銘柄名', 'Ticker', '売買区分', '約定単価', '株数', '理由', 'AI分析コメント']
  .map((label) => ({ label }));

// rows: [date, name, ticker, side, price, qty] -> getRows shape (sheet row = index+2)
function ledger(specs) {
  return specs.map((s, i) => ({
    row: i + 2,
    cells: [s[0], s[1] ?? 'テスト株', s[2], s[3], s[4], s[5], '', ''],
  }));
}

test('ledgerPositions: single buy', () => {
  const pos = ledgerPositions(H, ledger([['2026-01-05', , '0000.T', '買い', '¥1,000', '100']]));
  assert.equal(pos['0000.T'].shares, 100);
  assert.equal(pos['0000.T'].avgPrice, 1000);
  assert.equal(pos['0000.T'].oversold, false);
  assert.equal(pos['0000.T'].invalid, 0);
  assert.equal(pos['0000.T'].dateFallback, false);
});

test('ledgerPositions: moving average across two buys', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '買い', '2,000', '100'],
  ]));
  assert.equal(pos['0000.T'].shares, 200);
  assert.equal(pos['0000.T'].avgPrice, 1500); // (100*1000+100*2000)/200
});

test('ledgerPositions: partial sell keeps avg, buy after sell recomputes', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '買い', '2,000', '100'],
    ['2026-03-05', , '0000.T', '売り', '2,500', '50'],
    ['2026-04-05', , '0000.T', '買い', '1,800', '50'],
  ]));
  // after sell: 150sh @1500 (avg unchanged); buy: (150*1500+50*1800)/200 = 1575
  assert.equal(pos['0000.T'].shares, 200);
  assert.equal(pos['0000.T'].avgPrice, 1575);
  assert.equal(pos['0000.T'].oversold, false);
});

test('ledgerPositions: oversell flags oversold', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '売り', '1,200', '150'],
  ]));
  assert.equal(pos['0000.T'].oversold, true);
});

test('ledgerPositions: fully sold position nets to zero', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '売り', '1,200', '100'],
  ]));
  assert.equal(pos['0000.T'].shares, 0);
  assert.equal(pos['0000.T'].oversold, false);
});

test('ledgerPositions: processes by date even when sheet rows are out of order', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-02-05', , '0000.T', '売り', '1,200', '100'], // sheet-first but date-later
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
  ]));
  assert.equal(pos['0000.T'].shares, 0);
  assert.equal(pos['0000.T'].oversold, false); // date order: buy then sell
});

test('ledgerPositions: same-date ties break by sheet row order', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-01-05', , '0000.T', '売り', '1,100', '100'],
  ]));
  assert.equal(pos['0000.T'].oversold, false);
});

test('ledgerPositions: unparseable date falls back to row order with flag', () => {
  const pos = ledgerPositions(H, ledger([
    ['一月ごろ', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '売り', '1,200', '100'],
  ]));
  assert.equal(pos['0000.T'].dateFallback, true);
  assert.equal(pos['0000.T'].shares, 0);
});

test('ledgerPositions: slash dates parse, yen/comma display strings parse', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026/01/05', , '0000.T', '買い', '¥1,000', '1,000'],
  ]));
  assert.equal(pos['0000.T'].dateFallback, false);
  assert.equal(pos['0000.T'].shares, 1000);
  assert.equal(pos['0000.T'].avgPrice, 1000);
});

test('ledgerPositions: blank-ticker rows skipped, ticker case-normalized', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '', '買い', '1,000', '100'],
    ['2026-01-05', , '0000.t', '買い', '1,000', '100'],
    ['2026-02-05', , ' 0000.T ', '買い', '2,000', '100'],
  ]));
  assert.deepEqual(Object.keys(pos), ['0000.T']);
  assert.equal(pos['0000.T'].shares, 200);
  assert.equal(pos['0000.T'].avgPrice, 1500);
});

test('ledgerPositions: malformed numbers and unknown side count as invalid, excluded', () => {
  const pos = ledgerPositions(H, ledger([
    ['2026-01-05', , '0000.T', '買い', '1,000', '100'],
    ['2026-02-05', , '0000.T', '買い', '1.2.3', '100'],   // malformed price
    ['2026-03-05', , '0000.T', '譲渡', '1,000', '100'],    // unknown side
  ]));
  assert.equal(pos['0000.T'].invalid, 2);
  assert.equal(pos['0000.T'].shares, 100);
  assert.equal(pos['0000.T'].avgPrice, 1000);
});

test('reconcileHolding: exact match and rounding tolerance', () => {
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1000, oversold: false, invalid: 0 }, 100, 1000), 'match');
  // display strings round JPY to integers: 1234.4 vs 1234 within max(0.5, 1.234)
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1234.4, oversold: false, invalid: 0 }, 100, 1234), 'match');
});

test('reconcileHolding: share or price mismatch', () => {
  assert.equal(reconcileHolding({ shares: 200, avgPrice: 1000, oversold: false, invalid: 0 }, 100, 1000), 'mismatch');
  // 台帳上は全売却済みなのに保有側に株数が残っている（記入漏れ検出）
  assert.equal(reconcileHolding({ shares: 0, avgPrice: 1000, oversold: false, invalid: 0 }, 100, 1000), 'mismatch');
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1100, oversold: false, invalid: 0 }, 100, 1000), 'mismatch');
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1000, oversold: false, invalid: 0 }, null, null), 'mismatch');
  assert.equal(reconcileHolding({ shares: 100, avgPrice: null, oversold: false, invalid: 0 }, 100, 1000), 'mismatch');
});

test('reconcileHolding: oversold or invalid rows warn instead of comparing', () => {
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1000, oversold: true, invalid: 0 }, 100, 1000), 'warn');
  assert.equal(reconcileHolding({ shares: 100, avgPrice: 1000, oversold: false, invalid: 1 }, 100, 1000), 'warn');
});
