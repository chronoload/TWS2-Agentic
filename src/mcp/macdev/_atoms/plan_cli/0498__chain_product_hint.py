# 原子：_chain_product_hint（原 plan_cli.py 第 498 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _chain_product_hint() -> None:
    """产物利用导向（宏观优先）：提醒先看整体链路，勿陷缺陷清单。"""
    print("\n[chain] 产物利用（宏观优先，勿陷于缺陷清单）:")
    print("  ① 先看整体：stats / endpoints --by-file → 模块规模与端点分布；")
    print("     PROJECT_CHAIN.md §关键端点依赖链（text 树 + mermaid）回答“系统长什么样、谁依赖谁、链路断没断”")
    print("  ② 再定向查：SQL 或 chain endpoints/issues/models 针对具体问题，替代 grep-read 逐文件拼链路")
    print("  ③ 主产品 = 链路数据库 + 可读文档；缺陷清单只是附加值，别用缺陷数量衡量价值")
