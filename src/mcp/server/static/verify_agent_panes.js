// Agent 分屏 2.0 静态一致性验证脚本
const fs = require('fs');
const path = process.argv[2] || 'app.js';
const src = fs.readFileSync(path, 'utf8');
let ok = true;

const funcs = [
  'setAgentPaneMode', 'initAgentPaneMode', '_applyAgentModeUI', 'closeAllAgentPanes',
  'toggleSplitKanban', '_restoreSplitKanban',
  '_agentPaneInit', '_agentPaneUpdateInfo', '_agentPaneLoadSessions',
  '_agentPaneSelectSession', '_agentPaneLoadSession', '_agentPaneRenderMessages',
  '_agentPaneRenderOne', '_agentPaneSend', '_agentPaneNewSession',
  '_agentPaneToggleNestedKanban', '_agentPaneRenderNestedKanban',
  '_agentPaneStartPolling', '_agentPaneStopPolling'
];
funcs.forEach(f => {
  if (!src.includes('function ' + f + '(')) { console.log('MISSING_FUNC: ' + f); ok = false; }
});
console.log('functions defined: ' + funcs.length + (ok ? ' ALL OK' : ' FAIL'));

// onclick 引用（避免转义，用双引号字符串）
const refs = [
  "splitPane(\\'agent\\',\\'h\\')", 'toggleSplitKanban()', '_agentPaneNewSession',
  '_agentPaneSend', 'toggleHarnessPanel(event)', 'toggleFlowNav()',
  'toggleConvSidebar()', 'toggleAgentStatusPanel()', 'showAgentCheckpoints()'
];
refs.forEach(c => {
  if (!src.includes(c)) { console.log('MISSING_REF: ' + c); ok = false; }
});
console.log('onclick refs OK: ' + ok);

// id 一致性
const ids = ['agentPaneSelect-', 'agentPaneStatus-', 'agentPaneMsgs-', 'agentPaneTyping-',
  'agentPaneInput-', 'agentPaneSend-', 'agentPaneBar-', 'agentPaneInfo-', 'agentPaneChat-', 'agentPaneBody-'];
ids.forEach(id => {
  const created = (src.split('id="' + id).length - 1);
  const used = (src.split("getElementById('" + id).length - 1);
  if (used > 0 && created === 0) { console.log('ID_CREATE_MISSING: ' + id); ok = false; }
  console.log('  ' + id + ': created=' + created + ' used=' + used);
});

['ts2_agent_pane_mode', 'ts2_agent_kanban'].forEach(k => {
  if (!src.includes(k)) { console.log('MISSING_LS_KEY: ' + k); ok = false; }
});
console.log(ok ? '=== ALL CHECKS PASSED ===' : '=== CHECKS FAILED ===');
process.exit(ok ? 0 : 1);
