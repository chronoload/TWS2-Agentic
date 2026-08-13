# 原子：_extract_defuse_one（原 interface_chain_extractor.py 第 1136 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _extract_defuse_one(file: Path, reads: list, writes: list) -> None:
    """扫描单个 Python 文件：收集 getattr/hasattr/setattr 调用与 obj.attr 赋值"""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except Exception:
        return
    for node in ast.walk(tree):
        # getattr / hasattr / setattr(obj, 'attr', [default])
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("getattr", "hasattr", "setattr")
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            name, attr, obj = node.func.id, node.args[1].value, _obj_root(node.args[0])
            line = node.lineno
            if name == "getattr":
                default = ast.unparse(node.args[2]) if len(node.args) >= 3 else "—"
                reads.append(DefUseRead(file=file.name, line=line, obj=obj, attr=attr, default=default))
            elif name == "hasattr":
                # 存在性前置检查：作为"属性确实存在"的弱证据记录，不参与恒值报告
                reads.append(DefUseRead(file=file.name, line=line, obj=obj, attr=attr, default="hasattr"))
            else:  # setattr
                expr = ast.unparse(node.args[2])[:40] if len(node.args) >= 3 else "?"
                writes.append(DefUseWrite(file=file.name, line=line, obj=obj, attr=attr, expr=expr))
        # obj.attr = value（Assign / AnnAssign 目标为 Attribute）
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = getattr(node, "value", None)
            for t in targets:
                if isinstance(t, ast.Attribute):
                    writes.append(DefUseWrite(
                        file=file.name, line=node.lineno,
                        obj=_obj_root(t.value), attr=t.attr,
                        expr=ast.unparse(value)[:40] if value else "?"))
        # 类属性定义（ClassDef body 顶层的 Name 赋值，如 `_chat_active = threading.Event()`）
        # 以及类方法名（property/getter/普通方法都是实例属性，消除 `getattr(mw,'instance_id')` 误报）
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                    value = getattr(stmt, "value", None)
                    for t in targets:
                        if isinstance(t, ast.Name):
                            writes.append(DefUseWrite(
                                file=file.name, line=stmt.lineno,
                                obj=node.name, attr=t.id,
                                expr=ast.unparse(value)[:40] if value else "?"))
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    writes.append(DefUseWrite(
                        file=file.name, line=stmt.lineno,
                        obj=node.name, attr=stmt.name, expr="<method/property>"))
