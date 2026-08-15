// -*- coding: utf-8 -*-
// agent_pool_status 会话隔离测试：其他会话（标签页/loop 实例）的状态变化
// 不得覆盖本页流式状态——防止"他页 loop done → 本页判断完成被打断"（用户报告，偶发）
//
// 方法：从 app.js 提取 _handleAgentPoolStatus 真实函数体，Node 执行，
// stub 三个依赖（_isLocalStreaming/_getAgentSessionId/_setAgentStreaming），
// 验证过滤谓词行为。语义不漂移：changed_session 缺省（旧广播）保持旧行为。
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const appJs = fs.readFileSync(path.join(__dirname, '..', '..', 'server', 'static', 'app.js'), 'utf8');

/** 提取 app.js 中真实函数体（log #30 模式：起始标记 + 首个 `\n}` 截取） */
function extractBody(name, params) {
  const re = new RegExp('function ' + name + '\\(' + params + '\\) \\{([\\s\\S]*?)\\n\\}');
  const m = appJs.match(re);
  assert.ok(m, '未找到 ' + name + ' 定义');
  return m[1];
}

/** 构造 _handleAgentPoolStatus 执行器：stub 依赖 + 记录 _setAgentStreaming 调用 */
function makeHandler(currentSid, opts) {
  opts = opts || {};
  const calls = [];
  const body = extractBody('_handleAgentPoolStatus', 'payload');
  // 内部函数作用域注入 stub：函数体里的 return 只退出内部函数，外层拿 calls
  const fn = new Function('payload', `
    let calls = [];
    const _isLocalStreaming = () => ${opts.localStreaming ? 'true' : 'false'};
    const _getAgentSessionId = () => ${JSON.stringify(currentSid)};
    const _setAgentStreaming = (v, s) => { calls.push([v, s]); };
    (function _handleAgentPoolStatus(payload) {
      ${body}
    })(payload);
    return calls;
  `);
  fn.calls = calls;
  return fn;
}

// ── 1) 失败测试（复现 bug）：异会话广播 → 本页不得被覆盖 ──
test('异会话 changed_session 广播不覆盖本页流式状态（修复前应红）', () => {
  const handler = makeHandler('sess-B');
  const calls = handler({
    changed_session: 'sess-A',   // 其他标签页/loop 实例触发的广播
    instances: [{ session_id: 'sess-B', is_streaming: false }],
  });
  assert.strictEqual(calls.length, 0,
    '异会话状态变化不得调用 _setAgentStreaming（否则本页被误判完成）');
});

// ── 2) 同会话广播：正常同步（语义保留）──
test('同会话 changed_session 广播正常同步 _setAgentStreaming', () => {
  const handler = makeHandler('sess-B');
  const calls = handler({
    changed_session: 'sess-B',
    instances: [{ session_id: 'sess-B', is_streaming: true }],
  });
  assert.strictEqual(calls.length, 1, '同会话应同步一次');
  assert.strictEqual(calls[0][0], true, 'is_streaming=true 应同步为 true');
});

// ── 3) 兼容：无 changed_session（旧广播）→ 保持旧行为（按当前会话 find 同步）──
test('无 changed_session 的旧广播保持旧行为（语义不漂移）', () => {
  const handler = makeHandler('sess-B');
  const calls = handler({
    instances: [{ session_id: 'sess-B', is_streaming: false }],
  });
  assert.strictEqual(calls.length, 1, '缺省来源时按旧行为同步');
  assert.strictEqual(calls[0][0], false);
});

// ── 4) 本地流式保护仍生效（不回归）──
test('本地流式进行中（_isLocalStreaming）ws 广播不打回', () => {
  const handler = makeHandler('sess-B', { localStreaming: true });
  const calls = handler({
    changed_session: 'sess-B',
    instances: [{ session_id: 'sess-B', is_streaming: false }],
  });
  assert.strictEqual(calls.length, 0, '本地流式保护优先，不打回');
});
