from pathlib import Path
from macdev.plan.db import PlanStore
from macdev.plan import commands
from macdev.plan.workflow import cmd_verify, cmd_review, cmd_tdd_check, cmd_ledger
from macdev.plan.export import export_plan


def test_plan_full_loop(tmp_path):
    db = tmp_path / "plans.db"
    store = PlanStore(db=db)
    code, lines = commands.cmd_create(store, "闭环", "目标", "方案", "FastAPI", "约束")
    assert code == 0
    # id 机制：日期+计划名（缺省取 title 的 slug）
    pid = commands._plan_id("闭环")
    assert f"id={pid}" in lines[0]
    code, _ = commands.cmd_task_add(store, pid, "T1", files="Create: x.py")
    assert code == 0
    code, _ = commands.cmd_step_add(store, 1, "写失败测试", "test", run="pytest -q", expected="FAIL")
    assert code == 0
    code, _ = commands.cmd_step_add(store, 1, "实现", "implement")
    assert code == 0
    # TDD 合规
    code, lines = cmd_tdd_check(store)
    assert code == 0, lines
    # review 循环
    assert cmd_review(store, 1, "request")[0] == 0
    assert cmd_review(store, 1, "approve")[0] == 0
    # 全部完成
    commands.cmd_task_update(store, 1, status="done")
    commands.cmd_step_update(store, 1, status="done")
    commands.cmd_step_update(store, 2, status="done")
    # verify 门禁通过
    code, lines = cmd_verify(store, pid, project_root=tmp_path)
    assert code == 0, lines
    assert any("可宣告完成" in ln for ln in lines)
    # export
    code, lines, md_path, json_path = export_plan(store, pid, out=tmp_path / "PLAN_1.md")
    assert code == 0
    assert md_path.exists() and json_path.exists()
    assert "# 闭环 Implementation Plan" in md_path.read_text(encoding="utf-8")
    # ledger
    code, lines, _ = cmd_ledger(store, pid, out=tmp_path / "progress.md")
    assert code == 0
    assert (tmp_path / "progress.md").exists()
