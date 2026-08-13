# 原子：analyze_chain_break（原 interface_chain_extractor.py 第 1341 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_chain_break(files: list, rules: dict) -> list:
    """链路断裂检查（规范 F 补集）：兜底源调用是否被活跃性守卫保护。

    规则：入口函数 → { fallback_sources, guard_terms, detail }
    - 在入口函数体（含嵌套闭包）内找兜底源调用（如 _build_messages_from_checkpoints）。
    - 兜底调用必须位于任一祖先 if 条件含 guard_term（agent_present / was_in_pool …）。
    - 若兜底调用存在但其所有祖先 if 条件都不含任何 guard_term → 链路断裂（🔴）。
    - 入口未找到 → 规则失效告警（🟠，与行为契约同口径）。
    """
    issues: list[ChainBreakIssue] = []
    for f in files:
        path = Path(f)
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        # 入口定位：递归收集（含 create_app 内嵌套路由方法）
        entry_funcs: dict[str, ast.FunctionDef] = {}

        def _collect_funcs(node, out):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.setdefault(child.name, child)
                _collect_funcs(child, out)

        _collect_funcs(tree, entry_funcs)

        for entry, rule in rules.items():
            func = entry_funcs.get(entry)
            if func is None:
                issues.append(ChainBreakIssue(
                    entry=entry, fallback="?", file=str(f), line=0,
                    detail="入口函数未找到（规则过期或函数已改名）"))
                continue
            fallbacks = rule.get("fallback_sources", [])
            guards = rule.get("guard_terms", [])
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                r = _call_repr(node)
                if not r:
                    continue
                # 命中兜底源调用
                if not any(fb in r or r in fb for fb in fallbacks):
                    continue
                conds = _iter_ancestor_ifs(node, func)
                if any(any(g in c for g in guards) for c in conds):
                    continue  # 已被活跃性守卫保护，正常
                issues.append(ChainBreakIssue(
                    entry=entry, fallback=r, file=str(f), line=node.lineno,
                    detail=rule.get("detail", "兜底源调用无活跃性守卫，活跃会话可能读到旧快照")))
    return issues
