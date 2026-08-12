# 原子：analyze_behavior（原 interface_chain_extractor.py 第 1397 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_behavior(files: list, rules: dict) -> list:
    """行为契约检查：入口函数正常完成路径必须触发的副作用调用是否存在。

    入口规则是全局的（不绑定单个文件）：先在整个文件集合中定位入口所在文件，
    只在该文件上做 must-call 路径覆盖；所有文件都找不到入口才报「规则失效」。

    返回 BehaviorIssue 列表：
      - 入口在所有源码中不存在 → detail 注明「入口未找到」（规则可能已过期）
      - 入口存在但未触发任何 must-call → 该规则目标的 missing 全量列出
    """
    issues: list[BehaviorIssue] = []
    # 一遍解析所有文件 → {entry: [(file, func), ...]}；同名入口多文件全收集，
    # 每个文件上的该入口都独立做 must-call 检查（同名字符串匹配，不做限定名区分）。
    parsed: dict[str, list[tuple[Path, ast.AST]]] = {}

    def _collect_funcs(node, out):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # setdefault：外层/先出现的函数优先，不被内层同名覆盖
                out.setdefault(child.name, child)
            _collect_funcs(child, out)

    for f in files:
        path = Path(f)
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        module_funcs = {}
        _collect_funcs(tree, module_funcs)
        for name, func in module_funcs.items():
            parsed.setdefault(name, []).append((path, func))

    for entry, must_calls in rules.items():
        hits = parsed.get(entry)
        if not hits:
            issues.append(BehaviorIssue(
                entry=entry, missing=list(must_calls),
                file="", detail="入口函数未找到（规则过期或函数已改名）"))
            continue
        for file, func in hits:
            call_reprs = _collect_entry_call_reprs(func)
            missing = [m for m in must_calls
                       if not any(m in r or r in m for r in call_reprs)]
            # OR 语义：must-call 是同一副作用契约的等价途径（store.update /
            # _sync_agent_from_store / _persist_snapshot 都是"写回会话记录"），
            # 任一命中即满足；全部缺失才算缺陷，避免封装函数被误报。
            if missing and len(missing) == len(must_calls):
                issues.append(BehaviorIssue(
                    entry=entry, missing=missing, file=str(file),
                    detail="正常完成路径缺少必须的副作用调用（如写回会话记录），"
                           "依赖链无法发现——需补齐或在入口断言"))
    return issues
