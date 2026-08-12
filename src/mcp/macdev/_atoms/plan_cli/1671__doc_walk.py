# 原子：_doc_walk（原 plan_cli.py 第 1671 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _doc_walk(parser: argparse.ArgumentParser, level: int, lines: list) -> None:
    """递归遍历 argparse 子命令树，生成 markdown 文档。"""
    indent = "  " * level
    sub_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not sub_actions:
        return
    for sa in sub_actions:
        for name, subp in sa.choices.items():
            lines.append(f"\n{indent}### {name}")
            desc = subp.description or _choice_help(sa, name) or ""
            if desc:
                lines.append(f"\n{indent}{desc}")
            for a in subp._actions:
                if isinstance(a, argparse._SubParsersAction):
                    continue
                if a.dest == "help":  # -h/--help 自动添加，不列出
                    continue
                if a.help == argparse.SUPPRESS:
                    continue
                lines.append(f"{indent}- {_arg_help(a)}")
            _doc_walk(subp, level + 1, lines)
