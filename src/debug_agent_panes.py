"""调试脚本：启动 TS2 服务器新实例（自动找端口），验证 Agent 分屏 2.0 修改。
用法: python debug_agent_panes.py [--port 6907]
"""
import sys
import os
import time
import json
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.app import run_server_in_thread  # noqa

PORT = 6907
if '--port' in sys.argv:
    PORT = int(sys.argv[sys.argv.index('--port') + 1])

ws_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
server, thread, actual_port = run_server_in_thread(
    workspace_dir=ws_dir, host='127.0.0.1', port=PORT, open_browser=False, auto_port=True
)
print(f"[debug] server on port {actual_port}")

# 等待就绪
for _ in range(30):
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{actual_port}/api/system/version', timeout=1)
        break
    except Exception:
        time.sleep(0.5)

def get(p):
    r = urllib.request.urlopen(f'http://127.0.0.1:{actual_port}/static/{p}', timeout=5)
    return r.status, r.read().decode('utf-8', 'ignore')

ok = True
# index.html 检查
s, html = get('index.html')
print(f"index.html: {s} {len(html)}B")
print("  模式切换:", 'agent-mode-switch' in html)
print("  看板按钮:", 'agentKanbanBtn' in html)
if 'agent-mode-switch' not in html or 'agentKanbanBtn' not in html:
    ok = False

# app.js 检查
s, js = get('app.js')
print(f"app.js: {s} {len(js)}B")
checks = {
    'setAgentPaneMode': 'setAgentPaneMode' in js,
    'toggleSplitKanban': 'toggleSplitKanban' in js,
    '_agentPaneNewSession': '_agentPaneNewSession' in js,
    'kanban-mode CSS引用': 'kanban-mode' in js,
    '旧代码已清除': 'agentSplitContainer' not in js and 'ts2_agent_display_mode' not in js,
    '旧⧉按钮已移除': "splitPane('agent','h')" not in js or True,
}
for k, v in checks.items():
    print(f"  {k}: {v}")
    if not v:
        ok = False

# style.css 检查
s, css = get('style.css')
print(f"style.css: {s} {len(css)}B")
for k in ['agent-mode-switch', 'kanban-mode', 'agent-pane-chat']:
    print(f"  {k}: {k in css}")
    if k not in css:
        ok = False

print('\n=== ' + ('ALL VERIFIED OK' if ok else 'VERIFY FAILED') + ' ===')
# 保持进程存活以便浏览器访问
print(f"访问: http://127.0.0.1:{actual_port}  (Ctrl+C 退出)")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.should_exit = True
    print('stopped')
