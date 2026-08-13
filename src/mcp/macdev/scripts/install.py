"""macdev 安装脚本：把 macdev 包注册到当前 Python 环境的第三方库目录。

原理：在 site-packages 写入 `macdev.pth`，内容为 macdev 包的父目录绝对路径。
Python 解释器启动时按 .pth 注入 sys.path，`import macdev` 即可全局可用
（不复制文件，保持 macdev/ 为单一事实源，改动即时生效）。

用法：
  python macdev/scripts/install.py            # 探测当前解释器 site-packages
  python macdev/scripts/install.py --target DIR   # 手动指定 site-packages
  python macdev/scripts/install.py --list     # 查看已注册状态
"""
from __future__ import annotations
import argparse
import site
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # macdev 包根
PARENT_DIR = PACKAGE_DIR.parent                       # .pth 注入目标（macdev 的父目录）


def find_site_packages() -> list:
    """候选 site-packages：当前解释器的 purelib + 用户 site。
    只保留真正的 site-packages 目录（过滤 python 根目录等非目标位置）。"""
    cands = []
    try:
        import sysconfig
        purelib = sysconfig.get_paths().get("purelib", "")
        if purelib:
            cands.append(Path(purelib))
    except Exception:
        pass
    try:
        for p in site.getsitepackages():
            if "site-packages" in str(p).lower():
                cands.append(Path(p))
    except Exception:
        pass
    try:
        cands.append(Path(site.getusersitepackages()))
    except Exception:
        pass
    # 去重保序（Windows 路径不区分大小写）
    seen = set()
    out = []
    for p in cands:
        key = str(p).lower()
        if p and p.exists() and key not in seen:
            seen.add(key)
            out.append(p)
    return out


def is_registered(site_pkgs: Path) -> bool:
    pth = site_pkgs / "macdev.pth"
    return pth.exists() and str(PARENT_DIR) in pth.read_text(encoding="utf-8", errors="ignore")


def install(target: Path) -> tuple:
    """写入 macdev.pth → (ok, message)"""
    target.mkdir(parents=True, exist_ok=True)
    pth = target / "macdev.pth"
    if is_registered(target):
        return False, f"已注册（{pth}），无需重复安装"
    pth.write_text(f"{PARENT_DIR}\n", encoding="utf-8")
    return True, f"已写入 {pth} → {PARENT_DIR}"


def cmd_list() -> None:
    print(f"macdev 包: {PACKAGE_DIR}")
    for p in find_site_packages():
        status = "✅ 已注册" if is_registered(p) else "—"
        print(f"  {p}  {status}")


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="macdev-install", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="", help="site-packages 目录（默认探测当前解释器）")
    ap.add_argument("--list", action="store_true", help="仅列出候选与注册状态")
    args = ap.parse_args(argv)

    if args.list:
        cmd_list()
        return 0

    if args.target:
        ok, msg = install(Path(args.target))
        print(("[install] " if ok else "[install] ") + msg)
        return 0 if ok else 0
    targets = find_site_packages()
    if not targets:
        print("[install] 未找到 site-packages，请用 --target 指定")
        return 1
    for t in targets:
        ok, msg = install(t)
        print(f"[install] {t}: {msg}")
        if ok:
            print(f"[install] 完成：`import macdev` 现可在该解释器中全局使用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
