# 原子：Endpoint（原 interface_chain_extractor.py 第 120 行）
# 逻辑组：core · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

class Endpoint:
    method: str
    path: str
    func: str
    file: str
    line: int
    doc: str
    params: list[str] = field(default_factory=list)   # 函数参数
    request_model: str = ""                            # 使用的 Pydantic 模型名
    response_keys: list[str] = field(default_factory=list)  # ok(data={...}) 顶层键
    note: str = ""
