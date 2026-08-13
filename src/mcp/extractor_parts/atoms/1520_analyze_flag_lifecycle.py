# 原子：analyze_flag_lifecycle（原 interface_chain_extractor.py 第 1520 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_flag_lifecycle(files: list) -> list:
    """状态标志生命周期检查：
       (a) clear_without_set：Event 标志 clear() 后同方法内无 set() 恢复
           （若 clear 后有 wait 或跨调用恢复，由 finally 兜底；此处只报「同函数内完全无 set」）
       (b) stale_cache：函数内多处给 _instance_id 赋值，且未重置 _last_hash/_snapshot_seq
    """
    issues: list[FlagLifecycleIssue] = []
    stale_fields = ("_instance_id", "_last_hash", "_initialized", "_snapshot_seq")

    for f in files:
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        event_attrs = _event_flag_attrs(tree)
        if not event_attrs:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn = node

            # (a) clear/set 配对（只对 Event 标志）
            clears: dict[str, int] = {}
            sets: dict[str, int] = {}
            for sub in ast.walk(fn):
                if not isinstance(sub, ast.Call):
                    continue
                attr = _flag_attr_of(sub)
                if not attr or attr not in event_attrs:
                    continue
                if isinstance(sub.func, ast.Attribute) and sub.func.attr == "clear":
                    clears.setdefault(attr, sub.lineno)
                elif isinstance(sub.func, ast.Attribute) and sub.func.attr == "set":
                    sets.setdefault(attr, sub.lineno)
            for attr, cline in clears.items():
                if attr not in sets:
                    issues.append(FlagLifecycleIssue(
                        kind="clear_without_set", attr=attr, file=str(f), line=cline,
                        detail="方法内 clear() 该 Event 标志但无 set() 恢复；若该处后续有 wait() 或跨调用依赖，"
                               "可能永久阻塞或状态残留（需 finally 兜底）"))

            # (b) 跨会话缓存重置：多处赋值 _instance_id 但未见缓存字段重置
            assigns: dict[str, list[int]] = {}
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Attribute) and t.attr in stale_fields:
                            assigns.setdefault(t.attr, []).append(sub.lineno)
            if "_instance_id" in assigns and len(assigns["_instance_id"]) > 1:
                reset_fields = [k for k in ("_last_hash", "_snapshot_seq")
                                if assigns.get(k)]
                if not reset_fields:
                    issues.append(FlagLifecycleIssue(
                        kind="stale_cache", attr="_instance_id", file=str(f),
                        line=assigns["_instance_id"][0],
                        detail="多处赋值 _instance_id，但函数内未见 _last_hash/_snapshot_seq 重置，"
                               "session 切换可能残留旧检查点状态"))
    return issues
