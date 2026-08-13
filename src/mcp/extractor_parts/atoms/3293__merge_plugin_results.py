# 原子：_merge_plugin_results（原 interface_chain_extractor.py 第 3293 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _merge_plugin_results(report: dict, results: list[dict], md_text: str) -> str:
    """插件结果并入 project_map.json（plugins 键）与 PROJECT_CHAIN.md（插件章节）。"""
    if results:
        report["plugins"] = [{
            "name": r.get("name"), "lang": r.get("lang"),
            "stats": r.get("stats") or {}, "sections": r.get("sections") or {},
        } for r in results]
    plugin_mds = [r.get("report_md", "") for r in results if r.get("report_md")]
    if plugin_mds:
        md_text = (md_text.rstrip("\n") + "\n\n---\n\n## 插件扫描报告\n\n"
                   + "\n\n".join(plugin_mds) + "\n")
    return md_text
