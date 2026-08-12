# 原子：chain_mermaid（原 interface_chain_extractor.py 第 881 行）
# 逻辑组：chain · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def chain_mermaid(node: ChainNode, parent_id: str = "") -> list:
    """调用链 → mermaid graph 语句（broken 节点标红，cross_file 显示定义位置）"""
    lines = []
    mid = node.name.replace("/", "_").replace("-", "_").replace("{", "").replace("}", "")
    mid = f"n_{mid}_{abs(hash(mid)) % 100000}"
    label = node.name
    if node.kind == "broken":
        label += " 🔴"
    if node.file:
        label += f"<br/><small>{node.file}:{node.line}</small>"
    lines.append(f'    {mid}["{label}"]')
    if node.kind == "broken":
        lines.append(f"    class {mid} broken;")
    if parent_id:
        lines.append(f"    {parent_id} --> {mid}")
    for c in node.children:
        lines.extend(chain_mermaid(c, mid))
    return lines
