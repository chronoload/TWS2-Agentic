// FrontendScheduler T3(P2) 测试：register/unregister/pause/resume/pollState
// 运行: node mcp/server/static/frontend-scheduler.test.js
const assert = require('assert');
const createFrontendScheduler = require('./frontend-scheduler.js');

function makeFakeTimers() {
  const timeouts = new Map();
  const intervals = new Map();
  let tid = 0;
  return {
    setTimeout(fn) { const id = ++tid; timeouts.set(id, fn); return id; },
    clearTimeout(id) { timeouts.delete(id); },
    setInterval(fn) { const id = ++tid; intervals.set(id, fn); return id; },
    clearInterval(id) { intervals.delete(id); },
    runTimeouts() { for (const fn of [...timeouts.values()]) fn(); timeouts.clear(); },
    runIntervals() { for (const fn of [...intervals.values()]) fn(); },
    intervalCount() { return intervals.size; },
    timeoutCount() { return timeouts.size; },
  };
}
function makeCounter() {
  const calls = [];
  return { calls, fn: (ctx) => calls.push(ctx) };
}

// ── 1) register：注册即建 interval，tick 触发回调 ──
(function testRegisterFiresOnInterval() {
  const t = makeFakeTimers();
  const c = makeCounter();
  const sched = createFrontendScheduler({ timers: t });
  sched.register('poll-state', c.fn, 30000);
  assert.strictEqual(t.intervalCount(), 1, 'interval registered');
  assert.strictEqual(sched.tasks().length, 1, 'one task listed');
  assert.strictEqual(c.calls.length, 0, 'no fire before tick');
  t.runIntervals();
  assert.strictEqual(c.calls.length, 1, 'fired once on interval');
  t.runIntervals();
  assert.strictEqual(c.calls.length, 2, 'fired again on next interval');
  sched.stop();
  assert.strictEqual(t.intervalCount(), 0, 'all intervals cleared on stop');
  console.log('PASS testRegisterFiresOnInterval');
})();

// ── 2) unregister：注销即停，不再触发 ──
(function testUnregisterStopsTask() {
  const t = makeFakeTimers();
  const c = makeCounter();
  const sched = createFrontendScheduler({ timers: t });
  sched.register('a', c.fn, 1000);
  sched.register('b', c.fn, 2000);
  assert.strictEqual(t.intervalCount(), 2, 'two intervals');
  sched.unregister('a');
  assert.strictEqual(t.intervalCount(), 1, 'one interval after unregister');
  assert.strictEqual(sched.tasks().length, 1, 'one task left');
  t.runIntervals();
  assert.strictEqual(c.calls.length, 1, 'only remaining task fired');
  sched.stop();
  console.log('PASS testUnregisterStopsTask');
})();

// ── 3) pause/resume：暂停不触发，恢复继续 ──
(function testPauseResume() {
  const t = makeFakeTimers();
  const c = makeCounter();
  const sched = createFrontendScheduler({ timers: t });
  sched.register('x', c.fn, 1000);
  sched.pause('x');
  t.runIntervals();
  assert.strictEqual(c.calls.length, 0, 'paused: no fire');
  sched.resume('x');
  t.runIntervals();
  assert.strictEqual(c.calls.length, 1, 'resumed: fires');
  sched.stop();
  console.log('PASS testPauseResume');
})();

// ── 4) pollState：定时轮询后端端点（fake fetch 可测）──
(function testPollState() {
  const t = makeFakeTimers();
  const fetched = [];
  const fakeFetch = (url) => {
    fetched.push(url);
    return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
  };
  const sched = createFrontendScheduler({ timers: t, fetch: fakeFetch });
  const name = sched.pollState('/api/loop/state', 5000, { onData: () => {} });
  assert.strictEqual(typeof name, 'string', 'pollState returns task name');
  t.runIntervals();
  assert.deepStrictEqual(fetched, ['/api/loop/state'], 'fetch called with endpoint');
  sched.stop();
  console.log('PASS testPollState');
})();

// ── 5) 注入自定义 timers 的确定性（无真实计时器泄漏）──
(function testNoRealTimersLeak() {
  const t = makeFakeTimers();
  const c = makeCounter();
  const sched = createFrontendScheduler({ timers: t });
  sched.register('leak', c.fn, 1000);
  sched.stop();
  assert.strictEqual(t.intervalCount(), 0, 'no leak after stop');
  console.log('PASS testNoRealTimersLeak');
})();
