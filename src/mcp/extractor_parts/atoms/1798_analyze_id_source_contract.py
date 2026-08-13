# 原子：analyze_id_source_contract（原 interface_chain_extractor.py 第 1798 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_id_source_contract(files: list) -> list:
    """标识符命名空间来源契约检查（规范 J）"""
    issues: list[IdSourceIssue] = []
    # 文件 → 函数定义索引（guard 检查需要函数体）
    defs_by_file: dict[str, dict[str, ast.FunctionDef]] = {}

    for f in files:
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        fndefs: dict[str, ast.FunctionDef] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fndefs.setdefault(node.name, node)
        defs_by_file[str(f)] = fndefs

        # (a) 调用点：cross_namespace_key
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = _call_fn_name(node)
            for rule in ID_SOURCE_RULES:
                if fname not in rule["consumers"]:
                    continue
                arg = _key_arg_expr(node)
                if arg is None:
                    continue
                sig = _expr_sig(arg)
                if not sig:
                    continue
                if sig.startswith("str:"):
                    val = sig[4:]
                    # 字符串字面量：命中「另一命名空间」前缀 → 违约；自身前缀合法
                    for r2 in ID_SOURCE_RULES:
                        if r2 is rule or not r2["prefix"]:
                            continue
                        if val.startswith(r2["prefix"]):
                            issues.append(IdSourceIssue(
                                kind="cross_namespace_key", consumer=fname,
                                key_arg=val, file=str(f), line=node.lineno,
                                detail=(f"把字面量 '{val}'（{r2['ns']} 前缀）传给 {fname}()——"
                                        f"该消费者属于 {rule['ns']}，查询必然 miss 或误删。")))
                            break
                elif sig in rule["conflict_hints"]:
                    issues.append(IdSourceIssue(
                        kind="cross_namespace_key", consumer=fname,
                        key_arg=sig, file=str(f), line=node.lineno,
                        detail=(f"把「{sig}」传给 {fname}()——{rule['ns']} 的 key 参数。"
                                f"该变量/属性名命中另一命名空间的提示词，key 来源必须回溯到"
                                f"本命名空间的创建点（如 cp = reloader.create_checkpoint(...)），"
                                f"否则查询必 miss 或误删。")))

    # (b) 定义点：unguarded_key_consumer（仅对声明 guard 的命名空间）
    for f, fndefs in defs_by_file.items():
        for rule in ID_SOURCE_RULES:
            if not rule.get("guard"):
                continue
            prefix = rule["prefix"]
            for fn_name, fn in fndefs.items():
                if fn_name not in rule["consumers"]:
                    continue
                key_params = [a.arg for a in fn.args.args
                              if a.arg in ("key", "id", "checkpoint_id", "checkpoint", "session_id")]
                if not key_params:
                    continue
                kp = key_params[0]
                used_as_key = False
                has_guard = False
                for sub in ast.walk(fn):
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr in ("get", "find", "query", "pop", "delete")):
                        if any(getattr(a, "id", None) == kp for a in sub.args):
                            used_as_key = True
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "startswith"):
                        # 守卫可能是 key.startswith('cp-') 或 str(key).startswith('cp-')
                        target = sub.func.value
                        if (isinstance(target, ast.Call) and isinstance(target.func, ast.Name)
                                and target.func.id == "str" and target.args):
                            target = target.args[0]
                        if getattr(target, "id", None) == kp:
                            has_guard = True
                if used_as_key and not has_guard:
                    issues.append(IdSourceIssue(
                        kind="unguarded_key_consumer", consumer=fn_name,
                        key_arg=kp, file=f, line=fn.lineno,
                        detail=(f"{fn_name}({kp}) 直接把 key 用于存储查找（dict.get/store.get），"
                                f"但函数内无 '{prefix}' 前缀守卫；任何命名空间的标识符都会被"
                                f"当作本系统 key 查询——跨命名空间误用的传播土壤。"
                                f"建议入口处校验 key.startswith('{prefix}') 并给出明确错误。")))

    return issues
