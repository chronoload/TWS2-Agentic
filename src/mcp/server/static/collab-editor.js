// 独立协同编辑器（正式项目）：右键"协同打开副本"→ 创建物理副本文件 → 独立编辑器实例 + 协同 + 真落盘保存。
// 完全解耦主编辑器：不碰 state.fileContents/originalContents/saveCurrentFile/自动保存/chunk。
// 作为 ES module 加载，通过 window.CollabEditor 暴露 open/close。
import * as Loro from './collab/loro_wasm_bg.js';

// Vditor CDN 必须与主编辑器一致（unpkg 3.10.7），且主资源(cdn)与所有子资源
// (i18n/lute/content-theme) 必须同源 CDN 加载，否则子资源相对本地 /static/vditor
// 加载会因本地文件缺失或版本错位而 404（net::ERR_ABORTED）。
const __VDITOR_CDN = window.__VDITOR_CDN || 'https://unpkg.com/vditor@3.10.7';

// ---- Loro wasm 初始化 ----
let _wasmReady = null;
const _WASM_CDN = 'https://cdn.jsdelivr.net/npm/loro-wasm@1.0.7/bundler/loro_wasm_bg.wasm';
const _WASM_LOCAL = '/static/collab/loro_wasm_bg.wasm';
function initLoro() {
  if (!_wasmReady) {
    _wasmReady = (async () => {
      let res = await fetch(_WASM_CDN);
      if (!res.ok) res = await fetch(_WASM_LOCAL);
      if (!res.ok) throw new Error('wasm 下载失败 ' + res.status);
      const bytes = await res.arrayBuffer();
      const { instance } = await WebAssembly.instantiate(bytes, { './loro_wasm_bg.js': Loro });
      Loro.__wbg_set_wasm(instance.exports);
      if (typeof instance.exports.__wbindgen_start === 'function') instance.exports.__wbindgen_start();
    })();
  }
  return _wasmReady;
}

// ---- 文本 diff + selection 变换（与 collab-client 一致的已验证逻辑）----
function simpleDiff(before, after) {
  let p = 0, s = 0;
  const lim = Math.min(before.length, after.length);
  while (p < lim && before[p] === after[p]) p++;
  while (s < before.length - p && s < after.length - p && before[before.length - 1 - s] === after[after.length - 1 - s]) s++;
  return { pos: p, deleteText: before.slice(p, before.length - s), insertText: after.slice(p, after.length - s) };
}
function transformPosition(pos, { pos: start, deleteText, insertText }) {
  const end = start + deleteText.length;
  if (pos < start) return pos;
  if (pos > end) return pos + insertText.length - deleteText.length;
  return start + insertText.length;
}
function transformSelection(sel, patch) {
  return { anchor: Math.max(0, transformPosition(sel.anchor, patch)), head: Math.max(0, transformPosition(sel.head, patch)) };
}

// ---- DOM 定位（字符串检索 + 估算窗口扫描，来自 POC 验证）----
function editorEl(vd) {
  if (vd.vditor.currentMode === 'ir') return vd.vditor.ir.element;
  if (vd.vditor.currentMode === 'wysiwyg') return vd.vditor.wysiwyg.element;
  return vd.vditor.sv.element;
}
function isPreviewNode(n, root) {
  let c = n.nodeType === 1 ? n : n.parentElement;
  while (c && c !== root) { if (c.classList && (c.classList.contains('vditor-ir__preview') || c.classList.contains('vditor-wysiwyg__preview'))) return true; c = c.parentElement; }
  return false;
}
function flatText(vd) {
  const root = editorEl(vd), flat = [];
  const w = document.createTreeWalker(root, 3); // SHOW_TEXT
  let n;
  while ((n = w.nextNode())) {
    if (isPreviewNode(n, root) || !n.nodeValue) continue;
    const v = n.nodeValue.replace(/\u200b/g, '');
    if (!v.trim()) continue;
    for (let i = 0; i < v.length; i++) flat.push({ node: n, offset: i, ch: v[i], idx: flat.length });
  }
  return flat;
}
function approxIdx(src, flat, pos) { return src.length && flat.length ? Math.floor(pos / src.length * flat.length) : 0; }
function nearestMatch(ft, anchor, approx, fwd) {
  let best = -1, bd = Infinity, from = 0;
  while (true) { const i = ft.indexOf(anchor, from); if (i < 0) break; const p = fwd ? i : i + anchor.length; const d = Math.abs(p - approx); if (d < bd) { bd = d; best = i; } from = i + 1; }
  return best;
}
function locatePos(src, flat, ft, pos, win = 80) {
  const ax = approxIdx(src, flat, pos);
  const lo = Math.max(0, ax - win), hi = Math.min(ft.length, ax + win);
  const wt = ft.slice(lo, hi);
  const after = src.slice(pos, Math.min(src.length, pos + 12));
  const before = src.slice(Math.max(0, pos - 12), pos);
  if (after) {
    let r = wt.indexOf(after);
    if (r < 0) { for (let k = 12; k >= 2; k--) { const a = src.slice(pos, Math.min(src.length, pos + k)); if (a && (r = wt.indexOf(a)) >= 0) break; } }
    if (r >= 0) return flat[lo + r];
    const gi = nearestMatch(ft, after, ax, true); if (gi >= 0) return flat[gi];
  }
  if (before) {
    let r = wt.lastIndexOf(before);
    if (r < 0) { for (let k = 12; k >= 2; k--) { const b = src.slice(Math.max(0, pos - k), pos); if (b && (r = wt.lastIndexOf(b)) >= 0) break; } }
    if (r >= 0) return flat[Math.min(lo + r + before.length, flat.length - 1)];
    const gi = nearestMatch(ft, before, ax, false); if (gi >= 0) return flat[Math.min(gi + before.length, flat.length - 1)];
  }
  if (pos >= src.length && flat.length) return flat[flat.length - 1];
  if (ax >= 0 && ax < flat.length) return flat[ax];
  return null;
}
function selRange(vd, patch) {
  const src = vd.getValue(), flat = flatText(vd);
  if (!flat.length) return null;
  const ft = flat.map(f => f.ch).join('');
  const s = locatePos(src, flat, ft, patch.pos);
  if (!s) return null;
  const r = document.createRange();
  if (patch.deleteText) {
    const e = locatePos(src, flat, ft, patch.pos + patch.deleteText.length);
    if (!e || e.idx < s.idx) return null;
    r.setStart(s.node, s.offset); r.setEnd(e.node, e.offset);
  } else { r.setStart(s.node, s.offset); r.collapse(true); }
  if (patch.deleteText && r.toString() !== patch.deleteText) return null;
  return r;
}
// ---- 选区映射（移植 IR POC buildMap 系统，保留所有文本节点 + 原始 offset）----
// flatText 跳过空白节点 + 用过滤后索引当 offset，在 WYSIWYG/IR 空行处 curSel 必返回 null。
// buildMap 保留所有文本节点，offset 直接对应 DOM offset，选区映射可靠。
function textNodesAll(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) {
    if (!isPreviewNode(node, root) && node.nodeValue &&
        node.nodeValue.replace(/\u200b/g, '').trim() !== '') nodes.push(node);
  }
  return nodes;
}
function buildMap(vd) {
  const root = editorEl(vd);
  const source = vd.getValue();
  const entries = [];
  let sourceIndex = 0;
  for (const node of textNodesAll(root)) {
    const raw = node.nodeValue;
    const chars = raw.replace(/\u200b/g, '');
    if (!chars) continue;
    const start = source.indexOf(chars, sourceIndex);
    if (start < 0) return null;
    // 构建 entries 时跳过 \u200b，保持 DOM offset 正确
    const nodeEntries = [];
    for (let i = 0, domOff = 0; i < raw.length; i++) {
      if (raw[i] === '\u200b') { domOff++; continue; }
      nodeEntries.push({ source: start + nodeEntries.length, offset: domOff });
      domOff++;
    }
    sourceIndex = start + chars.length;
    entries.push({ node, chars, entries: nodeEntries });
  }
  return { source, entries };
}
function pointAtSource(map, position) {
  let previous = null;
  for (const item of map.entries) {
    for (const entry of item.entries) {
      if (entry.source === position) return { node: item.node, offset: entry.offset };
      if (entry.source > position) {
        if (previous && previous.source + 1 === position) {
          return { node: previous.node, offset: previous.offset + 1 };
        }
        return { node: item.node, offset: entry.offset };
      }
      previous = { ...entry, node: item.node };
    }
  }
  if (previous && previous.source + 1 === position) {
    return { node: previous.node, offset: previous.offset + 1 };
  }
  const last = map.entries[map.entries.length - 1];
  if (!last) return { node: editorEl(vd), offset: 0 };
  return { node: last.node, offset: last.chars.length };
}
function sourceAtPoint(map, node, offset) {
  const item = map.entries.find((entry) => entry.node === node);
  if (!item) return null;
  if (offset < item.entries.length) return item.entries[offset].source;
  const last = item.entries[item.entries.length - 1];
  return last ? last.source + 1 : null;
}
function pointAt(vd, pos) {
  const map = buildMap(vd);
  if (!map) return null;
  return pointAtSource(map, pos);
}
function curSel(vd) {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0), root = editorEl(vd);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const map = buildMap(vd);
  if (!map) return null;
  const a = sourceAtPoint(map, range.startContainer, range.startOffset);
  const h = sourceAtPoint(map, range.endContainer, range.endOffset);
  if (a == null || h == null) return null;
  return { anchor: a, head: h };
}
function placeSel(vd, sel) {
  const map = buildMap(vd);
  if (!map || !sel) return false;
  const start = pointAtSource(map, sel.anchor);
  const end = pointAtSource(map, sel.head);
  if (!start || !end) return false;
  const r = document.createRange();
  r.setStart(start.node, start.offset);
  r.setEnd(end.node, end.offset);
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  return true;
}

// ---- 远程光标绘制（使用独立叠加层容器，避免污染 contenteditable）----
// 光标元素放在 .vditor-content 内的 .vd-collab-cursors 容器中（pre 的兄弟元素），
// 叠加层 absolute 定位的容器是 .vditor-content（cursorLayer.parentElement），
// 位置计算用 cursorLayer.parentElement.getBoundingClientRect 作为基准。
function drawRemoteCursors(vd, awareness, selfPeer, fallbackLabel) {
  const pre = editorEl(vd);
  if (!pre) return;
  const cursorLayer = pre.parentElement && pre.parentElement.querySelector('.vd-collab-cursors');
  if (!cursorLayer) return;
  cursorLayer.querySelectorAll('.vd-collab-cursor').forEach((el) => el.remove());
  let states;
  try { states = awareness.getAllStates(); } catch (e) { console.warn('[collab-aw] getAllStates error', e); return; }
  if (!states) return;
  const selfStr = String(selfPeer);
  const peerKeys = Object.keys(states);
  console.log('[collab-aw] drawRemoteCursors self=', selfStr, 'peers=', peerKeys, 'states=', states);
  const hostRect = cursorLayer.parentElement.getBoundingClientRect();
  let drawn = 0;
  for (const peerKey of peerKeys) {
    if (String(peerKey) === selfStr) continue;
    const state = states[peerKey];
    if (!state || !state.cursor) { console.log('[collab-aw] peer', peerKey, '无 cursor state=', state); continue; }
    const point = pointAt(vd, state.cursor.anchor);
    if (!point || !point.node) { console.log('[collab-aw] peer', peerKey, 'pointAt 失败 anchor=', state.cursor.anchor); continue; }
    const range = document.createRange();
    range.setStart(point.node, point.offset);
    range.collapse(true);
    const rects = range.getClientRects();
    const rect = (rects && rects[0]) || range.getBoundingClientRect();
    if (!rect || (rect.left === 0 && rect.top === 0 && rect.width === 0)) {
      console.log('[collab-aw] peer', peerKey, 'rect 为空');
      continue;
    }
    const el = document.createElement('span');
    el.className = 'vd-collab-cursor';
    el.textContent = state.name || fallbackLabel;
    el.style.left = Math.max(0, rect.left - hostRect.left) + 'px';
    el.style.top = Math.max(0, rect.top - hostRect.top) + 'px';
    cursorLayer.appendChild(el);
    drawn++;
    console.log('[collab-aw] 绘制光标 peer=', peerKey, 'at', el.style.left, el.style.top);
  }
  if (drawn === 0 && peerKeys.length > (peerKeys.includes(selfStr) ? 1 : 0)) {
    console.log('[collab-aw] 有远端 peer 但未绘制任何光标');
  }
}

// ---- Awareness 设置（参照 IR POC setupAwareness，适配 WebSocket）----
function setupAwareness({ vd, awareness, sendAwareness, name }) {
  const editor = editorEl(vd);
  if (!editor) return null;
  let awTimer = null;
  const publish = () => {
    if (!editor.contains(document.activeElement)) return;
    // 防抖：selectionchange 在拖选时高频触发，100ms 足够
    if (awTimer) clearTimeout(awTimer);
    awTimer = setTimeout(() => {
      awTimer = null;
      try {
        const selection = curSel(vd);
        if (!selection) { console.warn('[collab-aw] publish: 无选区'); return; }
        awareness.setLocalState({ cursor: { anchor: selection.anchor, head: selection.head }, name });
        const bytes = awareness.encodeAll();
        console.log('[collab-aw] publish sel=', selection, 'bytes=', bytes && bytes.length, 'peer=', String(awareness.peer()));
        if (bytes && bytes.length) {
          sendAwareness(bytes);
          drawRemoteCursors(vd, awareness, awareness.peer(), name);
        }
      } catch (e) { console.warn('[collab-aw] publish error', e); }
    }, 100);
  };
  document.addEventListener('selectionchange', publish);
  editor.addEventListener('focus', publish);
  editor.addEventListener('keyup', publish);
  return {
    dispose() {
      if (awTimer) { clearTimeout(awTimer); awTimer = null; }
      try { document.removeEventListener('selectionchange', publish); } catch (e) {}
      try { editor.removeEventListener('focus', publish); } catch (e) {}
      try { editor.removeEventListener('keyup', publish); } catch (e) {}
    }
  };
}

// ---- 编辑器绑定（Loro + 远端增量应用，来自 POC 验证）----
function bindEditor({ vd, doc, text, sendUpdate, awareness, sendAwareness, name }) {
  let applyingRemote = false, composing = false, queuedRemote = false;
  let disposed = false;
  let unsubText = null, unsubDoc = null, awDispose = null;
  const syncLocal = () => {
    if (disposed) return;
    const md = vd.getValue();
    if (md === text.toString()) return;
    const patch = simpleDiff(text.toString(), md);
    text.delete(patch.pos, patch.deleteText.length);
    if (patch.insertText) text.insert(patch.pos, patch.insertText);
    doc.commit();
  };
  const applyPatchInc = (patch, selection) => {
    const before = vd.getValue();
    const expected = before.slice(0, patch.pos) + patch.insertText + before.slice(patch.pos + patch.deleteText.length);
    const range = selRange(vd, patch);
    if (!range) return false;
    const ed = editorEl(vd); ed.focus();
    const act = window.getSelection(); act.removeAllRanges(); act.addRange(range);
    vd.vditor[vd.vditor.currentMode].preventInput = false;
    if (patch.deleteText) document.execCommand('delete', false);
    if (patch.insertText) document.execCommand('insertText', false, patch.insertText);
    ed.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: patch.insertText }));
    const ok = vd.getValue() === expected;
    if (ok && selection) placeSel(vd, transformSelection(selection, patch));
    return ok;
  };
  const applyRemote = () => {
    if (disposed) return;
    // composing 状态下不应用远端（避免打断 IME 丢字），排队等 compositionend
    if (composing) { queuedRemote = true; return; }
    const target = text.toString(), before = vd.getValue();
    // 基准对齐后，本地 commit 不会改变 text 与 vd 的相等关系（同步输入二者都变），
    // 此处 target === before 短路即可避免本地 commit 触发的回调进入处理逻辑。
    if (target === before) return;
    const hadFocus = editorEl(vd).contains(document.activeElement);
    if (!hadFocus) {
      vd.setValue(target);
      vd.vditor[vd.vditor.currentMode].preventInput = false;
      // 远端更新后 DOM 变化，重绘远端光标到新位置
      if (awareness) drawRemoteCursors(vd, awareness, awareness.peer(), '远端');
      return;
    }
    const sel = curSel(vd), patch = simpleDiff(before, target);
    applyingRemote = true;
    try {
      const ok = applyPatchInc(patch, sel);
      if (!ok || vd.getValue() !== target) {
        // 增量失败：直接全量对齐 DOM 到 Loro，绝不调 syncLocal。
        // 此处 DOM 落后于 Loro（缺远端 update），syncLocal 会把"DOM 缺失的远端内容"
        // 误解为"本地要删除的内容"回写 Loro → 远端内容被反向删除，CRDT 失效。
        // 本地未提交输入由 onInput 实时同步兜底（非 composing 状态下 DOM 与 Loro 应已一致）。
        vd.setValue(target);
        vd.vditor[vd.vditor.currentMode].preventInput = false;
        if (sel) placeSel(vd, transformSelection(sel, patch));
      }
    } finally {
      applyingRemote = false;
      // 远端更新后 DOM 变化，重绘远端光标到新位置
      if (awareness) drawRemoteCursors(vd, awareness, awareness.peer(), '远端');
      if (queuedRemote) { queuedRemote = false; queueMicrotask(applyRemote); }
    }
  };
  const ed = editorEl(vd);
  const onCompStart = () => { composing = true; };
  const onCompEnd = () => { composing = false; if (queuedRemote) { queuedRemote = false; applyRemote(); } syncLocal(); };
  const onInput = () => { if (applyingRemote || composing) return; syncLocal(); };
  const onKeyDown = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const k = e.key.toLowerCase();
    if (k === 'z') { e.preventDefault(); undo.undo(vd.vditor); }
    else if (k === 'y') { e.preventDefault(); undo.redo(vd.vditor); }
  };
  ed.addEventListener('compositionstart', onCompStart);
  ed.addEventListener('compositionend', onCompEnd);
  ed.addEventListener('input', onInput);
  const origInput = vd.vditor.options.input;
  vd.vditor.options.input = (md) => {
    if (disposed) return;
    // 对齐 POC：统一走 syncLocal，内部 if (md === text.toString()) return 防重复
    if (!applyingRemote && !composing) syncLocal();
  };
  const undo = vd.vditor.undo;
  const origUndo = undo.undo.bind(undo), origRedo = undo.redo.bind(undo);
  undo.undo = (v) => { origUndo(v); syncLocal(); };
  undo.redo = (v) => { origRedo(v); syncLocal(); };
  ed.addEventListener('keydown', onKeyDown);
  try { unsubText = text.subscribe(() => { if (disposed) return; if (composing || applyingRemote) { queuedRemote = true; return; } applyRemote(); }); } catch (e) {}
  try { unsubDoc = doc.subscribeLocalUpdates((update) => { if (!disposed) sendUpdate(update); }); } catch (e) {}
  // 光标 Awareness：监听本地选区变化 → 广播；远端 awareness 到达时 drawRemoteCursors 重绘
  if (awareness && sendAwareness) {
    awDispose = setupAwareness({ vd, awareness, sendAwareness, name: name || '远端' });
  }
  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      try { ed.removeEventListener('compositionstart', onCompStart); } catch (e) {}
      try { ed.removeEventListener('compositionend', onCompEnd); } catch (e) {}
      try { ed.removeEventListener('input', onInput); } catch (e) {}
      try { ed.removeEventListener('keydown', onKeyDown); } catch (e) {}
      try { if (typeof unsubText === 'function') unsubText(); } catch (e) {}
      try { if (typeof unsubDoc === 'function') unsubDoc(); } catch (e) {}
      try { if (awDispose) awDispose.dispose(); } catch (e) {}
      try { undo.undo = origUndo; undo.redo = origRedo; } catch (e) {}
      try { vd.vditor.options.input = origInput; } catch (e) {}
    }
  };
}

// ---- b64 辅助 ----
function bytesToB64(bytes) { return btoa(String.fromCharCode(...new Uint8Array(bytes))); }
function b64ToBytes(b64) { const raw = atob(b64), a = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) a[i] = raw.charCodeAt(i); return a; }

// ---- 独立协同编辑器（挂载到虚拟标签页，对标 Monaco） ----
// 多实例：按 srcPath 维护，容器由宿主在 collabEditorArea 内提供。
// active 仅为兼容旧 API（save/close 无参时用 active），实际操作按 srcPath。
let _instances = Object.create(null);  // { [srcPath]: { vd, doc, text, ws, bind, copyPath, srcPath, containerId, disposed } }
let _opening = Object.create(null);    // { [srcPath]: true } 并发锁：防止同路径 open 重入

// 主题切换：宿主 refreshVditorInstanceThemes 调用，遍历所有协同实例。
// 完整对标主编辑器 refreshVditorInstanceThemes：
//   1. 宿主 applyBaseTheme 已切全局 #vditorContentTheme link（content-theme，编辑区渲染样式）
//   2. 这里只调 setTheme(v) 切 Vditor 外壳主题（toolbar/边框），与主编辑器完全一致
// 判断亮/暗用宿主 isLightTheme（基于主题注册表 modes，支持任意自定义主题），
// 不再硬编码 'light' === 'classic'，避免自定义主题误判。
function _refreshAllThemes() {
  var t = document.documentElement.getAttribute('data-theme') || 'dark';
  var isLight = (typeof isLightTheme === 'function') ? isLightTheme(t) : (t === 'light');
  var v = isLight ? 'classic' : 'dark';
  for (var src in _instances) {
    var inst = _instances[src];
    if (inst && inst.vd && !inst.disposed) {
      try { if (inst.vd.setTheme) inst.vd.setTheme(v); } catch (e) {}
    }
  }
}

async function open(srcPath, opts) {
  opts = opts || {};
  var containerId = opts.containerId || 'collabEditorArea';
  // 并发锁：同路径 open 进行中则忽略
  if (_opening[srcPath]) { console.warn('[collab-editor] open() 重入', srcPath); return; }
  // 已存在实例：由宿主 switchTo 处理显示，这里直接返回
  if (_instances[srcPath] && !_instances[srcPath].disposed) {
    if (typeof opts.onReady === 'function') opts.onReady(_instances[srcPath]);
    return;
  }
  _opening[srcPath] = true;
  try {
    await _openImpl(srcPath, containerId, opts);
  } catch (e) {
    console.error('[collab-editor] open() 失败', e);
    if (typeof opts.onError === 'function') opts.onError(e);
    else _toast('协同打开失败: ' + (e && e.message || e), true);
  } finally {
    _opening[srcPath] = false;
  }
}

async function _openImpl(srcPath, containerId, opts) {
  await initLoro();
  // 若已存在（防御），先关掉
  if (_instances[srcPath]) { _closeBySrc(srcPath); }

  // 创建物理副本
  const res = await fetch('/api/collab/createCopy', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: srcPath }),
  });
  if (!res.ok) throw new Error('createCopy HTTP ' + res.status);
  const result = await res.json();
  if (!result || result.code !== 0 || !result.data) {
    throw new Error((result && result.msg) || '未知错误');
  }
  const copyPath = result.data.path;
  const content = result.data.content || '';
  const created = result.data.created;

  // 宿主负责显示/隐藏容器，这里只校验容器存在
  const editorDiv = document.getElementById(containerId);
  if (!editorDiv) throw new Error('#' + containerId + ' not found');
  // 清空容器（避免上次 destroy 残留）
  editorDiv.innerHTML = '';

  // 创建独立 Vditor 实例（配置完全对标主编辑器 initVditor）
  // 判断亮/暗用宿主 isLightTheme（基于主题注册表 modes，支持任意自定义主题）
  const _themeAttr = document.documentElement.getAttribute('data-theme') || 'dark';
  const isLight = (typeof isLightTheme === 'function') ? isLightTheme(_themeAttr) : (_themeAttr === 'light');
  var editorContent = content;
  // Rmd 副本：经 rmdToEditorSource 转换为编辑器源
  var isRmd = /\.rmd$/i.test(srcPath);
  if (isRmd && window.rmdToEditorSource) {
    try { editorContent = window.rmdToEditorSource(content); } catch (e) {}
  }

  // 新建副本时，用 editor-source 格式覆盖副本文件，保证服务端 LoroDoc
  // _load_text 读到的内容与 vd.getValue() 一致（否则 import snapshot 会用
  // 原始 Rmd 覆盖 vd，破坏 editor-source 格式且 text!==vd 永久死循环）
  if (created && isRmd && editorContent !== content) {
    try {
      await fetch('/api/file/putFile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: copyPath, content: editorContent }),
      });
    } catch (e) { /* 非致命：最坏情况是服务端用原始内容，activate 时 diff 对齐 */ }
  }

  // 先占位实例（标记"正在打开"），_startCollab 会校验 inst.vd === vd
  // 防止 Vditor after 回调异步触发时实例已被 close 置 disposed
  const placeholderInst = { vd: null, copyPath, srcPath, ws: null, doc: null, text: null, bind: null, containerId, disposed: false };
  _instances[srcPath] = placeholderInst;

  let vd = null;
  try {
    vd = new Vditor(containerId, {
      height: '100%',
      mode: 'ir',
      theme: isLight ? 'classic' : 'dark',
      icon: 'material',
      cdn: __VDITOR_CDN,
      _lutePath: __VDITOR_CDN + '/dist/js/lute/lute.min.js',
      placeholder: '协同编辑中...',
      cache: { enable: false },
      value: editorContent,
      tab: '\t',
      toolbarConfig: { pin: true },
      math: { engine: 'KaTeX', inlineDigit: true },
      hint: {
        delay: 30,
        parse: false,
        extend: (window.buildHintExtends ? window.buildHintExtends(window.loadAcConfig ? window.loadAcConfig() : {}) : []),
      },
      toolbar: [
        'headings', 'bold', 'italic', 'strike', '|',
        'list', 'ordered-list', 'check', 'outdent', 'indent', '|',
        'quote', 'code', 'inline-code', 'table', '|',
        'link', 'upload', 'emoji', '|',
        'undo', 'redo', '|',
        'fullscreen', 'edit-mode', 'both',
        '|',
        { name: 'save', tip: '保存副本', tipPosition: 's', click: () => save(srcPath) },
        { name: 'exit', tip: '退出协同', tipPosition: 's', click: () => close(srcPath) },
      ],
      markdown: {
        linkBase: (location.origin || '') + '/api/file/download/',
      },
      preview: {
        markdown: {
          linkBase: (location.origin || '') + '/api/file/download/',
        },
        theme: { current: isLight ? 'light' : 'dark', path: __VDITOR_CDN + '/dist/css/content-theme' },
        hljs: { style: isLight ? 'github' : 'tokyo-night-dark', lineNumber: true },
        math: { engine: 'KaTeX', inlineDigit: true },
      },
      upload: {
        url: (location.origin || '') + '/api/file/upload',
        fieldName: 'files',
        extraData: () => ({ path: '' }),
        format: (files, responseText) => {
          try {
            const res = JSON.parse(responseText);
            if (res.code === 0 && res.data && res.data.uploaded) {
              return JSON.stringify({
                msg: '', code: 0,
                data: {
                  errFiles: [],
                  succMap: res.data.uploaded.reduce((m, f) => {
                    m[f.name] = f.url || ((location.origin || '') + '/api/file/download/' + f.path);
                    return m;
                  }, {})
                }
              });
            }
          } catch (e) {}
          return responseText;
        },
      },
      after: () => {
        // 若实例已被 close 置 disposed 或被覆盖，销毁自己并退出
        if (!_instances[srcPath] || _instances[srcPath] !== placeholderInst || placeholderInst.disposed) {
          try { vd.destroy(); } catch (e) {}
          return;
        }
        placeholderInst.vd = vd;
        // 对标主编辑器 after：格式化保护 + 快捷键 + Rmd 增强
        if (window.setupCodeBlockPreservation) try { window.setupCodeBlockPreservation(vd); } catch (e) {}
        if (window.setupPandocDivPreservation) try { window.setupPandocDivPreservation(vd); } catch (e) {}
        if (window.bindVditorShortcuts) try { window.bindVditorShortcuts(vd); } catch (e) {}
        var cont = document.getElementById(containerId);
        if (cont) {
          if (window.enhanceRmdChunks) try { window.enhanceRmdChunks(cont, vd); } catch (e) {}
          if (window.initRmdChunksWatcher) try { window.initRmdChunksWatcher(cont, vd); } catch (e) {}
        }
        // 主动应用主题：协同编辑器可能在 display:none 容器中初始化，
        // Vditor 内部主题注入可能延迟。显式调 setTheme 确保外壳 + content-theme 立即生效，
        // 不依赖后续 refreshVditorInstanceThemes（用户切设置 nav 才触发）。
        try {
          var _t = document.documentElement.getAttribute('data-theme') || 'dark';
          var _isLight = (typeof isLightTheme === 'function') ? isLightTheme(_t) : (_t === 'light');
          if (vd.setTheme) vd.setTheme(_isLight ? 'classic' : 'dark');
        } catch (e) {}
        // 创建光标叠加层容器（放在 .vditor-content 内，pre 的兄弟元素，避免污染 contenteditable）
        var _pre = editorEl(vd);
        var _parent = _pre && _pre.parentElement;
        if (_parent && !_parent.querySelector('.vd-collab-cursors')) {
          var _layer = document.createElement('div');
          _layer.className = 'vd-collab-cursors';
          _layer.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;overflow:hidden;';
          _parent.appendChild(_layer);
        }
        _startCollab(srcPath, vd, copyPath, editorContent);
        if (!created) console.log('[collab-editor] 使用已有副本', copyPath);
        if (typeof opts.onReady === 'function') opts.onReady(placeholderInst);
      },
    });
  } catch (e) {
    // Vditor 构造失败：清理占位实例
    if (_instances[srcPath] === placeholderInst) delete _instances[srcPath];
    throw e;
  }
}

// ---- IndexedDB 持久化（离线编辑时保存 LoroDoc 状态，刷新页面不丢编辑）----
// 数据库名: collab-editor, 存储名: loro-states, 键: srcPath
// 值: { loroBytes: Uint8Array, text: string, timestamp: number }
function _idbOpen() {
  return new Promise(function (resolve, reject) {
    var req = indexedDB.open('collab-editor', 1);
    req.onupgradeneeded = function () { req.result.createObjectStore('loro-states'); };
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { reject(req.error); };
  });
}
async function _idbSaveLoro(srcPath, doc) {
  try {
    var db = await _idbOpen();
    var tx = db.transaction('loro-states', 'readwrite');
    var store = tx.objectStore('loro-states');
    store.put({ loroBytes: doc.exportSnapshot(), text: doc.getText('md').toString(), timestamp: Date.now() }, srcPath);
  } catch (e) { console.warn('[collab-idb] save error', e); }
}
async function _idbLoadLoro(srcPath) {
  try {
    var db = await _idbOpen();
    return new Promise(function (resolve) {
      var tx = db.transaction('loro-states', 'readonly');
      var req = tx.objectStore('loro-states').get(srcPath);
      req.onsuccess = function () { resolve(req.result || null); };
      req.onerror = function () { resolve(null); };
    });
  } catch (e) { return null; }
}
async function _idbDeleteLoro(srcPath) {
  try {
    var db = await _idbOpen();
    var tx = db.transaction('loro-states', 'readwrite');
    tx.objectStore('loro-states').delete(srcPath);
  } catch (e) {}
}

// ---- 冲突检测（离线编辑后，用 simpleDiff 比较双方修改区域）----
// 返回冲突区域数组: [{ start, end, ourText, theirText }]
function _detectConflicts(baseText, ourText, mergedText) {
  if (!baseText || !ourText || !mergedText) return [];
  // 我们的修改: base → our 的 diff
  var ourPatch = simpleDiff(baseText, ourText);
  // 合并后的总修改: base → merged 的 diff
  var mergedPatch = simpleDiff(baseText, mergedText);
  var conflicts = [];
  // 检测重叠区域: ourPatch 和 mergedPatch 的 pos 范围是否有交集
  var ourStart = ourPatch.pos, ourEnd = ourPatch.pos + ourPatch.deleteText.length + ourPatch.insertText.length;
  var mergedStart = mergedPatch.pos, mergedEnd = mergedPatch.pos + mergedPatch.deleteText.length + mergedPatch.insertText.length;
  // 如果双方修改区域有重叠，标记为冲突
  if (ourStart < mergedEnd && mergedStart < ourEnd) {
    var start = Math.max(ourStart, mergedStart);
    var end = Math.min(ourEnd, mergedEnd);
    // 从 mergedText 中提取冲突区域的内容
    var conflictText = mergedText.slice(start, end);
    // 从 ourText 中提取我们的版本
    var ourVersion = ourText.slice(Math.max(0, ourStart), Math.min(ourText.length, ourEnd));
    conflicts.push({ start: start, end: end, ourText: ourVersion, mergedText: conflictText, ourPatch: ourPatch, mergedPatch: mergedPatch });
  }
  return conflicts;
}

// ---- 冲突可视化（渲染冲突标记）----
// 用一个浮动面板显示冲突信息，不修改编辑器 DOM
var _conflictPanel = null;
function _renderConflictMarkers(vd, conflicts, peerName) {
  _clearConflictMarkers();
  if (!conflicts || !conflicts.length) return;
  // 在编辑器上方创建一个冲突提示面板
  var editor = editorEl(vd);
  if (!editor) return;
  var panel = document.createElement('div');
  panel.className = 'collab-conflict-panel';
  panel.style.cssText = 'padding:8px 12px;margin:0 0 8px;background:#3b1f1f;border:1px solid #d32f2f;border-radius:6px;font-size:12px;color:#ffcdd2;display:flex;flex-direction:column;gap:6px;';
  panel.innerHTML = '<div style="font-weight:700;color:#ef9a9a">⚠️ 检测到离线冲突（' + conflicts.length + ' 处）</div>';
  for (var i = 0; i < conflicts.length; i++) {
    var c = conflicts[i];
    var preview = c.mergedText.length > 60 ? c.mergedText.slice(0, 60) + '...' : c.mergedText;
    panel.innerHTML += '<div style="padding:4px 8px;background:rgba(211,47,47,0.15);border-radius:4px;font-size:11px;line-height:1.5">' +
      '位置 <b>' + c.start + '</b>-<b>' + c.end + '</b>：双方同时修改了同一区域<br>' +
      '合并结果：' + escapeHtml(preview) + '</div>';
  }
  editor.parentNode.insertBefore(panel, editor);
  _conflictPanel = panel;
}
function _clearConflictMarkers() {
  if (_conflictPanel) { try { _conflictPanel.remove(); } catch (e) {} _conflictPanel = null; }
}

// ---- 离线编辑 + 自动重连 + 冲突检测 ----
// 在 _startCollab 内实现：缓冲本地更新、ws 断线重连、合并后检测冲突
function _startCollab(srcPath, vd, copyPath, content) {
  // 实例校验：若 open() 设置的占位实例已被 close 置 disposed 或被覆盖，直接退出
  const inst = _instances[srcPath];
  if (!inst || inst.vd !== vd || inst.disposed) {
    console.warn('[collab-editor] _startCollab: 实例已失效，跳过', srcPath);
    return;
  }

  const doc = new Loro.LoroDoc();
  // peerId 必须全局唯一：同浏览器多标签页 Date.now() 可能相同，
  // 叠加 Math.random 避免冲突（Loro 相同 peerId 会导致 CRDT 操作丢失）
  const peerId = (Date.now() % 0xFFFFFF) * 256 + Math.floor(Math.random() * 256);
  doc.setPeerId(peerId);
  const text = doc.getText('md');
  // Awareness：光标状态同步（参照 IR POC AwarenessWasm）
  let awareness = null;
  try {
    awareness = new Loro.AwarenessWasm(BigInt(peerId), 10000);
    console.log('[collab-editor] AwarenessWasm 创建成功 peerId=', peerId, 'awareness.peer()=', String(awareness.peer()));
  } catch (e) { console.warn('[collab-editor] AwarenessWasm 创建失败', e); }
  console.log('[collab-editor] _startCollab srcPath=', srcPath, 'copyPath=', copyPath);

  let ws = null, peers = 1, activated = false, snapshotPending = null;
  // ---- 离线编辑状态 ----
  let _pendingUpdates = [];      // 离线时缓冲的 subscribeLocalUpdates 更新
  let _offline = false;          // 离线模式标志
  let _reconnectAttempts = 0;    // 重连尝试次数
  let _reconnectTimer = null;    // 重连定时器
  let _lastSyncedText = '';      // 最后一次同步时的文本内容（冲突检测基线）
  let _idbSaveTimer = null;      // IndexedDB 持久化防抖定时器

  // text 播种延迟到 activate：用 vd.getValue()（Vditor 规范化后的文本）作为基准，
  // 而非原始 content（可能经 rmdToEditorSource 转换，与 vd.getValue() 不一致）。
  // 若提前用 content 播种，text.toString() !== vd.getValue() 会致 applyRemote 永久 diff 死循环。

  const sendUpdate = (update) => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !activated) {
      // 离线模式：缓冲更新，重连后发送
      if (_offline && activated) {
        _pendingUpdates.push(update);
        if (_pendingUpdates.length <= 3) console.log('[collab-editor] 离线缓冲 update, 队列长度=', _pendingUpdates.length);
      }
      return;
    }
    ws.send(JSON.stringify({ cmd: 'collab_update', data: { bytes: bytesToB64(update) } }));
  };

  const sendAwareness = (bytes) => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !activated) {
      if (_offline) return; // 离线不发送 awareness
      console.warn('[collab-aw] sendAwareness 跳过: ws=', ws && ws.readyState, 'activated=', activated);
      return;
    }
    ws.send(JSON.stringify({ cmd: 'collab_awareness', data: { bytes: bytesToB64(bytes) } }));
    console.log('[collab-aw] sendAwareness 已发送 bytes=', bytes.length);
  };

  // 保存 LoroDoc 状态到 IndexedDB（防抖 5 秒，避免频繁写入）
  const _scheduleIdbSave = () => {
    if (_idbSaveTimer) { clearTimeout(_idbSaveTimer); _idbSaveTimer = null; }
    _idbSaveTimer = setTimeout(() => {
      _idbSaveTimer = null;
      _idbSaveLoro(srcPath, doc);
    }, 5000);
  };

  const activate = () => {
    if (activated) return;
    // 再次校验实例：close() 后 ws.onmessage 可能仍触发
    const cur = _instances[srcPath];
    if (!cur || cur.vd !== vd || cur.disposed) {
      console.warn('[collab-editor] activate: 实例已失效，跳过', srcPath);
      activated = true;  // 防止重复进入
      return;
    }
    activated = true;
    // 对齐 collab-client.js：不做基准对齐，直接 bindEditor。
    // text 初始为空，依赖 snapshot import 填充 → subscribe → applyRemote 同步 vd。
    // 若先基准对齐用 vd.getValue() 覆盖 text，会丢弃服务端 snapshot 内容，
    // 且 text.toString()===vd.getValue() 永久成立 → applyRemote 永远短路 → 远端无法同步。
    cur.bind = bindEditor({ vd, doc, text, sendUpdate, awareness, sendAwareness, name: 'peer' });
    if (snapshotPending) {
      try { doc.import(b64ToBytes(snapshotPending)); } catch (e) {}
      _lastSyncedText = vd.getValue();
      _scheduleIdbSave();
      snapshotPending = null;
    }
  };

  // ---- 自动重连逻辑 ----
  function _scheduleReconnect() {
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    if (inst.disposed) return;
    _reconnectAttempts++;
    // 指数退避：3s → 4.5s → 6.75s → ... → 最大 30s
    const delay = Math.min(3000 * Math.pow(1.5, _reconnectAttempts - 1), 30000);
    console.log('[collab-editor] 离线重连尝试', _reconnectAttempts, '延迟', Math.round(delay), 'ms');
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null;
      _doReconnect();
    }, delay);
  }

  function _doReconnect() {
    if (inst.disposed) return;
    const scheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
    const url = scheme + location.host + '/ws/collab/' + encodeURIComponent(copyPath);
    // 保存本地 LoroDoc 状态（用于重连后 CRDT 合并）
    const localBytes = doc.exportSnapshot();
    const localText = vd.getValue();
    const pending = _pendingUpdates.slice();
    _pendingUpdates = [];
    console.log('[collab-editor] 开始重连, 待发送缓冲更新数=', pending.length, 'localText len=', localText.length);

    const newWs = new WebSocket(url);
    let snapshotReceived = false;

    newWs.onmessage = (ev) => {
      if (inst.disposed) { try { newWs.close(); } catch (e) {} return; }
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      console.log('[collab-reconnect] 收到 cmd=', msg.cmd);

      if (msg.cmd === 'collab_snapshot' && !snapshotReceived) {
        snapshotReceived = true;
        // 1. 导入服务端权威 snapshot（此时本地离线编辑被覆盖）
        try { doc.import(b64ToBytes(msg.data.bytes)); } catch (e) { console.warn('[collab-reconnect] 导入 snapshot 失败', e); }
        // 2. 重新导入本地状态（CRDT 合并，自动处理冲突）
        try { doc.import(localBytes); } catch (e) { console.warn('[collab-reconnect] 导入本地状态失败', e); }
        // 3. 发送缓冲的更新到服务端（服务端 import 后广播给所有客户端）
        for (const upd of pending) {
          try {
            const b64 = bytesToB64(upd);
            newWs.send(JSON.stringify({ cmd: 'collab_update', data: { bytes: b64 } }));
          } catch (e) {}
        }
        // 4. 冲突检测
        const mergedText = vd.getValue();
        const conflicts = _detectConflicts(_lastSyncedText, localText, mergedText);
        if (conflicts.length > 0) {
          console.log('[collab-editor] 检测到冲突', conflicts.length, '处');
          _renderConflictMarkers(vd, conflicts, '远端');
        }
        _lastSyncedText = mergedText;
        _offline = false;
        _reconnectAttempts = 0;
        _scheduleIdbSave();
        console.log('[collab-editor] 离线同步完成');
      } else if (msg.cmd === 'collab_update') {
        try { doc.import(b64ToBytes(msg.data.bytes)); } catch (e) {}
        _lastSyncedText = vd.getValue();
        _scheduleIdbSave();
      } else if (msg.cmd === 'collab_awareness') {
        if (!awareness) return;
        try {
          awareness.apply(b64ToBytes(msg.data.bytes));
          drawRemoteCursors(vd, awareness, awareness.peer(), '远端');
        } catch (e) {}
      } else if (msg.cmd === 'collab_connected' || msg.cmd === 'collab_peer_count') {
        peers = (msg.data && msg.data.peers) || 1;
      }
    };
    newWs.onerror = (e) => {
      console.warn('[collab-editor] 重连 ws 错误', e);
      _scheduleReconnect();
    };
    newWs.onclose = (ev) => {
      console.warn('[collab-editor] 重连 ws 断开 code=', ev.code);
      if (!inst.disposed) { _offline = true; _scheduleReconnect(); }
    };
    // 更新 ws 引用（sendUpdate/sendAwareness 通过闭包引用 ws）
    ws = newWs;
    inst.ws = newWs;
  }

  // ---- 初始 WebSocket 连接 ----
  const scheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
  const url = scheme + location.host + '/ws/collab/' + encodeURIComponent(copyPath);
  try {
    ws = new WebSocket(url);
  } catch (e) {
    // ws 创建失败：进入离线模式，用户可继续本地编辑
    console.warn('[collab-editor] WebSocket 创建失败，进入离线模式', e);
    _offline = true;
    // 延迟激活（无 ws 也能编辑）
    setTimeout(() => {
      if (!activated && !inst.disposed) {
        activated = true;
        // 从 IndexedDB 恢复 LoroDoc 状态
        _idbLoadLoro(srcPath).then(function (saved) {
          if (saved && saved.loroBytes) {
            try { doc.import(saved.loroBytes); } catch (e) {}
            _lastSyncedText = doc.getText('md').toString();
          }
          inst.bind = bindEditor({ vd, doc, text, sendUpdate, awareness, sendAwareness, name: 'peer' });
          _scheduleReconnect();
        }).catch(function () {
          inst.bind = bindEditor({ vd, doc, text, sendUpdate, awareness, sendAwareness, name: 'peer' });
          _scheduleReconnect();
        });
      }
    }, 100);
    return;
  }
  // 再次校验：new WebSocket 期间用户可能已 close()
  const cur2 = _instances[srcPath];
  if (!cur2 || cur2.vd !== vd || cur2.disposed) {
    try { ws.close(); } catch (e) {}
    return;
  }
  cur2.ws = ws; cur2.doc = doc; cur2.text = text;

  ws.onmessage = (ev) => {
    // close() 后仍可能收到消息（WS 关闭握手期间），校验实例
    const cur = _instances[srcPath];
    if (!cur || cur.vd !== vd || cur.disposed) return;
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    console.log('[collab-ws] 收到 cmd=', msg.cmd, 'peers=', peers, 'activated=', activated);
    if (msg.cmd === 'collab_connected' || msg.cmd === 'collab_peer_count') {
      peers = (msg.data && msg.data.peers) || 1;
      // 单实例也 activate：协同副本只通过协同管理，需把编辑同步到服务端 LoroDoc，
      // 否则第二个客户端加入时拿到旧 snapshot 覆盖第一个客户端的编辑。
      // （与 collab-client.js 的 peers>=2 不同：主编辑器有自己的 putFile 保存）
      if (peers >= 1) activate();
    } else if (msg.cmd === 'collab_snapshot') {
      const bytes = msg.data.bytes;
      // 已 activate 直接 import（subscribe → applyRemote 同步 vd）；
      // 未 activate 存 pending，activate 时 import
      if (activated) {
        try { doc.import(b64ToBytes(bytes)); } catch (e) {}
        _lastSyncedText = vd.getValue();
        _scheduleIdbSave();
      } else {
        snapshotPending = bytes;
      }
    } else if (msg.cmd === 'collab_update') {
      if (!activated) return;
      try { doc.import(b64ToBytes(msg.data.bytes)); } catch (e) {}
      _lastSyncedText = vd.getValue();
      _scheduleIdbSave();
    } else if (msg.cmd === 'collab_awareness') {
      if (!activated || !awareness) return;
      try {
        const awBytes = b64ToBytes(msg.data.bytes);
        console.log('[collab-aw] 收到远端 awareness bytes=', awBytes.length);
        awareness.apply(awBytes);
        drawRemoteCursors(vd, awareness, awareness.peer(), '远端');
      } catch (e) { console.warn('[collab-aw] apply error', e); }
    }
  };
  ws.onerror = (e) => console.warn('[collab-editor] WS error', e);
  ws.onclose = (ev) => {
    console.warn('[collab-editor] WS close 进入离线模式 code=', ev.code, 'reason=', ev.reason, 'wasClean=', ev.wasClean);
    // 仅当已激活且实例未 disposed 时进入离线模式
    if (!activated || inst.disposed) return;
    _offline = true;
    _lastSyncedText = vd.getValue();
    _clearConflictMarkers();
    // 开始自动重连
    _scheduleReconnect();
  };
}

async function save(srcPath) {
  // 无参兼容：保存当前活动协同标签（由宿主传入，或取第一个未 disposed 实例）
  if (!srcPath) srcPath = _anyActiveSrc();
  const inst = srcPath ? _instances[srcPath] : null;
  if (!inst || inst.disposed) return;
  try {
    let content = inst.vd.getValue();
    if (/\.rmd$/i.test(inst.srcPath) && window.editorSourceToRmd) {
      try { content = window.editorSourceToRmd(content); } catch (e) {}
    }
    console.log('[collab-editor] save getValue len=', content.length, 'head=', content.slice(0, 40));
    const res = await fetch('/api/file/putFile', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: inst.copyPath, content }),
    });
    if (!res.ok) throw new Error('save HTTP ' + res.status);
    const result = await res.json();
    if (result && result.code === 0) {
      console.log('[collab-editor] 已保存副本', inst.copyPath);
      _toast('已保存协同副本');
    } else {
      console.error('[collab-editor] save failed', result);
      _toast('保存失败: ' + (result && result.msg || '未知错误'), true);
    }
  } catch (e) {
    console.error('[collab-editor] save error', e);
    _toast('保存失败: ' + (e && e.message || e), true);
  }
}

// 取一个未 disposed 的实例 srcPath（兼容旧无参 API）
function _anyActiveSrc() {
  for (var src in _instances) {
    if (_instances[src] && !_instances[src].disposed) return src;
  }
  return null;
}

// 按 srcPath 销毁实例（内部用，不处理 UI 显示）
function _closeBySrc(srcPath) {
  const inst = _instances[srcPath];
  if (!inst) return;
  inst.disposed = true;
  _clearConflictMarkers();
  try { if (inst.ws) inst.ws.close(); } catch (e) {}
  try { if (inst.bind) inst.bind.dispose(); } catch (e) {}
  try { if (inst.vd) inst.vd.destroy(); } catch (e) {}
  delete _instances[srcPath];
}

function close(srcPath) {
  // 无参兼容：关闭当前活动协同标签
  if (!srcPath) srcPath = _anyActiveSrc();
  if (!srcPath) return;
  _closeBySrc(srcPath);
  // 通知宿主关闭对应标签页（避免协同实例与 tab 状态不同步）
  // 仅由协同编辑器内部"退出协同"按钮触发；宿主 closeTab 主动关闭应调 dispose 避免循环
  if (typeof window._collabCloseTab === 'function') {
    try { window._collabCloseTab(srcPath); } catch (e) {}
  }
}

// 宿主主动销毁实例（closeTab 调用，不触发 _collabCloseTab 回调，避免循环）
function dispose(srcPath) {
  if (!srcPath) return;
  _closeBySrc(srcPath);
}

function _toast(msg, isError) {
  // 复用全局 showToast 如果可用
  if (typeof window.showToast === 'function') window.showToast(msg, isError ? 'error' : 'success');
  else console.log('[collab-editor]', msg);
}

// 暴露全局
window.CollabEditor = {
  open,
  close,
  dispose,
  save,
  // 按 srcPath 查询实例 Vditor（供主题切换 / 标签切换使用）
  getVditor: (srcPath) => {
    const inst = _instances[srcPath];
    return (inst && !inst.disposed && inst.vd) ? inst.vd : null;
  },
  hasInstance: (srcPath) => !!(_instances[srcPath] && !_instances[srcPath].disposed),
  isActive: () => _anyActiveSrc() != null,
  getPath: (srcPath) => {
    const inst = _instances[srcPath || _anyActiveSrc()];
    return inst ? inst.copyPath : null;
  },
  // 供宿主 refreshVditorInstanceThemes 调用
  refreshThemes: _refreshAllThemes,
};
