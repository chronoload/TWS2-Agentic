import json
import threading
import time

from mcp.team import TEAM_TOOL_NAMES, AgentTeam, AgentTeamsRuntime, get_team_tools
from mcp.team.types import TeamMemberConfig

CLINE_TEAM_TOOL_NAMES = [
    "team_spawn_teammate",
    "team_shutdown_teammate",
    "team_status",
    "team_task",
    "team_run_task",
    "team_cancel_run",
    "team_list_runs",
    "team_await_runs",
    "team_send_message",
    "team_broadcast",
    "team_read_mailbox",
    "team_mission_log",
    "team_cleanup",
    "team_create_outcome",
    "team_attach_outcome_fragment",
    "team_review_outcome_fragment",
    "team_finalize_outcome",
    "team_list_outcomes",
]


def _find_tool(tools, name):
    for tool in tools:
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not found")


def test_all_18_team_tools_registered():
    assert len(TEAM_TOOL_NAMES) == 18
    assert TEAM_TOOL_NAMES == CLINE_TEAM_TOOL_NAMES
    tools = get_team_tools(AgentTeamsRuntime())
    assert len(tools) == 18
    assert [t.name for t in tools] == CLINE_TEAM_TOOL_NAMES


def test_team_tools_registered_in_get_tools():
    from mcp.tools import get_tools

    tools = get_tools()
    names = {t.name for t in tools}
    for name in TEAM_TOOL_NAMES:
        assert name in names


def test_team_run_task_submits_and_executes():
    calls = []
    runtime = AgentTeamsRuntime(executor=lambda m, c=None: f"done-{m}")
    runtime.add_member("worker", role="teammate")
    tools = get_team_tools(runtime)
    run_tool = _find_tool(tools, "team_run_task")

    result = json.loads(run_tool.execute(agent_id="worker", message="do X"))
    assert result["status"] == "queued"
    run_id = result["run_id"]

    run = runtime.await_run(run_id, timeout=5)
    assert run.status == "completed"
    assert run.result == "done-do X"

    runs = json.loads(_find_tool(tools, "team_list_runs").execute())
    assert len(runs["runs"]) == 1
    assert runs["runs"][0]["run_id"] == run_id
    assert runs["runs"][0]["status"] == "completed"


def test_run_queue_dependency_resolution():
    a_started = threading.Event()

    def stub_a(message, context=None):
        a_started.set()
        time.sleep(0.3)
        return "A-output"

    def stub_b(message, context=None):
        return "B-output"

    runtime = AgentTeamsRuntime(max_concurrent_runs=3)
    runtime.add_member("a", executor=stub_a)
    runtime.add_member("b", executor=stub_b)

    run_a = runtime.submit_task("a", "do A")
    run_b = runtime.submit_task("b", "do B", depends_on=[run_a])

    assert a_started.wait(timeout=5)
    time.sleep(0.05)
    assert runtime.get_run(run_b).status == "pending"

    runtime.await_run(run_a, timeout=5)
    runtime.await_run(run_b, timeout=5)
    assert runtime.get_run(run_a).status == "completed"
    assert runtime.get_run(run_b).status == "completed"


def test_max_concurrent_runs_limit():
    gate = threading.Event()
    started = []
    lock = threading.Lock()

    def stub(message, context=None):
        with lock:
            started.append(message)
        gate.wait(timeout=5)
        return "out"

    runtime = AgentTeamsRuntime(executor=stub, max_concurrent_runs=2)
    for i in range(4):
        runtime.add_member(f"m{i}", executor=stub)
    run_ids = [runtime.submit_task(f"m{i}", f"task-{i}") for i in range(4)]

    deadline = time.time() + 5
    while time.time() < deadline:
        with lock:
            count = len(started)
        if count == 2:
            break
        time.sleep(0.02)
    assert len(started) == 2

    gate.set()
    runtime.await_all_runs(timeout=5)
    assert all(runtime.get_run(rid).status == "completed" for rid in run_ids)


def test_mailbox_send_broadcast_read():
    runtime = AgentTeamsRuntime()
    runtime.add_member("lead", role="lead", kind="subagent")
    runtime.add_member("alice")
    runtime.add_member("bob")
    tools = get_team_tools(runtime)

    send_tool = _find_tool(tools, "team_send_message")
    send_tool.execute(to="alice", content="hello alice", **{"from": "lead"})

    broadcast_tool = _find_tool(tools, "team_broadcast")
    result = json.loads(broadcast_tool.execute(content="hello all", **{"from": "lead"}))
    assert result["delivered"] == 2

    mailbox_tool = _find_tool(tools, "team_read_mailbox")
    messages = json.loads(mailbox_tool.execute(agent_id="alice"))["messages"]
    contents = [m["content"] for m in messages]
    assert "hello alice" in contents
    assert "hello all" in contents

    second = json.loads(mailbox_tool.execute(agent_id="alice"))["messages"]
    assert all(m["read"] is True for m in second)

    bob_mail = runtime.read_mailbox("bob")
    assert [m.content for m in bob_mail] == ["hello all"]


def test_outcome_lifecycle():
    runtime = AgentTeamsRuntime()
    runtime.add_member("researcher")
    tools = get_team_tools(runtime)

    create_tool = _find_tool(tools, "team_create_outcome")
    created = json.loads(create_tool.execute(title="v2 plan", owner_agent_id="researcher"))
    outcome_id = created["outcome_id"]
    assert created["status"] == "draft"

    attach_tool = _find_tool(tools, "team_attach_outcome_fragment")
    attached = json.loads(attach_tool.execute(outcome_id=outcome_id, content="frag one", author_agent_id="researcher"))
    fragment_id = attached["fragment_id"]

    review_tool = _find_tool(tools, "team_review_outcome_fragment")
    reviewed = json.loads(
        review_tool.execute(outcome_id=outcome_id, fragment_id=fragment_id, status="approve", comment="ok")
    )
    assert reviewed["status"] == "approved"

    finalize_tool = _find_tool(tools, "team_finalize_outcome")
    finalized = json.loads(finalize_tool.execute(outcome_id=outcome_id))
    assert finalized["status"] == "finalized"

    list_tool = _find_tool(tools, "team_list_outcomes")
    outcomes = json.loads(list_tool.execute(status="finalized"))["outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["outcome_id"] == outcome_id
    assert outcomes[0]["status"] == "finalized"
    assert len(outcomes[0]["fragments"]) == 1
    assert outcomes[0]["fragments"][0]["review_status"] == "approved"


def test_team_status_snapshot():
    runtime = AgentTeamsRuntime(executor=lambda m, c=None: "ok")
    runtime.add_member("lead", role="lead")
    runtime.add_member("mate")
    run_id = runtime.submit_task("mate", "work")
    runtime.await_run(run_id, timeout=5)
    tools = get_team_tools(runtime)

    status_tool = _find_tool(tools, "team_status")
    snapshot = json.loads(status_tool.execute())
    assert {m["agent_id"] for m in snapshot["members"]} == {"lead", "mate"}
    assert snapshot["mailbox_unread"] == 0
    assert snapshot["outcomes"] == {"draft": 0, "in_review": 0, "finalized": 0}


def test_mission_log_append_and_read():
    runtime = AgentTeamsRuntime()
    runtime.add_member("lead", role="lead")
    tools = get_team_tools(runtime)

    log_tool = _find_tool(tools, "team_mission_log")
    log_tool.execute(action="append", content="milestone one", agent_id="lead")
    entries = json.loads(log_tool.execute(action="read"))["entries"]
    assert len(entries) == 1
    assert entries[0]["content"] == "milestone one"
    assert entries[0]["agent_id"] == "lead"


def test_agent_team_route_to_and_run_parallel():
    events = []
    team = AgentTeam(on_event=lambda e: events.append(e))
    team.add_agent(
        "coder",
        TeamMemberConfig(agent_id="coder", role="coder", kind="subagent"),
        executor=lambda m, c=None: f"code-{m}",
    )
    team.add_agent(
        "reviewer",
        TeamMemberConfig(agent_id="reviewer", role="review", kind="teammate"),
        executor=lambda m, c=None: f"review-{m}",
    )

    result = team.route_to("coder", "write")
    assert result.content == "code-write"
    assert [e.type for e in events] == ["TaskStart", "TaskEnd"]
    assert events[0].agent_id == "coder"
    assert events[1].payload["result"]["status"] == "completed"

    results = team.run_parallel(
        [
            {"agent_id": "coder", "message": "a"},
            {"agent_id": "reviewer", "message": "b", "metadata": {"k": 1}},
        ]
    )
    assert [r.agent_name for r in results] == ["coder", "reviewer"]
    assert [r.content for r in results] == ["code-a", "review-b"]
    assert results[1].metadata == {"k": 1}


def test_agent_team_run_pipeline_prefixes_previous_result():
    recorder = []

    def recording(name):
        def executor(message, context=None):
            recorder.append((name, message))
            return f"OUT-{name}"
        return executor

    team = AgentTeam()
    team.add_agent("a", TeamMemberConfig(agent_id="a"), executor=recording("a"))
    team.add_agent("b", TeamMemberConfig(agent_id="b"), executor=recording("b"))

    results = team.run_pipeline(
        [
            {"agent_id": "a", "message": "first"},
            {"agent_id": "b", "message": "second"},
        ]
    )
    assert [r.content for r in results] == ["OUT-a", "OUT-b"]
    assert recorder[0] == ("a", "first")
    assert recorder[1][0] == "b"
    assert "OUT-a" in recorder[1][1]
    assert "second" in recorder[1][1]


def test_agent_team_continue_to_falls_back_to_route_to():
    team = AgentTeam()
    team.add_agent("a", TeamMemberConfig(agent_id="a"), executor=lambda m, c=None: "done")
    result = team.continue_to("a", "more")
    assert result.content == "done"
