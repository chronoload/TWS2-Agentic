# -*- coding: utf-8 -*-
"""worktree P0 验证实例：6909 端口（加载 TS2_dev_p0 最新代码）"""
import sys
import time

sys.path.insert(0, r"C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev_p0\src")
from mcp.server.app import run_server_in_thread  # noqa: E402

server, thread, port = run_server_in_thread(
    workspace_dir=r"C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev_p0\src",
    host="127.0.0.1",
    port=6911,
    open_browser=False,
    auto_port=False,
)
print(f"[DEBUG-P0] server on 127.0.0.1:{port}", flush=True)
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("[DEBUG-P0] stopping", flush=True)
