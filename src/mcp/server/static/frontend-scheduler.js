(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.createFrontendScheduler = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /**
   * FrontendScheduler —— 前端定时任务框架（浏览器/Node 通用，UMD）
   *
   * 能力：注册/注销定时任务、单任务暂停恢复、全局停止、后端端点轮询器。
   * 设计（langdriven）：
   * - 注册表 + 调度器：每个任务一个 setInterval，tick 检查 enabled flag；
   * - 可注入 timers / fetch（测试确定性，沿用 autosave-scheduler 模式）；
   * - pollState = "公交发车间隔表"：误点（后端未响应）则跳过本轮不等。
   */
  function createFrontendScheduler(opts) {
    opts = opts || {};
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
    var fetchFn = opts.fetch || (typeof g.fetch === 'function' ? g.fetch.bind(g) : null);
    var tasks = {};          // name -> {name, fn, intervalMs, handle, enabled}
    var pollSeq = 0;

    function register(name, fn, intervalMs) {
      if (tasks[name]) unregister(name);
      var handle = T.setInterval(function tick() {
        var task = tasks[name];
        if (!task || !task.enabled) return;
        try { task.fn({ name: task.name, intervalMs: task.intervalMs }); }
        catch (e) { /* 单次 tick 异常不影响调度器 */ }
      }, intervalMs);
      tasks[name] = { name: name, fn: fn, intervalMs: intervalMs, handle: handle, enabled: true };
      return name;
    }

    function unregister(name) {
      var task = tasks[name];
      if (!task) return false;
      T.clearInterval(task.handle);
      delete tasks[name];
      return true;
    }

    function pause(name) {
      var task = tasks[name];
      if (task) task.enabled = false;
      return !!task;
    }

    function resume(name) {
      var task = tasks[name];
      if (task) task.enabled = true;
      return !!task;
    }

    function stop() {
      Object.keys(tasks).forEach(function (name) { unregister(name); });
    }

    function tasksList() {
      return Object.keys(tasks).map(function (name) {
        var t = tasks[name];
        return { name: t.name, intervalMs: t.intervalMs, enabled: t.enabled };
      });
    }

    /**
     * pollState —— 定时轮询后端状态端点。
     * 返回任务名（可用于 unregister/pause/resume）。
     * @param {string} url 轮询端点
     * @param {number} intervalMs 轮询间隔（毫秒）
     * @param {object} o { onData(data), onError(err), name }
     */
    function pollState(url, intervalMs, o) {
      o = o || {};
      var name = o.name || ('poll-' + (++pollSeq));
      register(name, function () {
        if (!fetchFn) return;
        fetchFn(url)
          .then(function (res) { return res.json(); })
          .then(function (data) { if (o.onData) o.onData(data); })
          .catch(function (err) { if (o.onError) o.onError(err); });
      }, intervalMs);
      return name;
    }

    return {
      register: register,
      unregister: unregister,
      pause: pause,
      resume: resume,
      stop: stop,
      tasks: tasksList,
      pollState: pollState
    };
  }
  return createFrontendScheduler;
});
