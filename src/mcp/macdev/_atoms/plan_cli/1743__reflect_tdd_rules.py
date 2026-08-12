# 原子：_reflect_tdd_rules（原 plan_cli.py 第 1743 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _reflect_tdd_rules() -> list:
    """反射提取 TDD 检查规则（从 cmd_tdd_check 函数体解析）。"""
    import inspect as _inspect
    rules = []
    try:
        src = _inspect.getsource(cmd_tdd_check)
        for m in re.finditer(r'"(\w+)":\s*\{[^}]*"label":\s*"([^"]*)"[^}]*"severity":\s*"(\w+)"', src):
            rules.append((m.group(1), m.group(2), m.group(3)))
    except Exception:
        pass
    return rules
