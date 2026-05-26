#!/usr/bin/env python3
"""
通用项目快捷方式创建脚本
自动发现项目结构并创建快捷启动方式 (.lnk)

配置文件: shortcuts_config.json (可选)
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def load_config():
    """加载配置文件，若无则返回默认配置"""
    config_path = Path(__file__).parent / "shortcuts_config.json"
    default_config = {
        "project_name": "项目",
        "python_apps": [],
        "directories": [],
        "terminal_dirs": [],
        "ps1_scripts": [],
        "rproj": "",
        "use_pwsh": True,
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return {**default_config, **loaded}
        except Exception as e:
            print(f"  配置文件加载失败，使用默认: {e}")

    return default_config


def find_python():
    """查找 Python 可执行文件"""
    return sys.executable


def create_shortcut(name, target, arguments="", work_dir="", description="", shortcuts_dir=None):
    """使用 PowerShell 创建 Windows 快捷方式"""
    if shortcuts_dir is None:
        shortcuts_dir = Path(__file__).parent
    lnk_path = shortcuts_dir / f"{name}.lnk"

    target = str(target).replace("'", "''")
    arguments = str(arguments).replace("'", "''")
    work_dir = str(work_dir).replace("'", "''")
    description = str(description).replace("'", "''")

    ps_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{str(lnk_path)}')
$shortcut.TargetPath = '{target}'
$shortcut.Arguments = '{arguments}'
$shortcut.WorkingDirectory = '{work_dir}'
$shortcut.Description = '{description}'
$shortcut.Save()
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"  OK  {name}.lnk")
        else:
            print(f"  FAIL  {name}.lnk: {result.stderr.strip()[:100]}")
    except Exception as e:
        print(f"  FAIL  {name}.lnk: {str(e)[:100]}")


def create_folder_shortcut(name, folder_path, shortcuts_dir=None):
    """创建打开文件夹的快捷方式"""
    create_shortcut(
        name=name,
        target="explorer.exe",
        arguments=f'"{folder_path}"',
        work_dir=str(folder_path),
        description=f"打开目录: {name}",
        shortcuts_dir=shortcuts_dir,
    )


def auto_discover_project(project_root):
    """自动发现项目中的主要 Python 脚本和目录"""
    discovered = {
        "python_apps": [],
        "directories": [],
        "ps1_scripts": [],
        "rproj": "",
    }

    # 查找顶级 Python 文件
    py_files = list(project_root.glob("*.py"))
    priority_keywords = [
        "course", "track", "main", "run", "manager", "agent", "assistant",
        "builder", "converter", "research", "synergy"
    ]

    for py_file in py_files:
        name_lower = py_file.stem.lower()
        if any(kw in name_lower for kw in priority_keywords):
            discovered["python_apps"].append({
                "name": py_file.stem.replace("_", "-").title(),
                "script": str(py_file.relative_to(project_root)),
                "desc": f"{py_file.stem} - 自动发现"
            })

    # 查找常见目录
    common_dirs = ["src", "data", "logs", "doc", "Notes", "mcp", "Courses"]
    for d in common_dirs:
        dir_path = project_root / d
        if dir_path.exists() and dir_path.is_dir():
            discovered["directories"].append((d, str(dir_path.relative_to(project_root))))

    # 查找 R 项目
    rproj_files = list(project_root.glob("*.Rproj"))
    if rproj_files:
        discovered["rproj"] = str(rproj_files[0].relative_to(project_root))

    # 查找 PowerShell 脚本
    ps1_files = list(project_root.glob("*.ps1"))
    for ps1 in ps1_files:
        discovered["ps1_scripts"].append({
            "name": ps1.stem.replace("_", "-").title(),
            "script": str(ps1.relative_to(project_root)),
            "desc": f"{ps1.stem} - PowerShell 脚本"
        })

    return discovered


def main():
    PROJECT_ROOT = Path(__file__).parent
    shortcuts_dir = PROJECT_ROOT

    python_exe = find_python()
    config = load_config()
    auto = auto_discover_project(PROJECT_ROOT)

    print(f"\n{'='*60}")
    print(f"  通用快捷方式创建工具")
    print(f"{'='*60}")
    print(f"\nPython: {python_exe}")
    print(f"项目根目录: {PROJECT_ROOT}\n")

    # 合并配置和自动发现
    py_apps = config.get("python_apps", []) or auto["python_apps"]
    dirs = config.get("directories", []) or auto["directories"]
    terminal_dirs = config.get("terminal_dirs", [("根目录", ".")])
    ps1_scripts = config.get("ps1_scripts", []) or auto["ps1_scripts"]
    rproj = config.get("rproj", auto["rproj"])
    use_pwsh = config.get("use_pwsh", True)

    # ═══════════════════════════════════════════════════
    #  Python 程序快捷方式
    # ═══════════════════════════════════════════════════
    print("── Python 程序 ──")

    for app in py_apps:
        script_path = PROJECT_ROOT / app["script"]
        if not script_path.exists():
            print(f"  SKIP {app['name']} (文件不存在)")
            continue
        work_dir = str(PROJECT_ROOT / app.get("work_dir", Path(app["script"]).parent))
        create_shortcut(
            name=app["name"],
            target=python_exe,
            arguments=f'"{str(script_path)}"',
            work_dir=work_dir,
            description=app.get("desc", app["name"]),
            shortcuts_dir=shortcuts_dir,
        )

    # ═══════════════════════════════════════════════════
    #  PowerShell 脚本快捷方式
    # ═══════════════════════════════════════════════════
    if ps1_scripts:
        print("\n── PowerShell 脚本 ──")
        for ps1 in ps1_scripts:
            script_path = PROJECT_ROOT / ps1["script"]
            if not script_path.exists():
                print(f"  SKIP {ps1['name']} (文件不存在)")
                continue
            work_dir = str(PROJECT_ROOT / ps1.get("work_dir", Path(ps1["script"]).parent))
            create_shortcut(
                name=ps1["name"],
                target="powershell.exe",
                arguments=f'-ExecutionPolicy Bypass -File "{str(script_path)}"',
                work_dir=work_dir,
                description=ps1.get("desc", ps1["name"]),
                shortcuts_dir=shortcuts_dir,
            )

    # ═══════════════════════════════════════════════════
    #  目录快捷方式
    # ═══════════════════════════════════════════════════
    if dirs:
        print("\n── 项目目录 ──")
        for entry in dirs:
            if isinstance(entry, tuple):
                name, rel_path = entry
            else:
                name = entry.get("name", Path(entry["path"]).name)
                rel_path = entry["path"]

            full_path = PROJECT_ROOT / rel_path
            if full_path.exists():
                create_folder_shortcut(name, str(full_path), shortcuts_dir=shortcuts_dir)
            else:
                print(f"  SKIP {name} (目录不存在)")

    # ═══════════════════════════════════════════════════
    #  RStudio 项目
    # ═══════════════════════════════════════════════════
    if rproj:
        rproj_path = PROJECT_ROOT / rproj
        if rproj_path.exists():
            print("\n── RStudio 项目 ──")
            create_shortcut(
                name=f"RStudio-{Path(rproj).stem}",
                target=str(rproj_path),
                work_dir=str(PROJECT_ROOT),
                description=f"在 RStudio 中打开项目",
                shortcuts_dir=shortcuts_dir,
            )

    # ═══════════════════════════════════════════════════
    #  命令行快捷方式
    # ═══════════════════════════════════════════════════
    if terminal_dirs:
        print("\n── 命令行 ──")
        term_exe = "pwsh.exe" if use_pwsh and os.path.exists("C:\\Program Files\\PowerShell\\7\\pwsh.exe") else "powershell.exe"

        for entry in terminal_dirs:
            if isinstance(entry, tuple):
                name, rel_path = entry
            else:
                name = entry.get("name", Path(entry["path"]).name)
                rel_path = entry["path"]

            full_path = PROJECT_ROOT / rel_path
            if not full_path.exists():
                full_path = PROJECT_ROOT
                rel_path = "."

            create_shortcut(
                name=f"终端-{name}",
                target=term_exe,
                arguments=f'-NoExit -Command "Set-Location \'{str(full_path)}\'; Write-Host \'{name}\' -ForegroundColor Cyan"',
                work_dir=str(full_path),
                description=f"在 {name} 目录打开终端",
                shortcuts_dir=shortcuts_dir,
            )

    # ═══════════════════════════════════════════════════
    #  汇总
    # ═══════════════════════════════════════════════════
    lnk_files = sorted(shortcuts_dir.glob("*.lnk"))
    print(f"\n{'='*60}")
    print(f"  共创建 {len(lnk_files)} 个快捷方式")
    print(f"{'='*60}\n")

    # 检查是否创建配置文件
    config_template_path = PROJECT_ROOT / "shortcuts_config.example.json"
    if not config_template_path.exists():
        example_config = {
            "_comment": "将此文件重命名为 shortcuts_config.json 并编辑",
            "project_name": "你的项目",
            "use_pwsh": True,
            "python_apps": [
                {
                    "name": "主程序",
                    "script": "main.py",
                    "work_dir": ".",
                    "desc": "主程序描述"
                }
            ],
            "directories": [
                {"name": "源代码", "path": "src"},
                {"name": "数据", "path": "data"}
            ],
            "terminal_dirs": [
                {"name": "根目录", "path": "."},
                {"name": "源代码", "path": "src"}
            ],
            "ps1_scripts": [],
            "rproj": ""
        }
        with open(config_template_path, "w", encoding="utf-8") as f:
            json.dump(example_config, f, ensure_ascii=False, indent=2)
        print(f"  已创建配置模板: shortcuts_config.example.json")
        print(f"  如需自定义，请复制为 shortcuts_config.json 并编辑\n")

    for f in lnk_files[:20]:
        print(f"  {f.name}")
    if len(lnk_files) > 20:
        print(f"  ... 还有 {len(lnk_files)-20} 个")


if __name__ == "__main__":
    main()