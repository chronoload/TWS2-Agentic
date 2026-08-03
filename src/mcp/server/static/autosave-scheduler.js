(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.createAutoSaveScheduler = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  function key(scope, id) { return scope + ':' + (id == null ? '' : id); }
  function createAutoSaveScheduler(opts) {
    var debounceMs = opts.debounceMs || 1500;
    var intervalMs = opts.intervalMs || 30000;
    var performSave = opts.performSave;
    var flushAll = opts.flushAll;
    var g = (typeof window !== 'undefined') ? window
          : (typeof self !== 'undefined') ? self
          : (typeof globalThis !== 'undefined') ? globalThis
          : this;
    var T = opts.timers || {
      setTimeout: g.setTimeout.bind(g),
      clearTimeout: g.clearTimeout.bind(g),
      setInterval: g.setInterval.bind(g),
      clearInterval: g.clearInterval.bind(g)
    };
    var pending = {};
    var intervalHandle = null;
    function clearPending(k) { if (pending[k] != null) { T.clearTimeout(pending[k]); pending[k] = null; } }
    function schedule(scope, id) {
      var k = key(scope, id);
      clearPending(k);
      pending[k] = T.setTimeout(function () { pending[k] = null; performSave(scope, id); }, debounceMs);
    }
    function flush(scope, id) {
      var k = key(scope, id);
      clearPending(k);
      performSave(scope, id);
    }
    function start() { if (intervalHandle != null) return; intervalHandle = T.setInterval(function () { flushAll(); }, intervalMs); }
    function stop() {
      if (intervalHandle != null) { T.clearInterval(intervalHandle); intervalHandle = null; }
      Object.keys(pending).forEach(clearPending);
    }
    function isRunning() { return intervalHandle != null; }
    function pendingKeys() { return Object.keys(pending).filter(function (k) { return pending[k] != null; }); }
    return { schedule: schedule, flush: flush, start: start, stop: stop, isRunning: isRunning, pendingKeys: pendingKeys };
  }
  return createAutoSaveScheduler;
});
