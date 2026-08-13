"""pyinstaller 打包 macdev.exe（单文件，含全部插件 + 随包数据 macdev-skill/ 与 macdev/doc/）。

用法：python macdev/scripts/build_exe.py [--name macdev] [--onefile]
产物：dist/macdev.exe（onefile 单文件）或 dist/macdev/（目录版）。
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # 含 macdev/ + macdev-skill/


def build(name: str, onefile: bool) -> int:
    entry = ROOT / "macdev" / "scripts" / "macdev_entry.py"
    sep = os.pathsep  # Windows ';' / POSIX ':'
    cmd = [sys.executable, "-m", "PyInstaller",
           str(entry),
           "--name", name,
           "--add-data", f"macdev-skill{sep}macdev-skill",
           "--add-data", f"macdev/doc{sep}macdev/doc",
           "--clean", "--noconfirm",
           "--console",
           "--distpath", str(ROOT / "dist"),
           "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT)]
    if onefile:
        cmd.append("--onefile")
    print("[build] " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode == 0:
        out = ROOT / "dist" / (name + ".exe" if onefile and os.name == "nt" else name)
        print(f"[build] done → {out}")
    return r.returncode


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="macdev", help="可执行文件名（缺省 macdev）")
    ap.add_argument("--dir", action="store_true", help="目录版（缺省 --onefile 单文件）")
    args = ap.parse_args(argv)
    return build(args.name, onefile=not args.dir)


if __name__ == "__main__":
    sys.exit(main())
