# -*- coding: utf-8 -*-
"""pytest 共享配置：确保 src/ 在 sys.path 上，使 `from mcp.harness...` 可导入"""
import sys
from pathlib import Path

# mcp/tests/conftest.py -> parents[2] = src/（工作目录，mcp 包所在）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
