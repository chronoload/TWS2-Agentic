# 原子：_render_table（原 plan_cli.py 第 1313 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _render_table(plan, tasks, steps_by_task, req_map, defect_map) -> list:
    # plan 行: (id, title, goal, arch, stack, global_constraints, status, created_at)
    lines = [f"# Plan: {plan[1]}",
             "",
             f"> 状态: **{plan[6]}** · 创建: {plan[7]} · 任务: {len(tasks)}",
             "",
             "## 目标",
             "",
             plan[2] or "（未填写）",
             "",
             "## 任务",
             "",
             "| # | 状态 | 标题 | 说明 | 关联需求 | 关联缺陷 | Review |",
             "|----|------|------|------|----------|----------|--------|"]
    for t in tasks:
        # tasks 行: (id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status, review_findings)
        detail = t[2].replace("|", "\\|")[:100]
        defect_txt = _resolve_defect(t[5], defect_map)
        rev_txt = {"approved": "✅", "review_requested": "🔄",
                   "needs_fix": "❌", "pending": "⏳"}.get(t[8], t[8])
        lines.append(f"| {t[0]} | {t[7]} | `{t[1]}` | {detail} | {_resolve_req(t[4], req_map)} | {defect_txt} | {rev_txt} |")
    return lines
