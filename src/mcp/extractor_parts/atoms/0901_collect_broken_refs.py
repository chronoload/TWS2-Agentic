# 原子：collect_broken_refs（原 interface_chain_extractor.py 第 901 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def collect_broken_refs(node: ChainNode, out: list) -> list:
    """递归收集链路中的断裂引用（broken 节点），返回 [(目标, 调用行)]"""
    if node.kind == "broken":
        out.append((node.name, node.line, node.detail))
    for c in node.children:
        collect_broken_refs(c, out)
    return out
