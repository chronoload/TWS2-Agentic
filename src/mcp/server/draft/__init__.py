"""Texpile Draft 引擎 Python 复刻（可拔插）。

移植自 texpile 原版 Electron 主进程（electron/src/draft-service.ts、draft-daemon.ts）。
原版用 node.js child_process 调 lualatex，这里用 asyncio.create_subprocess_exec；
Lua 提取脚本（walker.lua / page-extract.lua / texd-loop.lua）原样复用，不做任何修改。

架构：
- compile_draft(root, main_file, engine_dir)   全量编译，返回 DraftResult
- DraftDaemon(root, main_file, engine_dir)     常驻 lualatex 进程，typeset_paragraph 单段排版

依赖：
- 用户机器上必须装 lualatex（TeX Live / MiKTeX）
- biber / bibtex 按需调用（缺失则引用不解析，但不会让编译失败）
"""
from .service import compile_draft, typeset_paragraph, stop_draft, DraftDaemon, get_engine_dir

__all__ = ["compile_draft", "typeset_paragraph", "stop_draft", "DraftDaemon", "get_engine_dir"]
