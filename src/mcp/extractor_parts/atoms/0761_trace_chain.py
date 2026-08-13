# 原子：trace_chain（原 interface_chain_extractor.py 第 761 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def trace_chain(start_name: str, func_map: dict, import_map: dict, path: Path,
                depth: int = 0, seen=None, max_depth: int = 3,
                global_index: dict = None) -> ChainNode:
    """从函数名开始递归展开调用链（亲属追逐 → 亲属反射）
    规则：同文件 helper 递归展开；跨模块类方法仅标记为叶子（标注源文件）。
    亲属反射：name 目标在本文件未解析时，查全项目符号索引（global_index）——
      命中 → cross_file（亲属已定位，标注定义位置）；是内置/导入 → builtin；
      全项目无定义 → broken（🔴 链路断裂，一步定位 bug）。
    """
    seen = seen or set()
    node = ChainNode(name=start_name, kind="unknown", file=path.name)
    if start_name in seen:
        node.kind = "recursive"
        return node
    if depth > max_depth:
        node.kind = "depth_limit"
        return node
    seen.add(start_name)
    func = func_map.get(start_name)
    if func is None:
        return node
    node.kind = "helper"
    node.line = func.lineno
    binds = extract_var_bindings(func)
    # 形参类型提示：store/agent 等按语义绑定
    for pname, ptype in ACTIVE_STRATEGY.param_type_hints.get(start_name, {}).items():
        binds.setdefault(pname, ptype)
    for target, kind, lineno in collect_call_targets(func):
        if kind == "name":
            if target in func_map and target != start_name:
                child = trace_chain(target, func_map, import_map, path,
                                    depth + 1, seen, max_depth, global_index)
                child.line = lineno
                node.children.append(child)
            elif target in ACTIVE_STRATEGY.helper_return_types:
                node.children.append(ChainNode(name=target, kind="helper",
                                               file=path.name, line=lineno))
            elif target in ACTIVE_STRATEGY.known_type_files:
                # 类实例化（如 MultiProviderManager / SimulatorLLM / CourseSystem）
                node.children.append(ChainNode(name=target, kind="class",
                                               file=ACTIVE_STRATEGY.known_type_files[target], line=lineno))
            else:
                # 亲属反射核查：本文件无此函数 → 全项目索引 / 内置 / 导入 / 断裂
                locs = (global_index or {}).get(target)
                # 强命中：func/class/method（可定位）；弱命中：仅 var（存在性已知，降级为 builtin，不误报断裂）
                strong = [l for l in (locs or []) if l[2] in ("func", "class", "method")]
                if strong:
                    # 同文件优先，否则取首个强命中
                    cur = path.name
                    pick = next((l for l in strong if l[0].split("/")[-1] == cur), strong[0])
                    rel, ln, knd = pick
                    child = ChainNode(name=target, kind="cross_file",
                                      file=rel, line=ln)
                    child.detail = f"定义于 {rel}:{ln}（{knd}）"
                    node.children.append(child)
                elif locs or target in _BUILTIN_NAMES or target in import_map:
                    # var 弱命中 / 内置 / 导入：引用存在但非本文件函数，保持 builtin
                    node.children.append(ChainNode(name=target, kind="builtin",
                                                   line=lineno))
                else:
                    # 项目内无任何定义 → 链路断裂（可能是改名/漏实现/拼写错误）
                    child = ChainNode(name=target, kind="broken", line=lineno)
                    child.detail = "项目内未找到定义（疑似改名/漏实现/拼写错误）"
                    node.children.append(child)
        else:  # attr: obj.method
            obj, method = target.split(".", 1)
            type_name = ""
            if obj in binds:
                t = binds[obj]
                if t in ACTIVE_STRATEGY.known_type_files:
                    type_name = t
                elif t in ACTIVE_STRATEGY.helper_return_types:
                    type_name = ACTIVE_STRATEGY.helper_return_types[t]
            elif obj in ACTIVE_STRATEGY.type_aliases:
                type_name = ACTIVE_STRATEGY.type_aliases[obj]
            if type_name:
                f = ACTIVE_STRATEGY.resolve_type_file(type_name, import_map)
                child = ChainNode(name=f"{type_name}.{method}", kind="class_method",
                                  file=f or path.name, line=lineno)
                # 1 层跨文件展开：类方法内部的 self 调用
                if f:
                    fp = MCP_ROOT / f
                    for inner_target, inner_kind, inner_line in _method_calls_of(fp, type_name, method):
                        child.children.append(ChainNode(name=inner_target, kind="class_method",
                                                        file=f, line=inner_line))
                node.children.append(child)
            elif method in NOISE_ATTRS:
                continue  # 未知对象的序列方法（msg.get / body.get 等），无追踪价值
            else:
                # 对象类型未知：可能是库对象（conn.execute / loop.run_in_executor /
                # ws_mgr.broadcast），无法可靠判定断裂 → 保持 unknown。
                # 仅当方法名恰为项目内某类的同名方法时给出候选归属提示。
                method_hits = [(rel, ln) for rel, ln, knd in (global_index or {}).get(method, [])
                               if knd == "method"]
                if method_hits:
                    rel, ln = method_hits[0]
                    child = ChainNode(name=target, kind="unknown", line=lineno)
                    child.detail = f"对象类型未知，方法同名定义于 {rel}:{ln}"
                    node.children.append(child)
                else:
                    node.children.append(ChainNode(name=target, kind="unknown",
                                                   line=lineno))
    return node
