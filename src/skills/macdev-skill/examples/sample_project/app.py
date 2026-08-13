# 示例项目 app.py — 故意埋入真实缺陷样本，供 macdev audit 演示
#   1. 跨文件调用 util（lib.py）→ 亲属追逐 cross_file 定位
#   2. threading.Event clear() 无 set() → flag_lifecycle 缺陷
#   3. 硬编码密钥/端口 → scan 4 维命中
#   4. 数据池 _agent_cache → data_pools 命中
import os
import threading
from fastapi import FastAPI

from lib import util

app = FastAPI()

API_KEY = "sk-secret-demo-value"
PORT = 8123

_agent_cache: dict = {}


class AgentSession:
    def __init__(self):
        self._chat_active = threading.Event()
        self._instance_id = 0

    def stop(self):
        # 缺陷：clear 后无 set 恢复（flag_lifecycle: clear_without_set）
        self._chat_active.clear()


def _helper():
    return util() + 1


@app.get("/api/a")
def a():
    return _helper()


@app.get("/api/b")
def b():
    return a()
