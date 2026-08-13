import subprocess
import sys
from pathlib import Path

def test_split_atoms_generates_atoms(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text(
        "import os\n\nX = 1\n\n\ndef hello():\n    return 'hi'\n\n\n"
        "class Greeter:\n    def greet(self):\n        return hello()\n",
        encoding="utf-8",
    )
    out = tmp_path / "parts"
    r = subprocess.run(
        [sys.executable, str(Path("macdev/scripts/split_atoms.py")),
         str(src), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert list(out.glob("*_hello.py")), "hello 原子文件缺失"
    assert list(out.glob("*_Greeter.py")), "Greeter 原子文件缺失"
    assert (out / "core.py").exists()
    assert any(
        "def hello" in f.read_text(encoding="utf-8") for f in out.glob("*_hello.py"))
