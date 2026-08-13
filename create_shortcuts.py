#!/usr/bin/env python3
"""
为 TS2-OpenSource 项目创建快捷启动方式 (.lnk)
双击此脚本即可运行，或在命令行: python create_shortcuts.py
"""

import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def find_python():
    """查找 Python 可执行文件"""
    return sys.executable

def create_shortcut(name, target, arguments="", work_dir="", description=""):
    """使用 PowerShell 创建 Windows 快捷方式"""
    lnk_path = PROJECT_ROOT / f"{name}.lnk"
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
            "name": "TS2-课程追踪系统",
            "script": PROJECT_ROOT / "run.py",
            "work_dir": str(PROJECT_ROOT),
            "desc": "TS2 课程追踪系统 - 主入口",
        },
        {
            "name": "TS2-MCP-Agent",
            "script": PROJECT_ROOT / "run_mcp_agent.py",
            "work_dir": str(PROJECT_ROOT),
            "desc": "TS2 MCP Agent - AI助手界面",
        },
        {
            "name": "TS2-MCP-Agent(源码)",
            "script": PROJECT_ROOT / "src" / "mcp" / "agent_assistant.py",
            "work_dir": str(PROJECT_ROOT / "src" / "mcp"),
            "desc": "TS2 MCP Agent - 直接运行源码",
        },
        {
            "name": "TS2-课程追踪(源码)",
            "script": PROJECT_ROOT / "src" / "course_tracker.py",
            "work_dir": str(PROJECT_ROOT / "src"),
            "desc": "TS2 课程追踪系统 - 直接运行源码",
        },
        {
            "name": "TS2-MD构建器",
            "script": PROJECT_ROOT / "src" / "md_builder.py",
            "work_dir": str(PROJECT_ROOT / "src"),
            "desc": "TS2 MD 构建器 - Markdown解析",
        },
        {
            "name": "TS2-公式转换器",
            "script": PROJECT_ROOT / "src" / "tex_to_utf8.py",
            "work_dir": str(PROJECT_ROOT / "src"),
            "desc": "TS2 LaTeX到UTF-8转换",
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
    #  测试工具快捷方式
    # ═══════════════════════════════════════════════════
    print("\n── 测试工具 ──")

    test_apps = [
        {
            "name": "TS2-测试导入",
            "script": PROJECT_ROOT / "test_imports.py",
            "work_dir": str(PROJECT_ROOT),
            "desc": "测试所有模块导入",
        },
        {
            "name": "TS2-测试MCP",
            "script": PROJECT_ROOT / "test_mcp.py",
            "work_dir": str(PROJECT_ROOT),
            "desc": "测试MCP Agent系统",
        },
    ]

    for app in test_apps:
        script_path = str(app["script"])
        if not app["script"].exists():
            print(f"  SKIP {app['name']} (文件不存在)")
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
        ("TS2-src", PROJECT_ROOT / "src"),
        ("TS2-mcp", PROJECT_ROOT / "src" / "mcp"),
        ("TS2-mcp-rag", PROJECT_ROOT / "src" / "mcp" / "rag"),
        ("TS2-mcp-prompt", PROJECT_ROOT / "src" / "mcp" / "prompt"),
        ("TS2-mcp-cache", PROJECT_ROOT / "src" / "mcp" / "cache"),
        ("TS2-tests", PROJECT_ROOT / "tests"),
        ("TS2-config", PROJECT_ROOT / "config"),
        ("TS2-examples", PROJECT_ROOT / "examples"),
        ("TS2-docs", PROJECT_ROOT / "docs"),
    ]

    for name, path in dirs:
        if path.exists():
            create_folder_shortcut(name, str(path))
        else:
            print(f"  SKIP {name} (目录不存在)")

    # ═══════════════════════════════════════════════════
    #  命令行快捷方式
    # ═══════════════════════════════════════════════════
    print("\n── 命令行 ──")

    create_shortcut(
        name="终端-TS2",
        target="pwsh.exe",
        arguments=f'-NoExit -Command "Set-Location \'{PROJECT_ROOT}\'; Write-Host \'TS2 OpenSource Project\' -ForegroundColor Cyan"',
        work_dir=str(PROJECT_ROOT),
        description="在项目根目录打开 PowerShell",
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
