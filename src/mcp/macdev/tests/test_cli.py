import subprocess, sys
from pathlib import Path

def test_cli_audit_runs(tmp_path):
    (tmp_path / "app.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/api/x')\ndef x(): return 1\n",
        encoding="utf-8")
    task = tmp_path / "task.json"
    task.write_text('{"endpoints": [{"file": "app.py", "module": "app", "methods": ["get"]}], '
                    '"chains": {"entries": [{"kind": "endpoint", "prefix": "/api/"}]}}',
                    encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "macdev", "audit", "--task", str(task),
         "--root", str(tmp_path), "--out", str(tmp_path / "out")],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / "INTERFACE_CHAIN.md").exists()
