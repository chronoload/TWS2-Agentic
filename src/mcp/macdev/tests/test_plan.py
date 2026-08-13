from macdev.plan.model import Plan, Task, Step
from macdev.plan.tdd import tdd_check
from macdev.plan.state import PlanState

def test_plan_create_and_tdd():
    p = Plan(id=1, title="t")
    p.tasks.append(Task(id=1, plan_id=1, title="impl",
                        steps=[Step(text="test", action="test", run="pytest", expected="pass"),
                               Step(text="impl", action="implement")]))
    assert PlanState.next(p) == "ready"
    issues = tdd_check(p)
    assert issues == []  # test 在 implement 前

def test_tdd_missing_test():
    p = Plan(id=1, title="t")
    p.tasks.append(Task(id=1, plan_id=1, title="impl",
                        steps=[Step(text="impl", action="implement")]))
    assert any(i["kind"] == "test_missing" for i in tdd_check(p))
