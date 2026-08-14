// discover-utils T5a 测试：fuzzyMatch / highlightHtml / rankAndGroup / MRU
// 运行: node mcp/server/static/discover-utils.test.js
const assert = require('assert');
const { fuzzyMatch, highlightHtml, rankAndGroup, createMRU } = require('./discover-utils.js');

// ── 1) fuzzyMatch：连续子串 ──
(function testSubstringMatch() {
  const m = fuzzyMatch('loop', 'ws2_loop_submit');
  assert.ok(m, 'substring should match');
  assert.ok(m.score > 0, 'positive score');
  assert.ok(m.ranges.length === 1, 'one contiguous range');
  assert.deepStrictEqual(m.ranges[0], { start: 4, end: 8 }, 'range hits "loop"');
  console.log('PASS testSubstringMatch');
})();

// ── 2) 非连续子串（跨词顺序）不命中——避免过宽 ──
(function testCrossWordNotMatch() {
  assert.strictEqual(fuzzyMatch('lsub', 'ws2_loop_submit'), null, 'cross-word chars not contiguous -> null');
  assert.strictEqual(fuzzyMatch('lst', 'ws2_loop_submit'), null, 'scattered chars -> null');
  console.log('PASS testCrossWordNotMatch');
})();

// ── 3) fuzzyMatch：负例与词长阈值 ──
(function testNegativeAndMinLength() {
  assert.strictEqual(fuzzyMatch('xyz', 'ws2_loop_submit'), null, 'unrelated -> null');
  assert.strictEqual(fuzzyMatch('a', 'abc'), null, 'single char too broad -> null');
  console.log('PASS testNegativeAndMinLength');
})();

// ── 4) highlightHtml：ranges → mark 高亮 + 转义安全 ──
(function testHighlightHtml() {
  assert.strictEqual(highlightHtml('loop submit', [{ start: 0, end: 4 }]), '<mark>loop</mark> submit');
  assert.strictEqual(highlightHtml('a<b>&c', []), 'a&lt;b&gt;&amp;c', 'escape when no ranges');
  assert.strictEqual(
    highlightHtml('x<y>z', [{ start: 2, end: 3 }]),
    'x&lt;<mark>y</mark>&gt;z',
    'escape outside mark, raw inside',
  );
  console.log('PASS testHighlightHtml');
})();

// ── 5) rankAndGroup：空 query 原序分组；有 query 名字优先 ──
(function testRankAndGroup() {
  const items = [
    { name: 'ws2_loop_submit', description: '提交长程任务', group: '长程任务' },
    { name: 'ws2_get_course', description: '获取课程 loop 相关', group: '课程' },
    { name: 'note_write', description: '写笔记', group: '笔记' },
  ];
  // 空 query → 原序分组（3 组）
  const empty = rankAndGroup(items, '');
  assert.strictEqual(empty.length, 3, 'three groups when no query');
  // query 'loop' → 名字命中排前（loop_submit），描述命中次之（course）
  const ranked = rankAndGroup(items, 'loop');
  const flat = ranked.flatMap(g => g.items).map(s => s.item.name);
  assert.strictEqual(flat[0], 'ws2_loop_submit', 'name match first');
  assert.ok(flat.includes('ws2_get_course'), 'desc match included');
  assert.ok(!flat.includes('note_write'), 'no match excluded');
  console.log('PASS testRankAndGroup');
})();

// ── 6) MRU：add 去重置顶 + LRU 上限 ──
(function testMRU() {
  const mem = {};
  const storage = { getItem: (k) => mem[k] || null, setItem: (k, v) => { mem[k] = v; } };
  const mru = createMRU({ storage, key: 'test-mru', max: 3 });
  mru.add('a'); mru.add('b'); mru.add('c'); mru.add('a'); // a 重新置顶
  assert.deepStrictEqual(mru.list(), ['a', 'c', 'b'], 'dedupe + move to front');
  mru.add('d'); // 超上限 → 淘汰最旧（b）
  assert.deepStrictEqual(mru.list(), ['d', 'a', 'c'], 'LRU eviction');
  // 持久化到 storage
  assert.ok(mem['test-mru'], 'persisted to storage');
  const mru2 = createMRU({ storage, key: 'test-mru', max: 3 });
  assert.deepStrictEqual(mru2.list(), ['d', 'a', 'c'], 'reload from storage');
  console.log('PASS testMRU');
})();
