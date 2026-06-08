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
const { ratingRank, compareKeys, sortRows, isPositiveNumberStr } = ctx;

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
