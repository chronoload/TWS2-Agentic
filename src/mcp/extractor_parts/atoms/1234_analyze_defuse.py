# 原子：analyze_defuse（原 interface_chain_extractor.py 第 1234 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_defuse(files: list) -> tuple:
    """跨文件 def-use 一致性分析。

    返回 (reads, writes, issues)：
      reads  — 所有 getattr 读取点（含 hasattr 存在性确认）
      writes — 所有属性赋值点
      issues — 恒值风险：
        no_assignment: 全库无任何 obj.attr 赋值 → 读取值恒为默认
        loose_match  : 全局有同名属性赋值但对象名不匹配（跨对象，低置信度）
    """
    reads: list[DefUseRead] = []
    writes: list[DefUseWrite] = []
    for f in files:
        _extract_defuse_one(f, reads, writes)

    writes_by_attr: dict = {}
    writes_by_obj_attr: dict = {}
    for w in writes:
        writes_by_attr.setdefault(w.attr, []).append(w)
        # self 是类内部名字，与外部调用处的变量名（agent/mw/...）指向同一实例 → 归一为通配符
        key = "*" if w.obj == "self" else w.obj
        writes_by_obj_attr.setdefault((key, w.attr), []).append(w)

    issues: list[DefUseIssue] = []
    for r in reads:
        if r.default == "hasattr":
            continue
        if not _falsy_literal_text(r.default):
            continue  # 非假值默认（如 getattr(x, 'k', 30) 配置读取）不报警
        obj_writes = (writes_by_obj_attr.get((r.obj, r.attr))
                      or writes_by_obj_attr.get(("*", r.attr)))
        any_writes = writes_by_attr.get(r.attr, [])
        if not any_writes:
            if _is_external_obj(r.obj):
                # 库 / 动态对象：属性无法在项目内验证 —— 用运行时反射尽力核查，仍作为风险暴露
                issues.append(DefUseIssue(
                    kind="external_contract", attr=r.attr, file=r.file, line=r.line,
                    obj=r.obj, default=r.default, writes=[],
                    detail=f"项目内无赋值点。{_verify_module_attr(r.obj, r.attr)}"))
            else:
                issues.append(DefUseIssue(
                    kind="no_assignment", attr=r.attr, file=r.file, line=r.line,
                    obj=r.obj, default=r.default, writes=[],
                    detail=f"getattr 默认值 {r.default} 恒为 {r.default}：全库无任何 `{r.attr}` 赋值点"))
        elif obj_writes is None:
            issues.append(DefUseIssue(
                kind="loose_match", attr=r.attr, file=r.file, line=r.line,
                obj=r.obj, default=r.default,
                writes=[(w.file, w.line, w.obj, w.expr) for w in any_writes],
                detail=f"对象名 `{r.obj}` 下无 `{r.attr}` 赋值，仅在其他对象/类上找到同名属性"))

    # 已闭合读取（供文档展示赋值链）
    closed = []
    for r in reads:
        if r.default == "hasattr":
            continue
        src = (writes_by_obj_attr.get((r.obj, r.attr))
               or writes_by_obj_attr.get(("*", r.attr))
               or writes_by_attr.get(r.attr, []))
        if src:
            closed.append((r, [(w.file, w.line, w.obj, w.expr) for w in src[:5]]))
    return reads, writes, issues, closed
