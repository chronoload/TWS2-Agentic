# 原子 core：顶层常量 / import / 模块头（原 interface_chain_extractor.py 头部区）
# 由 scripts/split_extractor.py 机械生成，勿手改。
from __future__ import annotations
"""接口链路提取器 — 仅用 Python 内置模块 (ast/json/re/pathlib)

用途：
  1. 从后端 app.py / saber/api.py 提取 FastAPI 端点、Pydantic 请求模型、返回字段
  2. 从 subagent/param_chain/agent 提取类型定义（dataclass / 关键方法签名）
  3. 从前端 static/app.js 提取 TS2Client 方法 → 端点映射
  4. 交叉比对 → 检测语义偏移（前端字段 ↔ 后端模型不匹配、端点缺失等）
  5. 生成 Markdown 接口链路文档（可重复运行，代码变更后重新生成即可）

用法：
  python mcp/interface_chain_extractor.py [--json] [--md] [--out DIR]
"""

from __future__ import annotations

import ast

import argparse

import csv

import importlib

import json

import os

import re

import sqlite3

import sys

from dataclasses import dataclass, field, asdict

from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parent

APP_PY = MCP_ROOT / "server" / "app.py"

SABER_PY = MCP_ROOT / "server" / "saber" / "api.py"

SUBAGENT_DIR = MCP_ROOT / "subagent"

PARAM_CHAIN_PY = MCP_ROOT / "param_chain.py"

AGENT_PY = MCP_ROOT / "agent.py"

TASK_DIR = MCP_ROOT / "tasks"

DEFAULT_TASK = TASK_DIR / "ts2.task.json"

TASK_FILES: dict = {}

TASK_ENDPOINTS: list = []

TASK_AGENT_METHODS: tuple = ()

CHAINS_CFG: dict = {}

TASK_SCAN_DIRS: list = []

try:
    from mcp.strategies import load_strategy, ChainStrategy
except ImportError:
    from strategies import load_strategy, ChainStrategy

ACTIVE_STRATEGY: ChainStrategy = ChainStrategy()

APP_JS = MCP_ROOT / "server" / "static" / "app.js"

CHAIN_BREAK_RULES = {
    # 会话读取链：活跃会话（实例在池中）不得回退检查点兜底
    "agent_session_get": {
        "fallback_sources": ["_build_messages_from_checkpoints", "get_checkpoints"],
        "guard_terms": ["agent_present", "was_in_pool"],
        "detail": ("会话读取链断裂：活跃会话（实例在池中）回退到 FileVersionDB 检查点兜底，"
                   "流式进行中 token 未落盘时会读到冻结快照，前端渲染旧历史、跟不上流式而卡死。"
                   "兜底调用必须位于活跃性守卫（agent_present/was_in_pool 否定）之下。"),
    },
    "agent_session_switch": {
        "fallback_sources": ["_build_messages_from_checkpoints", "get_checkpoints"],
        "guard_terms": ["agent_present", "was_in_pool"],
        "detail": ("会话切换链断裂：活跃会话（原在池中）回退检查点兜底会污染活跃实例，"
                   "读到冻结快照。兜底仅用于冷启动/迁移场景，须有 was_in_pool 守卫。"),
    },
}

BEHAVIOR_RULES: dict = {}

EXTRACTOR_ARTIFACTS = [
    # TS2 默认流程（无 --root/--preset）
    ("INTERFACE_CHAIN.md", "8 维接口链路报告（契约/对齐/依赖链/def-use/语义偏移/行为契约/状态标志/合并仲裁/命名空间）"),
    ("interface_chain.db", "SQLite 可查询索引（endpoints/models/client_methods/drifts/defuse_*/behavior/flag/merge/id_source/stats）"),
    ("interface_chain_index.json", "端点/模型/缺陷 JSON 索引（plan_cli defect list 数据源）"),
    ("endpoints.csv", "端点明细（method/path/func/file/line/request_model/response_keys/doc）"),
    ("models.csv", "请求模型字段明细（name/file/line/field/type/required/default）"),
    ("drifts.csv", "前后端语义漂移（kind/client/endpoint/detail）"),
    ("defuse_issues.csv", "def-use 读取-赋值一致性缺陷"),
    ("defuse_reads.csv", "def-use 读取点全量"),
    ("behavior_issues.csv", "行为契约缺失（entry/missing/file/detail）"),
    ("flag_lifecycle.csv", "状态标志生命周期（clear_without_set/stale_cache）"),
    ("merge_direction.csv", "合并方向仲裁（count_only_arbitration）"),
    ("id_source.csv", "标识符命名空间来源契约（cross_namespace_key/unguarded_key_consumer）"),
    ("FRONTEND_TRACE.md", "前端对齐报告（--frontend 指定入口时，Node 词法追踪输出）"),
    # 新增 4 维度扫描产物
    ("hardcoded.csv", "硬编码常量（url/port/path/key/secret/token/password/db_host/db_port）"),
    ("env_vars.csv", "环境变量读取（os.environ/os.getenv/process.env）"),
    ("data_pools.csv", "数据池/状态（dict/list/Singleton/cache/pool/store/vector_store 初始化）"),
    ("static_resources.csv", "静态资源路径（StaticFiles/express.static/模板/图片/字体/文件 IO）"),
    # 数据资源追踪报告
    ("DATA_RESOURCES_TRACE.md", "数据资源追踪报告（数据池/环境变量/硬编码/静态资源/端点数据源）"),
    # 通用项目模式（--root / --preset）
    ("PROJECT_CHAIN.md", "通用模式报告：模块地图/枢纽/跨模块边/API 端点/请求模型 + §7 关键端点依赖链（text + mermaid）"),
    ("project_map.json", "通用模式模块地图 JSON（modules/edges/hubs/endpoints/models/plugins）"),
    ("call_chain.csv", "通用模式调用链边（src_file/src_func/dst/dst_kind/dst_module/line）"),
    ("module_map.csv", "通用模式模块统计（module/file/classes/funcs/lines/out_degree/in_degree）"),
]

ART_NAMES = {n for n, _ in EXTRACTOR_ARTIFACTS}

NOISE_CALLS = {
    "logger", "log", "logging", "len", "str", "int", "float", "bool", "list", "dict", "set",
    "getattr", "setattr", "hasattr", "isinstance", "issubclass", "sum", "min", "max", "sorted",
    "abs", "round", "print", "open", "super", "type", "iter", "next", "enumerate", "zip", "map",
    "filter", "any", "all", "reversed", "repr", "Path", "os", "time", "json", "re", "asyncio",
    "traceback", "import", "sys", "copy", "threading", "uuid", "datetime", "random", "struct",
    "StringIO", "tempfile", "shutil", "glob", "fnmatch", "hashlib", "base64", "urllib", "requests",
    "ok", "err",  # API 响应封装，无依赖追踪价值
}

NOISE_ATTRS = {
    "get", "set", "append", "extend", "insert", "pop", "remove", "update", "items", "keys",
    "values", "join", "split", "replace", "strip", "format", "startswith", "endswith", "json",
}

HTTP_ATTRS = {"get", "post", "put", "delete", "patch", "websocket"}

_EXTERNAL_OBJ_HINTS = {
    "response", "usage", "chunk", "item", "tool", "tc", "tool_call", "step",
    "msg", "event", "req", "request", "args", "mod", "generator",
    "xcode_generator", "msvs_generator", "client", "conn", "obj", "ctx",
    "sys",  # sys.frozen 等由运行时注入
}

ID_SOURCE_RULES: list = []

_SCAN_DEFAULT_EXCLUDE = ("test", "tests", "migrations", "node_modules", ".git", ".venv",
                         "venv", "build", "dist", "site-packages", "__pycache__",
                         "docs", "examples", "assets", "static_arch", "static-branch",
                         "web", "android", "archs", "draft", "static-capacitor")

_HARDCODE_KEYWORDS = re.compile(
    r'(api[_-]?key|secret|token|password|passwd|pwd|DB_HOST|DB_PORT|'
    r'database[_-]?url|db[_-]?host|db[_-]?port|connection[_-]?string|'
    r'endpoint|base[_-]?url|api[_-]?url|server[_-]?url)', re.I)

_HARDCODE_URL_RE = re.compile(r'https?://[^\s\'\"<>]+')

_HARDCODE_PORT_RE = re.compile(r':\s*(\d{2,5})')

_HARDCODE_PATH_RE = re.compile(r'["\'](/(?:[\w.\-]+/?)+)["\']')

_ENV_VAR_JS_RE = re.compile(r"process\.env\[['\"]([A-Z0-9_]+)['\"]\]|process\.env\.([A-Z0-9_]+)")

_DATA_POOL_KINDS = {
    "cache": re.compile(r'(?:cache|_cache|Cache)'),
    "pool": re.compile(r'(?:pool|_pool|Pool|PoolManager)'),
    "store": re.compile(r'(?:store|_store|Store|SessionStore)'),
    "agent_pool": re.compile(r'(?:agent_pool|_agent_pool|AgentPool)'),
    "model_cache": re.compile(r'(?:model_cache|_model_cache|ModelCache)'),
    "vector_store": re.compile(r'(?:vector_store|_vector_store|VectorStore|qdrant|chroma|faiss|redis)'),
    "singleton": re.compile(r'(?:singleton|_instance|__instance|Singleton)'),
    "dict": re.compile(r'(?:_dict|registry|_registry|_map|_index)'),
    "list": re.compile(r'(?:_list|_items|_entries)'),
}

_STATIC_FILE_RE = re.compile(
    r'(?:StaticFiles|statics|express\.static|app\.use\(\s*express\.static|mount\s*\(\s*["\']static["\'])')

_IO_PATH_RE = re.compile(r'(?:open|Path\s*\(|Path\([^)]*\))\s*\(\s*["\']([^"\']{3,})["\']')

_PATH_LITERAL_RE = re.compile(r'["\']((?:\.{1,2}/)?(?:[\w.\-]+/)*(?:[\w.\-]+)\.(?:html|htm|jinja2|jinja|'
                               r'css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|pdf|md|txt))["\']')

_BUILTIN_NAMES = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))

DEFAULT_EXCLUDE = ("test", "tests", "migrations", "node_modules", ".git", ".venv",
                   "venv", "build", "dist", "site-packages", "__pycache__",
                   "docs", "examples", "assets", "static_arch", "static-branch")

PROJECT_PRESETS: dict = {
    "ts2": {
        "root": "mcp",
        "out": "ts2map",
        "exclude": ["web", "static", "static_desktop", "static_electron", "staticselfcontaine",
                    "cache_data", "data", "plugins", "mcp_client", "sandbox", "research", "feishu",
                    "extensions", "ecosystem", "memory", "rag", "voice", "vis", "automation",
                    "skill_system", "gt", "runtime", "skills", "archs", "draft", "static-capacitor",
                    "prompt", "subagent", "test", "sch"],
    },
    "kimi": {
        "root": r"c:\Users\qu\Desktop\物理科学与技术论题\TS2-reference\agent\kimi-cli-main\src",
        "out": "kimi",
        "exclude": [],
    },
    "kimicode": {
        "root": r"c:\Users\qu\Desktop\物理科学与技术论题\TS2-reference\agent\kimi-code-main",
        "out": "kimicode",
        "exclude": ["node_modules", "dist", "build", "coverage", ".pnpm", "scripts", "docs"],
    },
}

_TS_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function",
                "import", "export", "typeof", "new", "delete", "in", "of",
                "instanceof", "throw", "yield", "await", "async", "case", "do",
                "else", "finally", "try", "with", "class", "extends", "super",
                "this", "const", "let", "var", "void", "static", "default"}

_TS_FN_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+"
                       r"([A-Za-z_$][\w$]*)\s*\(", re.M)

_TS_ARROW_RE = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
                          r"\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", re.M)

_TS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)

_TS_METHOD_RE = re.compile(r"^\s{2,}(?:async\s+|static\s+|public\s+|private\s+|protected\s+"
                           r"|get\s+|set\s+|readonly\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M)

_TS_IMPORT_RE = re.compile(r"import\s+[^'\";\n]*?\s+from\s+['\"]([^'\"]+)['\"]", re.M)

_TS_REQUIRE_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]")

_TS_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\(")

_TS_ENTRY_RE = re.compile(r'''require\.main\s*===|import\.meta\.url|process\.argv\b|main\s*:\s*["'`]''')

_TS_HTTP_METHODS = re.compile(r"\.(get|post|put|delete|patch|options)\s*\(\s*['\"`]([^'\"`]+)['\"`]")

PLUGIN_CONTEXT_KEYS = ("root", "out", "backend", "frontend_class", "client")

_BUILTIN_TRANSFORM_NAMES: list[str] = []

if __name__ == "__main__":
    main()
