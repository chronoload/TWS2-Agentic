(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.createLoopPanel = factory().createLoopPanel;
    root.renderTasks = factory().renderTasks;
    root.statusBadge = factory().statusBadge;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /**
   * LoopPanel —— AgentLoop 前端面板组件（UMD，自包含）
   *
   * 能力：
   * - 提交长程任务（POST /api/loop/submit）
   * - 轮询任务状态（用 FrontendScheduler.pollState 定时刷新）
   * - 任务列表渲染（status/turn_count/result）+ 完成/挂起通知回调
   *
   * 可注入：fetch / timers / 容器（node 测试用 {innerHTML} 假容器）。
   * 纯函数 renderTasks / statusBadge 顶层导出，node 可直接单测。
   */

  var STATUS_META = {
    pending:   { icon: '⏳', cls: 'lp-pending' },
    running:   { icon: '🔄', cls: 'lp-running' },
    completed: { icon: '✅', cls: 'lp-completed' },
    failed:    { icon: '❌', cls: 'lp-failed' },
    halted:    { icon: '⏸️', cls: 'lp-halted' },
  };

  function statusBadge(status) {
    var meta = STATUS_META[status] || { icon: '❔', cls: 'lp-unknown' };
    return '<span class="lp-badge ' + meta.cls + '">' + meta.icon + ' ' + status + '</span>';
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderTasks(tasks) {
    if (!tasks || tasks.length === 0) return '';
    return tasks.map(function (t) {
      return '<li class="lp-task" data-task-id="' + esc(t.task_id) + '">'
        + statusBadge(t.status)
        + ' <span class="lp-goal">' + esc(t.goal) + '</span>'
        + ' <span class="lp-meta">回合 ' + (t.turn_count || 0) + '/' + (t.max_turns || 30) + '</span>'
        + (t.result ? ' <span class="lp-result">' + esc(t.result) + '</span>' : '')
        + (t.error ? ' <span class="lp-error">' + esc(t.error) + '</span>' : '')
        + '</li>';
    }).join('');
  }

  function createLoopPanel(opts) {
    opts = opts || {};
    var container = opts.container;   // DOM 元素或 {innerHTML} 假容器
    var fetchFn = opts.fetch || (typeof window !== 'undefined' && window.fetch ? window.fetch.bind(window) : null);
    var stateUrl = opts.stateUrl || '/api/loop/state';
    var submitUrl = opts.submitUrl || '/api/loop/submit';
    var intervalMs = opts.intervalMs || 3000;
    var onNotify = opts.onNotify || function () {};
    var scheduler = opts.scheduler || null;   // 外部注入 FrontendScheduler（可测）
    var pollName = null;
    var lastStatusMap = {};

    function notify(evtType, taskId) {
      onNotify({ type: evtType, task_id: taskId });
    }

    function refresh() {
      if (!fetchFn) return Promise.resolve();
      return fetchFn(stateUrl)
        .then(function (res) { return res.json(); })
        .then(function (state) {
          if (!container) return;
          var html = '<div class="lp-status">loop: '
            + statusBadge(state.loop_status) + '</div>'
            + '<ul class="lp-list">' + renderTasks(state.tasks || []) + '</ul>';
          container.innerHTML = html;
          // 终态通知（completed/halted/failed）
          (state.tasks || []).forEach(function (t) {
            var prev = lastStatusMap[t.task_id];
            if (prev && prev !== t.status &&
                (t.status === 'completed' || t.status === 'halted' || t.status === 'failed')) {
              notify(t.status, t.task_id);
            }
            lastStatusMap[t.task_id] = t.status;
          });
        })
        .catch(function () { /* 后端未响应：跳过本轮（公交误点语义） */ });
    }

    function submit(goal) {
      if (!fetchFn) return Promise.resolve(null);
      return fetchFn(submitUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal }),
      })
        .then(function (res) { return res.json(); })
        .then(function (data) { return data.task_id || null; })
        .catch(function () { return null; });
    }

    function mount() {
      // 构建面板骨架（提交框 + 列表容器）
      if (container) {
        container.innerHTML = '<div class="lp-root">'
          + '<div class="lp-form">'
          + '<input class="lp-input" type="text" placeholder="输入长程任务目标…" />'
          + '<button class="lp-submit-btn">提交</button>'
          + '</div>'
          + '<div class="lp-body"></div>'
          + '</div>';
      }
      // 绑定提交事件（浏览器环境）
      if (container && typeof document !== 'undefined' && document.addEventListener) {
        var input = container.querySelector('.lp-input');
        var btn = container.querySelector('.lp-submit-btn');
        function doSubmit() {
          var goal = (input && input.value || '').trim();
          if (!goal) return;
          submit(goal).then(function () { if (input) input.value = ''; refresh(); });
        }
        if (btn) btn.addEventListener('click', doSubmit);
        if (input) input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') doSubmit();
        });
      }
      // 启动轮询（用外部 scheduler 或内部创建 FrontendScheduler）
      var sched = scheduler;
      if (!sched && typeof createFrontendScheduler !== 'undefined') {
        sched = createFrontendScheduler(opts);
      }
      if (sched && typeof sched.pollState === 'function') {
        pollName = sched.pollState(stateUrl, intervalMs, { onData: function () { refresh(); } });
      } else {
        refresh(); // 无 scheduler 时至少刷一次
      }
      return refresh();
    }

    function destroy() {
      if (scheduler && pollName && typeof scheduler.unregister === 'function') {
        scheduler.unregister(pollName);
      }
      if (container) container.innerHTML = '';
    }

    return { mount: mount, refresh: refresh, submit: submit, destroy: destroy };
  }

  return { createLoopPanel: createLoopPanel, renderTasks: renderTasks, statusBadge: statusBadge };
});
