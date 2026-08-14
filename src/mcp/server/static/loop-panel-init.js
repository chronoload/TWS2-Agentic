/* LoopPanel 兜底引导：集成进"发现面板"（Skill/Tool/MCP/Workflow/Plugin/Loop）

app.js 的 `_renderDiscoverList` 已含 loop 分支 + `_mountLoopPanelInDiscover`（首选路径）。
本脚本仅作兜底：
- 若发现面板缺 Loop tab → 补加；
- 若用户切到 Loop tab 但 app.js 未挂载面板（旧版 app.js）→ 自行注入骨架 + 挂载。
两路径幂等，互不冲突。
*/
(function () {
  'use strict';

  function ensureLoopTab() {
    var tabs = document.getElementById('discoverTabs');
    if (!tabs) return false;
    if (tabs.querySelector('.discover-tab[data-tab="loop"]')) return true;
    var tab = document.createElement('div');
    tab.className = 'discover-tab';
    tab.dataset.tab = 'loop';
    tab.title = 'AgentLoop 长程任务';
    tab.textContent = 'Loop';
    tab.style.cssText = 'flex:1;text-align:center;padding:6px 0;cursor:pointer;color:var(--fg-muted);border-bottom:2px solid transparent';
    tabs.appendChild(tab);
    return true;
  }

  function mountFallback() {
    if (typeof createLoopPanel === 'undefined') return;
    if (window._loopPanelInDiscover) return;          // app.js 已挂载
    var wrap = document.getElementById('loopListWrap');
    if (!wrap) return;                                 // 骨架不存在（未切到 loop tab / 已切走）
    // 注入骨架（若 app.js 未渲染）
    if (!document.getElementById('loopGoalInput')) {
      wrap.parentNode.innerHTML = '<div class="lp-root" style="padding:8px 12px">'
        + '<div class="lp-form" style="display:flex;gap:6px;margin-bottom:8px">'
        + '<input id="loopGoalInput" type="text" placeholder="输入长程任务目标…（提交后后台自主执行）" '
        + 'style="flex:1;padding:4px 8px;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:4px;color:var(--fg);font-size:11px;outline:none"/>'
        + '<button id="loopSubmitBtn" style="padding:4px 10px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px">提交</button>'
        + '</div><div id="loopListWrap"></div></div>';
      wrap = document.getElementById('loopListWrap');
    }
    var sched = (typeof createFrontendScheduler !== 'undefined') ? createFrontendScheduler() : null;
    var panel = createLoopPanel({ container: wrap, scheduler: sched, stateUrl: '/api/loop/state', submitUrl: '/api/loop/submit', intervalMs: 3000 });
    window._loopPanelInDiscover = panel;
    panel.refresh();
    var btn = document.getElementById('loopSubmitBtn');
    var input = document.getElementById('loopGoalInput');
    var doSubmit = function () {
      var goal = (input && input.value || '').trim();
      if (!goal) return;
      panel.submit(goal).then(function () { if (input) input.value = ''; panel.refresh(); });
    };
    if (btn) btn.addEventListener('click', doSubmit);
    if (input) input.addEventListener('keydown', function (e) { if (e.key === 'Enter') doSubmit(); });
  }

  function boot() {
    if (typeof document === 'undefined') return;
    if (!ensureLoopTab()) return;
    // 捕获阶段监听 Loop tab 点击 → 延迟后兜底挂载（app.js 新版已挂载则跳过）
    document.addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== document.body) {
        if (el.classList && el.classList.contains('discover-tab') && el.dataset.tab === 'loop') {
          setTimeout(mountFallback, 80);
          return;
        }
        el = el.parentNode;
      }
    }, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
