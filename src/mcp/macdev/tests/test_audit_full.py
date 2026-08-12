from pathlib import Path
from macdev import Engine, Registry, EventBus
from macdev import audit
from macdev.audit.task import AuditTask

def _mk(tmp_path):
    (tmp_path / "app.py").write_text(
        "import os, threading\nfrom fastapi import FastAPI\nfrom lib import util\n"
        "app = FastAPI()\nAPI_KEY = 'sk-demo'\nPORT = 8123\n"
        "class AgentSession:\n"
        "    def __init__(self):\n"
        "        self._chat_active = threading.Event()\n"
        "    def stop(self):\n"
        "        self._chat_active.clear()\n"
        "def _helper():\n    return util()\n"
        "@app.get('/api/a')\ndef a():\n    return _helper()\n"
        "@app.get('/api/b')\ndef b():\n    return a()\n",
        encoding="utf-8")
    (tmp_path / "lib.py").write_text("def util():\n    return 1\n", encoding="utf-8")
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "app.js").write_text(
        "class TS2Client {\n  async fetchA() { return this.api('/api/a'); }\n}\n",
        encoding="utf-8")

def test_audit_full_dimensions(tmp_path):
    _mk(tmp_path)
    task = AuditTask(root=tmp_path,
                     endpoints=[{"file": "app.py", "module": "app", "methods": ["get"]}],
                     files={"app": "app.py", "client": "client/app.js"},
                     chains={"max_depth": 2, "entries": [{"kind": "endpoint", "prefix": "/api/"}]},
                     strategy="base")
    reg = Registry()
    audit.register(reg)
    engine = Engine(reg, EventBus())
    r = engine.run_audit(task, out_dir=tmp_path / "out")
    assert r.ok
    assert r.data["endpoints"] == 2
    assert r.data["flag"] >= 1          # clear_without_set 命中
    assert r.data["hardcoded"] >= 1     # sk-demo / 8123 命中
    md = (tmp_path / "out" / "INTERFACE_CHAIN.md").read_text(encoding="utf-8")
    assert "## 8. 关键端点依赖链" in md
    assert "↦ 亲属" in md
    assert "## 11. 状态标志生命周期" in md
    # 双轨产物齐全
    for name in ("interface_chain.db", "endpoints.csv", "hardcoded.csv",
                 "flag_lifecycle.csv", "behavior_issues.csv", "data_pools.csv"):
        assert (tmp_path / "out" / name).exists(), name
