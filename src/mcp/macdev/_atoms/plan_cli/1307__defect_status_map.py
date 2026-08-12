# 原子：_defect_status_map（原 plan_cli.py 第 1307 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _defect_status_map() -> dict:
    """构建 {defect_id: detail} 映射（来自 extractor 的 index.json，用于 export 显示缺陷是否已修复）"""
    defects = _load_defects()
    return {d["id"]: d for d in defects}
