# 原子：_reflect_dataclass_schemas（原 interface_chain_extractor.py 第 4012 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_dataclass_schemas() -> list:
    """反射提取 4 个 dataclass 的字段定义（用于文档）。"""
    return [
        ("HardcodedItem", HardcodedItem, "硬编码常量条目"),
        ("EnvVarItem", EnvVarItem, "环境变量读取条目"),
        ("DataPoolItem", DataPoolItem, "数据池/状态条目"),
        ("StaticResourceItem", StaticResourceItem, "静态资源路径条目"),
    ]
