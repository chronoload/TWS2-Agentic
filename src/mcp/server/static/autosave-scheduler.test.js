const assert = require('assert');
const createAutoSaveScheduler = require('./autosave-scheduler.js');

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
function makeSaveCounter() {
  const calls = [];
  return { calls, fn: (scope, id) => calls.push([scope, id]) };
}

(function testDebounceCoalesces() {
  const t = makeFakeTimers();
  const s = makeSaveCounter();
  const sched = createAutoSaveScheduler({ debounceMs: 1500, intervalMs: 30000, performSave: s.fn, flushAll: () => {}, timers: t });
  sched.schedule('main');
  sched.schedule('main');
  assert.strictEqual(s.calls.length, 0, 'debounced: no call before timer fires');
  assert.strictEqual(t.timeoutCount(), 1, 'only one pending timer');
  t.runTimeouts();
  assert.strictEqual(s.calls.length, 1, 'fired exactly once');
  assert.deepStrictEqual(s.calls[0], ['main', undefined]);
  console.log('PASS testDebounceCoalesces');
})();

(function testFlushImmediate() {
  const t = makeFakeTimers();
  const s = makeSaveCounter();
  const sched = createAutoSaveScheduler({ debounceMs: 1500, intervalMs: 30000, performSave: s.fn, flushAll: () => {}, timers: t });
  sched.schedule('pane', '2');
  sched.flush('pane', '2');
  assert.strictEqual(s.calls.length, 1, 'flush calls performSave immediately');
  assert.deepStrictEqual(s.calls[0], ['pane', '2']);
  assert.strictEqual(t.timeoutCount(), 0, 'pending timer cleared after flush');
  t.runTimeouts();
  assert.strictEqual(s.calls.length, 1, 'no extra call after flush');
  console.log('PASS testFlushImmediate');
})();

(function testIntervalCallsFlushAll() {
  const t = makeFakeTimers();
  let flushAllCalls = 0;
  const sched = createAutoSaveScheduler({ debounceMs: 1500, intervalMs: 30000, performSave: () => {}, flushAll: () => { flushAllCalls++; }, timers: t });
  sched.start();
  assert.strictEqual(t.intervalCount(), 1, 'interval registered');
  assert.strictEqual(sched.isRunning(), true);
  t.runIntervals();
  assert.strictEqual(flushAllCalls, 1, 'flushAll called on interval');
  sched.stop();
  assert.strictEqual(sched.isRunning(), false);
  assert.strictEqual(t.intervalCount(), 0, 'interval cleared after stop');
  console.log('PASS testIntervalCallsFlushAll');
})();
