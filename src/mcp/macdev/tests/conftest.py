import sys
from pathlib import Path

_MCP = str(Path(__file__).resolve().parent.parent)


def pytest_configure(config):
    """确保收集前 macdev 包可见（模块级 insert 在部分 pytest 环境不生效时兜底）"""
    if _MCP not in sys.path:
        sys.path.insert(0, _MCP)


sys.path.insert(0, _MCP)
