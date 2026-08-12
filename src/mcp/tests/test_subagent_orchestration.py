from types import SimpleNamespace

from mcp.subagent.coordinator import Coordinator
from mcp.subagent.prompts import build_subagent_system_prompt, build_teammate_system_prompt
from mcp.subagent.types import AgentRole, AgentSpec, SubAgentResult


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return SimpleNamespace(content="llm-output", tool_calls=[], reasoning_content="")


def _make_stub_agent(recorder):
    class StubSessionAgent:
        def __init__(self, spec, llm=None, tools=None, tool_executor=None, cancel_event=None, on_event=None):
            self.spec = spec
            self.llm = llm

        def run(self, prompt, context=None):
            recorder["prompts"].append(prompt)
            recorder["contexts"].append(context)
            recorder["order"].append(self.spec.name)
            result = SubAgentResult(agent_name=self.spec.name, role=self.spec.role)
            result.mark_completed(content=f"output-from-{self.spec.name}")
            return result

    return StubSessionAgent


def _make_coordinator(monkeypatch):
    recorder = {"prompts": [], "contexts": [], "order": []}
    monkeypatch.setattr("mcp.subagent.coordinator.SessionAgent", _make_stub_agent(recorder))
    coordinator = Coordinator(llm=FakeLLM())
    return coordinator, recorder


def test_run_sequential_executes_in_order_with_previous_results(monkeypatch):
    coordinator, rec = _make_coordinator(monkeypatch)
    coordinator.register_agent(AgentSpec(role=AgentRole.CODER, name="a"))
    coordinator.register_agent(AgentSpec(role=AgentRole.TASK, name="b"))
    coordinator.register_agent(AgentSpec(role=AgentRole.REVIEW, name="c"))

    tasks = [
        {"agent": "a", "prompt": "write code"},
        {"agent": "b", "prompt": "refactor code"},
        {"agent": "c", "prompt": "review code"},
    ]
    results = coordinator.run_sequential(tasks)

    assert [r.agent_name for r in results] == ["a", "b", "c"]
    assert rec["order"] == ["a", "b", "c"]
    assert rec["prompts"][0] == "write code"
    assert rec["contexts"][0] is None
    assert "前置 Agent 结果" in rec["prompts"][1]
    assert "output-from-a" in rec["prompts"][1]
    assert "refactor code" in rec["prompts"][1]
    prev1 = rec["contexts"][1]["previous_results"]
    assert len(prev1) == 1
    assert prev1[0]["agent"] == "a"
    assert prev1[0]["content"] == "output-from-a"
    assert prev1[0]["status"] == "completed"
    prev2 = rec["contexts"][2]["previous_results"]
    assert len(prev2) == 2
    assert prev2[0]["agent"] == "a"
    assert prev2[1]["agent"] == "b"
    assert prev2[1]["status"] == "completed"
    assert "output-from-a" in rec["prompts"][2]
    assert "output-from-b" in rec["prompts"][2]
    assert "review code" in rec["prompts"][2]


def test_run_pipeline_with_transformer(monkeypatch):
    coordinator, rec = _make_coordinator(monkeypatch)
    coordinator.register_agent(AgentSpec(role=AgentRole.CODER, name="a"))
    coordinator.register_agent(AgentSpec(role=AgentRole.REVIEW, name="b"))

    stages = [
        {"agent": "a", "prompt": "write code"},
        {"agent": "b", "prompt": "review code"},
    ]
    transformers = {0: lambda result: f"TRANSFORMED:{result.content}"}
    results = coordinator.run_pipeline(stages, transformers=transformers)

    assert [r.agent_name for r in results] == ["a", "b"]
    assert rec["prompts"][0] == "write code"
    assert rec["prompts"][1].startswith("TRANSFORMED:output-from-a")
    assert "review code" in rec["prompts"][1]


def test_run_pipeline_without_transformer_prefixes_stage_result(monkeypatch):
    coordinator, rec = _make_coordinator(monkeypatch)
    coordinator.register_agent(AgentSpec(role=AgentRole.CODER, name="a"))
    coordinator.register_agent(AgentSpec(role=AgentRole.TASK, name="b"))

    stages = [
        {"agent": "a", "prompt": "step one"},
        {"agent": "b", "prompt": "step two"},
    ]
    results = coordinator.run_pipeline(stages)

    assert len(results) == 2
    assert rec["prompts"][0] == "step one"
    assert "阶段结果" in rec["prompts"][1]
    assert "output-from-a" in rec["prompts"][1]
    assert "step two" in rec["prompts"][1]


def test_run_pipeline_transformer_accepts_str(monkeypatch):
    coordinator, rec = _make_coordinator(monkeypatch)
    coordinator.register_agent(AgentSpec(role=AgentRole.CODER, name="a"))
    coordinator.register_agent(AgentSpec(role=AgentRole.TASK, name="b"))

    stages = [
        {"agent": "a", "prompt": "produce"},
        {"agent": "b", "prompt": "consume"},
    ]
    transformers = {0: lambda s: "STR:" + s}
    results = coordinator.run_pipeline(stages, transformers=transformers)

    assert len(results) == 2
    assert rec["prompts"][1].startswith("STR:output-from-a")
    assert "consume" in rec["prompts"][1]


def test_agent_spec_default_kind_is_subagent():
    spec = AgentSpec(role=AgentRole.CODER, name="legacy", system_prompt="old prompt", max_turns=15)
    assert spec.kind == "subagent"
    assert spec.name == "legacy"
    assert spec.system_prompt == "old prompt"
    assert spec.max_turns == 15


def test_agent_spec_kind_teammate_compatible():
    spec = AgentSpec(role=AgentRole.TASK, name="mate", kind="teammate")
    assert spec.kind == "teammate"

    coordinator = Coordinator(llm=FakeLLM())
    coordinator.register_agent(spec)
    assert coordinator._specs["mate"].kind == "teammate"


def test_prompts_structure():
    sub = build_subagent_system_prompt("coder", cwd="/workspace", extra_instructions="extra1")
    assert "coder" in sub
    assert "/workspace" in sub
    assert "约束" in sub
    assert "extra1" in sub

    mate = build_teammate_system_prompt("task", team_goal="ship v2", cwd="/workspace", extra_instructions="extra2")
    assert "task" in mate
    assert "ship v2" in mate
    assert "/workspace" in mate
    assert "团队协作规则" in mate
    assert "extra2" in mate
