# 原子：_write_csv（原 interface_chain_extractor.py 第 3775 行）
# 逻辑组：output · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _write_csv(path: Path, headers: list, rows: list) -> None:
    """写 CSV（utf-8-sig 便于 Excel 直接打开）"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(["" if v is None else str(v) for v in r])
