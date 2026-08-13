#!/usr/bin/env node
/**
 * 前端 Agent 子集追踪对齐器 (Node)
 *
 * 目的：精确追踪 static/app.js 中 TS2Client 类的 agent 相关方法，
 *      并找到它们在 UI 代码中的调用点（调用链），与后端端点对齐。
 *      相比 Python 正则，Node 处理 JS 更准确（词法级大括号匹配）。
 *
 * 用法（两种模式）：
 *   1) 插件协议（extractor subprocess 编排，推荐）：
 *        python mcp/interface_chain_extractor.py --root <前端目录> \
 *          --plugin node:mcp/server/static/trace_agent_frontend.mjs
 *      extractor 以 stdin 传 JSON 上下文 {root,out,backend,...}，
 *      脚本 stdout 回 JSON {name,lang,stats,report_md,artifacts}，
 *      FRONTEND_TRACE.md 作为 artifact 落盘到 out/。
 *   2) 独立 CLI（向后兼容）：
 *        node mcp/server/static/trace_agent_frontend.mjs \
 *          [--file app.js] [--class TS2Client] [--client client] \
 *          [--out FRONTEND_TRACE.md] [--label 标签] [--backend index.json]
 *      直接写 mcp/docs/AGENT_FRONTEND_TRACE.md。
 *
 * 输出：
 *   FRONTEND_TRACE.md / AGENT_FRONTEND_TRACE.md — 前端 agent 方法 → 调用点 → 端点 → 后端 对齐报告
 */
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ─── 参数：--stdin-json（插件协议）或 CLI 兼容参数 ────────────
const argv = process.argv.slice(2);
const STDIN_JSON = argv.includes('--stdin-json');
function argVal(name, dflt = '') {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
}

let APP_JS = argVal('--file') || resolve(__dirname, 'app.js');
let OUT_MD = argVal('--out') || resolve(__dirname, '..', '..', 'docs', 'AGENT_FRONTEND_TRACE.md');
let INDEX_JSON = argVal('--backend') || resolve(__dirname, '..', '..', 'docs', 'interface_chain_index.json');
let LABEL = argVal('--label') || APP_JS;

let JS = '';
let LINES = [];

// ─── 工具 ────────────────────────────────────────────────────

function findClassBody(text, className) {
  const re = new RegExp(`class\\s+${className}\\b`);
  const m = re.exec(text);
  if (!m) return null;
  const startIdx = m.index;
  const open = text.indexOf('{', startIdx);
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === '{') depth++;
    else if (text[i] === '}') {
      depth--;
      if (depth === 0) return { startIdx, open, endIdx: i, startLine: countLines(text, startIdx) };
    }
    // 跳过字符串/注释的简单防护
  }
  return { startIdx, open, endIdx: text.length, startLine: countLines(text, startIdx) };
}

function countLines(text, idx) {
  let n = 0;
  for (let i = 0; i < idx; i++) if (text[i] === '\n') n++;
  return n + 1;
}

/** 忽略字符串字面量与注释后查找字符 */
function stripStringsAndComments(seg) {
  return seg
    .replace(/\/\*[\s\S]*?\*\//g, ' ') // 块注释
    .replace(/\/\/[^\n]*/g, ' ')       // 行注释
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/`(?:\\.|[^`\\])*`/g, '``');
}

/** 在类体中提取方法定义（词法级） */
function extractMethods(text) {
  const cls = findClassBody(text, 'TS2Client');
  if (!cls) return [];
  const body = text.slice(cls.open + 1, cls.endIdx);
  const bodyLines = body.split(/\r?\n/);
  const methods = [];
  // 方法定义正则：行首缩进 + (async )?name(params) { 或 单行 name(params) { ... }
  const methodRe = /^(\s*)(?:async\s+)?(get\s+|set\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{/;
  const skip = new Set(['if', 'for', 'while', 'switch', 'catch', 'return', 'function', 'try', 'else', 'do', 'new', 'this']);
  for (let i = 0; i < bodyLines.length; i++) {
    const m = methodRe.exec(bodyLines[i]);
    if (!m) continue;
    const name = m[3];
    if (skip.has(name) || name.startsWith('_')) continue;
    const indent = m[1].length;
    if (indent === 0) continue; // 不允许顶层
    // 方法体：直到缩进小于等于当前且大括号平衡
    let depth = 0;
    let j = i;
    let bodySeg = '';
    let braceBalanced = false;
    let endLine = i;
    for (; j < bodyLines.length; j++) {
      const ln = bodyLines[j];
      const stripped = stripStringsAndComments(ln);
      for (const ch of stripped) {
        if (ch === '{') depth++;
        else if (ch === '}') depth--;
      }
      bodySeg += ln + '\n';
      if (depth === 0 && j >= i) { braceBalanced = true; endLine = j; break; } // j>=i: 允许单行方法
    }
    if (!braceBalanced) endLine = Math.min(i + 6, bodyLines.length - 1);
    methods.push({
      name,
      line: cls.startLine + i,       // 文件行号
      endLine: cls.startLine + endLine,
      params: m[4].split(',').map(s => s.trim()).filter(Boolean),
      accessor: !!m[2],
      body: bodySeg,
    });
    i = endLine;
  }
  return methods;
}

// ─── 方法信息提取 ────────────────────────────────────────────

function endpointInfo(method) {
  const seg = method.body;
  // HTTP 方法判定
  let http = 'POST';
  if (/\.api_get\(/.test(seg)) http = 'GET';
  else if (/\.api_patch\(/.test(seg)) http = 'PATCH';
  else if (/\.api_put\(/.test(seg)) http = 'PUT';
  else if (/\.api_del\(/.test(seg)) http = 'DELETE';
  else if (/fetch\(/.test(seg)) {
    const mm = seg.match(/method\s*:\s*['"]([A-Z]+)['"]/);
    http = mm ? mm[1] : 'GET';
  }

  // 端点 URL：提取方法体内所有字符串字面量片段，从含 /api/ 的锚点向两端按 + 拼接扩展
  let endpoint = '';
  const litRe = /(['"`])((?:\\.|(?!\1)[^\\])*)\1/g;
  const pieces = [];
  let m3;
  while ((m3 = litRe.exec(seg))) {
    pieces.push({ start: m3.index, end: m3.index + m3[0].length, text: m3[2] });
  }
  const anchorIdx = pieces.findIndex(p => p.text.includes('/api/'));
  if (anchorIdx >= 0) {
    let url = pieces[anchorIdx].text;
    // gap 分类：' + x + ' 有变量（路径参数） / ' + ' 无变量（纯拼接）
    const gapVar = (g) => /^['"`]?\s*\+\s*[A-Za-z_$][\w$]*\s*\+\s*['"`]?$/.test(g);
    const gapPlain = (g) => /^['"`]?\s*\+\s*['"`]?$/.test(g);
    // 向左扩展（前缀变量忽略，仅纯拼接合并）
    for (let i = anchorIdx - 1; i >= 0; i--) {
      const gap = seg.slice(pieces[i].end, pieces[anchorIdx].start);
      if (gapPlain(gap)) { url = pieces[i].text + url; continue; }
      break;
    }
    // 向右扩展（变量 → {} 占位；纯拼接直接合并）
    for (let i = anchorIdx + 1; i < pieces.length; i++) {
      const gap = seg.slice(pieces[i - 1].end, pieces[i].start);
      if (gapPlain(gap)) { url = url + pieces[i].text; continue; }
      if (gapVar(gap)) { url = url + '{}' + pieces[i].text; continue; }
      break;
    }
    endpoint = url.replace(/\$\{[^}]*\}/g, '{}');
    // 清理：前缀 ${API_BASE} / 路径变量 / 尾部 query 参数拼接
    endpoint = endpoint.replace(/^\$\{[^}]*\}\/?/, '');
    endpoint = endpoint.replace(/^\{\}/, '').replace(/\{\}$/, '').replace(/\{\}\?/g, '?');
  }

  // payload 键（this.api('...', {...}) / fetch body）
  const payloadKeys = [];
  const apiCall = seg.match(/\.api\(\s*['"`][^'"`]+['"`]\s*,\s*(\{[^}]*\})/);
  if (apiCall) {
    const obj = apiCall[1];
    if (/\.\.\./.test(obj)) payloadKeys.push('...(spread)');
    for (const k of obj.matchAll(/([A-Za-z_$][\w$]*)\s*:/g)) payloadKeys.push(k[1]);
    // shorthand
    for (const k of obj.matchAll(/(?:\{\s*|,\s*)([A-Za-z_$][\w$]*)(?=\s*[,}])/g)) {
      if (!payloadKeys.includes(k[1])) payloadKeys.push(k[1]);
    }
  }
  return { http, endpoint, payloadKeys: [...new Set(payloadKeys)] };
}

// ─── 调用点追踪 ──────────────────────────────────────────────

/** 全文件函数栈：返回第 lineIdx 行所属的最近函数名 */
function enclosingFunction(lineIdx) {
  const stack = []; // { name, depth }
  const fnRe = /^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/;
  const constFnRe = /^const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\(.*\)\s*=>)/;
  const methodRe = /^(\s*)(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{\s*$/;
  let depth = 0;
  let lastResult = null;
  for (let i = 0; i <= lineIdx; i++) {
    const ln = LINES[i];
    const stripped = stripStringsAndComments(ln);
    const fn = fnRe.exec(ln) || constFnRe.exec(ln) || methodRe.exec(ln);
    const name = fn && (fn[1] || fn[2]);
    const skip = new Set(['if', 'for', 'while', 'switch', 'catch', 'return', 'function', 'try', 'else', 'do', 'new', 'this']);
    if (name && !skip.has(name)) {
      // 只认函数，记录进入深度
      stack.push({ name, depth });
      lastResult = name;
    }
    for (const ch of stripped) {
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        while (stack.length && stack[stack.length - 1].depth >= depth) stack.pop();
      }
    }
    // 行末闭合时弹出
    if (stack.length) {
      const top = stack[stack.length - 1];
      // 该行是函数最后一行（缩进返回）时已在上面处理
      void top;
    }
  }
  return stack.length ? stack[stack.length - 1].name : '(global)';
}

/** 查找 client.<method>( 的调用点（只追踪给定方法集合） */
function trackCallSites(targetNames) {
  const results = new Map();
  const callRe = /\bclient\.([A-Za-z_$][\w$]*)\s*\(/g;
  let m;
  while ((m = callRe.exec(JS))) {
    const name = m[1];
    if (!targetNames.has(name)) continue;
    const line = countLines(JS, m.index);
    const caller = enclosingFunction(line - 1);
    if (!results.has(name)) results.set(name, []);
    const calls = results.get(name);
    // 收集参数摘要（简单截取）
    const openIdx = m.index + m[0].length - 1;
    let depth = 0;
    let argSeg = '';
    for (let i = openIdx; i < JS.length; i++) {
      if (JS[i] === '(') depth++;
      else if (JS[i] === ')') { depth--; if (depth === 0) { argSeg = JS.slice(openIdx + 1, i); break; } }
    }
    calls.push({ line, caller, args: argSeg.slice(0, 120) });
  }
  return results;
}

// ─── 后端对齐 ────────────────────────────────────────────────

function loadBackendIndex() {
  try {
    const idx = JSON.parse(readFileSync(INDEX_JSON, 'utf-8'));
    return new Map(idx.endpoints.map(e => [e.method + ' ' + normPath(e.path), e]));
  } catch {
    return new Map();
  }
}

function normPath(p) {
  return p.replace(/\{[^}]+\}/g, '{}').replace(/\/+$/, '');
}

// ─── 主流程 ──────────────────────────────────────────────────

function readStdin() {
  return new Promise((res) => {
    let data = '';
    process.stdin.setEncoding('utf-8');
    process.stdin.on('data', (chunk) => (data += chunk));
    process.stdin.on('end', () => res(data));
  });
}

async function main() {
  if (STDIN_JSON) {
    // 插件协议：extractor 以 stdin 传 JSON 上下文 {root,out,backend,file,frontend_class,client}
    const ctx = JSON.parse((await readStdin()) || '{}');
    const root = ctx.root || __dirname;
    const outDir = ctx.out || resolve(root, '..');
    APP_JS = ctx.file || resolve(root, 'app.js');
    OUT_MD = resolve(outDir, 'FRONTEND_TRACE.md');
    if (ctx.backend) INDEX_JSON = ctx.backend;
    LABEL = ctx.frontend_label || ctx.file || APP_JS;
  }
  JS = readFileSync(APP_JS, 'utf-8');
  LINES = JS.split(/\r?\n/);

  const methods = extractMethods(JS);
  const agentMethods = methods.filter(m =>
    /agent|Agent|checkpoint|Checkpoint|swarm|Swarm|migrate/i.test(m.name) ||
    /\/api\/agent\//.test(m.body) || /\/api\/swarm\//.test(m.body)
  );
  const backend = loadBackendIndex();
  const callSites = trackCallSites(new Set(agentMethods.map(m => m.name)));
  const callCount = [...callSites.values()].reduce((a, c) => a + c.length, 0);

  const mdLines = [];
  mdLines.push('# 前端 Agent 子集追踪报告（自动生成）\n');
  mdLines.push(`> 由 \`${LABEL}\` 生成 · Node ${process.version}`);
  mdLines.push(`> 重新生成：extractor --plugin node:${resolve(__dirname, 'trace_agent_frontend.mjs')}\n`);
  mdLines.push(`- TS2Client 方法总数: **${methods.length}**`);
  mdLines.push(`- Agent 相关方法: **${agentMethods.length}**`);
  mdLines.push(`- 检测到调用点: **${callCount}**\n`);

  mdLines.push('---\n\n## 1. Agent 方法 → 端点对齐\n');
  mdLines.push('| 前端方法 | 行号 | HTTP | 端点 | 后端状态 | Payload 键 |');
  mdLines.push('|----------|------|------|------|----------|-----------|');
  let missing = 0;
  for (const m of agentMethods) {
    const info = endpointInfo(m);
    const key = info.http + ' ' + normPath(info.endpoint);
    const okBackend = backend.has(key) || [...backend.keys()].some(k => k.split(' ').slice(1).join(' ') === normPath(info.endpoint));
    if (!okBackend) missing++;
    const status = okBackend ? '✅ 已对齐' : '⚠️ 后端缺失';
    mdLines.push(`| \`${m.name}\` | ${m.line} | ${info.http} | \`${info.endpoint || '—'}\` | ${status} | ${info.payloadKeys.join(', ') || '—'} |`);
  }
  mdLines.push(`\n**后端缺失: ${missing} 个**\n`);

  mdLines.push('\n## 2. 调用点（UI → client 方法）\n');
  for (const m of agentMethods) {
    const calls = callSites.get(m.name) || [];
    mdLines.push(`### \`${m.name}\` — 行 ${m.line}${calls.length ? `，调用 ${calls.length} 处` : '，无直接调用'}\n`);
    if (calls.length) {
      mdLines.push('| 调用行 | 所在函数 | 参数摘要 |');
      mdLines.push('|--------|----------|----------|');
      for (const c of calls) {
        mdLines.push(`| ${c.line} | \`${c.caller}\` | \`${c.args}\` |`);
      }
    }
    mdLines.push('');
  }

  mdLines.push('\n## 3. 后端对应端点详情（agent/checkpoint/swarm）\n');
  for (const [key, ep] of backend) {
    if (ep.path.startsWith('/api/agent/') || ep.path.startsWith('/api/swarm/')) {
      mdLines.push(`- \`${ep.method} ${ep.path}\` — \`${ep.func}\` (${ep.file}:${ep.line})${ep.request_model ? ` · 模型 \`${ep.request_model}\`` : ''}`);
    }
  }

  const md = mdLines.join('\n');

  if (STDIN_JSON) {
    // 插件协议：stdout 只输出一行 JSON（artifacts 由 extractor 落盘到 out/）
    process.stdout.write(JSON.stringify({
      name: 'frontend-trace', lang: 'node',
      stats: { methods: methods.length, agentMethods: agentMethods.length,
               callSites: callCount, backendMissing: missing },
      report_md: md,
      artifacts: [{ path: 'FRONTEND_TRACE.md', content: md }],
    }));
  } else {
    mkdirSync(dirname(OUT_MD), { recursive: true });
    writeFileSync(OUT_MD, md, 'utf-8');
    console.log(`[OK] → ${OUT_MD}`);
    console.log(`TS2Client 方法=${methods.length}  Agent 相关=${agentMethods.length}  调用点=${callCount}  后端缺失=${missing}`);
    for (const m of agentMethods) {
      const calls = callSites.get(m.name) || [];
      if (!calls.length) console.log(`  · ${m.name} (行${m.line}) 无直接调用`);
    }
  }
}

main().catch((e) => { console.error(String((e && e.stack) || e)); process.exit(1); });
