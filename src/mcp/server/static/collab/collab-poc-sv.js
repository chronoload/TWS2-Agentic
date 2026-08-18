// SV 协同最小闭环：两个 Vditor(SV) 实例，各绑一个 LoroDoc，互发 update 模拟网络。
// Vditor SV/IR 都是 contenteditable，不用绑 textarea；本地用 options.input → LoroText，
// 远端用 setValue（enableInput:false，不会回环）。
import * as Loro from './loro_wasm_bg.js';

const INITIAL_MD = [
  '# 协同试验',
  '',
  '> 在 **A** 或 **B** 中编辑，另一边会实时同步。',
  '',
  '## 可以试试',
  '',
  '- 同时在 A、B 两端输入（模拟两人并发）',
  '- 输入中文（IME 组合输入）',
  '- 插入代码块、行内公式 $E=mc^2$',
  '',
  '```python',
  'print("hello collab")',
  '```',
].join('\n');

let _updCount = 0;
let _appCount = 0;

const $ = (id) => document.getElementById(id);

function log(msg, cls) {
  const el = $('log');
  const line = document.createElement('div');
  line.className = cls || '';
  line.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

function updCountUI() {
  $('updCount').textContent = _updCount;
  $('appCount').textContent = _appCount;
}

// ---- wasm 初始化（fetch + instantiate，避开 wasm module MIME）----
let _wasmReady = null;
function initLoro() {
  if (!_wasmReady) {
    _wasmReady = (async () => {
      const res = await fetch('/static/collab/loro_wasm_bg.wasm');
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

// ---- 文本 diff：共同前缀 + 共同后缀 → 单一替换点 ----
function simpleDiff(a, b) {
  let p = 0;
  const maxP = Math.min(a.length, b.length);
  while (p < maxP && a[p] === b[p]) p++;
  let s = 0;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
  const delStart = p;
  const delLen = a.length - p - s;
  const insText = b.slice(p, b.length - s);
  const ops = [];
  if (delLen) ops.push({ type: 'del', pos: delStart, len: delLen });
  if (insText) ops.push({ type: 'ins', pos: delStart, text: insText });
  return ops;
}

// 把 markdown 字符串同步进 LoroText（本地 input 路径）
function applyMdToLoro(text, md) {
  const ot = text.toString();
  if (ot === md) return false;
  const ops = simpleDiff(ot, md);
  for (const op of ops) {
    if (op.type === 'del') text.delete(op.pos, op.len);
    else text.insert(op.pos, op.text);
  }
  return ops.length > 0;
}

function bindEditor({ vd, doc, text, peer, name }) {
  let applying = false;
  let remoteQueued = false;

  const applyRemote = () => {
    if (applying) {
      remoteQueued = true;
      return;
    }
    const cur = text.toString();
    let local;
    try {
      local = vd.getValue();
    } catch (e) {
      return;
    }
    if (cur === local) return;

    applying = true;
    try {
      vd.setValue(cur);
      _appCount++;
      updCountUI();
      log(name + ': 应用远端 setValue (' + cur.length + ' chars)', 'lg-ok');
    } catch (err) {
      log(name + ': setValue 失败 ' + err.message, 'lg-err');
    } finally {
      applying = false;
      if (remoteQueued) {
        remoteQueued = false;
        queueMicrotask(applyRemote);
      }
    }
  };

  // 本地输入 → LoroText
  // Vditor 在 processAfterRender 里调用 options.input(md)
  vd.vditor.options.input = (md) => {
    if (applying) return;
    if (!applyMdToLoro(text, md)) return;
    doc.commit();
  };

  // 远端 LoroText 变化 → setValue（enableInput:false，不触发 input）
  text.subscribe(applyRemote);

  // 网络：本地增量 → peer.import
  doc.subscribeLocalUpdates((update) => {
    if (!peer) return;
    _updCount++;
    updCountUI();
    try {
      peer.import(update);
    } catch (err) {
      log(name + ': import 失败 ' + err.message, 'lg-err');
    }
  });
}

function createVditor(elId, value, after) {
  return new Vditor(elId, {
    mode: 'sv',
    cdn: 'https://unpkg.com/vditor@3.10.7',
    height: '100%',
    theme: 'dark',
    icon: 'material',
    placeholder: '输入...',
    value: value,
    cache: { enable: false },
    toolbar: [
      'headings', 'bold', 'italic', 'strike', '|',
      'list', 'ordered-list', 'check', '|',
      'quote', 'inline-code', 'code', 'table', '|',
      'link', 'emoji', '|', 'undo', 'redo',
    ],
    preview: {
      theme: { current: 'dark', path: 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme' },
      hljs: { style: 'tokyo-night-dark', lineNumber: true },
      math: { engine: 'KaTeX', inlineDigit: true },
    },
    after: after,
  });
}

async function main() {
  try {
    await initLoro();
  } catch (err) {
    log('Loro wasm 初始化失败：' + err.message, 'lg-err');
    $('netDot').classList.add('off');
    return;
  }
  log('Loro wasm 就绪');

  const docA = new Loro.LoroDoc();
  const docB = new Loro.LoroDoc();
  docA.setPeerId(1n);
  docB.setPeerId(2n);
  const textA = docA.getText('md');
  const textB = docB.getText('md');

  // 初始内容：A 写，B 同步
  textA.insert(0, INITIAL_MD);
  docA.commit();
  try {
    // 优先新 API，fallback 旧 exportSnapshot
    const snap = typeof docA.export === 'function'
      ? docA.export({ mode: 'snapshot' })
      : docA.exportSnapshot();
    docB.import(snap);
    log('初始文本已就绪（docA → docB 快照同步，' + INITIAL_MD.length + ' chars）');
  } catch (err) {
    log('初始快照同步失败：' + err.message, 'lg-err');
  }

  let vdA = null;
  let vdB = null;
  let ready = 0;
  const onReady = () => {
    ready++;
    if (ready < 2) return;
    bindEditor({ vd: vdA, doc: docA, text: textA, peer: docB, name: 'A' });
    bindEditor({ vd: vdB, doc: docB, text: textB, peer: docA, name: 'B' });
    window.vdA = vdA;
    window.vdB = vdB;
    log('双实例绑定完成，可以开始编辑', 'lg-ok');
  };

  vdA = createVditor('vdA', INITIAL_MD, () => {
    log('实例 A 就绪');
    onReady();
  });
  vdB = createVditor('vdB', INITIAL_MD, () => {
    log('实例 B 就绪');
    onReady();
  });

  $('btnReset').addEventListener('click', () => {
    if (!confirm('重置为初始文本？当前未保存内容会丢失。')) return;
    // 只改 A，通过协同传到 B
    applyMdToLoro(textA, INITIAL_MD);
    docA.commit();
    // 本地也立刻 setValue（subscribe 会再 set 一次，幂等）
    if (vdA) vdA.setValue(INITIAL_MD);
    log('已重置');
  });
  $('btnClearLog').addEventListener('click', () => { $('log').innerHTML = ''; });
}

main();
