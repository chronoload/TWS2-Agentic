# 原子：_type_short（原 interface_chain_extractor.py 第 3470 行）
# 逻辑组：output · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _type_short(t: str) -> str:
    t = t.replace("typing.", "")
    # 逐层剥掉泛型包裹（Optional/List/Dict/Tuple）
    prev = None
    while prev != t:
        prev = t
        t = (t.replace("Optional[", "")
               .replace("List[", "list[")
               .replace("Dict[", "dict[")
               .replace("Tuple[", "tuple["))
    # 修复多余右括号：如 "list[str]]" → "list[str]"
    t = re.sub(r"\]+$", "]", t)
    return t
