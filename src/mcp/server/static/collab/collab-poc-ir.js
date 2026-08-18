import * as Loro from './loro_wasm_bg.js';

const {
  simpleDiff,
  applyTextPatch,
  transformSelection,
} = globalThis.CollabIrCore;

const INITIAL_MD = [
  '# IR 协同试验',
  '',
  '两端都可以直接敲击。远端变化应尽量只修改自己的位置。',
  '',
  '## 试验内容',
  '',
  '- 在不同段落同时输入',
  '- 输入中文（IME）',
  '- 尝试 **加粗**、列表和行内公式 $E=mc^2$',
].join('\n');

const stats = { updates: 0, incremental: 0, fallback: 0, imeQueued: 0, lostChars: 0, passiveSync: 0 };
let docA;
let docB;
let textA;
let textB;
let vdA;
let vdB;

// 模拟网络层：可配置延迟/抖动，默认即时。乱序由 Loro 版本向量天然容忍。
const netSim = { delayMs: 0, maxJitter: 0 };
let netQueue = [];
let netFlushTimer = null;

function forwardUpdate(peer, update) {
  const delay = netSim.delayMs + Math.random() * netSim.maxJitter;
  if (delay <= 0) {
    peer.import(update);
    return;
  }
  netQueue.push({ peer, update, at: Date.now() + delay });
  if (!netFlushTimer) {
    netFlushTimer = setInterval(() => {
      const now = Date.now();
      const due = netQueue.filter((item) => item.at <= now);
      netQueue = netQueue.filter((item) => item.at > now);
      for (const item of due) {
        try {
          item.peer.import(item.update);
        } catch (error) {
          log('网络转发 import 失败 ' + error.message, 'lg-err');
        }
      }
      if (!netQueue.length) {
        clearInterval(netFlushTimer);
        netFlushTimer = null;
      }
    }, 25);
  }
}

const $ = (id) => document.getElementById(id);
const editorElement = (vd) => vd.vditor.ir.element;

function log(message, cls) {
  const line = document.createElement('div');
  line.className = cls || '';
  line.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
  $('log').appendChild(line);
  $('log').scrollTop = $('log').scrollHeight;
}

function updateStats() {
  $('updCount').textContent = stats.updates;
  $('incrementalCount').textContent = stats.incremental;
  $('fallbackCount').textContent = stats.fallback;
  $('imeCount').textContent = stats.imeQueued;
}

let wasmReady;
function initLoro() {
  if (!wasmReady) {
    wasmReady = (async () => {
      const response = await fetch('/static/collab/loro_wasm_bg.wasm');
      if (!response.ok) throw new Error('wasm 下载失败 ' + response.status);
      const bytes = await response.arrayBuffer();
      const { instance } = await WebAssembly.instantiate(bytes, {
        './loro_wasm_bg.js': Loro,
      });
      Loro.__wbg_set_wasm(instance.exports);
      if (typeof instance.exports.__wbindgen_start === 'function') {
        instance.exports.__wbindgen_start();
      }
    })();
  }
  return wasmReady;
}

function isPreviewNode(node, root) {
  let current = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  while (current && current !== root) {
    if (current.classList && current.classList.contains('vditor-ir__preview')) return true;
    current = current.parentElement;
  }
  return false;
}

function textNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let node;
  while ((node = walker.nextNode())) {
    if (!isPreviewNode(node, root) && node.nodeValue) nodes.push(node);
  }
  return nodes;
}

// Build a best-effort source-offset map. IR keeps syntax markers in text nodes,
// while block separators and list markers are represented by element structure.
function buildMap(vd) {
  const root = editorElement(vd);
  const source = vd.getValue();
  const entries = [];
  let sourceIndex = 0;
  for (const node of textNodes(root)) {
    const chars = node.nodeValue;
    const start = source.indexOf(chars, sourceIndex);
    if (start < 0) return null;
    const nodeEntries = Array.from(chars, (_, index) => ({
      source: start + index,
      offset: index,
    }));
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
  if (!last) return { node: editorElement(vdA), offset: 0 };
  return { node: last.node, offset: last.chars.length };
}

function sourceAtPoint(map, node, offset) {
  const item = map.entries.find((entry) => entry.node === node);
  if (!item) return null;
  if (offset < item.entries.length) return item.entries[offset].source;
  const last = item.entries[item.entries.length - 1];
  return last ? last.source + 1 : null;
}

function currentSelection(vd) {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  const root = editorElement(vd);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const map = buildMap(vd);
  if (!map) return null;
  const anchor = sourceAtPoint(map, range.startContainer, range.startOffset);
  const head = sourceAtPoint(map, range.endContainer, range.endOffset);
  if (anchor == null || head == null) return null;
  return { anchor, head };
}

function placeSelection(vd, selection) {
  const map = buildMap(vd);
  if (!map || !selection) return false;
  const start = pointAtSource(map, selection.anchor);
  const end = pointAtSource(map, selection.head);
  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset);
  const active = window.getSelection();
  active.removeAllRanges();
  active.addRange(range);
  return true;
}

function selectionRange(vd, patch) {
  const source = vd.getValue();
  const flat = flatDomText(vd);
  if (!flat.length) return null;
  const flatText = flat.map((f) => f.ch).join('');
  const start = locateSourcePos(vd, source, flat, flatText, patch.pos);
  if (!start) return null;
  const range = document.createRange();
  if (patch.deleteText) {
    const end = locateSourcePos(vd, source, flat, flatText, patch.pos + patch.deleteText.length);
    if (!end || end.idx < start.idx) return null;
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);
  } else {
    range.setStart(start.node, start.offset);
    range.collapse(true);
  }
  // 防御：若定位选中的文本与要删除的文本不一致，说明映射错误，放弃增量（走 fallback），
  // 避免 execCommand 在错误位置误删/错插内容。
  if (patch.deleteText && range.toString() !== patch.deleteText) return null;
  return range;
}

// 扁平化编辑 DOM 的可编辑文本节点（排除 preview），每字符记录 node/offset/idx
function flatDomText(vd) {
  const root = editorElement(vd);
  const flat = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (isPreviewNode(node, root) || !node.nodeValue) continue;
    for (let i = 0; i < node.nodeValue.length; i++) {
      flat.push({ node, offset: i, ch: node.nodeValue[i], idx: flat.length });
    }
  }
  return flat;
}

// 估算 sourcePos 在扁平 DOM 文本中的大致索引（buildMap 粗定位，失败按比例估算）
function approxFlatIndex(vd, source, flat, sourcePos) {
  const map = buildMap(vd);
  if (map) {
    const point = pointAtSource(map, sourcePos);
    if (point && point.node) {
      let idx = flat.findIndex((f) => f.node === point.node && f.offset >= point.offset);
      if (idx < 0) idx = flat.findIndex((f) => f.node === point.node);
      if (idx >= 0) return idx;
    }
  }
  if (!source.length || !flat.length) return 0;
  return Math.floor(sourcePos / source.length * flat.length);
}

// 全文档检索 anchor 的所有出现，返回最接近 approx 的索引（优先 >= approx 的前向位置）
function nearestMatch(flatText, anchor, approx, forward) {
  let bestIdx = -1;
  let bestDist = Infinity;
  let from = 0;
  while (true) {
    const idx = flatText.indexOf(anchor, from);
    if (idx < 0) break;
    const pos = forward ? idx : idx + anchor.length;
    const dist = Math.abs(pos - approx);
    if (dist < bestDist) {
      bestDist = dist;
      bestIdx = idx;
    }
    from = idx + 1;
  }
  return bestIdx;
}

// 在估算位置附近的窗口内扫描上下文锚，精确定位 sourcePos（避免全文档重复文本歧义）
function locateSourcePos(vd, source, flat, flatText, sourcePos, windowSize = 80) {
  const approx = approxFlatIndex(vd, source, flat, sourcePos);
  const lo = Math.max(0, approx - windowSize);
  const hi = Math.min(flatText.length, approx + windowSize);
  const windowText = flatText.slice(lo, hi);
  const after = source.slice(sourcePos, Math.min(source.length, sourcePos + 12));
  const before = source.slice(Math.max(0, sourcePos - 12), sourcePos);
  // 前向锚优先：插入点在 after 之前
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
    // 窗口内失败：全文档找最接近估算位置的匹配兜底
    const gi = nearestMatch(flatText, after, approx, true);
    if (gi >= 0) return flat[gi];
  }
  // 后向锚：插入点在 before 之后
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
    if (rel >= 0) {
      const end = rel + before.length;
      return flat[Math.min(lo + end, flat.length - 1)];
    }
    const gi = nearestMatch(flatText, before, approx, false);
    if (gi >= 0) {
      const end = gi + before.length;
      return flat[Math.min(end, flat.length - 1)];
    }
  }
  // 兜底：sourcePos 在末尾
  if (sourcePos >= source.length && flat.length) return flat[flat.length - 1];
  // 最后兜底：返回估算位置对应点（锚匹配全部失败时，避免中断，插入大致位置）
  if (approx >= 0 && approx < flat.length) return flat[approx];
  return null;
}

function applyPatchIncrementally(vd, patch, selection) {
  const before = vd.getValue();
  const expected = applyTextPatch(before, patch);
  const range = selectionRange(vd, patch);
  if (!range) {
    log('增量映射失败：没有 Range pos=' + patch.pos, 'lg-warn');
    return false;
  }
  const hadFocus = editorElement(vd).contains(document.activeElement);
  const editor = editorElement(vd);
  editor.focus();
  const active = window.getSelection();
  active.removeAllRanges();
  active.addRange(range);
  vd.vditor.ir.preventInput = false;
  if (patch.deleteText) document.execCommand('delete', false);
  if (patch.insertText) document.execCommand('insertText', false, patch.insertText);
  editor.dispatchEvent(new InputEvent('input', {
    bubbles: true,
    inputType: patch.deleteText ? 'insertText' : 'insertText',
    data: patch.insertText,
  }));
  const applied = vd.getValue() === expected;
  if (applied && selection) {
    placeSelection(vd, transformSelection(selection, patch));
  } else if (!hadFocus) {
    editor.blur();
  }
  if (!applied) {
    const actual = vd.getValue();
    log('增量校验失败：pos=' + patch.pos + ' expected=' + expected.length + ' actual=' + actual.length, 'lg-warn');
  }
  return applied;
}

function applyFallback(vd, target, patch, selection, name) {
  vd.setValue(target);
  vd.vditor.ir.preventInput = false;
  if (selection) placeSelection(vd, transformSelection(selection, patch));
  stats.fallback++;
  updateStats();
  log(name + ': fallback setValue', 'lg-warn');
}

function bindEditor({ vd, doc, text, peer, name }) {
  let applyingRemote = false;
  let composing = false;
  let queuedRemote = false;

  // 把当前编辑器 DOM 状态同步进 Loro（撤销/重做/fallback 前调用，避免丢失本地输入）
  const syncLocalToLoro = () => {
    const md = vd.getValue();
    if (md === text.toString()) return;
    const patch = simpleDiff(text.toString(), md);
    text.delete(patch.pos, patch.deleteText.length);
    if (patch.insertText) text.insert(patch.pos, patch.insertText);
    doc.commit();
  };

  const applyRemote = (event) => {
    if (event && event.by !== 'import') return;
    if (composing || applyingRemote) {
      queuedRemote = true;
      if (composing) stats.imeQueued++;
      updateStats();
      return;
    }
    const target = text.toString();
    const before = vd.getValue();
    if (target === before) return;
    // 远端编辑器未聚焦：全量对齐（不抢本地焦点，避免打断本地输入）。
    const hadFocus = editorElement(vd).contains(document.activeElement);
    if (!hadFocus) {
      vd.setValue(target);
      vd.vditor.ir.preventInput = false;
      stats.passiveSync++;
      updateStats();
      return;
    }
    const selection = currentSelection(vd);
    const patches = [simpleDiff(before, target)];
    const ordered = patches.slice().sort((a, b) => b.pos - a.pos);
    applyingRemote = true;
    let ok = true;
    try {
      for (const patch of ordered) {
        if (!patch.deleteText && !patch.insertText) continue;
        if (!ok || !applyPatchIncrementally(vd, patch, selection)) {
          ok = false;
          break;
        }
      }
      if (!ok || vd.getValue() !== target) {
        // 增量定位失败：先把本地已提交输入同步进 Loro，再全量对齐，避免丢字
        syncLocalToLoro();
        vd.setValue(target);
        vd.vditor.ir.preventInput = false;
        if (selection) placeSelection(vd, transformSelection(selection, ordered[0]));
        stats.fallback++;
        updateStats();
        log(name + ': fallback setValue', 'lg-warn');
      } else {
        stats.incremental++;
        updateStats();
        log(name + ': 增量应用', 'lg-ok');
      }
    } catch (error) {
      stats.lostChars++;
      syncLocalToLoro();
      vd.setValue(target);
      vd.vditor.ir.preventInput = false;
      if (selection) placeSelection(vd, transformSelection(selection, ordered[0]));
      stats.fallback++;
      updateStats();
      log(name + ': 增量异常 ' + error.message, 'lg-err');
    } finally {
      applyingRemote = false;
      if (queuedRemote) {
        queuedRemote = false;
        queueMicrotask(() => applyRemote({ by: 'import' }));
      }
    }
  };

  vd.vditor.options.input = (md) => {
    if (applyingRemote || md === text.toString()) return;
    const patch = simpleDiff(text.toString(), md);
    text.delete(patch.pos, patch.deleteText.length);
    if (patch.insertText) text.insert(patch.pos, patch.insertText);
    doc.commit();
  };

  const editor = editorElement(vd);
  editor.addEventListener('compositionstart', () => { composing = true; });
  editor.addEventListener('compositionend', () => {
    composing = false;
    // 先应用组合期间排队的远端更新（DOM = Loro），再同步本地组合内容，
    // 避免 DOM（缺远端）覆盖 Loro 导致远端内容丢失
    if (queuedRemote) {
      queuedRemote = false;
      applyRemote({ by: 'import' });
    }
    syncLocalToLoro();
  });
  // Vditor IR 的 options.input 并非每条输入路径都触发，监听原生 input 兜底同步 Loro
  editor.addEventListener('input', () => {
    if (applyingRemote || composing) return;
    syncLocalToLoro();
  });
  text.subscribe(applyRemote);
  doc.subscribeLocalUpdates((update) => {
    stats.updates++;
    updateStats();
    forwardUpdate(peer, update);
  });

  // undo/redo 直接改 DOM 不触发 options.input，需包装以同步 Loro，避免协同脱节
  const undo = vd.vditor.undo;
  const origUndo = undo.undo.bind(undo);
  const origRedo = undo.redo.bind(undo);
  undo.undo = (v) => { origUndo(v); syncLocalToLoro(); };
  undo.redo = (v) => { origRedo(v); syncLocalToLoro(); };
  // toolbar 含 undo/redo 时 Vditor 不接管 Ctrl+Z/Y，需自行绑定并阻止浏览器默认
  editor.addEventListener('keydown', (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key === 'z') {
      e.preventDefault();
      undo.undo(vd.vditor);
    } else if (key === 'y') {
      e.preventDefault();
      undo.redo(vd.vditor);
    }
  });
}

function setNetworkSim(delayMs, maxJitter) {
  netSim.delayMs = delayMs;
  netSim.maxJitter = maxJitter;
}

// ---- 远程光标（Loro Awareness）----
function drawRemoteCursors(vd, awareness, selfPeer, fallbackLabel) {
  const pre = editorElement(vd);
  const host = pre.parentElement;
  if (!host) return;
  host.querySelectorAll('.vd-collab-cursor').forEach((el) => el.remove());
  const states = awareness.getAllStates();
  const hostRect = host.getBoundingClientRect();
  for (const [peerKey, state] of Object.entries(states)) {
    if (String(peerKey) === String(selfPeer)) continue;
    if (!state || !state.cursor) continue;
    const map = buildMap(vd);
    if (!map) continue;
    const point = pointAtSource(map, state.cursor.anchor);
    if (!point || !point.node) continue;
    const range = document.createRange();
    range.setStart(point.node, point.offset);
    range.collapse(true);
    const rects = range.getClientRects();
    const rect = rects[0] || range.getBoundingClientRect() || hostRect;
    const el = document.createElement('span');
    el.className = 'vd-collab-cursor';
    el.textContent = state.name || fallbackLabel;
    el.style.left = Math.max(0, rect.left - hostRect.left) + 'px';
    el.style.top = Math.max(0, rect.top - hostRect.top) + 'px';
    host.appendChild(el);
  }
}

function setupAwareness({ vd, awareness, peerAwareness, peerVd, name }) {
  const editor = editorElement(vd);
  const publish = () => {
    if (!editor.contains(document.activeElement)) return;
    const selection = currentSelection(vd);
    if (!selection) return;
    awareness.setLocalState({ cursor: { anchor: selection.anchor, head: selection.head }, name });
    const bytes = awareness.encodeAll();
    if (bytes && bytes.length) {
      peerAwareness.apply(bytes);
      drawRemoteCursors(peerVd, peerAwareness, peerAwareness.peer(), name);
    }
  };
  document.addEventListener('selectionchange', publish);
  editor.addEventListener('focus', publish);
  editor.addEventListener('keyup', publish);
}

function createVditor(id, value, after) {
  return new Vditor(id, {
    mode: 'ir', cdn: 'https://unpkg.com/vditor@3.10.7', height: '100%', theme: 'dark',
    icon: 'material', placeholder: '输入...', value,
    cache: { enable: false },
    preview: {
      theme: { current: 'dark', path: 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme' },
      math: { engine: 'KaTeX', inlineDigit: true },
    },
    after,
  });
}

function selectMarkdownOffset(vd, offset) {
  const source = vd.getValue();
  const flat = flatDomText(vd);
  if (!flat.length) return false;
  const flatText = flat.map((f) => f.ch).join('');
  const point = locateSourcePos(vd, source, flat, flatText, offset);
  if (!point || !point.node) return false;
  const range = document.createRange();
  range.setStart(point.node, point.offset);
  range.collapse(true);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

async function main() {
  try { await initLoro(); } catch (error) {
    $('netDot').classList.add('off');
    log('Loro wasm 初始化失败：' + error.message, 'lg-err');
    return;
  }
  docA = new Loro.LoroDoc(); docB = new Loro.LoroDoc();
  docA.setPeerId(1n); docB.setPeerId(2n);
  textA = docA.getText('md'); textB = docB.getText('md');
  textA.insert(0, INITIAL_MD); docA.commit();
  docB.import(docA.export({ mode: 'snapshot' }));

  let ready = 0;
  const bindWhenReady = () => {
    ready++;
    if (ready !== 2) return;
    // 基准对齐：Vditor 渲染后的规范文本与 INITIAL_MD 可能存在规范化差异（如尾部换行），
    // 以渲染结果为 Loro 基准，保证 before(target) 与编辑器 getValue 一致，增量 diff 精确。
    const canon = vdA.getValue();
    if (canon !== textA.toString()) {
      textA.delete(0, textA.toString().length);
      textA.insert(0, canon);
      docA.commit();
      docB.import(docA.export({ mode: 'snapshot' }));
    }
    bindEditor({ vd: vdA, doc: docA, text: textA, peer: docB, name: 'A' });
    bindEditor({ vd: vdB, doc: docB, text: textB, peer: docA, name: 'B' });
    const awA = new Loro.AwarenessWasm(1n, 10000);
    const awB = new Loro.AwarenessWasm(2n, 10000);
    setupAwareness({ vd: vdA, awareness: awA, peerAwareness: awB, peerVd: vdB, name: 'A', peerLabel: 'B' });
    setupAwareness({ vd: vdB, awareness: awB, peerAwareness: awA, peerVd: vdA, name: 'B', peerLabel: 'A' });
    window.vdA = vdA; window.vdB = vdB; window.testStats = stats;
    window.testSetNetwork = setNetworkSim;
    window.testInsert = (name, offset, value) => {
      const vd = name === 'A' ? vdA : vdB;
      if (!selectMarkdownOffset(vd, offset)) throw new Error('无法定位 Markdown 偏移 ' + offset);
      editorElement(vd).focus();
      document.execCommand('insertText', false, value);
      editorElement(vd).dispatchEvent(new InputEvent('input', {
        bubbles: true, inputType: 'insertText', data: value,
      }));
      // The deterministic hook completes Vditor's async IR processing path.
      queueMicrotask(() => vd.vditor.options.input(vd.getValue()));
    };
    window.selectMarkdownOffset = selectMarkdownOffset;
    window.testCaretMarkdown = (name) => {
      const vd = name === 'A' ? vdA : vdB;
      const selection = currentSelection(vd);
      return selection ? selection.anchor : -1;
    };
    window.testLoroInsert = (name, offset, value) => {
      const text = name === 'A' ? textA : textB;
      const vd = name === 'A' ? vdA : vdB;
      text.insert(offset, value);
      (name === 'A' ? docA : docB).commit();
      vd.setValue(text.toString());
      vd.vditor.ir.preventInput = false;
    };
    window.testLoroDelete = (name, pos, len) => {
      const text = name === 'A' ? textA : textB;
      const vd = name === 'A' ? vdA : vdB;
      text.delete(pos, len);
      (name === 'A' ? docA : docB).commit();
      vd.setValue(text.toString());
      vd.vditor.ir.preventInput = false;
    };
    window.testLoroAppend = (name, md) => {
      const text = name === 'A' ? textA : textB;
      const vd = name === 'A' ? vdA : vdB;
      text.insert(text.toString().length, md);
      (name === 'A' ? docA : docB).commit();
      vd.setValue(text.toString());
      vd.vditor.ir.preventInput = false;
    };
    window.testLoroA = () => textA.toString();
    window.testLoroB = () => textB.toString();
    log('IR 双实例增量绑定完成', 'lg-ok');
  };
  vdA = createVditor('vdA', INITIAL_MD, bindWhenReady);
  vdB = createVditor('vdB', INITIAL_MD, bindWhenReady);
  $('btnReset').addEventListener('click', () => {
    textA.delete(0, textA.toString().length); textA.insert(0, INITIAL_MD); docA.commit();
    vdA.setValue(INITIAL_MD); log('已重置');
  });
  $('btnClearLog').addEventListener('click', () => { $('log').innerHTML = ''; });
}

main();
