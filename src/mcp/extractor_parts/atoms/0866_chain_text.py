# 原子：chain_text（原 interface_chain_extractor.py 第 866 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def chain_text(node: ChainNode, indent: int = 0) -> list:
    """调用链 → 文本树（broken 断裂节点标红 🔴，cross_file 显示定义位置）"""
    pad = "  " * indent
    loc = f" [{node.file}:{node.line}]" if node.file and node.line else ""
    kind = f" ({node.kind})" if node.kind not in ("helper",) else ""
    if node.kind == "broken":
        kind = " (🔴 broken)"
    elif node.kind == "cross_file":
        kind = " (↦ 亲属)" if not node.detail else f" (↦ {node.detail})"
    lines = [f"{pad}└ {node.name}{kind}{loc}"]
    for c in node.children:
        lines.extend(chain_text(c, indent + 1))
    return lines
