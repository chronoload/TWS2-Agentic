#!/usr/bin/env python3
"""
为「物理科学与技术论题」项目创建快捷启动方式 (.lnk)
双击此脚本即可运行，或在命令行: python create_shortcuts.py
"""

import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

def find_python():
    """查找 Python 可执行文件"""
    # 优先使用当前解释器
    return sys.executable

def create_shortcut(name, target, arguments="", work_dir="", description=""):
    """使用 PowerShell 创建 Windows 快捷方式"""
    lnk_path = PROJECT_ROOT / f"{name}.lnk"
    # 转义单引号
    target = target.replace("'", "''")
    arguments = arguments.replace("'", "''")
    work_dir = work_dir.replace("'", "''")
    description = description.replace("'", "''")

    ps_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{str(lnk_path)}')
$shortcut.TargetPath = '{target}'
$shortcut.Arguments = '{arguments}'
$shortcut.WorkingDirectory = '{work_dir}'
$shortcut.Description = '{description}'
$shortcut.Save()
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  OK  {name}.lnk")
    else:
        print(f"  FAIL  {name}.lnk: {result.stderr.strip()}")

def create_folder_shortcut(name, folder_path):
    """创建打开文件夹的快捷方式"""
    create_shortcut(
        name=name,
        target="explorer.exe",
        arguments=f'"{folder_path}"',
        work_dir=folder_path,
        description=f"打开目录: {name}"
    )

def main():
    python_exe = find_python()
    print(f"\nPython: {python_exe}")
    print(f"项目根目录: {PROJECT_ROOT}\n")

    # ═══════════════════════════════════════════════════
    #  Python 程序快捷方式
    # ═══════════════════════════════════════════════════
    print("── Python 程序 ──")

    py_apps = [
        {
            "name": "课程数据库构建器",
            "script": PROJECT_ROOT / "course_builder.py",
            "work_dir": PROJECT_ROOT,
            "desc": "课程数据库构建器 - 解析 PDF Syllabus 为结构化数据",
        },
        {
            "name": "教学管理系统",
            "script": PROJECT_ROOT / "teaching_manager.py",
            "work_dir": PROJECT_ROOT,
            "desc": "教学管理系统 - 课程进度追踪与可视化 (tkinter GUI)",
        },
        {
            "name": "资源索引器",
            "script": PROJECT_ROOT / "resource_index.py",
            "work_dir": PROJECT_ROOT,
            "desc": "资源索引构建工具",
        },
        {
            "name": "CN MDS",
            "script": PROJECT_ROOT / "cn_mds.py",
            "work_dir": PROJECT_ROOT,
            "desc": "CN MDS 脚本",
        },
        {
            "name": "TS2-课程追踪系统",
            "script": PROJECT_ROOT / "course_tracker.py",
            "work_dir": str(PROJECT_ROOT ),
            "desc": "TS2 课程追踪系统 - 进度管理、MD 导入、资源管理",
        },
        {
            "name": "TS2-MD构建器",
            "script": PROJECT_ROOT / "md_builder.py",
            "work_dir": str(PROJECT_ROOT  ),
            "desc": "TS2 MD 构建器 - 课程 MD 文件解析",
        },
        {
            "name": "TeachingSystem-教学管理",
            "script": PROJECT_ROOT / "TeachingSystem" / "teaching_manager.py",
            "work_dir": str(PROJECT_ROOT / "TeachingSystem"),
            "desc": "TeachingSystem 教学管理 - 课程进度追踪",
        },
        {
            "name": "TeachingSystem-数据管理",
            "script": PROJECT_ROOT / "TeachingSystem" / "data_manager.py",
            "work_dir": str(PROJECT_ROOT / "TeachingSystem"),
            "desc": "TeachingSystem 数据管理",
        },
    ]

    for app in py_apps:
        script_path = str(app["script"])
        if not app["script"].exists():
            print(f"  SKIP {app['name']} (文件不存在: {script_path})")
            continue
        create_shortcut(
            name=app["name"],
            target=python_exe,
            arguments=f'"{script_path}"',
            work_dir=str(app["work_dir"]),
            description=app["desc"],
        )

    # ═══════════════════════════════════════════════════
    #  目录快捷方式
    # ═══════════════════════════════════════════════════
    print("\n── 项目目录 ──")

    dirs = [
        ("Courses", PROJECT_ROOT / "Courses"),
        ("TS2", PROJECT_ROOT / "TS2"),
        ("TeachingSystem", PROJECT_ROOT / "TeachingSystem"),
        ("Literature", PROJECT_ROOT / "Literature"),
        ("Information", PROJECT_ROOT / "Information"),
        ("PyMathUniverse", PROJECT_ROOT / "PyMathUniverse"),
        ("Pynote", PROJECT_ROOT / "Pynote"),
        ("notes", PROJECT_ROOT / "notes"),
        ("Statistical Modeling 2026", PROJECT_ROOT / "Statistical Modeling_2026"),
        ("hortay", PROJECT_ROOT / "hortay"),
    ]

    for name, path in dirs:
        if path.exists():
            create_folder_shortcut(name, str(path))
        else:
            print(f"  SKIP {name} (目录不存在)")

    # ═══════════════════════════════════════════════════
    #  RStudio 项目
    # ═══════════════════════════════════════════════════
    rproj = PROJECT_ROOT / "物理科学与技术论题.Rproj"
    if rproj.exists():
        print("\n── RStudio 项目 ──")
        create_shortcut(
            name="RStudio-物理科学与技术论题",
            target=str(rproj),
            work_dir=str(PROJECT_ROOT),
            description="在 RStudio 中打开物理科学与技术论题项目",
        )

    # ═══════════════════════════════════════════════════
    #  命令行快捷方式
    # ═══════════════════════════════════════════════════
    print("\n── 命令行 ──")

    terminal_apps = [
        {
            "name": "终端-项目根目录",
            "args": f'-NoExit -Command "Set-Location \'{PROJECT_ROOT}\'; Write-Host \'物理科学与技术论题\' -ForegroundColor Cyan"',
            "work_dir": str(PROJECT_ROOT),
            "desc": "在项目根目录打开 PowerShell 7",
        },
        {
            "name": "终端-TS2",
            "args": f'-NoExit -Command "Set-Location \'{PROJECT_ROOT / "TS2"}\'; Write-Host \'TS2 课程追踪系统\' -ForegroundColor Cyan"',
            "work_dir": str(PROJECT_ROOT / "TS2"),
            "desc": "在 TS2 目录打开 PowerShell 7",
        },
        {
            "name": "终端-TeachingSystem",
            "args": f'-NoExit -Command "Set-Location \'{PROJECT_ROOT / "TeachingSystem"}\'; Write-Host \'TeachingSystem\' -ForegroundColor Cyan"',
            "work_dir": str(PROJECT_ROOT / "TeachingSystem"),
            "desc": "在 TeachingSystem 目录打开 PowerShell 7",
        },
    ]

    for t in terminal_apps:
        create_shortcut(
            name=t["name"],
            target="pwsh.exe",
            arguments=t["args"],
            work_dir=t["work_dir"],
            description=t["desc"],
        )

    # ═══════════════════════════════════════════════════
    #  汇总
    # ═══════════════════════════════════════════════════
    lnk_files = sorted(PROJECT_ROOT.glob("*.lnk"))
    print(f"\n{'='*50}")
    print(f"  共创建 {len(lnk_files)} 个快捷方式")
    print(f"{'='*50}\n")
    for f in lnk_files:
        print(f"  {f.name}")

if __name__ == "__main__":
    main()
