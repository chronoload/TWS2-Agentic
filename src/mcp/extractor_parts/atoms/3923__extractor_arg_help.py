# 原子：_extractor_arg_help（原 interface_chain_extractor.py 第 3923 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _extractor_arg_help(action) -> str:
    """格式化 argparse action 的选项与说明（供 --doc 自举导出）。"""
    if action.help == argparse.SUPPRESS:
        return ""
    opts = " ".join(action.option_strings) if action.option_strings else "[" + action.dest + "]"
    req = "**必填** " if action.required else ""
    meta = ""
    if action.choices:
        meta = f"（choices: {', '.join(str(c) for c in action.choices)}）"
    dflt = ""
    if getattr(action, "default", None) is not None and action.default not in (None, "", False, argparse.SUPPRESS):
        dflt = f"（默认 `{action.default}`）"
    help_txt = (action.help or "").replace("\n", " ")
    return f"`{opts}` {req}{meta}{dflt} — {help_txt}"
