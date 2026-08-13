# -*- coding: utf-8 -*-
"""临时测试实例：auto_port 自动选择可用端口，不干扰现有 6906 服务"""
from pathlib import Path
import sys, os

_ws = str(Path(__file__).resolve().parent)
sys.path.insert(0, _ws)
os.chdir(_ws)

from mcp.server.app import run_server
run_server(workspace_dir=_ws, host="0.0.0.0", port=6906,
           open_browser=False, auto_port=True)
