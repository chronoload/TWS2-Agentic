# 原子 core：顶层常量/import/模块头（原 plan_cli.py）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations
"""Plan 文档结构化 CLI — 像 writing-plans skill 一样生成 plan，但通过结构化 API 而非手写文件。

设计：
  - plan 存 SQLite（mcp/data/plans.db），plan.md 由数据渲染，可复现。
  - 对齐 writing-plans 规范：plan 级（goal/arch/stack）、task 级（files 清单）、
    step 级（checkbox 步骤 + 代码块 + Run/Expected，覆盖 TDD 闭环）。
  - 任务可引用需求条目（--req kind:name），export 时实时显示需求状态
    （open/done/missing，来自 requirement_cli 维护的 requirements.db）。
  - Agent 不再 WriteFile 写 plan 文档，直接填 API。

用法：
  python mcp/plan_cli.py create --title "接入新端点" --goal "目标" --arch "方案" --stack "FastAPI/JS"
  python mcp/plan_cli.py list
  python mcp/plan_cli.py update --id 1 --status done
  python mcp/plan_cli.py task add --plan 1 --title "实现后端" --detail "..." --files "Create: mcp/x.py`nModify: mcp/y.py:10-20" --req path:/api/agent/chat/stream
  python mcp/plan_cli.py task list --plan 1
  python mcp/plan_cli.py task step add --task 1 --text "写失败测试" --action test --code "def test_x():\n    pass" --lang python --run "pytest tests/test_x.py -v" --expected "FAIL"
  python mcp/plan_cli.py task step list --task 1
  python mcp/plan_cli.py task step update --id 1 --status done
  python mcp/plan_cli.py task step delete --id 1
  python mcp/plan_cli.py task delete --id 1
  python mcp/plan_cli.py export --id 1 --out mcp/docs/PLAN_1.md --format writing-plans
"""

from __future__ import annotations

import argparse

import contextlib

import io

import json

import os

import re

import shutil

import sqlite3

import subprocess

import sys

from datetime import datetime

from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = MCP_ROOT.parent

PLANS_DB = MCP_ROOT / "data" / "plans.db"

REQ_DB = MCP_ROOT / "data" / "requirements.db"

DOCS_DIR = MCP_ROOT / "docs"

INDEX_JSON = MCP_ROOT / "docs" / "interface_chain_index.json"

CHAIN_DB = DOCS_DIR / "interface_chain.db"

if __name__ == "__main__":
    sys.exit(main())
