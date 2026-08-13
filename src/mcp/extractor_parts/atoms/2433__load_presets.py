# 原子：_load_presets（原 interface_chain_extractor.py 第 2433 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _load_presets(presets_file: str = "") -> dict:
    """内置预设 + 可选外部预设 JSON（{name: {root, out, exclude[]}}）合并"""
    presets = dict(PROJECT_PRESETS)
    if presets_file:
        try:
            ext = json.loads(Path(presets_file).read_text(encoding="utf-8"))
            presets.update(ext or {})
        except Exception as e:
            print(f"[project] 预设文件加载失败: {e}")
    return presets
