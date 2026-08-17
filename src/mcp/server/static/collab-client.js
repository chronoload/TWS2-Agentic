// 前端协同客户端（正式项目）：Loro + Vditor 绑定 + WebSocket 传输。
// 作为 ES module 加载（import Loro wasm），通过 window.CollabClient 暴露给 app.js。
// 协议：连接 /ws/collab/{path}；服务端发快照初始化；本地编辑 → Loro → 发 update；远端 update → import → 增量应用。
import * as Loro from './collab/loro_wasm_bg.js';

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
      const { instance } = await WebAssembly.instantiate(bytes, {
        './loro_wasm_bg.js': Loro,
      });
      Loro.__wbg_set_wasm(instance.exports);
      if (typeof instance.exports.__wbindgen_start === 'function') {
        instance.exports.__wbindgen_start();
      }
    })();
  }
  return _wasmReady;
}

// ---- 文本 diff：共同前缀 + 后缀 → 单一替换点 ----
function simpleDiff(before, after) {
  let p = 0;
  const lim = Math.min(before.length, after.length);
  while (p < lim && before[p] === after[p]) p++;
  let s = 0;
  while (s < before.length - p && s < after.length - p && before[before.length - 1 - s] === after[after.length - 1 - s]) s++;
  return {
    pos: p,
    deleteText: before.slice(p, before.length - s),
    insertText: after.slice(p, after.length - s),
  };
}

function transformPosition(pos, patch) {
  const start = patch.pos;
  const end = start + patch.deleteText.length;
  const delta = patch.insertText.length - patch.deleteText.length;
  if (pos < start) return pos;
  if (pos > end) return pos + delta;
  return start + patch.insertText.length;
}

function transformSelection(sel, patch) {
  return { anchor: Math.max(0, transformPosition(sel.anchor, patch)), head: Math.max(0, transformPosition(sel.head, patch)) };
}

// ---- DOM 定位（字符串检索 + 估算窗口扫描，来自 POC）----
function editorElementOf(vd) {
  if (vd.vditor.currentMode === 'ir') return vd.vditor.ir.element;
  if (vd.vditor.currentMode === 'wysiwyg') return vd.vditor.wysiwyg.element;
  return vd.vditor.sv.element;
}

function isPreviewNode(node, root) {
  let cur = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  while (cur && cur !== root) {
    if (cur.classList && (cur.classList.contains('vditor-ir__preview') || cur.classList.contains('vditor-wysiwyg__preview'))) return true;
    cur = cur.parentElement;
  }
  return false;
}

function flatDomText(vd) {
  const root = editorElementOf(vd);
  const flat = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (isPreviewNode(node, root) || !node.nodeValue) continue;
    const val = node.nodeValue.replace(/\u200b/g, '');
    if (!val.trim()) continue;
    for (let i = 0; i < val.length; i++) {
      flat.push({ node, offset: i, ch: val[i], idx: flat.length });
    }
  }
  return flat;
}

function approxFlatIndex(source, flat, sourcePos) {
  if (!source.length || !flat.length) return 0;
  return Math.floor(sourcePos / source.length * flat.length);
}

function nearestMatch(flatText, anchor, approx, forward) {
  let best = -1, bestDist = Infinity, from = 0;
  while (true) {
    const idx = flatText.indexOf(anchor, from);
    if (idx < 0) break;
    const pos = forward ? idx : idx + anchor.length;
    const dist = Math.abs(pos - approx);
    if (dist < bestDist) { bestDist = dist; best = idx; }
    from = idx + 1;
  }
  return best;
}

function locateSourcePos(source, flat, flatText, sourcePos, windowSize = 80) {
  const approx = approxFlatIndex(source, flat, sourcePos);
  const lo = Math.max(0, approx - windowSize);
  const hi = Math.min(flatText.length, approx + windowSize);
  const windowText = flatText.slice(lo, hi);
  const after = source.slice(sourcePos, Math.min(source.length, sourcePos + 12));
  const before = source.slice(Math.max(0, sourcePos - 12), sourcePos);
  if (after) {
    let rel = windowText.indexOf(after);
    if (rel < 0) {
      for (let k = 12; k >= 2; k--) {
        const a2 = source.slice(sourcePos, Math.min(source.length, sourcePos + k));
        if (!a2) continue;
        rel = windowText.indexOf(a2);
        if (rel >= 0) break;
      }
    }
    if (rel >= 0) return flat[lo + rel];
    const gi = nearestMatch(flatText, after, approx, true);
    if (gi >= 0) return flat[gi];
  }
  if (before) {
    let rel = windowText.lastIndexOf(before);
    if (rel < 0) {
      for (let k = 12; k >= 2; k--) {
        const b2 = source.slice(Math.max(0, sourcePos - k), sourcePos);
        if (!b2) continue;
        rel = windowText.lastIndexOf(b2);
        if (rel >= 0) break;
      }
    }
    if (rel >= 0) return flat[Math.min(lo + rel + before.length, flat.length - 1)];
    const gi = nearestMatch(flatText, before, approx, false);
    if (gi >= 0) return flat[Math.min(gi + before.length, flat.length - 1)];
  }
  if (sourcePos >= source.length && flat.length) return flat[flat.length - 1];
  if (approx >= 0 && approx < flat.length) return flat[approx];
  return null;
}

function sourcePoint(vd, sourcePos) {
  const source = vd.getValue();
  const flat = flatDomText(vd);
  if (!flat.length) return null;
  const flatText = flat.map((f) => f.ch).join('');
  return locateSourcePos(source, flat, flatText, sourcePos);
}

function selectionRange(vd, patch) {
  const source = vd.getValue();
  const flat = flatDomText(vd);
  if (!flat.length) return null;
  const flatText = flat.map((f) => f.ch).join('');
  const start = locateSourcePos(source, flat, flatText, patch.pos);
  if (!start) return null;
  const range = document.createRange();
  if (patch.deleteText) {
    const end = locateSourcePos(source, flat, flatText, patch.pos + patch.deleteText.length);
    if (!end || end.idx < start.idx) return null;
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);
  } else {
    range.setStart(start.node, start.offset);
    range.collapse(true);
  }
  if (patch.deleteText && range.toString() !== patch.deleteText) return null;
  return range;
}

function sourceAtPoint(flat, node, offset) {
  const chars = [];
  for (const f of flat) if (f.node === node) chars.push(f);
  if (!chars.length) return null;
  if (offset <= 0) return chars[0].idx;
  if (offset >= chars.length) return chars[chars.length - 1].idx + 1;
  return chars[offset - 1].idx + 1;
}

function currentSelection(vd) {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0);
  const root = editorElementOf(vd);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const flat = flatDomText(vd);
  if (!flat.length) return null;
  const anchor = sourceAtPoint(flat, range.startContainer, range.startOffset);
  const head = sourceAtPoint(flat, range.endContainer, range.endOffset);
  if (anchor == null || head == null) return null;
  return { anchor, head };
}

// ---- 绑定一个 Vditor 实例到 LoroText + 远端应用 ----
function bindEditor({ vd, text, doc, sendUpdate }) {
  let applyingRemote = false;
  let composing = false;
  let queuedRemote = false;
  let disposed = false;
  let unsubText = null;
  let unsubDoc = null;

  const syncLocalToLoro = () => {
    if (disposed) return;
    const md = vd.getValue();
    if (md === text.toString()) return;
    const patch = simpleDiff(text.toString(), md);
    text.delete(patch.pos, patch.deleteText.length);
    if (patch.insertText) text.insert(patch.pos, patch.insertText);
    doc.commit();
  };

  const applyPatchIncrementally = (patch, selection) => {
    const before = vd.getValue();
    const expected = before.slice(0, patch.pos) + patch.insertText + before.slice(patch.pos + patch.deleteText.length);
    const range = selectionRange(vd, patch);
    if (!range) return false;
    const editor = editorElementOf(vd);
    editor.focus();
    const active = window.getSelection();
    active.removeAllRanges();
    active.addRange(range);
    vd.vditor[vd.vditor.currentMode].preventInput = false;
    if (patch.deleteText) document.execCommand('delete', false);
    if (patch.insertText) document.execCommand('insertText', false, patch.insertText);
    editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: patch.insertText }));
    const applied = vd.getValue() === expected;
    if (applied && selection) {
      const point = sourcePoint(vd, transformSelection(selection, patch).anchor);
      if (point) {
        const r = document.createRange();
        r.setStart(point.node, point.offset);
        r.collapse(true);
        const s = window.getSelection();
        s.removeAllRanges();
        s.addRange(r);
      }
    }
    return applied;
  };

  const applyRemote = () => {
    if (disposed) return;
    const target = text.toString();
    const before = vd.getValue();
    if (target === before) return;
    const hadFocus = editorElementOf(vd).contains(document.activeElement);
    if (!hadFocus) {
      vd.setValue(target);
      vd.vditor[vd.vditor.currentMode].preventInput = false;
      return;
    }
    const selection = currentSelection(vd);
    const patch = simpleDiff(before, target);
    applyingRemote = true;
    try {
      const ok = applyPatchIncrementally(patch, selection);
      if (!ok || vd.getValue() !== target) {
        syncLocalToLoro();
        vd.setValue(target);
        vd.vditor[vd.vditor.currentMode].preventInput = false;
      }
    } finally {
      applyingRemote = false;
      if (queuedRemote) {
        queuedRemote = false;
        queueMicrotask(applyRemote);
      }
    }
  };

  const editor = editorElementOf(vd);
  const onCompStart = () => { composing = true; };
  const onCompEnd = () => {
    composing = false;
    if (queuedRemote) {
      queuedRemote = false;
      applyRemote();
    }
    syncLocalToLoro();
  };
  const onInput = () => {
    if (applyingRemote || composing) return;
    syncLocalToLoro();
  };
  const onKeyDown = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key === 'z') { e.preventDefault(); undo.undo(vd.vditor); }
    else if (key === 'y') { e.preventDefault(); undo.redo(vd.vditor); }
  };
  editor.addEventListener('compositionstart', onCompStart);
  editor.addEventListener('compositionend', onCompEnd);
  editor.addEventListener('input', onInput);

  const origInput = vd.vditor.options.input;  // app.js 的 input 回调（更新 fileContents/autosave），须保留
  vd.vditor.options.input = (md) => {
    if (disposed) return;
    if (!applyingRemote && md !== text.toString()) {
      const patch = simpleDiff(text.toString(), md);
      text.delete(patch.pos, patch.deleteText.length);
      if (patch.insertText) text.insert(patch.pos, patch.insertText);
      doc.commit();
    }
    if (typeof origInput === 'function') {
      try { origInput(md); } catch (e) { /* keep collab intact */ }
    }
  };

  const undo = vd.vditor.undo;
  const origUndo = undo.undo.bind(undo);
  const origRedo = undo.redo.bind(undo);
  undo.undo = (v) => { origUndo(v); syncLocalToLoro(); };
  undo.redo = (v) => { origRedo(v); syncLocalToLoro(); };
  editor.addEventListener('keydown', onKeyDown);

  try { unsubText = text.subscribe(() => {
    if (disposed) return;
    if (composing || applyingRemote) {
      queuedRemote = true;
      return;
    }
    applyRemote();
  }); } catch (e) {}
  try { unsubDoc = doc.subscribeLocalUpdates((update) => {
    if (!disposed) sendUpdate(update);
  }); } catch (e) {}

  return {
    syncLocalToLoro,
    dispose() {
      if (disposed) return;
      disposed = true;
      try { editor.removeEventListener('compositionstart', onCompStart); } catch (e) {}
      try { editor.removeEventListener('compositionend', onCompEnd); } catch (e) {}
      try { editor.removeEventListener('input', onInput); } catch (e) {}
      try { editor.removeEventListener('keydown', onKeyDown); } catch (e) {}
      try { if (typeof unsubText === 'function') unsubText(); } catch (e) {}
      try { if (typeof unsubDoc === 'function') unsubDoc(); } catch (e) {}
      try { undo.undo = origUndo; undo.redo = origRedo; } catch (e) {}
      try { vd.vditor.options.input = origInput; } catch (e) {}
    },
  };
}

// ---- 协同会话 ----
let active = null;

function _b64ToBytes(b64) {
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

async function start({ vditor, path, wsUrl }) {
  await initLoro();
  if (active) stop();
  const doc = new Loro.LoroDoc();
  doc.setPeerId(Date.now() % 0xFFFFFFFF);
  const text = doc.getText('md');
  let ws = null;
  let peers = 1;
  let activated = false;          // D7：仅 ≥2 实例才激活编辑器绑定与广播
  let snapshotPending = null;
  let bind = null;

  const sendUpdate = (update) => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !activated) return;
    ws.send(JSON.stringify({ cmd: 'collab_update', data: { bytes: btoa(String.fromCharCode(...new Uint8Array(update))) } }));
  };

  const activate = () => {
    if (activated) return;
    activated = true;
    bind = bindEditor({ vd: vditor, text, doc, sendUpdate });
    if (snapshotPending) {
      const arr = snapshotPending;
      snapshotPending = null;
      doc.import(arr);  // text.subscribe 已注册，import 触发 applyRemote 覆盖为服务端权威
    }
  };

  ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = () => reject(new Error('WS 连接失败'));
  });

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.cmd === 'collab_connected' || msg.cmd === 'collab_peer_count') {
      peers = (msg.data && msg.data.peers) || 1;
      if (peers >= 2) activate();
    } else if (msg.cmd === 'collab_snapshot') {
      const arr = _b64ToBytes(msg.data.bytes);
      if (peers >= 2) {
        doc.import(arr);
      } else {
        snapshotPending = arr;
      }
    } else if (msg.cmd === 'collab_update') {
      if (!activated) return;
      try { doc.import(_b64ToBytes(msg.data.bytes)); } catch (e) {}
    }
  };

  active = { path, doc, text, ws, vditor, bind };
  return active;
}

function stop() {
  if (!active) return;
  try { active.ws.close(); } catch (e) {}
  try { if (active.bind) active.bind.dispose(); } catch (e) {}
  active = null;
}

export function initCollabClient() {
  return { start, stop, isActive: () => !!active, getPath: () => (active ? active.path : null) };
}

// 作为 module 加载：把协同客户端暴露为全局，供 app.js（普通 script）使用
window.CollabClient = initCollabClient();
