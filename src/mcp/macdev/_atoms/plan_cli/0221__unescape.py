# 原子：_unescape（原 plan_cli.py 第 221 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _unescape(s: str) -> str:
    """把 shell 传入的字面 \\n / \\t 转成真实换行/制表，方便 Agent 填多行代码。"""
    if not s:
        return s
    return s.replace("\\n", "\n").replace("\\t", "\t")
