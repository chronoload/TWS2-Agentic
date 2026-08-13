#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务端工具集 — 让 Agent 可以操作 Web 前端界面
通过 WebSocket 向前端推送指令（打开文件、切换面板等）

工具在执行时动态发现 ws_manager 和主事件循环，
无需在构造时传入，支持在 Agent.__init__ 中统一加载。
"""

import logging
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from ..tools import Tool, ToolResult

logger = logging.getLogger(__name__)

# ── 主事件循环引用（服务端启动时设置）──────────────────────
_main_loop = None
# ── 服务端子进程引用（本地端自动启动时设置）──────────────────
_server_process = None
# ── 默认端口 ──────────────────────────────────────────────
DEFAULT_PORT = 6906


def set_main_loop(loop):
    """设置主事件循环引用（服务端启动时调用一次）"""
    global _main_loop
    _main_loop = loop


def _get_main_loop():
    """获取主事件循环引用"""
    global _main_loop
    if _main_loop is not None and not _main_loop.is_closed():
        return _main_loop
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            return loop
    except RuntimeError:
        pass
    return None


def _is_server_running(port: int = DEFAULT_PORT) -> bool:
    """检测服务端是否在运行"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _find_available_port(start_port: int = DEFAULT_PORT, max_tries: int = 100) -> int:
    """从 start_port 开始查找可用端口"""
    from .app import find_available_port
    return find_available_port(start_port, max_tries=max_tries, host="0.0.0.0")


def _ensure_server_running(workspace_dir: str = "", port: int = DEFAULT_PORT) -> dict:
    """确保服务端正在运行，如果没有则自动启动

    如果指定端口被占用，会自动递增查找可用端口。

    Returns:
        dict: {"running": bool, "pid": int|None, "started": bool, "port": int}
    """
    global _server_process

    # 1. 检查指定端口是否已在运行
    if _is_server_running(port):
        # 尝试获取已有进程的 PID
        pid = None
        try:
            import urllib.request
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/system/stats", timeout=3)
            if req.status == 200:
                pid = os.getpid()  # 如果是自己进程内的服务端
        except Exception:
            pass
        return {"running": True, "pid": pid, "started": False, "port": port}

    # 2. 检查之前启动的子进程是否还活着
    if _server_process is not None:
        if _server_process.poll() is None:
            # 子进程还在，再检查一次端口
            if _is_server_running(port):
                return {"running": True, "pid": _server_process.pid, "started": False, "port": port}
        # 子进程已死，清理
        _server_process = None

    # 3. 自动查找可用端口（支持多实例）
    actual_port = port
    try:
        actual_port = _find_available_port(port)
    except OSError:
        return {"running": False, "pid": None, "started": False, "port": port,
                "error": f"端口 {port}-{port+99} 均被占用"}

    if actual_port != port:
        logger.info(f"端口 {port} 已被占用，自动使用 {actual_port}")

    # 3.5 自动配置防火墙规则（允许局域网和公用网络访问）
    try:
        from .network import configure_firewall
        ok, msg = configure_firewall(actual_port, allow=True)
        if ok:
            logger.info(f"防火墙配置成功: {msg}")
        else:
            logger.warning(f"防火墙配置失败: {msg}")
    except Exception as e:
        logger.debug(f"防火墙配置跳过: {e}")

    # 4. 自动启动服务端
    if not workspace_dir:
        workspace_dir = os.getcwd()

    # 检测项目根目录（向上查找含 mcp/server 的目录）
    if not Path(workspace_dir).exists():
        workspace_dir = os.getcwd()

    # auto_port=False 因为已经在上层选好了端口
    server_script = f'''
import sys
sys.path.insert(0, {repr(str(Path(__file__).parent.parent.parent))})
from mcp.server.app import run_server
run_server(workspace_dir={repr(str(Path(workspace_dir).resolve()))}, host="0.0.0.0", port={actual_port}, open_browser=False, auto_port=False)
'''
    try:
        _server_process = subprocess.Popen(
            [sys.executable, "-c", server_script],
            cwd=workspace_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"自动启动服务端进程 PID={_server_process.pid}, port={actual_port}")
    except Exception as e:
        logger.error(f"自动启动服务端失败: {e}")
        return {"running": False, "pid": None, "started": False, "port": actual_port, "error": str(e)}

    # 5. 等待服务端就绪（最多15秒）
    for i in range(30):
        time.sleep(0.5)
        if _is_server_running(actual_port):
            logger.info(f"服务端已就绪 (PID={_server_process.pid}, port={actual_port})")
            return {"running": True, "pid": _server_process.pid, "started": True, "port": actual_port}
        # 检查子进程是否意外退出
        if _server_process.poll() is not None:
            logger.error(f"服务端进程意外退出，返回码={_server_process.returncode}")
            _server_process = None
            return {"running": False, "pid": None, "started": False, "port": actual_port, "error": "进程意外退出"}

    logger.warning("服务端启动超时")
    return {"running": False, "pid": _server_process.pid if _server_process else None, "started": True, "port": actual_port, "error": "启动超时"}


def _get_ws_broadcast():
    """动态获取 WebSocket broadcast 函数"""
    try:
        from .ws import get_ws_manager
        mgr = get_ws_manager()
        return mgr.broadcast
    except Exception:
        return None


def _ws_broadcast_sync(cmd: str, data: dict = None, workspace_dir: str = "") -> bool:
    """从同步上下文安全地调用异步 WebSocket broadcast

    自动发现 ws_manager 和主事件循环，无需外部传入。
    如果服务端未运行，自动启动。
    """
    # 先确保服务端在运行
    if not _is_server_running():
        result = _ensure_server_running(workspace_dir=workspace_dir)
        if not result["running"]:
            logger.warning(f"WS broadcast: 服务端未运行且自动启动失败: {result.get('error', 'unknown')}")
            return False

    broadcast_fn = _get_ws_broadcast()
    if not broadcast_fn:
        logger.warning("WS broadcast: ws_manager 不可用")
        return False

    main_loop = _get_main_loop()
    if main_loop is None:
        logger.warning("WS broadcast: 主事件循环不可用")
        return False

    try:
        future = asyncio.run_coroutine_threadsafe(broadcast_fn(cmd, data=data), main_loop)
        future.result(timeout=5)
        return True
    except Exception as e:
        logger.warning(f"WS broadcast failed: {e}")
        return False


class OpenInEditorTool(Tool):
    """在 Web 编辑器中打开文件"""
    name = "open_in_editor"
    category = "server"
    keywords = ["open", "editor", "编辑器", "打开", "文件", "前端"]
    model_hint = "当需要在 Web 编辑器中打开文件让用户查看或编辑时使用。"
    description = "在 Web 前端编辑器中打开指定文件，用户可以直接在浏览器中查看和编辑。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于工作目录），如 Notes/物理/力学笔记.md 或 TS2/mcp/agent.py",
            },
        },
        "required": ["path"],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "")
        if not path:
            return ToolResult.err("缺少 path 参数").to_json()

        abs_path = Path(self._workspace_dir) / path
        if not abs_path.exists():
            return ToolResult.err(f"文件不存在: {path}").to_json()
        if abs_path.is_dir():
            return ToolResult.err(f"路径是目录，不是文件: {path}").to_json()

        ok = _ws_broadcast_sync("openInEditor", {"path": path}, workspace_dir=self._workspace_dir)
        if not ok:
            return ToolResult.err("WebSocket 广播失败，无法通知前端打开文件（可能无客户端连接）").to_json()

        return ToolResult.ok(
            data={"path": path},
            message=f"已在编辑器中打开: {path}",
        ).to_json()


class ListServerFilesTool(Tool):
    """列出服务端工作目录中的文件"""
    name = "list_server_files"
    category = "server"
    keywords = ["list", "files", "目录", "文件列表", "浏览"]
    model_hint = "当需要浏览工作目录中的文件和目录结构时使用。"
    description = "列出服务端工作目录中的文件和子目录，不受 EXPOSED_DIRS 限制。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径（相对于工作目录），留空表示根目录",
            },
            "pattern": {
                "type": "string",
                "description": "文件名过滤模式（如 *.py, *.md），留空表示不过滤",
            },
        },
        "required": [],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "")
        pattern = kwargs.get("pattern", "")

        target = Path(self._workspace_dir) / path if path else Path(self._workspace_dir)

        if not target.exists():
            return ToolResult.err(f"目录不存在: {path or '/'}").to_json()
        if not target.is_dir():
            return ToolResult.err(f"路径不是目录: {path}").to_json()

        try:
            target.resolve().relative_to(Path(self._workspace_dir).resolve())
        except ValueError:
            return ToolResult.err("Access denied: path outside workspace").to_json()

        entries = []
        try:
            for item in sorted(target.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue
                if pattern and not item.name.endswith(pattern.lstrip("*")):
                    if item.is_dir():
                        continue

                entry = {
                    "name": item.name,
                    "path": str(item.relative_to(self._workspace_dir)).replace("\\", "/"),
                    "is_dir": item.is_dir(),
                }
                if not item.is_dir():
                    try:
                        entry["size"] = item.stat().st_size
                        entry["ext"] = item.suffix.lower()
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except PermissionError:
            return ToolResult.err(f"无权限访问: {path or '/'}").to_json()

        dirs = [e for e in entries if e["is_dir"]]
        files = [e for e in entries if not e["is_dir"]]

        lines = [f"目录: {path or '/'} ({len(dirs)} 个目录, {len(files)} 个文件)\n"]
        for d in dirs:
            lines.append(f"  📁 {d['name']}/")
        for f in files:
            size = f.get('size', 0)
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            lines.append(f"  📄 {f['name']}  ({size_str})")

        return ToolResult.ok(
            data={"entries": entries, "dirs": len(dirs), "files": len(files)},
            message="\n".join(lines),
        ).to_json()


class ReadServerFileTool(Tool):
    """读取服务端文件内容（不受 EXPOSED_DIRS 限制）"""
    name = "read_server_file"
    category = "server"
    keywords = ["read", "file", "读取", "查看", "源码"]
    model_hint = "当需要读取不在 EXPOSED_DIRS 中的文件时使用（如项目源码）。EXPOSED_DIRS 内的文件优先用 read_file。"
    description = "读取服务端任意文件内容，不受 EXPOSED_DIRS 限制。适合读取项目源码等文件。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于工作目录）",
            },
            "lines": {
                "type": "integer",
                "description": "读取前N行",
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号（从1开始）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含）",
            },
        },
        "required": ["path"],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "")
        lines = kwargs.get("lines")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        if not path:
            return ToolResult.err("缺少 path 参数").to_json()

        abs_path = Path(self._workspace_dir) / path

        try:
            abs_path.resolve().relative_to(Path(self._workspace_dir).resolve())
        except ValueError:
            return ToolResult.err("Access denied: path outside workspace").to_json()

        if not abs_path.exists():
            return ToolResult.err(f"文件不存在: {path}").to_json()
        if abs_path.is_dir():
            return ToolResult.err(f"路径是目录: {path}").to_json()

        try:
            size = abs_path.stat().st_size
            if size > 2 * 1024 * 1024:
                return ToolResult.err(f"文件过大 ({size/1024/1024:.1f}MB)，最大支持 2MB").to_json()
        except OSError:
            return ToolResult.err("无法读取文件信息").to_json()

        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult.err("二进制文件，无法以文本方式读取").to_json()
        except (OSError, PermissionError) as e:
            return ToolResult.err(f"读取失败: {e}").to_json()

        all_lines = content.split("\n")
        total_lines = len(all_lines)

        if start_line or end_line:
            s = max(1, start_line or 1) - 1
            e = min(total_lines, end_line or total_lines)
            selected = all_lines[s:e]
            result = "\n".join(f"{i+1:>{len(str(e))}d}→{line}" for i, line in enumerate(selected, start=s+1))
        elif lines:
            selected = all_lines[:lines]
            result = "\n".join(f"{i+1:>{len(str(lines))}d}→{line}" for i, line in enumerate(selected))
        else:
            if total_lines > 200:
                result = "\n".join(f"{i+1:>3d}→{line}" for i, line in enumerate(all_lines[:200]))
                result += f"\n\n... 共 {total_lines} 行，仅显示前 200 行"
            else:
                result = "\n".join(f"{i+1:>3d}→{line}" for i, line in enumerate(all_lines))

        return ToolResult.ok(
            data={"path": path, "total_lines": total_lines, "size": size},
            message=result,
        ).to_json()


class WriteServerFileTool(Tool):
    """写入服务端文件（不受 EXPOSED_DIRS 限制）"""
    name = "write_server_file"
    category = "server"
    keywords = ["write", "file", "写入", "保存", "创建"]
    model_hint = "当需要写入或创建不在 EXPOSED_DIRS 中的文件时使用。EXPOSED_DIRS 内的文件优先用 write_file。"
    description = "写入服务端文件内容，不受 EXPOSED_DIRS 限制。适合修改项目源码等文件。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于工作目录）",
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容",
            },
        },
        "required": ["path", "content"],
    }
    risk_level = "medium"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")

        if not path:
            return ToolResult.err("缺少 path 参数").to_json()

        if ".." in path:
            return ToolResult.err("Access denied: invalid path").to_json()

        abs_path = Path(self._workspace_dir) / path
        try:
            abs_path.resolve().relative_to(Path(self._workspace_dir).resolve())
        except ValueError:
            return ToolResult.err("Access denied: path outside workspace").to_json()

        abs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            abs_path.write_text(content, encoding="utf-8")
            stat = abs_path.stat()
            return ToolResult.ok(
                data={"path": path, "size": stat.st_size},
                message=f"已写入: {path} ({stat.st_size} 字节)",
            ).to_json()
        except (OSError, PermissionError) as e:
            return ToolResult.err(f"写入失败: {e}").to_json()


class SwitchPanelTool(Tool):
    """切换前端面板"""
    name = "switch_panel"
    category = "server"
    keywords = ["panel", "面板", "切换", "navigate", "导航"]
    model_hint = "当需要引导用户查看特定面板（如源码浏览器、课程面板）时使用。"
    description = "切换 Web 前端显示的面板。"
    parameters = {
        "type": "object",
        "properties": {
            "panel": {
                "type": "string",
                "description": "面板名称: files(文件树), tasks(任务), bookmarks(书签), projects(项目), source(源码浏览器), courses(课程), execution(执行), agent(Agent), stats(统计)",
            },
        },
        "required": ["panel"],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        panel = kwargs.get("panel", "")
        valid_panels = {"files", "tasks", "bookmarks", "projects", "source", "courses", "execution", "agent", "stats"}
        if panel not in valid_panels:
            return ToolResult.err(f"无效面板: {panel}，可选: {', '.join(sorted(valid_panels))}").to_json()

        ok = _ws_broadcast_sync("switchPanel", {"panel": panel}, workspace_dir=self._workspace_dir)
        if not ok:
            return ToolResult.err("WebSocket 广播失败，无法切换面板（可能无客户端连接）").to_json()

        return ToolResult.ok(
            data={"panel": panel},
            message=f"已切换到 {panel} 面板",
        ).to_json()


class NavigateSourceTool(Tool):
    """在源码浏览器中导航到指定目录"""
    name = "navigate_source"
    category = "server"
    keywords = ["source", "navigate", "源码", "浏览", "导航"]
    model_hint = "当需要在源码浏览器中打开某个目录让用户浏览时使用。"
    description = "在 Web 前端源码浏览器中导航到指定目录。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径（相对于工作目录），留空表示根目录",
            },
        },
        "required": [],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path", "")

        if path:
            abs_path = Path(self._workspace_dir) / path
            if not abs_path.exists() or not abs_path.is_dir():
                return ToolResult.err(f"目录不存在: {path}").to_json()

        ok = _ws_broadcast_sync("navigateSource", {"path": path}, workspace_dir=self._workspace_dir)
        if not ok:
            return ToolResult.err("WebSocket 广播失败，无法导航源码浏览器（可能无客户端连接）").to_json()

        return ToolResult.ok(
            data={"path": path},
            message=f"已在源码浏览器中导航到: {path or '/'}",
        ).to_json()


class EnsureServerTool(Tool):
    """检测并启动 TS2 服务端"""
    name = "ensure_server"
    category = "server"
    keywords = ["server", "start", "启动", "服务", "检测", "进程"]
    model_hint = "当需要检测服务端是否运行，或自动启动服务端时使用。返回运行状态和进程号。"
    description = "检测 TS2 服务端是否在运行，如果没有则自动启动。返回运行状态、进程号(PID)和端口。"
    parameters = {
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "服务端端口（默认6906）",
            },
        },
        "required": [],
    }
    risk_level = "low"

    def __init__(self, workspace_dir: str = ""):
        self._workspace_dir = workspace_dir

    def execute(self, **kwargs) -> str:
        port = kwargs.get("port", DEFAULT_PORT)
        result = _ensure_server_running(workspace_dir=self._workspace_dir, port=port)

        if result["running"]:
            if result.get("started"):
                msg = f"服务端已自动启动 (PID={result['pid']}, 端口={result['port']})"
            else:
                msg = f"服务端已在运行 (PID={result.get('pid', 'unknown')}, 端口={result['port']})"
        else:
            msg = f"服务端未运行，自动启动失败: {result.get('error', '未知错误')}"

        return ToolResult.ok(
            data=result,
            message=msg,
        ).to_json()


def get_server_tools(workspace_dir: str = "") -> List[Tool]:
    """获取服务端工具集（动态发现 ws_manager，无需传入运行时依赖）"""
    return [
        EnsureServerTool(workspace_dir=workspace_dir),
        OpenInEditorTool(workspace_dir=workspace_dir),
        ListServerFilesTool(workspace_dir=workspace_dir),
        ReadServerFileTool(workspace_dir=workspace_dir),
        WriteServerFileTool(workspace_dir=workspace_dir),
        SwitchPanelTool(workspace_dir=workspace_dir),
        NavigateSourceTool(workspace_dir=workspace_dir),
    ]
