"""macdev 安装脚本：把 macdev 包整体复制进当前 Python 环境的第三方库目录。

原理：将 macdev/ 包目录（单一事实源）物理复制到 site-packages/macdev，
`import macdev` 即可在该解释器中全局使用。与旧版（.pth 指针注册）不同：
  - 不写任何 .pth 指针 → 不污染 sys.path、不把项目目录注入全局；
  - 复制为独立快照 → 与主程序（mcp）完全隔离，`import macdev` 不携带 mcp。

用法：
  python macdev/scripts/install.py            # 探测当前解释器 site-packages 并复制
  python macdev/scripts/install.py --target DIR   # 手动指定 site-packages
  python macdev/scripts/install.py --list     # 查看候选目录与安装状态
  python macdev/scripts/install.py --uninstall [--target DIR]  # 移除已安装副本
"""
from __future__ import annotations
import argparse
import shutil
import site
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # macdev 包根（单一事实源）
INSTALL_NAME = "macdev"

# 复制时排除的缓存/测试临时目录
_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}


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


def is_installed(site_pkgs: Path) -> bool:
    """site-packages 下是否已有 macdev 副本。"""
    return (site_pkgs / INSTALL_NAME / "__init__.py").exists()


def _copy_package(src: Path, dst: Path) -> None:
    """复制 macdev 包 → dst/macdev，排除缓存目录。"""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in _EXCLUDE_DIRS:
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*_EXCLUDE_DIRS))
        else:
            shutil.copy2(item, target)


def install(target: Path) -> tuple:
    """复制 macdev 包到目标 site-packages → (ok, message)"""
    target.mkdir(parents=True, exist_ok=True)
    dst = target / INSTALL_NAME
    _copy_package(PACKAGE_DIR, dst)
    return True, f"已复制 {PACKAGE_DIR} -> {dst}（{INSTALL_NAME}/ 独立副本，无 .pth 指针）"


def uninstall(target: Path) -> tuple:
    """移除目标 site-packages 下的 macdev 副本 → (ok, message)"""
    dst = target / INSTALL_NAME
    if not dst.exists():
        return False, f"未安装（{dst} 不存在）"
    shutil.rmtree(dst)
    return True, f"已移除 {dst}"


def cmd_list() -> None:
    print(f"macdev 包: {PACKAGE_DIR}（单一事实源）")
    for p in find_site_packages():
        status = "已复制" if is_installed(p) else "—"
        print(f"  {p}  {status}")


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="macdev-install", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="", help="site-packages 目录（默认探测当前解释器）")
    ap.add_argument("--list", action="store_true", help="仅列出候选与安装状态")
    ap.add_argument("--uninstall", action="store_true", help="移除已安装副本（而非安装）")
    args = ap.parse_args(argv)

    if args.list:
        cmd_list()
        return 0

    targets = [Path(args.target)] if args.target else find_site_packages()
    if not targets:
        print("[install] 未找到 site-packages，请用 --target 指定")
        return 1
    for t in targets:
        ok, msg = (uninstall(t) if args.uninstall else install(t))
        print(f"[install] {t}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())