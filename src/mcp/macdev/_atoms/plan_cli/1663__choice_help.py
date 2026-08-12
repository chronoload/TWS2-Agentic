# 原子：_choice_help（原 plan_cli.py 第 1663 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _choice_help(sa: argparse._SubParsersAction, name: str) -> str:
    """从 _SubParsersAction._choices_actions 读取 add_parser(help=...) 的说明。"""
    for ca in getattr(sa, "_choices_actions", []) or []:
        if getattr(ca, "dest", None) == name:
            return getattr(ca, "help", "") or ""
    return ""
