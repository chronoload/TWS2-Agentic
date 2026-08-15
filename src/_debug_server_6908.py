# -*- coding: utf-8 -*-
"""T3 验证实例：6908（停止按钮 + 队列放回输入框 + content 校验修复）"""
import sys
import time

sys.path.insert(0, r"C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev\src")
from mcp.server.app import run_server_in_thread  # noqa: E402

server, thread, port = run_server_in_thread(
    workspace_dir=r"C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev\src",
    host="127.0.0.1",
    port=6908,
    open_browser=False,
    auto_port=False,
)
print(f"[T3] server on 127.0.0.1:{port}", flush=True)
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("[T3] stopping", flush=True)
