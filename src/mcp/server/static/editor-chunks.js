/* editor-chunks.js - 超长文本动态递归分割编辑模块（独立于 app.js）
 *
 * 模型：不预先分割正文。load 时只扫描标题行（H1-H4，围栏感知）建立一棵
 *       轻量索引树，每个节点记录其在原始文本中的 [start, end) 区间。
 *
 *   - 拓扑子集：父节点区间完全包含子节点区间；任意节点的完整文本 =
 *     src.slice(node.start, node.end)，一次连续切片，无需拼接。
 *   - 动态递归分割：提交某个节点时把它编辑后的文本写回 src，随即重扫该
 *     文本重新构建子树；下次就能选中新出现的子块。H1 整段可直接选中编辑，
 *     也可继续展开到 H2 / H3 逐级编辑。
 *   - 编辑单元 = 树上当前节点（可大可小），Vditor 始终只渲染活跃节点的切片。
 *
 * 宿主对接（window.EditorChunks）：
 *   attach(adapter)     注入适配器（getVditor / getActivePath / getEditorSource /
 *                       setValue / promptTitle / onStateChange）
 *   load(src)           载入完整 editor-source；命中阈值则建树并渲染首个节点
 *   read() / notifyInput()  提交活跃节点并返回完整 editor-source（未启用返回 null）
 *   toggle()            手动开/关分块
 *   gotoBlock(i) / prevBlock() / nextBlock()
 *   renderOutline(el)   渲染树状大纲（可折叠；未启用返回 false）
 *   addSection(title, afterIdx)  在节点后插入新标题节
 *   scrollToHeading(title)  在当前节点内定位标题
 *   takeFull()          提交 + 关闭分块，返回完整文本
 *   isEnabled() / getBlockCount() / getActiveIdx() / setAutoFollow()
 *   splitBlocks / assemble / subHeadings / shouldChunk  纯函数，可独立测试
 *
 * 依赖：Vditor（全局，outlineRender 可选）。宿主保证传入 src 已是 editor-source。
 */
(function (global) {
  'use strict';

  var CONFIG = {
    minLength: 15000, // 字符数达到该值才考虑启用
    minH2: 3          // 标题数达到该值才启用
  };

  var adapter = null;
  var chunk = {
    active: false,    // 是否处于分块模式
    path: null,       // 对应文件路径
    yamlPrefix: '',   // 文档开头的 YAML frontmatter（原样保留，不进入分块树）
    src: '',          // 去除 YAML 后的完整 editor-source（内存中的唯一正文）
    tree: null,       // 索引树根节点 {level, heading, start, end, subs, parent}
    flat: [],         // 前序遍历节点数组（每个节点带 _fi 序号）
    activeIdx: 0      // flat 中的活跃节点序号
  };

  var TITLE_RE = /^(#{1,4})\s+(.+?)\s*$/;

  // 分块大纲绑定的容器（用于 disable 时清理捕获监听器）
  var _outlineContainer = null;

  /* ================= 纯函数（可独立测试） ================= */

  // 提取文档开头 YAML front matter（`---` 起止）。返回 {prefix, body}：
  // prefix 为含末尾换行的原始 YAML 块（若存在），body 为去掉前缀后的正文。
  // 不匹配或非字符串时返回 { prefix: '', body: text }。
  function extractYamlFrontmatter(text) {
    if (typeof text !== 'string') return { prefix: '', body: text };
    var m = /^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
    if (!m) return { prefix: '', body: text };
    return { prefix: m[0], body: text.slice(m[0].length) };
  }

  // 扫描标题行，返回 [{offset, level, heading}]；围栏（``` ```）内的行忽略
  function scanTitles(text) {
    var out = [];
    if (typeof text !== 'string') return out;
    var lines = text.split('\n');
    var offset = 0;
    var fence = null;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var fm = /^(`{3,})/.exec(line);
      if (fm) {
        if (fence === null) fence = fm[1].length;
        else if (fm[1].length >= fence && /^`{3,}\s*$/.test(line)) fence = null;
      } else if (fence === null) {
        var tm = TITLE_RE.exec(line);
        if (tm) out.push({ offset: offset, level: tm[1].length, heading: tm[2].trim() });
      }
      offset += line.length + 1;
    }
    return out;
  }

  // 根据标题列表构建索引树。根节点 level=0，覆盖整个文本。
  // 每个标题节点的 end = 其右侧第一个 level<=自己的标题 offset，否则文本末尾，
  // 从而保证父区间包含全部子区间（拓扑子集）。
  function buildTree(text, titles) {
    var len = (typeof text === 'string') ? text.length : 0;
    titles = titles || [];
    var n = titles.length;

    var ends = new Array(n);
    var st = [];
    for (var i = n - 1; i >= 0; i--) {
      while (st.length && titles[st[st.length - 1]].level > titles[i].level) st.pop();
      ends[i] = st.length ? titles[st[st.length - 1]].offset : len;
      st.push(i);
    }

    var nodes = [];
    for (var k = 0; k < n; k++) {
      nodes.push({
        level: titles[k].level,
        heading: titles[k].heading,
        start: titles[k].offset,
        end: ends[k],
        subs: [],
        parent: null
      });
    }

    var root = { level: 0, heading: null, start: 0, end: len, subs: [], parent: null };
    var stack = [root];
    for (var j = 0; j < nodes.length; j++) {
      var nd = nodes[j];
      while (stack[stack.length - 1].level >= nd.level) stack.pop();
      var p = stack[stack.length - 1];
      nd.parent = p;
      p.subs.push(nd);
      stack.push(nd);
    }
    return root;
  }

  // 前序遍历，把整棵树拍平成节点数组
  function flatten(node, out) {
    out = out || [];
    out.push(node);
    for (var i = 0; i < node.subs.length; i++) flatten(node.subs[i], out);
    return out;
  }

  // 树根节点（兼容旧 API 名；正文用 assemble 取）
  function splitBlocks(text) {
    if (typeof text !== 'string') return null;
    return buildTree(text, scanTitles(text));
  }

  // 取节点完整文本：src 的一次连续切片
  function nodeText(node, src) {
    if (!node || typeof src !== 'string') return '';
    return src.slice(node.start, node.end);
  }

  // 树根 -> 整棵文本（兼容旧 API 名）
  function assemble(root, src) {
    return nodeText(root, src);
  }

  // 节点的直接子标题列表
  function subHeadings(node) {
    return (node && node.subs) ? node.subs : [];
  }

  // 是否命中启用阈值：长度 + 标题数（YAML 块不计入标题）
  function shouldChunk(text) {
    if (typeof text !== 'string' || text.length < CONFIG.minLength) return false;
    var y = extractYamlFrontmatter(text);
    return scanTitles(y.body).length >= CONFIG.minH2;
  }

  /* ================= Vditor 访问 ================= */

  function getVditor() {
    if (!adapter || typeof adapter.getVditor !== 'function') return null;
    try { return adapter.getVditor(); } catch (e) { return null; }
  }

  function modeElement(vd) {
    try {
      var v = vd.vditor;
      if (v && v.currentMode && v[v.currentMode] && v[v.currentMode].element) {
        return v[v.currentMode].element;
      }
    } catch (e) {}
    return null;
  }

  /* ================= 索引维护 ================= */

  function rebuildIndex() {
    chunk.tree = splitBlocks(chunk.src);
    chunk.flat = [];
    if (chunk.tree) flatten(chunk.tree, chunk.flat);
    for (var i = 0; i < chunk.flat.length; i++) chunk.flat[i]._fi = i;
  }

  function activeNode() {
    return chunk.flat[chunk.activeIdx] || null;
  }

  // 把编辑后的文本写回 src 的 [start,end) 区间，然后重建整棵索引树，
  // 并尽量按 heading 路径重新定位到原节点（文本变化后旧节点对象失效）。
  function commitActive() {
    if (!chunk.active || !chunk.src) return;
    var vd = getVditor();
    if (!vd) return;
    var node = activeNode();
    if (!node) return;
    var after;
    try { after = vd.getValue(); } catch (e) { return; }
    var before = chunk.src.slice(node.start, node.end);
    if (after === before) return;
    // Vditor 刚初始化（after 钩子中）getValue() 返回空，但 before 非空时不应覆盖，
    // 否则 takeFull 会把当前块清空导致内容丢失
    if (!after && before) return;

    var path = [];
    for (var p = node; p && p.level > 0; p = p.parent) path.unshift(p.heading);

    chunk.src = chunk.src.slice(0, node.start) + after + chunk.src.slice(node.end);
    rebuildIndex();

    var cur = chunk.tree;
    for (var i = 0; i < path.length && cur; i++) {
      var nxt = null;
      for (var j = 0; j < cur.subs.length; j++) {
        if (cur.subs[j].heading === path[i]) { nxt = cur.subs[j]; break; }
      }
      if (!nxt) break;
      cur = nxt;
    }
    if (cur && cur._fi != null) chunk.activeIdx = cur._fi;
    else chunk.activeIdx = 0;
  }

  /* ================= 编辑流程 ================= */

  function renderActive() {
    var vd = getVditor();
    if (!vd) return;
    var node = activeNode();
    if (!node) return;
    chunk.activeIdx = node._fi != null ? node._fi : 0;
    var text = chunk.src.slice(node.start, node.end);
    try { vd.setValue(text); } catch (e) {}
    var el = modeElement(vd);
    if (el) {
      bindScroll(el);
      try { el.scrollTop = 0; } catch (e) {}
    }
    _lastSwitchAt = Date.now();
    _lastTop = 0;
    notifyState();
  }

  function enable(src) {
    chunk.active = true;
    chunk.path = (adapter && typeof adapter.getActivePath === 'function') ? adapter.getActivePath() : null;
    var y = extractYamlFrontmatter(src);
    chunk.yamlPrefix = y.prefix;
    chunk.src = y.body;
    rebuildIndex();
    chunk.activeIdx = chunk.flat.length > 1 ? 1 : 0;
    renderActive();
  }

  function disable() {
    // 清理分块大纲绑定的捕获监听器，避免切回未分块后残留拦截
    if (_outlineContainer && _outlineContainer._ecOutlineHandler) {
      try {
        _outlineContainer.removeEventListener('click', _outlineContainer._ecOutlineHandler, true);
      } catch (e) {}
      _outlineContainer._ecOutlineHandler = null;
    }
    _outlineContainer = null;
    // 清理 bindScroll 绑定的 wheel/scroll 监听器
    if (_boundEl) {
      try { _boundEl.removeEventListener('wheel', onWheel); } catch (e) {}
      try { _boundEl.removeEventListener('scroll', onScroll); } catch (e) {}
      _boundEl = null;
    }
    chunk.active = false;
    chunk.path = null;
    chunk.yamlPrefix = '';
    chunk.src = '';
    chunk.tree = null;
    chunk.flat = [];
    chunk.activeIdx = 0;
    notifyState();
  }

  function notifyState() {
    if (adapter && typeof adapter.onStateChange === 'function') {
      try { adapter.onStateChange(); } catch (e) {}
    }
  }

  /* ================= 滚动喂给：Shift+滚轮切节点 ================= */

  var _boundEl = null;
  var _lastSwitchAt = 0;
  var _lastTop = 0;
  var _autoFollow = true;
  var _shiftHeld = false;
  var _shiftBound = false;

  function trackShift() {
    var w = typeof window !== 'undefined' ? window : null;
    if (!w || !w.addEventListener || _shiftBound) return;
    _shiftBound = true;
    w.addEventListener('keydown', function (e) {
      if (e && e.shiftKey) _shiftHeld = true;
    });
    w.addEventListener('keyup', function (e) {
      if (e && !e.shiftKey) _shiftHeld = false;
    });
    w.addEventListener('blur', function () { _shiftHeld = false; });
  }

  function bindScroll(el) {
    if (!el || el === _boundEl) return;
    // 先清理旧元素上的监听器，避免累积
    if (_boundEl) {
      try { _boundEl.removeEventListener('wheel', onWheel); } catch (e) {}
      try { _boundEl.removeEventListener('scroll', onScroll); } catch (e) {}
    }
    _boundEl = el;
    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('scroll', onScroll);
  }

  function scrollState(el) {
    var top = el.scrollTop || 0;
    var client = el.clientHeight || 0;
    var height = el.scrollHeight || 0;
    var scrollable = height > client + 4;
    return {
      top: top,
      scrollable: scrollable,
      atTop: !scrollable || top <= 40,
      atBottom: !scrollable || top + client >= height - 40
    };
  }

  function onWheel(e) {
    var el = _boundEl;
    if (!_autoFollow || !_shiftHeld || !chunk.active || !chunk.flat.length || !el) return;
    var deltaY = (e && e.deltaY) || 0;
    if (!deltaY) return;
    var now = Date.now();
    if (now - _lastSwitchAt < 600) return;
    var st = scrollState(el);
    if (deltaY > 0 && st.atBottom && chunk.activeIdx < chunk.flat.length - 1) {
      _lastSwitchAt = now;
      _lastTop = st.top;
      api.gotoBlock(chunk.activeIdx + 1);
      if (e && e.preventDefault) e.preventDefault();
    } else if (deltaY < 0 && st.atTop && chunk.activeIdx > 0) {
      _lastSwitchAt = now;
      _lastTop = st.top;
      api.gotoBlock(chunk.activeIdx - 1);
      if (e && e.preventDefault) e.preventDefault();
    }
  }

  function onScroll() {
    var el = _boundEl;
    if (!_autoFollow || !_shiftHeld || !chunk.active || !chunk.flat.length || !el) return;
    var now = Date.now();
    if (now - _lastSwitchAt < 600) return;
    var st = scrollState(el);
    var top = st.top;
    var prevTop = _lastTop;
    _lastTop = top;
    if (st.atTop && prevTop > 40 && chunk.activeIdx > 0) {
      _lastSwitchAt = now;
      api.gotoBlock(chunk.activeIdx - 1);
      return;
    }
    if (st.atBottom && chunk.activeIdx < chunk.flat.length - 1) {
      _lastSwitchAt = now;
      api.gotoBlock(chunk.activeIdx + 1);
    }
  }

  /* ================= 公共 API ================= */

  var api = {

    attach: function (a) { adapter = a || null; trackShift(); },

    // 宿主 setEditorContent 调用；返回是否启用了分块
    load: function (src) {
      disable();
      if (typeof src !== 'string' || !shouldChunk(src)) return false;
      enable(src);
      return chunk.active;
    },

    // 宿主 getEditorContent 调用；返回完整 editor-source（未启用返回 null）
    read: function () {
      if (!chunk.active) return null;
      commitActive();
      return chunk.yamlPrefix + chunk.src;
    },

    // 宿主 input 回调调用；返回完整 editor-source（未启用返回 null）
    notifyInput: function () {
      if (!chunk.active) return null;
      commitActive();
      return chunk.yamlPrefix + chunk.src;
    },

    toggle: function () {
      if (chunk.active) {
        commitActive();
        var full = chunk.yamlPrefix + chunk.src;
        // 先写回完整内容，再关闭分块触发 onStateChange，
        // 否则切回时大纲会在 Vditor 仍是分块文本时被重绘（残留旧内容）
        if (adapter && typeof adapter.setValue === 'function') {
          try { adapter.setValue(full); } catch (e) {}
        }
        disable();
      } else {
        if (!adapter || typeof adapter.getEditorSource !== 'function') return;
        var src;
        try { src = adapter.getEditorSource(); } catch (e) { return; }
        if (src == null) return;
        if (typeof src !== 'string' || !shouldChunk(src)) return;
        enable(src);
      }
    },

    gotoBlock: function (idx) {
      if (!chunk.active || !chunk.flat.length) return;
      if (idx < 0 || idx >= chunk.flat.length) return;
      if (idx === chunk.activeIdx) {
        var vd = getVditor();
        var el = modeElement(vd);
        if (el) { try { el.scrollTop = 0; } catch (e) {} }
        return;
      }
      commitActive();
      chunk.activeIdx = idx;
      renderActive();
    },

    prevBlock: function () {
      if (chunk.active) api.gotoBlock(chunk.activeIdx - 1);
    },

    nextBlock: function () {
      if (chunk.active) api.gotoBlock(chunk.activeIdx + 1);
    },

    // 渲染树状大纲到容器；未启用返回 false
    // 复用 Vditor.outlineRender 的展示逻辑（vditor-outline 样式 + 箭头折叠），
    // 但数据源是分块索引树（完整文档标题），点击项切换对应块。
    renderOutline: function (container) {
      if (!container || !chunk.active || !chunk.tree) return false;
      container.innerHTML = '';
      var vd = getVditor();
      if (!vd) return true;

      // 从索引树构造标题 DOM（同步，无需渲染全文）
      var tmp = document.createElement('div');
      var heads = [];
      for (var fi = 1; fi < chunk.flat.length; fi++) {
        var n = chunk.flat[fi];
        if (n.level < 1 || n.level > 4) continue;
        heads.push(n);
        var h = document.createElement('h' + n.level);
        h.textContent = n.heading;
        tmp.appendChild(h);
      }
      if (!heads.length) return true;

      var usedHandler = container._ecOutlineHandler;
      try {
        Vditor.outlineRender(tmp, container, vd.vditor);
      } catch (e) { return true; }

      // 捕获阶段拦截点击：把 outlineRender 的滚动跳转替换为分块切换。
      // 先移除上次绑定的 handler，避免重复监听。
      if (usedHandler) container.removeEventListener('click', usedHandler, true);
      container._ecOutlineHandler = function (ev) {        // 放行箭头折叠按钮（vditor-outline__action），否则捕获阶段会拦截它
        var probe = ev.target;
        while (probe && probe !== container) {
          if (probe.classList && probe.classList.contains &&
              probe.classList.contains('vditor-outline__action')) return;
          probe = probe.parentElement;
        }
        var t = ev.target;
        while (t && t !== container && !(t.getAttribute && t.getAttribute('data-target-id'))) {
          t = t.parentElement;
        }
        if (!t || t === container) return;
        var id = t.getAttribute('data-target-id');
        if (!id) return;
        // 解析收集序号：outlineRender 把标题 id 重写为 "前缀_{序号}"
        var m = /_(\d+)$/.exec(id);
        if (!m) return;
        var idx = parseInt(m[1], 10);
        if (idx < 0 || idx >= heads.length) return;
        ev.preventDefault();
        ev.stopPropagation();
        api.gotoBlock(heads[idx]._fi);
        var cont = container;
        setTimeout(function () { api.renderOutline(cont); }, 0);
      };
      container.addEventListener('click', container._ecOutlineHandler, true);
      _outlineContainer = container;

      var addRow = document.createElement('div');
      addRow.textContent = 'Add heading';
      addRow.setAttribute('style',
        'padding:4px 8px;margin-top:2px;border-radius:4px;cursor:pointer;color:var(--fg-muted);font-size:12px;' +
        'user-select:none');
      addRow.addEventListener('mouseenter', function () { this.style.background = 'rgba(128,128,128,.12)'; });
      addRow.addEventListener('mouseleave', function () { this.style.background = ''; });
      addRow.addEventListener('click', function () {
        if (adapter && typeof adapter.promptTitle === 'function') {
          adapter.promptTitle('New heading').then(function (t) {
            if (t == null || !String(t).trim()) return;
            api.addSection(String(t), chunk.activeIdx);
          }).catch(function () {});
        }
      });
      container.appendChild(addRow);
      return true;
    },

    // 在当前活跃节点之后插入一个新的标题节，并切换为活跃
    addSection: function (title, afterIdx) {
      if (!chunk.active || !chunk.src) return false;
      commitActive();
      var t = String(title || '').trim() || 'New heading';
      var idx = (typeof afterIdx === 'number' && afterIdx >= 0 && afterIdx < chunk.flat.length)
        ? afterIdx
        : chunk.activeIdx;
      var node = chunk.flat[idx];
      if (!node) return false;
      var at = node.end;
      var sep = chunk.src.slice(Math.max(0, at - 1), at) === '\n' ? '\n' : '\n\n';
      var line = '\n\n## ' + t + '\n';
      chunk.src = chunk.src.slice(0, at) + sep + line + chunk.src.slice(at);
      rebuildIndex();
      // 定位到新节点
      var target = null;
      for (var i = 0; i < chunk.flat.length; i++) {
        if (chunk.flat[i].heading === t) { target = chunk.flat[i]; break; }
      }
      chunk.activeIdx = target && target._fi != null ? target._fi : chunk.activeIdx;
      renderActive();
      return true;
    },

    scrollToHeading: function (title) {
      var vd = getVditor();
      if (!vd) return;
      var el = modeElement(vd);
      if (!el) return;
      var heads = el.querySelectorAll('h1,h2,h3,h4');
      for (var i = 0; i < heads.length; i++) {
        if ((heads[i].textContent || '').trim() === title) {
          try { el.scrollTop = heads[i].offsetTop - 16; } catch (e) {}
          return;
        }
      }
    },

    isEnabled: function () { return chunk.active; },
    getBlockCount: function () { return chunk.flat.length; },
    getActiveIdx: function () { return chunk.activeIdx; },
    setAutoFollow: function (on) { _autoFollow = !!on; },
    getAutoFollow: function () { return _autoFollow; },

    // Vditor 重建等场景：提交 + 关闭分块，返回完整文本（未启用返回 null）
    takeFull: function () {
      if (!chunk.active) return null;
      commitActive();
      var full = chunk.yamlPrefix + chunk.src;
      disable();
      return full;
    },

    splitBlocks: splitBlocks,
    assemble: assemble,
    subHeadings: subHeadings,
    shouldChunk: shouldChunk,
    extractYamlFrontmatter: extractYamlFrontmatter,
    scanTitles: scanTitles
  };

  global.EditorChunks = api;
})(window);
