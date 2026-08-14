// LoopPanel T4c 测试：渲染纯函数 + 组件 refresh/submit（fake fetch / fake DOM）
// 运行: node mcp/server/static/loop-panel.test.js
const assert = require('assert');
const { createLoopPanel, renderTasks, statusBadge } = require('./loop-panel.js');

// ── 1) statusBadge：状态 → 标签映射 ──
(function testStatusBadge() {
  const cases = {
    pending: '⏳', running: '🔄', completed: '✅',
    failed: '❌', halted: '⏸️', unknown: '❔',
  };
  Object.keys(cases).forEach((s) => {
    const b = statusBadge(s);
    assert.ok(b.includes(cases[s]), `badge for ${s} should contain ${cases[s]}`);
  });
  console.log('PASS testStatusBadge');
})();

// ── 2) renderTasks：任务列表 HTML ──
(function testRenderTasks() {
  assert.strictEqual(renderTasks([]), '', 'empty -> empty html');
  const html = renderTasks([
    { task_id: 'abc123', goal: '算个题', status: 'completed', turn_count: 2, max_turns: 30, result: '42' },
  ]);
  assert.ok(html.includes('abc123'), 'contains task_id');
  assert.ok(html.includes('✅'), 'contains completed badge');
  assert.ok(html.includes('算个题'), 'contains goal');
  assert.ok(html.includes('42'), 'contains result');
  console.log('PASS testRenderTasks');
})();

// ── 3) refresh：fake fetch → 渲染到容器 ──
(function testRefreshRenders() {
  const container = { innerHTML: '' };
  const fakeFetch = (url) => {
    assert.strictEqual(url, '/api/loop/state');
    return Promise.resolve({
      json: () => Promise.resolve({
        loop_status: 'running',
        tasks: [{ task_id: 't1', goal: 'g', status: 'pending', turn_count: 0, max_turns: 30, result: null }],
      }),
    });
  };
  const panel = createLoopPanel({ container, fetch: fakeFetch, stateUrl: '/api/loop/state', timers: {} });
  return panel.refresh().then(() => {
    assert.ok(container.innerHTML.includes('t1'), 'task rendered after refresh');
    assert.ok(container.innerHTML.includes('running'), 'loop status rendered');
  }).then(() => console.log('PASS testRefreshRenders'));
})();

// ── 4) submit：fake fetch POST → 返回 task_id ──
(function testSubmit() {
  const container = { innerHTML: '' };
  const calls = [];
  const fakeFetch = (url, opts) => {
    calls.push({ url, opts });
    return Promise.resolve({ json: () => Promise.resolve({ task_id: 'new-task-1' }) });
  };
  const panel = createLoopPanel({ container, fetch: fakeFetch, submitUrl: '/api/loop/submit', timers: {} });
  return panel.submit('跑个长任务').then((taskId) => {
    assert.strictEqual(taskId, 'new-task-1');
    assert.strictEqual(calls.length, 1);
    assert.strictEqual(calls[0].url, '/api/loop/submit');
    assert.ok(calls[0].opts.method === 'POST', 'POST method');
  }).then(() => console.log('PASS testSubmit'));
})();
