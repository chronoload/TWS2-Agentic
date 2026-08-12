from pathlib import Path
from macdev import Engine, Registry, EventBus
from macdev.audit.task import AuditTask
from macdev import audit

def _mk_sample(tmp_path):
    """构造一个含 2 端点 + 1 跨文件 helper 的小项目，验证亲属追逐可出图。"""
    (tmp_path / "app.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n"
        "def _helper():\n    return 1\n\n"
        "from lib import util\n"
        "@app.get('/api/a')\ndef a():\n    return _helper() + util()\n\n"
        "@app.get('/api/b')\ndef b():\n    return a()\n",
        encoding="utf-8")
    (tmp_path / "lib.py").write_text(
        "def util():\n    return 2\n",
        encoding="utf-8")

def test_engine_run_audit_chain(tmp_path):
    _mk_sample(tmp_path)
    task = AuditTask(root=tmp_path, endpoints=[{"file": "app.py", "module": "app",
                                                "methods": ["get"], "prefix": ""}],
                     chains={"max_depth": 2, "entries": [{"kind": "endpoint", "prefix": "/api/"}]},
                     strategy="base")
    reg = Registry()
    audit.register(reg)
    bus = EventBus()
    engine = Engine(reg, bus)
    result = engine.run_audit(task, out_dir=tmp_path / "out")
    assert result.ok
    md = (tmp_path / "out" / "INTERFACE_CHAIN.md").read_text(encoding="utf-8")
    assert "## 8. 关键端点依赖链" in md
    assert "api/a" in md
    assert "↦ 亲属" in md
    db = tmp_path / "out" / "interface_chain.db"
    assert db.exists()
