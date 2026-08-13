import json
from pathlib import Path
from macdev.core.registry import Registry
from macdev.core.bus import EventBus

def test_registry_factory():
    reg = Registry()
    reg.register("audit.strategy", "base", dict)
    assert reg.create("audit.strategy", "base", a=1) == {"a": 1}
    assert "audit.strategy" in reg.namespaces()

def test_registry_unknown():
    reg = Registry()
    try:
        reg.create("nope", "x")
        assert False
    except KeyError:
        pass

def test_bus_emit_subscribe_and_file(tmp_path):
    bus = EventBus()
    got = []
    bus.subscribe("audit.phase.done", lambda e: got.append(e["data"]["phase"]))
    bus.emit("audit.phase.done", {"phase": "chain"})
    assert got == ["chain"]

    sink = tmp_path / "events.ndjson"
    bus.set_sink(sink)
    bus.emit("plan.state.changed", {"state": "done"})
    line = json.loads(sink.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert line["event"] == "plan.state.changed"
    assert line["data"]["state"] == "done"
