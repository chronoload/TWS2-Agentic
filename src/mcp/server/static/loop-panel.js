(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.createLoopPanel = factory().createLoopPanel;
    root.renderTasks = factory().renderTasks;
    root.statusBadge = factory().statusBadge;
    root.renderLoopThread = factory().renderLoopThread;
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
   * - 【会话化】任务可点开 → 像普通会话一样审核：
   *     GET  /api/loop/task/{id}            → 消息流详情
   *     POST /api/loop/task/{id}/message    → 审核介入（追加 user 消息）
   *     POST /api/loop/control              → pause/resume/stop
   *   消息渲染复用 Agent 面板 .agent-msg 样式（气泡 + tool-call 卡片），观感一致。
   *
   * 可注入：fetch / timers / 容器（node 测试用 {innerHTML} 假容器）。
   * 纯函数 renderTasks / statusBadge / renderLoopThread 顶层导出，node 可直接单测。
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

  // ── 会话化：消息流渲染（复用 Agent 面板 .agent-msg 气泡样式 + tool-call 卡片）──
  function _renderToolCalls(toolCalls) {
    if (!toolCalls || !toolCalls.length) return '';
    return toolCalls.map(function (tc) {
      var name = tc && (tc.name || (tc.function && tc.function.name)) || 'tool';
      var args = tc && tc.arguments ? tc.arguments : '';
      if (typeof args !== 'string') args = JSON.stringify(args);
      return '<div class="lp-tool-call">🔧 <code>' + esc(name) + '</code>'
        + (args ? '<pre>' + esc(String(args).slice(0, 300)) + '</pre>' : '')
        + '</div>';
    }).join('');
  }

  function renderLoopThread(messages) {
    if (!messages || !messages.length) return '<div class="lp-empty">（暂无消息）</div>';
    return messages.map(function (m) {
      var role = m.role || 'assistant';
      var ts = m.ts ? '<span class="lp-ts">' + esc(m.ts) + '</span>' : '';
      if (role === 'user') {
        return '<div class="agent-msg agent-msg-user"><div class="lp-role">你</div>'
          + '<div class="lp-body">' + esc(m.content || '') + '</div>' + ts + '</div>';
      }
      if (role === 'tool') {
        var content = m.content == null ? '' : String(m.content);
        return '<div class="lp-tool-card">🔧 tool'
          + (m.tool_call_id ? ' <code>' + esc(m.tool_call_id) + '</code>' : '')
          + '<pre>' + esc(content.slice(0, 600)) + (content.length > 600 ? '…' : '') + '</pre>'
          + ts + '</div>';
      }
      // assistant
      return '<div class="agent-msg"><div class="lp-role">Agent</div>'
        + (m.content ? '<div class="lp-body">' + esc(m.content) + '</div>' : '')
        + _renderToolCalls(m.tool_calls) + ts + '</div>';
    }).join('');
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
        + ' <button class="lp-view" data-view-id="' + esc(t.task_id) + '">👁 审核</button>'
        + '</li>';
    }).join('');
  }

  function createLoopPanel(opts) {
    opts = opts || {};
    var container = opts.container;   // DOM 元素或 {innerHTML} 假容器
    var fetchFn = opts.fetch || (typeof window !== 'undefined' && window.fetch ? window.fetch.bind(window) : null);
    var stateUrl = opts.stateUrl || '/api/loop/state';
    var submitUrl = opts.submitUrl || '/api/loop/submit';
    var controlUrl = opts.controlUrl || '/api/loop/control';
    var intervalMs = opts.intervalMs || 3000;
    var onNotify = opts.onNotify || function () {};
    var scheduler = opts.scheduler || null;   // 外部注入 FrontendScheduler（可测）
    var pollName = null;
    var lastStatusMap = {};
    var openTaskId = null;   // 当前展开审核的任务

    function notify(evtType, taskId) {
      onNotify({ type: evtType, task_id: taskId });
    }

    function fetchJson(url, options) {
      if (!fetchFn) return Promise.reject(new Error('no fetch'));
      return fetchFn(url, options).then(function (res) {
        if (!res.ok) return res.json().then(function (b) {
          throw new Error((b && b.detail) || ('HTTP ' + res.status));
        });
        return res.json();
      });
    }

    // 会话化：打开任务审核视图
    function openTask(taskId) {
      openTaskId = taskId;
      if (!container) return Promise.resolve();
      var detailEl = container.querySelector('.lp-detail');
      if (!detailEl) return Promise.resolve();
      detailEl.innerHTML = '<div class="lp-loading">加载会话…</div>';
      return fetchJson(stateUrl.replace(/\/state$/, '/task/' + encodeURIComponent(taskId)))
        .then(function (task) {
          detailEl.innerHTML = renderDetail(task);
          bindDetailEvents(detailEl);
        })
        .catch(function (e) {
          detailEl.innerHTML = '<div class="lp-error">加载失败：' + esc(e.message || String(e)) + '</div>';
        });
    }

    function renderDetail(task) {
      var canIntervene = task.status === 'pending' || task.status === 'running' || task.status === 'halted';
      var controls = '<span class="lp-ctrl" data-ctrl="pause">⏸ 暂停</span>'
        + '<span class="lp-ctrl" data-ctrl="resume">▶ 继续</span>'
        + '<span class="lp-ctrl" data-ctrl="stop">⏹ 停止</span>';
      return '<div class="lp-detail-head">'
        + statusBadge(task.status)
        + ' <span class="lp-goal">' + esc(task.goal) + '</span>'
        + ' <span class="lp-meta">回合 ' + (task.turn_count || 0) + '/' + (task.max_turns || 30) + '</span>'
        + (task.error ? ' <span class="lp-error">' + esc(task.error) + '</span>' : '')
        + '</div>'
        + '<div class="lp-controls">' + controls + '</div>'
        + '<div class="lp-thread">' + renderLoopThread(task.messages || []) + '</div>'
        + (canIntervene
            ? '<div class="lp-intervene">'
              + '<input class="lp-intervene-input" type="text" placeholder="向 loop 追加指令（审核介入）…" />'
              + '<button class="lp-intervene-send" data-task-id="' + esc(task.task_id) + '">发送</button>'
              + '</div>'
            : '')
        + (task.result ? '<div class="lp-result">✅ 结果：' + esc(task.result) + '</div>' : '');
    }

    function bindDetailEvents(detailEl) {
      if (!detailEl || typeof document === 'undefined') return;
      // 控制按钮
      detailEl.querySelectorAll('.lp-ctrl').forEach(function (el) {
        el.addEventListener('click', function () {
          fetchJson(controlUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: el.getAttribute('data-ctrl') }),
          }).then(function () { refresh(); }).catch(function (e) { showErr(e); });
        });
      });
      // 介入发送
      detailEl.querySelectorAll('.lp-intervene-send').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var input = detailEl.querySelector('.lp-intervene-input');
          var content = (input && input.value || '').trim();
          if (!content) return;
          var tid = btn.getAttribute('data-task-id');
          fetchJson(stateUrl.replace(/\/state$/, '/task/' + encodeURIComponent(tid) + '/message'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content }),
          }).then(function () {
            if (input) input.value = '';
            return openTask(tid);   // 刷新会话视图
          }).then(refresh).catch(function (e) { showErr(e); });
        });
      });
    }

    function showErr(e) {
      if (typeof showToast === 'function') showToast(String(e.message || e), 'error');
    }

    function refresh() {
      if (!fetchFn) return Promise.resolve();
      return fetchJson(stateUrl)
        .then(function (state) {
          if (!container) return;
          var html = '<div class="lp-status">loop: '
            + statusBadge(state.loop_status) + '</div>'
            + '<ul class="lp-list">' + renderTasks(state.tasks || []) + '</ul>'
            + '<div class="lp-detail"></div>';
          container.innerHTML = html;
          bindListEvents();
          // 终态通知（completed/halted/failed）
          (state.tasks || []).forEach(function (t) {
            var prev = lastStatusMap[t.task_id];
            if (prev && prev !== t.status &&
                (t.status === 'completed' || t.status === 'halted' || t.status === 'failed')) {
              notify(t.status, t.task_id);
            }
            lastStatusMap[t.task_id] = t.status;
          });
          // 保持已打开的任务展开
          if (openTaskId) {
            var task = (state.tasks || []).filter(function (t) { return t.task_id === openTaskId; })[0];
            if (task) {
              container.querySelector('.lp-detail').innerHTML = renderDetail(task);
              bindDetailEvents(container.querySelector('.lp-detail'));
            }
          }
        })
        .catch(function () { /* 后端未响应：跳过本轮（公交误点语义） */ });
    }

    function bindListEvents() {
      if (!container || typeof document === 'undefined') return;
      container.querySelectorAll('.lp-view').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          openTask(btn.getAttribute('data-view-id'));
        });
      });
    }

    function submit(goal) {
      if (!fetchFn) return Promise.resolve(null);
      return fetchJson(submitUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal }),
      })
        .then(function (data) { return data.task_id || null; })
        .catch(function () { return null; });
    }

    function mount() {
      // 构建面板骨架（提交框 + 列表容器 + 会话详情容器）
      if (container) {
        container.innerHTML = '<div class="lp-root">'
          + '<div class="lp-form">'
          + '<input class="lp-input" type="text" placeholder="输入长程任务目标…" />'
          + '<button class="lp-submit-btn">提交</button>'
          + '</div>'
          + '<div class="lp-body">'
          + '<div class="lp-status">loop: ' + statusBadge('idle') + '</div>'
          + '<ul class="lp-list"></ul>'
          + '<div class="lp-detail"></div>'
          + '</div>'
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

    return { mount: mount, refresh: refresh, submit: submit, openTask: openTask, destroy: destroy };
  }

  return { createLoopPanel: createLoopPanel, renderTasks: renderTasks, statusBadge: statusBadge, renderLoopThread: renderLoopThread };
});