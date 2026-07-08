

================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\__init__.py
================================================

```python
"""
TS2 Server - 现代前后端服务
参考思源笔记架构：本地 HTTP API + WebSocket 实时推送 + 文件同步分发
"""

from .app import create_app, run_server, find_available_port
from .ws import WebSocketManager
from .sync import FileSyncEngine

__all__ = ["create_app", "run_server", "find_available_port", "WebSocketManager", "FileSyncEngine"]

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\app.py
================================================

```python
"""
TS2 FastAPI 服务端应用
参考思源笔记 API 设计：POST + JSON body，统一返回格式 {code, msg, data}
支持：文件 CRUD、目录浏览、搜索、WebSocket 实时推送、文件同步分发
      文件上传/下载（手机端传输）、局域网访问
"""

import asyncio
import json
import logging
import os
import sys
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import concurrent.futures
import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# 高性能 JSON 序列化（orjson 优先）
try:
    import orjson as _orjson
    def _json_dumps(obj, **kwargs):
        return _orjson.dumps(obj, option=_orjson.OPT_INDENT_2).decode('utf-8')
    def _json_loads(s, **kwargs):
        return _orjson.loads(s)
    def _json_dumps_compact(obj):
        """紧凑 JSON（无缩进），用于 SSE 等需要单行输出的场景"""
        return _orjson.dumps(obj).decode('utf-8')
    logger_json = "orjson"
except ImportError:
    _json_dumps = json.dumps
    _json_loads = json.loads
    def _json_dumps_compact(obj):
        return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
    logger_json = "json"

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.gzip import GZipMiddleware

from .ws import WebSocketManager, get_ws_manager
from .sync import FileSyncEngine, SyncEvent, SyncStatus, SyncChange
from .network import NetworkSettings, configure_firewall, check_network_access, set_network_profile_private, get_all_network_interfaces
from .tunnel import TunnelManager, get_tunnel_manager

logger = logging.getLogger(__name__)

# ─── 请求/响应模型 ───────────────────────────────────────────

class APIResponse(BaseModel):
    """统一 API 响应格式（参考思源笔记）"""
    code: int = 0
    msg: str = ""
    data: Any = None


class FileReadRequest(BaseModel):
    path: str


class FileWriteRequest(BaseModel):
    path: str
    content: str


class FileRemoveRequest(BaseModel):
    path: str


class FileRenameRequest(BaseModel):
    old_path: str
    new_path: str


class DirReadRequest(BaseModel):
    path: str = ""


class DirCreateRequest(BaseModel):
    path: str


class SearchRequest(BaseModel):
    query: str
    subdir: str = ""


class ScanRequest(BaseModel):
    subdir: str = ""


class SyncRequest(BaseModel):
    """同步请求（参考 siyuan-android mobileSwitch 参数）"""
    direction: str = "both"  # upload, download, both
    paths: list = []  # 指定路径，空=全部
    mobile_switch: bool = False  # 是否来自移动端前后台切换（参考 siyuan-android）


class WsCommand(BaseModel):
    """WebSocket 命令"""
    cmd: str
    req_id: float = 0
    param: Dict[str, Any] = {}


class TaskUpdateRequest(BaseModel):
    """任务更新请求"""
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    duration: Optional[int] = None
    recurrence: Optional[str] = None


class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    title: str
    description: str = ""
    due_date: str = ""
    priority: str = "中"
    status: str = "待办"
    start_time: str = ""
    duration: int = 60
    recurrence: str = "不循环"


class TaskDeleteRequest(BaseModel):
    """任务删除请求"""
    id: str


class CourseProgressRequest(BaseModel):
    """课程进度请求"""
    course_id: str


class LessonStatusRequest(BaseModel):
    """课时状态请求"""
    course_id: str
    lesson_number: int
    status: str


class TimetableSlotCreateRequest(BaseModel):
    """课程表课时创建请求"""
    timetable_id: str = ""
    course_name: str
    day_of_week: int  # 1-7
    start_time: str  # "08:00"
    end_time: str  # "08:45"
    location: str = ""
    teacher: str = ""
    period_idx: int = 0
    color: str = ""


class TimetableSlotDeleteRequest(BaseModel):
    """课程表课时删除请求"""
    timetable_id: str = ""
    slot_id: str


class TimetableCreateRequest(BaseModel):
    """课程表创建请求"""
    name: str
    semester_start: str = ""
    semester_end: str = ""


class TimetableSetActiveRequest(BaseModel):
    """设置激活课程表请求"""
    timetable_id: str


class TimetableDeleteRequest(BaseModel):
    """课程表删除请求"""
    timetable_id: str


class AgentChatRequest(BaseModel):
    """Agent 聊天请求"""
    message: str
    context: Optional[Dict[str, Any]] = None
    session_id: str = ""  # 前端持久化的会话 ID（参考 Crush Session.ID）
    attachments: Optional[List[Dict[str, str]]] = None  # 多模态附件 [{"kind":"image","data_url":"data:...","path":"..."}]


class AgentSessionSwitchRequest(BaseModel):
    """Agent 会话切换/删除请求"""
    session_id: str


# ─── 工具函数 ────────────────────────────────────────────────

def get_local_ip() -> str:
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def find_available_port(start_port: int = 6906, max_tries: int = 100,
                        host: str = "0.0.0.0") -> int:
    """从 start_port 开始查找可用端口，跳过已被占用的端口

    Args:
        start_port: 起始端口号
        max_tries: 最大尝试次数
        host: 检测绑定的地址

    Returns:
        可用的端口号

    Raises:
        OSError: 在 max_tries 范围内找不到可用端口
    """
    for port in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                # bind 成功 = 端口可用
                return port
        except OSError:
            continue
    raise OSError(f"在 {start_port}-{start_port + max_tries - 1} 范围内找不到可用端口")


# ─── API 配置加载 ──────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".ts2"
CONFIG_FILE = CONFIG_DIR / "ts2_api_config.json"

def load_api_config() -> dict:
    """读取 ts2_api_config.json，不存在则返回默认"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {
        "api_token": "",
        "source_auth_code": "",
        "workspaces": [
            {
                "name": "默认工作区",
                "path": str(Path.cwd().resolve()),
                "auth_code": "",
                "readable": True,
                "writable": True,
                "relaxed": True,
            }
        ],
    }

def check_path_access(file_path: str, mode: str = "read") -> bool:
    """检查文件路径是否在允许的工作区目录内"""
    config = load_api_config()
    real_path = Path(file_path).resolve()
    for ws in config.get("workspaces", []):
        ws_root = Path(ws["path"]).resolve()
        if not (str(real_path).startswith(str(ws_root) + os.sep) or real_path == ws_root):
            continue
        if ws.get("relaxed"):
            return True
        if mode == "read" and ws.get("readable"):
            return True
        if mode == "write" and ws.get("writable"):
            return True
    return False


def _is_resource_path(file_path: str, workspace_dir: str = "") -> bool:
    """检查路径是否在 resource_index.json 中注册（课程资源）"""
    if not workspace_dir:
        workspace_dir = str(Path.cwd())
    real_path = Path(file_path).resolve()
    for p in [Path(workspace_dir) / "data" / "resource_index.json", Path(workspace_dir) / "resource_index.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for resources in data.values():
                    for r in resources:
                        rp = r.get("path", "")
                        if rp and Path(rp).resolve() == real_path:
                            return True
            except Exception:
                pass
            break
    return False


# ─── 鉴权辅助 ──────────────────────────────────────────────────

# ─── 服务端 Session ──────────────────────────────────────────────

# {session_token: {"code": str, "created_at": float}}
_sessions: Dict[str, Dict] = {}
_SESSION_TTL = 86400 * 7  # 7 天过期
_RATE_LIMIT = 10          # 10 次
_RATE_WINDOW = 300        # 5 分钟内
_attempts: Dict[str, list] = {}

def _create_session(code: str) -> str:
    token = uuid.uuid4().hex
    _sessions[token] = {"code": code, "created_at": time.time(), "authed": []}
    return token

def _get_session_code(token: str) -> str:
    sess = _sessions.get(token)
    if not sess:
        return ""
    if time.time() - sess["created_at"] > _SESSION_TTL:
        del _sessions[token]
        return ""
    return sess["code"]

def _session_add_workspace(token: str, resolved_path: str):
    sess = _sessions.get(token)
    if sess and resolved_path not in sess["authed"]:
        sess["authed"].append(resolved_path)

def _session_has_workspace(token: str, resolved_path: str) -> bool:
    sess = _sessions.get(token)
    return bool(sess and resolved_path in sess["authed"])

def _delete_session(token: str):
    _sessions.pop(token, None)

def _check_rate_limit(key: str) -> bool:
    """每个 IP 5 分钟最多 _RATE_LIMIT 次登录尝试"""
    now = time.time()
    lst = _attempts.setdefault(key, [])
    lst[:] = [t for t in lst if now - t < _RATE_WINDOW]
    if len(lst) >= _RATE_LIMIT:
        return False
    lst.append(now)
    return True

PUBLIC_ENDPOINTS = {
    "/api/system/health",
    "/api/system/authInfo",
    "/api/system/loginAuth",
    "/api/system/sourceAuth",
    "/api/system/stats",
    "/api/system/version",
}

def _get_all_auth_codes(config: dict) -> set:
    """从所有工作区中收集授权码（兼容旧版全局 access_auth_code）"""
    codes = set()
    old_global = config.get("access_auth_code", "")
    if old_global:
        codes.add(old_global)
    for ws in config.get("workspaces", []):
        code = ws.get("auth_code", "")
        if code:
            codes.add(code)
    return codes

async def check_auth(request: Request, config: dict) -> bool:
    """鉴权检查：localhost 免检，无 auth_code/api_token 时远程也免检。
    token 和 auth_code 是与逻辑：两者都配置时必须同时满足，只配置其一则只需满足那一个。"""
    client_host = request.client.host if request.client else "127.0.0.1"
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True

    api_token = config.get("api_token", "")
    auth_codes = _get_all_auth_codes(config)

    # 没有任何授权要求时放行
    if not api_token and not auth_codes:
        return True

    # 检查 token
    token_ok = False
    code_ok = False
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith(("Token ", "Bearer ")):
        token_val = auth_header.split(" ", 1)[1]
        if token_val == api_token and api_token:
            token_ok = True
        # Token header 中的值也可匹配 auth_code（兼容旧 APK 或 file:// 场景）
        if not token_ok and not api_token and auth_codes and token_val in auth_codes:
            code_ok = True
    if not token_ok and request.query_params.get("token") == api_token and api_token:
        token_ok = True
    # query param token 也可匹配 auth_code（兼容旧前端 downloadFile）
    if not token_ok and not api_token and request.query_params.get("token", "") in auth_codes:
        code_ok = True
    if not token_ok:
        session_token = request.cookies.get("ts2_session", "")
        if session_token:
            sess_code = _get_session_code(session_token)
            if sess_code:
                if sess_code == api_token and api_token:
                    token_ok = True

    # 检查 auth_code
    if auth_codes:
        # Cookie session 中的 code 匹配
        session_token = request.cookies.get("ts2_session", "")
        if session_token:
            sess_code = _get_session_code(session_token)
            if sess_code and sess_code in auth_codes:
                code_ok = True
            # session 中已认证过工作区
            if not code_ok:
                sess = _sessions.get(session_token)
                if sess and sess.get("authed"):
                    code_ok = True
        # X-Auth-Code header（前端 axios 拦截器注入，与 token 同时发送）
        if not code_ok and request.headers.get("x-auth-code", "") in auth_codes:
            code_ok = True
        # Basic Auth
        if not code_ok and auth_header.startswith("Basic "):
            import base64
            try:
                decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
                if ":" in decoded and decoded.split(":", 1)[1] in auth_codes:
                    code_ok = True
            except Exception:
                pass

    # 与逻辑：两者都配置时必须都满足，只配置一则满足那一个即可
    need_token = bool(api_token)
    need_code = bool(auth_codes)
    if need_token and need_code:
        return token_ok and code_ok
    if need_token:
        return token_ok
    if need_code:
        return code_ok
    return True


def _check_ws_auth(websocket: WebSocket, config: dict) -> bool:
    """WebSocket 鉴权：同 check_auth，但基于 WebSocket 的 query_params 和 cookies"""
    client_host = websocket.client.host if websocket.client else "127.0.0.1"
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True

    api_token = config.get("api_token", "")
    auth_codes = _get_all_auth_codes(config)

    if not api_token and not auth_codes:
        return True

    token_ok = False
    if api_token:
        qp_token = websocket.query_params.get("token", "")
        if qp_token == api_token:
            token_ok = True
        if not token_ok:
            sess_token = websocket.cookies.get("ts2_session", "")
            if sess_token:
                sess_code = _get_session_code(sess_token)
                if sess_code == api_token:
                    token_ok = True

    code_ok = False
    if auth_codes:
        sess_token = websocket.cookies.get("ts2_session", "")
        if sess_token:
            sess_code = _get_session_code(sess_token)
            if sess_code and sess_code in auth_codes:
                code_ok = True
        if not code_ok:
            from urllib.parse import parse_qs
            raw_qs = websocket.url.query if hasattr(websocket.url, 'query') else ""
            qs_params = parse_qs(raw_qs) if raw_qs else {}
            qp_code = qs_params.get("auth_code", [None])[0]
            if qp_code and qp_code in auth_codes:
                code_ok = True

    need_token = bool(api_token)
    need_code = bool(auth_codes)
    if need_token and need_code:
        return token_ok and code_ok
    if need_token:
        return token_ok
    if need_code:
        return code_ok
    return True


def _check_source_auth(request: Request, require_write: bool = False) -> bool:
    """源码浏览器独立鉴权：读取需 source_auth_code 或工作区 auth_code，写入必须 source_auth_code"""
    config = load_api_config()
    source_code = config.get("source_auth_code", "")

    # 无 source_auth_code 时退化为普通鉴权
    if not source_code:
        return True

    # 本地免检读取，写入仍需验证
    client_host = request.client.host if request.client else "127.0.0.1"
    if not require_write and client_host in ("127.0.0.1", "::1", "localhost"):
        return True

    # Session 中已标记 source_authed
    session_token = request.cookies.get("ts2_session", "")
    if session_token:
        sess = _sessions.get(session_token)
        if sess and sess.get("source_authed"):
            return True

    # 从请求头取 source_code
    src_code = request.headers.get("X-Source-Auth", "")
    if not src_code:
        src_code = request.query_params.get("source_code", "")

    if src_code == source_code:
        return True

    return False

# ─── 应用创建 ────────────────────────────────────────────────

def create_app(workspace_dir: Optional[str] = None, host: str = "0.0.0.0",
               port: int = 6906) -> FastAPI:
    """创建 FastAPI 应用实例"""

    if workspace_dir is None:
        workspace_dir = os.getcwd()

    app = FastAPI(
        title="TS2 Server",
        description="TS2 本地文件同步分发服务（参考思源笔记架构）",
        version="1.0.0",
    )

    # ─── 自定义 CORS 中间件 ──────────────────────────────
    # 反射 Origin + credentials=True，methods/headers 用显式值（w3c 规范要求）
    @app.middleware("http")
    async def cors_middleware(request: Request, call_next):
        origin = request.headers.get("origin", "")
        if not origin:
            return await call_next(request)
        methods = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        headers = "Content-Type, Authorization, X-Auth-Code, X-Requested-With, Range, If-None-Match"
        if request.method == "OPTIONS":
            resp = JSONResponse(content="")
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Methods"] = methods
            resp.headers["Access-Control-Allow-Headers"] = headers
            resp.headers["Access-Control-Max-Age"] = "86400"
            return resp
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = methods
        response.headers["Access-Control-Allow-Headers"] = headers
        return response

    # GZip 压缩中间件
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 初始化引擎
    sync_engine = FileSyncEngine(workspace_dir)
    ws_manager = get_ws_manager()
    network_settings = NetworkSettings()
    network_settings.port = port

    # 文件变更回调 → WebSocket 推送
    async def on_file_change(event: SyncEvent):
        await ws_manager.notify_path_change(
            path=event.path,
            change_type=event.event_type,
            data=event.to_dict(),
        )
        # 同时推送文件树刷新
        if event.event_type in ("created", "deleted", "renamed"):
            await ws_manager.push_reload_filetree()

    sync_engine.set_change_callback(on_file_change)

    # 检查点事件回调 → WebSocket 推送（参考 Crush PubSub）
    def _on_checkpoint_event(event_type: str, payload: dict):
        """中间件事件 → WS 广播（同步→异步桥接）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        ws_manager.broadcast(event_type, 0, "", payload)
                    )
                )
            else:
                # 事件循环未运行时（罕见），直接忽略
                pass
        except Exception:
            pass

    # 延迟导入，避免循环依赖
    try:
        from ..middleware.shadow_checkpoint import CheckpointMiddleware
        CheckpointMiddleware.on_event(_on_checkpoint_event)
    except Exception:
        pass

    # 将引擎挂到 app.state
    app.state.sync_engine = sync_engine
    app.state.ws_manager = ws_manager
    app.state.network_settings = network_settings
    app.state.host = host
    app.state.port = port
    app.state.workspace_dir = workspace_dir
    app.state.start_time = time.time()
    app.state.local_ip = get_local_ip()
    app.state.tunnel_manager = get_tunnel_manager()
    app.state.jupyter_process = None
    app.state.jupyter_port = 8888
    app.state.jupyter_url = None
    app.state._exec_proc = None

    # ─── 鉴权中间件（OPTIONS 已由 cors_middleware 在之前处理）──────
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        # 静态文件和非 API 路由直接放行（让前端页面能加载）
        if not path.startswith("/api/"):
            return await call_next(request)
        # 公开 API 端点和 tunnel 放行
        if path in PUBLIC_ENDPOINTS or path.startswith("/api/tunnel/"):
            return await call_next(request)
        config = load_api_config()
        if not await check_auth(request, config):
            logger.warning(f"AUTH FAIL {request.method} {path} client={request.client.host if request.client else '?'} auth={request.headers.get('authorization','(none)')[:80]}")
            return JSONResponse(
                status_code=401,
                content={"code": 401, "msg": "未授权访问，请提供有效的 Token 或授权码", "data": None},
            )
        return await call_next(request)

    # ─── 公开端点 ────────────────────────────────────────────

    @app.get("/api/system/authInfo")
    async def auth_info(request: Request):
        """返回鉴权信息（客户端判断是否需要登录 + 工作区授权状态）"""
        client_host = request.client.host if request.client else "127.0.0.1"
        local = client_host in ("127.0.0.1", "::1", "localhost")
        config = load_api_config()
        auth_codes = _get_all_auth_codes(config)
        workspaces = config.get("workspaces", [])
        session_token = request.cookies.get("ts2_session", "")
        session_code = _get_session_code(session_token) if session_token else ""
        api_token = config.get("api_token", "")
        ws_access = []
        for ws in workspaces:
            ws_code = ws.get("auth_code", "")
            ws_resolved = str(Path(ws["path"]).resolve()) if ws.get("path") else ""
            accessible = local
            if not accessible and session_code:
                accessible = (session_code == ws_code) or (session_code == api_token)
            if not accessible and session_token and ws_resolved:
                accessible = _session_has_workspace(session_token, ws_resolved)
            ws_access.append({
                "name": ws.get("name", ""),
                "path": ws.get("path", ""),
                "accessible": accessible,
            })
        return ok({
            "needAuth": not local and bool(auth_codes or config.get("api_token")),
            "local": local,
            "hasAuthCode": bool(auth_codes),
            "hasToken": bool(config.get("api_token")),
            "hasSourceAuth": bool(config.get("source_auth_code")),
            "workspaceAccess": ws_access,
        })

    @app.post("/api/system/loginAuth")
    async def login_auth(request: Request):
        """远程登录：验证授权码和/或 token（与逻辑），创建服务端 session"""
        body = await request.json()
        code = body.get("code", "")
        token = body.get("token", "")
        config = load_api_config()
        api_token = config.get("api_token", "")
        auth_codes = _get_all_auth_codes(config)
        need_token = bool(api_token)
        need_code = bool(auth_codes)

        # 频率限制（本地免检）
        client_host = request.client.host if request.client else "unknown"
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            if not _check_rate_limit(f"login:{client_host}"):
                return err(429, "登录尝试过于频繁，请稍后再试")

        # 与逻辑验证
        token_ok = (not need_token) or (token and token == api_token)
        code_ok = (not need_code) or (code and code in auth_codes)

        if not (token_ok and code_ok):
            if need_token and need_code:
                return err(401, "需要同时提供正确的 Token 和授权码")
            if need_token:
                return err(401, "Token 错误")
            return err(401, "授权码错误")

        # 验证通过，创建 session
        session_code = token if (token and token == api_token) else code
        session_token = _create_session(session_code)
        # 标记已认证的工作区
        for ws in config.get("workspaces", []):
            if ws.get("path"):
                if not need_code or ws.get("auth_code") == code:
                    _session_add_workspace(session_token, str(Path(ws["path"]).resolve()))
        # 如果用 token 登录，放行所有工作区
        if token and token == api_token:
            for ws in config.get("workspaces", []):
                if ws.get("path"):
                    _session_add_workspace(session_token, str(Path(ws["path"]).resolve()))

        response = JSONResponse(content=ok(data={"needToken": need_token, "needCode": need_code}))
        response.set_cookie(key="ts2_session", value=session_token, httponly=True, samesite="lax")
        return response

    @app.post("/api/system/sourceAuth")
    async def source_auth(request: Request):
        """验证源码授权码，成功后在 session 中标记"""
        body = await request.json()
        code = body.get("code", "")
        config = load_api_config()
        source_code = config.get("source_auth_code", "")
        if not source_code:
            return ok(data={"sourceAuthed": True})
        if code == source_code:
            session_token = request.cookies.get("ts2_session", "")
            if session_token:
                sess = _sessions.get(session_token)
                if sess:
                    sess["source_authed"] = True
            else:
                # 无 session 时创建一个
                session_token = _create_session(code)
                _sessions[session_token]["source_authed"] = True
            response = JSONResponse(content=ok(data={"sourceAuthed": True}))
            if not request.cookies.get("ts2_session"):
                response.set_cookie(key="ts2_session", value=session_token, httponly=True, samesite="lax")
            return response
        return err(403, "源码授权码错误")

    @app.post("/api/system/logoutAuth")
    async def logout_auth(request: Request):
        """登出：删除服务端 session"""
        session_token = request.cookies.get("ts2_session", "")
        if session_token:
            _delete_session(session_token)
        response = JSONResponse(content=ok())
        response.delete_cookie("ts2_session")
        return response

    @app.post("/api/system/reloadConfig")
    async def reload_config():
        """重新加载配置（无需重启服务）"""
        config = load_api_config()
        return ok({"token": config.get("api_token", "")}, "配置已重新加载")

    @app.get("/api/system/workspaces")
    async def system_workspaces():
        """返回可用工作区列表（不含敏感字段）"""
        config = load_api_config()
        workspaces = config.get("workspaces", [])
        safe = []
        for ws in workspaces:
            safe.append({k: v for k, v in ws.items() if k != "auth_code"})
        return ok(data=safe)

    @app.post("/api/system/switchWorkspace")
    async def switch_workspace(req: Request):
        """切换当前工作区（热切换 sync_engine.root），同时校验工作区授权"""
        body = await req.json()
        ws_path = body.get("path", "")
        ws_code = body.get("code", "")
        if not ws_path or not Path(ws_path).exists():
            return err(400, f"工作区路径不存在: {ws_path}")
        if not check_path_access(ws_path, "read"):
            return err(403, "无权访问该工作区")

        config = load_api_config()
        api_token = config.get("api_token", "")

        # Authorization header token（API 客户端）
        auth_header = req.headers.get("authorization", "")
        token_valid = False
        if auth_header.startswith(("Token ", "Bearer ")):
            header_token = auth_header.split(" ", 1)[1]
            if header_token == api_token and api_token:
                token_valid = True

        # 查找目标工作区
        target_ws = None
        for ws in config.get("workspaces", []):
            if Path(ws["path"]).resolve() == Path(ws_path).resolve():
                target_ws = ws
                break

        # 鉴权：token 放行 / 无 auth_code 放行 / session 已认证过 / 传入正确 code
        session_token = req.cookies.get("ts2_session", "")
        resolved = str(Path(ws_path).resolve())
        known_ws = _session_has_workspace(session_token, resolved) if session_token else False

        if target_ws:
            need_check = bool(target_ws.get("auth_code", ""))
            if need_check and not token_valid and not known_ws:
                if ws_code != target_ws["auth_code"]:
                    return err(403, f"授权码错误，无权访问工作区「{target_ws.get('name', '')}」")
                if session_token:
                    _session_add_workspace(session_token, resolved)
        elif not token_valid and not known_ws:
            return err(403, "无权访问该工作区")

        app.state.workspace_dir = ws_path
        app.state.sync_engine = FileSyncEngine(ws_path)
        app.state.sync_engine.set_change_callback(on_file_change)
        logger.info(f"Switched workspace to {ws_path}")

        # 更新 session cookie
        resp = ok(msg=f"已切换到: {ws_path}")
        response = JSONResponse(content=resp)
        if ws_code and not session_token:
            session_token = _create_session(ws_code)
            _session_add_workspace(session_token, resolved)
            response.set_cookie(key="ts2_session", value=session_token, httponly=True, samesite="lax")
        return response

    # ─── 工具函数 ────────────────────────────────────────────

    def ok(data: Any = None, msg: str = "") -> dict:
        return {"code": 0, "msg": msg, "data": data}

    def err(code: int = -1, msg: str = "") -> dict:
        return {"code": code, "msg": msg, "data": None}

    # ─── Vue SPA 挂载（必须在 catch-all 路由之前）─────────────
    static_dir = Path(__file__).parent / "static"
    web_dist = Path(__file__).parent / "web" / "dist"
    if web_dist.exists():
        # 挂载 /app 的静态资源（js/css/images 等）
        app.mount("/app/assets", StaticFiles(directory=str(web_dist / "assets")), name="app-assets")

        # SPA fallback: /app, /app/, /app/xxx 路径返回 index.html
        @app.get("/app", response_class=HTMLResponse)
        @app.get("/app/", response_class=HTMLResponse)
        @app.get("/app/{spa_path:path}", response_class=HTMLResponse)
        async def app_spa(spa_path: str = ""):
            """Vue SPA fallback — 所有 /app 路径返回 index.html"""
            # 如果请求的是实际存在的文件（有扩展名且在 dist 中），直接返回文件
            if spa_path and "." in spa_path.split("/")[-1]:
                file_path = web_dist / spa_path
                if file_path.exists() and file_path.is_file():
                    return FileResponse(file_path)
            index_file = web_dist / "index.html"
            if index_file.exists():
                return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
            return HTMLResponse(content="<h1>Vue SPA not found</h1>", status_code=404)

    # ─── 首页 ─────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>TS2 Server</h1><p>Frontend not found</p>")

    # ─── 系统 API ────────────────────────────────────────────

    @app.post("/api/system/version")
    @app.get("/api/system/version")
    async def system_version():
        return ok(data={
            "version": "1.0.0",
            "runtime": "python",
            "port": app.state.port,
            "local_ip": app.state.local_ip,
            "network": app.state.network_settings.to_dict(),
        })

    # ─── 网络设置 API（参考思源笔记网络配置）──────────────

    @app.post("/api/system/getNetworkSettings")
    async def get_network_settings():
        """获取网络设置"""
        ns: NetworkSettings = app.state.network_settings
        access_info = check_network_access(ns.port)
        return ok(data={
            "settings": ns.to_dict(),
            "access": access_info,
        })

    @app.post("/api/system/setNetworkSettings")
    async def set_network_settings(req: Request):
        """更新网络设置"""
        ns: NetworkSettings = app.state.network_settings
        body = await req.json()

        if "allow_lan" in body:
            ns.allow_lan = bool(body["allow_lan"])
        if "allow_public_network" in body:
            ns.allow_public_network = bool(body["allow_public_network"])
        if "allow_usb" in body:
            ns.allow_usb = bool(body["allow_usb"])

        ns.save()
        return ok(data=ns.to_dict())

    @app.post("/api/system/configureFirewall")
    async def api_configure_firewall(req: Request):
        """配置防火墙规则（参考思源笔记自动配置防火墙）"""
        body = await req.json()
        allow = body.get("allow", True)
        port = body.get("port", app.state.port)

        success, message = configure_firewall(port, allow)

        if success:
            ns: NetworkSettings = app.state.network_settings
            ns.firewall_configured = allow
            ns.save()

        return ok(data={"success": success, "message": message})

    @app.post("/api/system/setNetworkPrivate")
    async def api_set_network_private():
        """将网络配置文件设为专用（参考思源笔记自动设置网络类别）"""
        success, message = set_network_profile_private()
        return ok(data={"success": success, "message": message})

    @app.post("/api/system/checkNetworkAccess")
    async def api_check_network_access():
        """检查网络访问状态"""
        port = app.state.port
        access_info = check_network_access(port)
        return ok(data=access_info)

    # ─── FRP 隧道 API ───────────────────────────────────────

    @app.get("/api/tunnel/status")
    async def tunnel_status():
        """获取 frp 隧道状态"""
        tm: "TunnelManager" = app.state.tunnel_manager
        return ok(data=tm.get_status())

    @app.post("/api/tunnel/start")
    async def tunnel_start():
        """启动 frp 隧道"""
        tm: "TunnelManager" = app.state.tunnel_manager
        result = tm.start()
        if result.get("success"):
            return ok(data=result)
        return err(msg=result.get("message", "启动失败"))

    @app.post("/api/tunnel/stop")
    async def tunnel_stop():
        """停止 frp 隧道"""
        tm: "TunnelManager" = app.state.tunnel_manager
        result = tm.stop()
        return ok(data=result)

    @app.post("/api/tunnel/restart")
    async def tunnel_restart():
        """重启 frp 隧道"""
        tm: "TunnelManager" = app.state.tunnel_manager
        result = tm.restart()
        if result.get("success"):
            return ok(data=result)
        return err(msg=result.get("message", "重启失败"))

    @app.get("/api/tunnel/settings")
    async def tunnel_settings_get():
        """获取 frp 隧道配置"""
        tm: "TunnelManager" = app.state.tunnel_manager
        return ok(data=tm.get_settings())

    @app.post("/api/tunnel/settings")
    async def tunnel_settings_update(req: Request):
        """更新 frp 隧道配置"""
        tm: "TunnelManager" = app.state.tunnel_manager
        body = await req.json()
        # 敏感字段过滤（不返回完整 token）
        result = tm.update_settings(**body)
        # 隐藏 token 前缀
        if result.get("token"):
            result["token_preview"] = result["token"][:4] + "****"
        return ok(data=result)

    @app.post("/api/tunnel/bootProgress")
    async def system_boot_progress():
        return ok(data={"progress": 100, "details": "TS2 Server is ready"})

    @app.post("/api/system/currentTime")
    async def system_current_time():
        return ok(data={"time": time.time(), "date": time.strftime("%Y-%m-%d %H:%M:%S")})

    @app.get("/api/system/stats")
    async def system_stats():
        engine: FileSyncEngine = app.state.sync_engine
        return ok(data={
            "workspace": str(engine.workspace_dir),
            "file_stats": engine.get_file_stats(),
            "ws_sessions": app.state.ws_manager.get_session_count(),
            "uptime": time.time() - app.state.start_time,
            "local_ip": app.state.local_ip,
        })

    @app.get("/api/system/health")
    async def system_health():
        return {
            "status": "ok",
            "version": "1.0.0",
            "uptime": time.time() - app.state.start_time,
            "workspace": app.state.workspace_dir,
            "features": ["rag", "terminal", "jupyter", "sync"],
        }

    # ─── JupyterLab 管理 API ──────────────────────────────

    @app.post("/api/system/jupyterStart")
    async def jupyter_start():
        """启动 JupyterLab 服务（后台异步，不阻塞主服务）"""
        proc = app.state.jupyter_process
        if proc and proc.poll() is None:
            return ok(data={"starting": False, "url": app.state.jupyter_url})
        port = app.state.jupyter_port
        try:
            def _launch():
                p = subprocess.Popen(
                    [sys.executable, "-m", "jupyter", "lab", "--no-browser",
                     f"--port={port}", "--notebook-dir", app.state.workspace_dir,
                     "--LabApp.token=", "--LabApp.password="],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                app.state.jupyter_process = p
            threading.Thread(target=_launch, daemon=True).start()
            app.state.jupyter_url = f"http://localhost:{port}/lab"
            return ok(data={"starting": True, "url": app.state.jupyter_url})
        except FileNotFoundError:
            return err(msg="JupyterLab 未安装，请执行: pip install jupyterlab")
        except Exception as e:
            return err(msg=f"启动 JupyterLab 失败: {e}")

    @app.post("/api/system/jupyterStop")
    async def jupyter_stop():
        """停止 JupyterLab 服务"""
        proc = app.state.jupyter_process
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        app.state.jupyter_process = None
        app.state.jupyter_url = None
        return ok(data={"running": False})

    @app.get("/api/system/jupyterStatus")
    async def jupyter_status():
        """获取 JupyterLab 运行状态"""
        proc = app.state.jupyter_process
        running = proc is not None and proc.poll() is None
        return ok(data={"running": running, "url": app.state.jupyter_url})

    @app.post("/api/system/jupyterWaitReady")
    async def jupyter_wait_ready():
        """轮询等待 JupyterLab HTTP 服务就绪（最多 30s）"""
        port = app.state.jupyter_port
        for i in range(30):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", port), timeout=2)
                writer.write(b"GET /lab HTTP/1.0\r\n\r\n")
                await reader.read(64)
                writer.close()
                break
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(1)
        else:
            return err(msg="JupyterLab 启动超时")
        app.state.jupyter_url = f"http://localhost:{port}/lab"
        return ok(data={"ready": True, "url": app.state.jupyter_url})

    @app.post("/api/system/openInJupyter")
    async def open_in_jupyter(req: Request):
        """获取在 JupyterLab 中打开文件的 URL"""
        body = await req.json()
        file_path = body.get("path", "")
        rel_path = os.path.relpath(file_path, app.state.workspace_dir) if file_path else ""
        jupyter_base = app.state.jupyter_url or f"http://localhost:{app.state.jupyter_port}/lab"
        url = f"{jupyter_base}/tree/{rel_path}" if rel_path else jupyter_base
        return ok(data={"url": url, "file": rel_path})

    @app.get("/api/system/openWithOptions")
    async def open_with_options():
        """获取可用的 IDE 打开方式列表"""
        options = [
            {"id": "jupyter", "name": "JupyterLab", "icon": "📓", "desc": "Python/数据科学"},
            {"id": "builtin", "name": "内置编辑器", "icon": "📝", "desc": "Vditor/纯文本"},
            {"id": "external", "name": "外部编辑器", "icon": "💻", "desc": "系统默认应用"},
            {"id": "vscode", "name": "VS Code", "icon": "💻", "desc": "vscode://file/{path}"},
            {"id": "cursor", "name": "Cursor", "icon": "🖥️", "desc": "cursor://file/{path}"},
        ]
        return ok(data={"options": options})

    # ─── 文件 API（参考思源笔记 /api/file/*）──────────────

    # ─── 独立管线：文件IO、数据查询、Agent 各自独立线程池 ──────
    _file_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="file-io")
    _data_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="data")
    _agent_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent")
    _push_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="push")

    async def _run_file(method, *args):
        """文件IO管线：读文件、写文件、目录操作、同步"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_file_executor, method, *args)

    async def _run_data(method, *args):
        """数据管线：任务、课程、项目、书签等轻量查询"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_data_executor, method, *args)

    def _build_multimodal_message(text: str, attachments: Optional[List[Dict[str, str]]] = None):
        """构建多模态消息：纯文本或 content parts 列表。

        如果有附件，返回 OpenAI 格式的 content parts：
        [{"type":"text",...}, {"type":"image_url",...}, {"type":"video_url",...}]
        如果没有附件，返回纯文本字符串。
        """
        if not attachments:
            return text
        from ..media_utils import build_multimodal_content
        return build_multimodal_content(text, attachments)

    async def _run_agent(method, *args, **kwargs):
        """Agent管线：LLM调用、工具执行（支持关键字参数传递 session_id）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_agent_executor, lambda: method(*args, **kwargs))

    async def _run_push(method, *args):
        """推送管线：聚合推送数据，独立于数据查询"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_push_executor, method, *args)

    @app.post("/api/file/getFile")
    async def file_get(req: FileReadRequest):
        """获取文件内容"""
        if not check_path_access(req.path, "read"):
            return err(403, "路径不在允许的读取目录中")
        engine: FileSyncEngine = app.state.sync_engine
        result = await _run_file(engine.get_file, req.path)
        if result is None:
            return err(code=404, msg=f"File not found: {req.path}")
        content, entry = result
        return ok(data={"content": content, "entry": entry.to_dict()})

    @app.post("/api/file/putFile")
    async def file_put(req: FileWriteRequest):
        """创建或更新文件"""
        if not check_path_access(req.path, "write"):
            return err(403, "路径不在允许的写入目录中")
        engine: FileSyncEngine = app.state.sync_engine
        entry = await _run_file(engine.put_file, req.path, req.content)
        if entry is None:
            return err(msg=f"Failed to write file: {req.path}")
        return ok(data=entry.to_dict())

    @app.post("/api/file/removeFile")
    async def file_remove(req: FileRemoveRequest):
        """删除文件"""
        if not check_path_access(req.path, "write"):
            return err(403, "路径不在允许的写入目录中")
        engine: FileSyncEngine = app.state.sync_engine
        if await _run_file(engine.remove_file, req.path):
            return ok()
        return err(msg=f"Failed to remove: {req.path}")

    @app.post("/api/file/renameFile")
    async def file_rename(req: FileRenameRequest):
        """重命名/移动文件"""
        if not check_path_access(req.old_path, "write") or not check_path_access(req.new_path, "write"):
            return err(403, "路径不在允许的写入目录中")
        engine: FileSyncEngine = app.state.sync_engine
        if await _run_file(engine.rename_file, req.old_path, req.new_path):
            return ok()
        return err(msg=f"Failed to rename: {req.old_path} -> {req.new_path}")

    @app.post("/api/file/readDir")
    async def file_read_dir(req: DirReadRequest):
        """读取目录内容"""
        if not check_path_access(req.path, "read"):
            return err(403, "路径不在允许的读取目录中")
        engine: FileSyncEngine = app.state.sync_engine
        entries = await _run_file(engine.read_dir, req.path)
        return ok(data=[e.to_dict() for e in entries])

    @app.post("/api/file/createDir")
    async def file_create_dir(req: DirCreateRequest):
        """创建目录"""
        if not check_path_access(req.path, "write"):
            return err(403, "路径不在允许的写入目录中")
        engine: FileSyncEngine = app.state.sync_engine
        if await _run_file(engine.create_dir, req.path):
            return ok()
        return err(msg=f"Failed to create dir: {req.path}")

    @app.post("/api/file/scanTree")
    async def file_scan_tree(req: ScanRequest):
        """扫描文件树"""
        if not check_path_access(req.subdir, "read"):
            return err(403, "路径不在允许的读取目录中")
        engine: FileSyncEngine = app.state.sync_engine
        entries = await _run_file(engine.scan_file_tree, req.subdir)
        return ok(data=[e.to_dict() for e in entries])

    @app.post("/api/file/search")
    async def file_search(req: SearchRequest):
        """搜索文件"""
        if not check_path_access(req.subdir, "read"):
            return err(403, "路径不在允许的读取目录中")
        engine: FileSyncEngine = app.state.sync_engine
        results = await _run_file(engine.search_files, req.query, req.subdir)
        return ok(data=[e.to_dict() for e in results])

    # ─── 文件下载 API ───────────────────────────────────────

    @app.get("/api/file/download/{file_path:path}")
    @app.head("/api/file/download/{file_path:path}")
    async def file_download(file_path: str, preview: bool = False, request: Request = None):
        """下载文件（二进制流，支持手机端下载），HEAD 请求仅检查文件是否存在（FastAPI 自动剥离 body）

        preview=True 时返回 inline 响应（浏览器内预览，不触发下载）
        """
        if not check_path_access(file_path, "read"):
            # 不在工作区目录：尝试资源索引放行（须鉴权）
            if not _is_resource_path(file_path, app.state.workspace_dir):
                raise HTTPException(status_code=403, detail="路径不在允许的读取目录中")
            if not await check_auth(request, load_api_config()):
                raise HTTPException(status_code=403, detail="未授权，请提供有效 token 或授权码")
        engine: FileSyncEngine = app.state.sync_engine
        # 支持绝对路径（如资源索引中的外部路径），直接检查是否存在
        p = Path(file_path)
        if p.is_absolute():
            abs_path = p.resolve()
        else:
            abs_path = engine._absolute_path(file_path)

        if not abs_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if abs_path.is_dir():
            # 目录打包为 zip
            import tempfile
            import zipfile
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            try:
                with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for f in abs_path.rglob("*"):
                        if f.is_file() and not engine._should_ignore(f):
                            arcname = str(f.relative_to(abs_path))
                            zf.write(f, arcname)
                return FileResponse(
                    tmp.name,
                    media_type="application/zip",
                    filename=f"{abs_path.name}.zip",
                )
            except Exception as e:
                os.unlink(tmp.name)
                raise HTTPException(status_code=500, detail=str(e))

        # 单文件下载
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml",
            ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".md": "text/markdown", ".txt": "text/plain", ".rmd": "text/plain",
            ".py": "text/x-python", ".json": "application/json",
            ".html": "text/html", ".htm": "text/html", ".css": "text/css",
            ".zip": "application/zip", ".tar": "application/x-tar",
            ".gz": "application/gzip",
        }
        media_type = mime_map.get(abs_path.suffix.lower(), "application/octet-stream")
        if preview:
            return FileResponse(abs_path, media_type=media_type)
        return FileResponse(abs_path, media_type=media_type, filename=abs_path.name)

    # ─── 文件上传 API（支持手机端上传）─────────────────────

    @app.post("/api/file/upload")
    async def file_upload(
        files: List[UploadFile] = File(...),
        path: str = Form(""),
    ):
        """
        上传文件（multipart/form-data，支持多文件）

        - files: 上传的文件列表
        - path: 目标目录（相对于工作区，默认根目录）
        """
        if not check_path_access(path if path else os.getcwd(), "write"):
            return err(403, "路径不在允许的写入目录中")
        engine: FileSyncEngine = app.state.sync_engine
        target_dir = engine._absolute_path(path) if path else engine.workspace_dir

        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)

        uploaded = []
        for upload_file in files:
            # 安全检查
            target_path = target_dir / upload_file.filename
            try:
                target_path.relative_to(engine.workspace_dir)
            except ValueError:
                continue

            # 写入文件
            try:
                content = await upload_file.read()
                target_path.write_bytes(content)

                rel_path = engine._relative_path(target_path)
                stat = target_path.stat()
                entry_dict = {
                    "path": rel_path,
                    "name": target_path.name,
                    "is_dir": False,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "ext": target_path.suffix.lower(),
                }
                uploaded.append(entry_dict)

                # 触发变更通知
                if sync_engine._on_change_callback:
                    event = SyncEvent(
                        event_type="created",
                        path=rel_path,
                        timestamp=time.time(),
                        size=stat.st_size,
                    )
                    asyncio.create_task(sync_engine._on_change_callback(event))

            except Exception as e:
                logger.error(f"Upload write error: {e}")

        return ok(data={
            "uploaded": uploaded,
            "count": len(uploaded),
            "target_dir": path,
        })

    # ─── 批量下载 API ──────────────────────────────────────

    @app.post("/api/file/batchDownload")
    async def file_batch_download(request: Request):
        """批量下载文件（打包为 zip）"""
        body = await request.json()
        paths: List[str] = body.get("paths", [])
        for p in paths:
            if not check_path_access(p, "read"):
                return err(403, f"路径不在允许的读取目录中: {p}")

        if not paths:
            return err(msg="No files specified")

        engine: FileSyncEngine = app.state.sync_engine
        import tempfile
        import zipfile

        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        try:
            with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
                for rel_path in paths:
                    abs_path = engine._absolute_path(rel_path)
                    if abs_path.exists() and abs_path.is_file():
                        zf.write(abs_path, abs_path.name)
            return FileResponse(
                tmp.name,
                media_type="application/zip",
                filename=f"ts2_download_{int(time.time())}.zip",
            )
        except Exception as e:
            os.unlink(tmp.name)
            raise HTTPException(status_code=500, detail=str(e))

    # ─── Office 转 PDF API ─────────────────────────────────

    @app.post("/api/file/convert-to-pdf")
    async def file_convert_to_pdf(request: Request):
        """将 Office 文件（docx/xlsx/pptx）转换为 PDF 并返回文件"""
        body = await request.json()
        file_path: str = body.get("file_path", "")
        if not file_path:
            return err(msg="缺少 file_path")

        abs_path = sync_engine._absolute_path(file_path)
        if not os.path.isfile(abs_path):
            return err(msg=f"文件不存在: {file_path}")

        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in (".docx", ".xlsx", ".pptx"):
            return err(msg=f"不支持的文件类型: {ext}")

        try:
            pdf_path = await asyncio.get_event_loop().run_in_executor(
                None, _convert_office_to_pdf, str(abs_path)
            )
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=os.path.splitext(os.path.basename(abs_path))[0] + ".pdf",
            )
        except Exception as e:
            return err(msg=f"转换失败: {e}")

    # ─── 同步 API（参考思源笔记 /api/sync/*）──────────────

    @app.post("/api/sync/performSync")
    async def sync_perform(req: SyncRequest):
        """
        执行增量同步（参考 better-sync syncHandler + siyuan-android syncData）
        
        流程：
        1. 检查同步锁（参考 siyuan-android syncing 互斥）
        2. 扫描变更（参考 better-sync scanDirectory）
        3. 冲突检测（参考 better-sync detectConflict）
        4. 创建冲突副本（参考 better-sync createConflictFile）
        5. 通过 WebSocket 推送变更
        6. 记录同步历史（参考 better-sync SyncHistory）
        """
        engine: FileSyncEngine = app.state.sync_engine

        # 检查同步锁（参考 siyuan-android: if (syncing) return）
        if engine.get_sync_status() == SyncStatus.InProgress:
            return ok(data={
                "synced": 0,
                "changes": [],
                "status": "InProgress",
                "message": "Sync already in progress",
                "direction": req.direction,
                "timestamp": time.time(),
            })

        # 执行增量同步
        changes, status = engine.perform_incremental_sync(mobile_switch=req.mobile_switch)

        # 转换变更列表为 API 格式
        api_changes = []
        for c in changes:
            change_dict = {
                "type": c.type,
                "path": c.path,
                "hash": c.hash,
                "size": c.size,
                "operation": c.operation,
            }
            if c.conflict_path:
                change_dict["conflict_path"] = c.conflict_path
            api_changes.append(change_dict)

        # 通过 WebSocket 推送变更
        if api_changes and hasattr(app.state, 'ws_manager'):
            for change in api_changes:
                await app.state.ws_manager.notify_path_change(
                    path=change["path"],
                    change_type=change["type"],
                    data=change,
                )
            if any(c["type"] in ("created", "deleted", "renamed", "conflict") for c in api_changes):
                await app.state.ws_manager.push_reload_filetree()

        return ok(data={
            "synced": len(api_changes),
            "changes": api_changes,
            "status": status.name,
            "conflicts": sum(1 for c in api_changes if c["type"] == "conflict"),
            "direction": req.direction,
            "mobile_switch": req.mobile_switch,
            "timestamp": time.time(),
        })

    @app.post("/api/sync/getSyncInfo")
    async def sync_info():
        """获取同步状态（参考 better-sync 同步状态管理）"""
        engine: FileSyncEngine = app.state.sync_engine
        return ok(data={
            "workspace": str(engine.workspace_dir),
            "file_stats": engine.get_file_stats(),
            "watching": engine._watching,
            "sync_status": engine.get_sync_status().name,
            "last_sync_time": engine._last_sync_time,
            "sync_history": engine.get_sync_history(limit=10),
        })

    @app.post("/api/sync/getSyncHistory")
    async def sync_history(request: Request):
        """获取同步历史（参考 better-sync SyncHistory）"""
        engine: FileSyncEngine = app.state.sync_engine
        body = await request.json()
        limit = body.get("limit", 20)
        return ok(data=engine.get_sync_history(limit=limit))

    @app.post("/api/sync/startWatch")
    async def sync_start_watch():
        """启动文件监听"""
        engine: FileSyncEngine = app.state.sync_engine
        await engine.start_watching()
        return ok(data={"watching": True})

    @app.post("/api/sync/stopWatch")
    async def sync_stop_watch():
        """停止文件监听"""
        engine: FileSyncEngine = app.state.sync_engine
        await engine.stop_watching()
        return ok(data={"watching": False})

    # ─── 通知 API（参考思源笔记 /api/notification/*）─────

    @app.post("/api/notification/pushMsg")
    async def push_msg(request: Request):
        """推送消息"""
        body = await request.json()
        msg = body.get("msg", "")
        timeout = body.get("timeout", 5000)
        await app.state.ws_manager.push_msg(msg, timeout)
        return ok()

    # ─── 代码执行 ─────────────────────────────────────────

    @app.post("/api/exec/run")
    async def exec_run(request: Request):
        """执行代码，返回 stdout/stderr/exit_code，支持停止"""
        body = await request.json()
        language = body.get("language", "python")
        code = body.get("code", "")
        file_path = body.get("file_path", "")

        JAVA_NEEDS_COMPILE = True  # Java 需 javac + java 两步

        lang_map = {
            "python": [sys.executable],
            "py": [sys.executable],
            "python3": [sys.executable],
            "javascript": ["node"],
            "js": ["node"],
            "typescript": ["npx", "--yes", "tsx"],
            "ts": ["npx", "--yes", "tsx"],
            "r": ["Rscript"],
            "bash": ["bash"],
            "sh": ["sh"],
            "powershell": ["powershell", "-NoProfile", "-Command"],
            "pwsh": ["pwsh", "-NoProfile", "-Command"],
            "cmd": ["cmd", "/c"],
            "java": ["javac"],
            "kt": ["kotlinc"],
            "kotlin": ["kotlinc"],
            "c": ["gcc"],
            "cpp": ["g++"],
            "go": ["go", "run"],
            "rs": ["rustc"],
            "rust": ["rustc"],
        }

        cmd_base = lang_map.get(language, [sys.executable])

        # Build execution environment: force UTF-8 everywhere
        exec_env = os.environ.copy()
        exec_env["PYTHONUNBUFFERED"] = "1"
        exec_env["PYTHONIOENCODING"] = "utf-8"
        if "LANG" not in exec_env:
            exec_env["LANG"] = "C.UTF-8"
        conda_prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("CONDA_EXE", "")
        if conda_prefix:
            conda_base = Path(conda_prefix).parent if "CONDA_EXE" in os.environ else Path(conda_prefix)
            scripts_dir = str(conda_base / "Scripts")
            condabin_dir = str(conda_base / "condabin")
            if "PATH" in exec_env:
                exec_env["PATH"] = f"{scripts_dir};{condabin_dir};{exec_env['PATH']}"

        # ── 编译型语言辅助函数 ──
        async def _run_java(source_path: Path, cwd: str):
            """javac 编译 → java 运行"""
            class_dir = source_path.parent
            class_name = source_path.stem
            compile_proc = await asyncio.create_subprocess_exec(
                "javac", "-d", str(class_dir), str(source_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd, env=exec_env,
            )
            cout, cerr = await compile_proc.communicate()
            if compile_proc.returncode != 0:
                return cout + b"\n[Java Compile Error]\n" + cerr
            run_proc = await asyncio.create_subprocess_exec(
                "java", "-cp", str(class_dir), class_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd, env=exec_env,
            )
            rout, rerr = await run_proc.communicate()
            return rout + b"\n" + rerr

        COMPILE_LANGS = {"java", "c", "cpp", "c++", "rs", "rust", "go"}

        try:
            if file_path:
                full_path = (Path(app.state.workspace_dir) / file_path).resolve()
                if language in COMPILE_LANGS:
                    display_cmd = f"{cmd_base[0]} {file_path}"
                else:
                    display_cmd = f"{cmd_base[0]} {file_path}"
                if language == "java":
                    combined = await _run_java(full_path, str(full_path.parent))
                    stdout = combined.decode("utf-8", errors="replace")
                    return ok(data={"exit_code": 0, "stdout": stdout, "stderr": "", "command": display_cmd})
                proc = await asyncio.create_subprocess_exec(
                    *cmd_base, str(full_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=full_path.parent,
                    env=exec_env,
                )
            elif code:
                if language in ("powershell", "pwsh"):
                    proc = await asyncio.create_subprocess_exec(
                        *cmd_base, code,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=app.state.workspace_dir,
                        env=exec_env,
                    )
                    display_cmd = f"{cmd_base[0]} <inline>"
                elif language in ("bash", "sh", "cmd"):
                    proc = await asyncio.create_subprocess_exec(
                        *cmd_base, code,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=app.state.workspace_dir,
                        env=exec_env,
                    )
                    display_cmd = f"{cmd_base[0]} <inline>"
                elif language in COMPILE_LANGS:
                    # Write code to temp file, then compile & run
                    tmp_dir = Path(app.state.workspace_dir) / ".ts2_data" / "exec_tmp"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    ext_map = {"java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
                               "rs": ".rs", "rust": ".rs", "go": ".go"}
                    suffix = ext_map.get(language, ".java")
                    tmp_file = tmp_dir / f"exec_{uuid.uuid4().hex}{suffix}"
                    tmp_file.write_text(code, encoding="utf-8")
                    if language == "java":
                        combined = await _run_java(tmp_file, str(app.state.workspace_dir))
                        stdout = combined.decode("utf-8", errors="replace")
                        return ok(data={"exit_code": 0, "stdout": stdout, "stderr": "", "command": f"{cmd_base[0]} <code>"})
                    display_cmd = f"{cmd_base[0]} <code>"
                    proc = await asyncio.create_subprocess_exec(
                        *cmd_base, str(tmp_file),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=app.state.workspace_dir,
                        env=exec_env,
                    )
                else:
                    # Write code to a UTF-8 temp file to avoid GBK cmdline corruption
                    tmp_dir = Path(app.state.workspace_dir) / ".ts2_data" / "exec_tmp"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    ext_map = {"python": ".py", "javascript": ".js", "js": ".js",
                               "typescript": ".ts", "ts": ".ts", "r": ".R",
                               "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
                               "rs": ".rs", "rust": ".rs", "go": ".go"}
                    suffix = ext_map.get(language, ".py")
                    tmp_file = tmp_dir / f"exec_{uuid.uuid4().hex}{suffix}"
                    tmp_file.write_text(code, encoding="utf-8")
                    proc = await asyncio.create_subprocess_exec(
                        *cmd_base, str(tmp_file),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=app.state.workspace_dir,
                        env=exec_env,
                    )
                    display_cmd = f"{cmd_base[0]} <code>"
            else:
                return ok(data={"exit_code": -1, "stdout": "", "stderr": "No code or file_path provided"})

            # Kill previous, store current
            if app.state._exec_proc and app.state._exec_proc.returncode is None:
                app.state._exec_proc.terminate()
            app.state._exec_proc = proc

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.CancelledError:
                if proc.returncode is None:
                    proc.terminate()
                raise

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Clean up temp file
            if not file_path and code and language not in ("powershell", "pwsh", "bash", "sh", "cmd"):
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass

            if proc.returncode is None:
                exit_code = -1
            else:
                exit_code = proc.returncode

            return ok(data={
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "command": display_cmd,
            })
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.terminate()
            return ok(data={"exit_code": -1, "stdout": "", "stderr": "Execution timed out (>120s)"})
        except asyncio.CancelledError:
            return ok(data={"exit_code": -2, "stdout": "", "stderr": "Execution cancelled"})
        except FileNotFoundError:
            return ok(data={"exit_code": -1, "stdout": "", "stderr": f"Interpreter not found: {cmd_base[0]}"})
        except Exception as e:
            return ok(data={"exit_code": -1, "stdout": "", "stderr": str(e)})

    @app.post("/api/exec/stop")
    async def exec_stop():
        """强制停止当前正在执行的代码"""
        proc = app.state._exec_proc
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
            return ok(msg="已停止")
        return ok(msg="没有正在执行的任务")

    # ─── WebSocket（参考思源笔记 /ws）─────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket 端点

        连接参数：
        - app: 应用ID
        - id: 会话ID
        - type: 客户端类型 (main, filetree, editor, sync)

        消息格式（参考思源笔记）：
        {"cmd": "...", "reqId": 1, "param": {...}}

        事件推送格式：
        {"cmd": "...", "code": 0, "msg": "", "data": {...}}
        """
        # 鉴权检查
        config = load_api_config()
        if not _check_ws_auth(websocket, config):
            await websocket.close(code=4001, reason="未授权")
            return

        await websocket.accept()

        # 解析连接参数
        app_id = websocket.query_params.get("app", str(uuid.uuid4())[:8])
        session_id = websocket.query_params.get("id", str(uuid.uuid4())[:8])
        client_type = websocket.query_params.get("type", "main")

        # 注册会话
        session = await app.state.ws_manager.add_session(
            websocket, app_id, session_id, client_type
        )

        try:
            # 发送连接成功事件
            await websocket.send_text(_json_dumps({
                "cmd": "connected",
                "code": 0,
                "msg": "",
                "data": {
                    "app_id": app_id,
                    "session_id": session_id,
                    "type": client_type,
                }
            }, ensure_ascii=False))

            # 消息循环
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = _json_loads(raw)
                    cmd = msg.get("cmd", "")
                    req_id = msg.get("reqId", 0)
                    param = msg.get("param", {})

                    # 处理命令
                    result = await _handle_ws_command(
                        app, cmd, param, app_id, session_id
                    )
                    result["reqId"] = req_id
                    await websocket.send_text(_json_dumps(result, ensure_ascii=False))

                except json.JSONDecodeError:
                    await websocket.send_text(_json_dumps({
                        "cmd": "error", "code": -1,
                        "msg": "Invalid JSON", "reqId": 0
                    }))
                except Exception as e:
                    logger.error(f"WS command error: {e}")
                    await websocket.send_text(_json_dumps({
                        "cmd": "error", "code": -1,
                        "msg": str(e), "reqId": msg.get("reqId", 0)
                    }))

        except WebSocketDisconnect:
            pass
        finally:
            await app.state.ws_manager.remove_session(app_id, session_id)

    # ─── 终端 WebSocket（xterm.js）────────────────────────

    @app.websocket("/api/terminal")
    async def terminal_ws(websocket: WebSocket):
        """xterm.js 终端 WebSocket — 桥接 shell stdio（使用 PTY 支持交互式 shell）"""
        # 鉴权检查
        config = load_api_config()
        if not _check_ws_auth(websocket, config):
            await websocket.close(code=4001, reason="未授权")
            return

        await websocket.accept()
        loop = asyncio.get_event_loop()

        # ── 检测 conda 环境 ──
        conda_prefix = os.environ.get("CONDA_PREFIX", "")
        conda_base = os.environ.get("CONDA_EXE", "")
        if conda_base:
            conda_base = str(Path(conda_base).parent)
        elif conda_prefix:
            conda_base = str(Path(conda_prefix).parent)
        # 使用 cmd.exe 而非 pwsh.exe — cmd 原生支持 conda.bat
        shell = "cmd.exe" if os.name == "nt" else "bash"
        proc_env = os.environ.copy()
        if conda_base:
            scripts_dir = os.path.join(conda_base, "Scripts")
            condabin_dir = os.path.join(conda_base, "condabin")
            proc_env["PATH"] = f"{scripts_dir};{condabin_dir};{proc_env.get('PATH', '')}"

        # ── 尝试 PTY 路径 ──
        import winpty as _winpty
        pty = None
        def _create_pty():
            p = _winpty.PTY(100, 30)
            p.spawn(shell)
            return p
        try:
            pty = await loop.run_in_executor(None, _create_pty)
        except Exception:
            pty = None

        if pty is not None:
            async def _run(method, *args):
                return await loop.run_in_executor(None, getattr(pty, method), *args)

            async def read_pty():
                while True:
                    try:
                        raw = await _run("read", 4096)
                        if raw:
                            await websocket.send_bytes(raw.encode("utf-8", errors="replace"))
                    except EOFError:
                        break
                    except Exception:
                        break

            async def write_pty():
                while True:
                    try:
                        msg = await websocket.receive_text()
                        if msg.startswith("__resize__"):
                            parts = msg.split(":")
                            if len(parts) == 3:
                                try:
                                    await _run("set_size", int(parts[1]), int(parts[2]))
                                except Exception:
                                    pass
                            continue
                        if await _run("isalive"):
                            await _run("write", msg)
                    except WebSocketDisconnect:
                        break
                    except Exception:
                        break

            tasks = [asyncio.create_task(read_pty()), asyncio.create_task(write_pty())]
            try:
                await asyncio.gather(*tasks)
            finally:
                for t in tasks:
                    t.cancel()
                try:
                    if await _run("isalive"):
                        await _run("write", "\x03")
                except Exception:
                    pass
            return

        # ── Fallback: 无 PTY ──
        try:
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=app.state.workspace_dir,
                env=proc_env,
            )
        except FileNotFoundError:
            shell = "powershell.exe" if os.name == "nt" else "sh"
            proc = await asyncio.create_subprocess_exec(
                shell,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=app.state.workspace_dir,
                env=proc_env,
            )

        async def read_proc():
            while True:
                data = await proc.stdout.read(4096)
                if not data:
                    break
                try:
                    await websocket.send_bytes(data)
                except Exception:
                    break

        async def write_proc():
            while True:
                try:
                    msg = await websocket.receive_text()
                    if msg == "__resize__":
                        continue
                    if proc.stdin and not proc.stdin.is_closing():
                        proc.stdin.write(msg.encode())
                        await proc.stdin.drain()
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        tasks = [asyncio.create_task(read_proc()), asyncio.create_task(write_proc())]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()

    async def _handle_ws_command(app, cmd: str, param: dict,
                                  app_id: str, session_id: str) -> dict:
        """处理 WebSocket 命令"""
        engine: FileSyncEngine = app.state.sync_engine
        manager: WebSocketManager = app.state.ws_manager

        if cmd == "subscribe":
            path = param.get("path", "")
            await manager.subscribe(app_id, session_id, path)
            return {"cmd": "subscribe", "code": 0, "data": {"path": path}}

        elif cmd == "unsubscribe":
            path = param.get("path", "")
            await manager.unsubscribe(app_id, session_id, path)
            return {"cmd": "unsubscribe", "code": 0, "data": {"path": path}}

        elif cmd == "getFile":
            fpath = param.get("path", "")
            if not check_path_access(fpath, "read"):
                return {"cmd": "getFile", "code": 403, "msg": "路径不在允许的读取目录中"}
            result = engine.get_file(fpath)
            if result:
                content, entry = result
                return {"cmd": "getFile", "code": 0, "data": {"content": content, "entry": entry.to_dict()}}
            return {"cmd": "getFile", "code": 404, "msg": "File not found"}

        elif cmd == "putFile":
            fpath = param.get("path", "")
            if not check_path_access(fpath, "write"):
                return {"cmd": "putFile", "code": 403, "msg": "路径不在允许的写入目录中"}
            entry = engine.put_file(fpath, param.get("content", ""))
            if entry:
                return {"cmd": "putFile", "code": 0, "data": entry.to_dict()}
            return {"cmd": "putFile", "code": -1, "msg": "Write failed"}

        elif cmd == "readDir":
            dpath = param.get("path", "")
            if dpath and not check_path_access(dpath, "read"):
                return {"cmd": "readDir", "code": 403, "msg": "路径不在允许的读取目录中"}
            entries = engine.read_dir(dpath)
            return {"cmd": "readDir", "code": 0, "data": [e.to_dict() for e in entries]}

        elif cmd == "search":
            entries = engine.search_files(param.get("query", ""), param.get("subdir", ""))
            return {"cmd": "search", "code": 0, "data": [e.to_dict() for e in entries]}

        elif cmd == "ping":
            return {"cmd": "pong", "code": 0, "data": {"time": time.time()}}

        else:
            return {"cmd": cmd, "code": -1, "msg": f"Unknown command: {cmd}"}

    # ─── 数据 API（任务、书签、项目、课程）──────────────────

    # ── 同步辅助函数（在线程池中执行，避免阻塞事件循环）──

    def _read_tasks_data(workspace_dir: str):
        """同步读取任务数据（在线程池中执行）"""
        tb_path = Path(workspace_dir) / "task_board.json"
        if tb_path.exists():
            try:
                content = tb_path.read_text(encoding="utf-8")
                return _json_loads(content)
            except Exception as e:
                logger.warning(f"Read task_board.json failed: {e}")

        db_path = Path(workspace_dir) / "data" / "automation.db"
        if not db_path.exists():
            return []
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            task_table = None
            for t in tables:
                if 'task' in t.lower() or 'todo' in t.lower():
                    task_table = t
                    break
            if not task_table and tables:
                task_table = tables[0]
            if task_table:
                cursor.execute(f"SELECT * FROM {task_table} LIMIT 500")
                rows = cursor.fetchall()
                result = [dict(r) for r in rows]
            else:
                result = []
            conn.close()
            return result
        except Exception as e:
            return []

    def _read_bookmarks_data(workspace_dir: str):
        """同步读取书签数据"""
        bm_path = Path(workspace_dir) / "bookmarks.json"
        if not bm_path.exists():
            return []
        try:
            content = bm_path.read_text(encoding="utf-8")
            return _json_loads(content)
        except Exception:
            return []

    def _add_bookmark_data(workspace_dir: str, bookmark: dict):
        """同步添加书签"""
        bm_path = Path(workspace_dir) / "bookmarks.json"
        bookmarks = _read_bookmarks_data(workspace_dir)
        if "id" not in bookmark or not bookmark["id"]:
            bookmark["id"] = str(uuid.uuid4())
        bookmarks.append(bookmark)
        bm_path.write_text(_json_dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")
        return bookmark, None

    def _delete_bookmark_data(workspace_dir: str, bookmark_id: str):
        """同步删除书签"""
        bm_path = Path(workspace_dir) / "bookmarks.json"
        bookmarks = _read_bookmarks_data(workspace_dir)
        filtered = [b for b in bookmarks if b.get("id") != bookmark_id and b.get("url") != bookmark_id]
        if len(filtered) == len(bookmarks):
            return None, "未找到该书签"
        bm_path.write_text(_json_dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        return None, None

    def _read_projects_data(workspace_dir: str):
        """同步读取项目列表"""
        workspace = Path(workspace_dir)
        projects = []
        for p in workspace.rglob(".ts2_project.json"):
            try:
                data = _json_loads(p.read_text(encoding="utf-8"))
                proj_dir = p.parent
                file_count = sum(1 for f in proj_dir.rglob("*") if f.is_file() and not f.name.startswith("."))
                data["file_count"] = file_count
                data["path"] = str(p.parent.relative_to(workspace)).replace("\\", "/")
                projects.append(data)
            except Exception:
                continue
        root_proj = workspace / ".ts2_project.json"
        if root_proj.exists():
            try:
                data = _json_loads(root_proj.read_text(encoding="utf-8"))
                data["path"] = ""
                projects.insert(0, data)
            except Exception:
                pass
        return projects

    def _read_projects_json(workspace_dir: str):
        """读取 projects.json（集中式项目列表，用于同步）"""
        pj_path = Path(workspace_dir) / "projects.json"
        if not pj_path.exists():
            return []
        try:
            return _json_loads(pj_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _read_courses_data(workspace_dir: str):
        """同步读取课程数据（多源合并，同 course_tracker.py 逻辑）"""
        excluded = {"courses_structured_progress.json", "resource_index.json",
                     "courses_structured_progress.bak.json"}
        scan_dirs = [Path(workspace_dir), Path.home() / ".ts2", Path(workspace_dir).parent]
        all_courses = []
        seen_keys = set()
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for f in sorted(scan_dir.glob("*.json")):
                if f.name in excluded or "_progress" in f.name:
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    data = _json_loads(content)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                courses = data.get("courses")
                if not isinstance(courses, list) or not courses:
                    continue
                for course in courses:
                    cid = course.get("note_id", "")
                    title = (course.get("course_title", "") or "").strip()
                    key = cid or title
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                    if isinstance(course.get("lessons"), list):
                        for lesson in course["lessons"]:
                            if "estimated_hours" not in lesson or lesson["estimated_hours"] is None:
                                lesson["estimated_hours"] = 1.0
                            elif not isinstance(lesson["estimated_hours"], (int, float)):
                                try:
                                    lesson["estimated_hours"] = float(lesson["estimated_hours"])
                                except (ValueError, TypeError):
                                    lesson["estimated_hours"] = 1.0
                    all_courses.append(course)
        return {"courses": all_courses, "metadata": {"source_count": len(scan_dirs)}}

    def _read_agent_status(workspace_dir: str):
        """同步读取 Agent 状态"""
        agent = _get_web_agent(workspace_dir)
        if agent is None:
            return {"available": False, "tools": 0}
        return {
            "available": True,
            "tools": len(agent.tools),
            "model": agent.config.model_id or "unknown",
            "messages": len(agent.messages),
        }

    def _read_projects_dir(workspace_dir: str, req_path: str):
        """同步读取项目目录内容"""
        workspace = Path(workspace_dir)
        target = workspace / req_path if req_path else workspace

        try:
            target.resolve().relative_to(workspace.resolve())
        except ValueError:
            return None, "Access denied: path outside workspace"

        if not target.exists() or not target.is_dir():
            return None, "Directory not found"

        entries = []
        try:
            for item in sorted(target.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue
                rel_path = str(item.relative_to(workspace)).replace("\\", "/")
                entry = {
                    "path": rel_path,
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "ext": item.suffix.lower() if item.suffix else "",
                }
                if not item.is_dir():
                    try:
                        stat = item.stat()
                        entry["size"] = stat.st_size
                        entry["modified"] = stat.st_mtime
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except PermissionError:
            return None, "Permission denied"

        return entries, None

    def _read_project_file(workspace_dir: str, req_path: str):
        """同步读取项目源代码文件内容"""
        workspace = Path(workspace_dir)
        target = workspace / req_path

        try:
            target.resolve().relative_to(workspace.resolve())
        except ValueError:
            return None, "Access denied: path outside workspace"

        if not target.exists() or not target.is_file():
            return None, "File not found"

        try:
            size = target.stat().st_size
            if size > 2 * 1024 * 1024:
                return None, "File too large (max 2MB)"
        except OSError:
            return None, "Cannot read file stats"

        try:
            content = target.read_text(encoding="utf-8")
            is_binary = False
        except UnicodeDecodeError:
            import base64
            raw = target.read_bytes()
            content = base64.b64encode(raw).decode("ascii")
            is_binary = True

        stat = target.stat()
        ext = target.suffix.lower()

        return {
            "path": req_path,
            "name": target.name,
            "content": content,
            "is_binary": is_binary,
            "size": stat.st_size,
            "ext": ext,
            "modified": stat.st_mtime,
        }, None

    def _write_project_file(workspace_dir: str, req_path: str, req_content: str):
        """同步写入项目源代码文件"""
        workspace = Path(workspace_dir)
        target = workspace / req_path

        try:
            target.resolve().relative_to(workspace.resolve())
        except ValueError:
            return None, "Access denied: path outside workspace"

        if ".." in req_path:
            return None, "Access denied: invalid path"

        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            target.write_text(req_content, encoding="utf-8")
            stat = target.stat()
            return {
                "path": req_path,
                "name": target.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }, None
        except (OSError, PermissionError) as e:
            return None, f"Write failed: {e}"

    def _update_task_data(workspace_dir: str, req_id: str, updates: dict):
        """同步更新任务"""
        tb_path = Path(workspace_dir) / "task_board.json"
        if not tb_path.exists():
            return None, "task_board.json not found"
        try:
            content = tb_path.read_text(encoding="utf-8")
            tasks = _json_loads(content)
        except Exception as e:
            return None, f"Read failed: {e}"

        updated = None
        for task in tasks:
            if task.get("id") == req_id:
                for key, value in updates.items():
                    if value is not None:
                        task[key] = value
                updated = task
                break

        if updated is None:
            return None, f"Task not found: {req_id}"

        try:
            tb_path.write_text(_json_dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, f"Write failed: {e}"

        return updated, None

    def _create_task_data(workspace_dir: str, new_task: dict):
        """同步创建任务"""
        tb_path = Path(workspace_dir) / "task_board.json"
        tasks = []
        if tb_path.exists():
            try:
                content = tb_path.read_text(encoding="utf-8")
                tasks = _json_loads(content)
            except Exception:
                tasks = []

        tasks.append(new_task)

        try:
            tb_path.write_text(_json_dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, f"Write failed: {e}"

        return new_task, None

    def _delete_task_data(workspace_dir: str, req_id: str):
        """同步删除任务"""
        tb_path = Path(workspace_dir) / "task_board.json"
        if not tb_path.exists():
            return None, "task_board.json not found"
        try:
            content = tb_path.read_text(encoding="utf-8")
            tasks = _json_loads(content)
        except Exception as e:
            return None, f"Read failed: {e}"

        original_len = len(tasks)
        tasks = [t for t in tasks if t.get("id") != req_id]
        if len(tasks) == original_len:
            return None, f"Task not found: {req_id}"

        try:
            tb_path.write_text(_json_dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, f"Write failed: {e}"

        return True, None

    def _read_course_progress(workspace_dir: str, course_id: str):
        """同步读取课程进度"""
        progress_path = Path(workspace_dir) / "data" / "progress" / f"{course_id}.json"
        if not progress_path.exists():
            return {}
        try:
            content = progress_path.read_text(encoding="utf-8")
            return _json_loads(content)
        except Exception:
            return {}

    def _update_lesson_status(workspace_dir: str, course_id: str, lesson_number: int, status: str):
        """同步更新课时状态"""
        progress_dir = Path(workspace_dir) / "data" / "progress"
        progress_path = progress_dir / f"{course_id}.json"

        progress_data = {}
        if progress_path.exists():
            try:
                content = progress_path.read_text(encoding="utf-8")
                progress_data = _json_loads(content)
            except Exception:
                progress_data = {}

        lessons = progress_data.get("lessons", {})
        lessons[str(lesson_number)] = status
        progress_data["lessons"] = lessons

        try:
            progress_dir.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(_json_dumps(progress_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, f"Write progress file failed: {e}"

        return progress_data, None

    # ── 数据 API 路由 ──

    @app.post("/api/data/tasks")
    async def data_tasks():
        """获取任务列表（优先从 task_board.json，回退到 automation.db）"""
        data = await _run_data(_read_tasks_data, app.state.workspace_dir)
        return ok(data=data)

    @app.post("/api/data/bookmarks")
    async def data_bookmarks():
        """获取书签数据"""
        data = await _run_data(_read_bookmarks_data, app.state.workspace_dir)
        return ok(data=data)

    @app.post("/api/data/projects")
    async def data_projects(request: Request):
        """获取项目列表"""
        if not _check_source_auth(request):
            return err(403, "源码浏览器需要单独授权，请输入源码授权码")
        data = await _run_data(_read_projects_data, app.state.workspace_dir)
        return ok(data=data)

    @app.post("/api/data/projects/readDir")
    async def data_projects_read_dir(req: DirReadRequest, request: Request):
        """读取项目目录内容（不受 EXPOSED_DIRS 限制）"""
        if not _check_source_auth(request):
            return err(403, "源码浏览器需要单独授权，请输入源码授权码")
        result, error = await _run_data(_read_projects_dir, app.state.workspace_dir, req.path)
        if error:
            if "Access denied" in error:
                return err(code=403, msg=error)
            if "not found" in error.lower():
                return err(code=404, msg=error)
            if "Permission" in error:
                return err(code=403, msg=error)
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/projects/readFile")
    async def data_projects_read_file(req: FileReadRequest, request: Request):
        """读取项目源代码文件内容（不受 EXPOSED_DIRS 限制）"""
        if not _check_source_auth(request):
            return err(403, "源码浏览器需要单独授权，请输入源码授权码")
        result, error = await _run_file(_read_project_file, app.state.workspace_dir, req.path)
        if error:
            if "Access denied" in error:
                return err(code=403, msg=error)
            if "not found" in error.lower():
                return err(code=404, msg=error)
            if "too large" in error.lower():
                return err(code=413, msg=error)
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/projects/writeFile")
    async def data_projects_write_file(req: FileWriteRequest, request: Request):
        """写入项目源代码文件（不受 EXPOSED_DIRS 限制）"""
        if not _check_source_auth(request, require_write=True):
            return err(403, "源码写入需要源码授权码")
        result, error = await _run_file(_write_project_file, app.state.workspace_dir, req.path, req.content)
        if error:
            if "Access denied" in error:
                return err(code=403, msg=error)
            if "Write failed" in error:
                return err(code=500, msg=error)
            return err(msg=error)
        return ok(data=result)

    # ─── RMD 编译工具 API ──────────────────────────────────────

    class KnitRmdRequest(BaseModel):
        path: str
        output_format: Optional[str] = "html_document"

    @app.post("/api/tools/knit-rmd")
    async def tools_knit_rmd(req: KnitRmdRequest):
        """编译 Rmd/Markdown 文件（参考 course_tracker._add_rmd_compile_buttons 方法）"""
        import subprocess
        workspace = Path(app.state.workspace_dir)
        rmd_path = (workspace / req.path).resolve()
        if not rmd_path.exists():
            return err(msg=f"文件不存在: {req.path}")
        ext = rmd_path.suffix.lower()
        if ext not in (".rmd", ".rmarkdown", ".md"):
            return err(msg=f"不支持的文件格式: {ext}")

        output_format = req.output_format or "html_document"
        # 使用 posix 路径，与 course_tracker 一致
        rmd_posix = rmd_path.as_posix()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["Rscript", "-e", f"rmarkdown::render('{rmd_posix}', output_format='{output_format}')"],
                    cwd=str(rmd_path.parent),
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300
                )
            )
            if result.returncode == 0:
                output_ext = {"pdf_document": ".pdf", "html_document": ".html", "word_document": ".docx",
                              "ioslides_presentation": ".html", "slidy_presentation": ".html",
                              "beamer_presentation": ".pdf"}.get(output_format, ".html")
                output_path = rmd_path.with_suffix(output_ext)
                rel_output = str(output_path.relative_to(workspace)) if output_path.exists() else None
                return ok(data={
                    "success": True,
                    "output_file": rel_output,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                })
            else:
                err_msg = (result.stderr or result.stdout or "未知错误")[:500]
                return ok(data={"success": False, "error": err_msg, "stdout": result.stdout, "stderr": result.stderr})
        except subprocess.TimeoutExpired:
            return ok(data={"success": False, "error": "编译超时 (超过5分钟)"})
        except Exception as e:
            return err(msg=f"编译失败: {e}")

    @app.get("/api/tools/rmd-files")
    async def tools_list_rmd_files():
        """列出所有 Rmd 文件"""
        try:
            from ..ws2_tools import NotesManager
            nm = NotesManager(Path(app.state.workspace_dir))
            if not nm.ready:
                return ok(data={"files": [], "courses": []})
            courses = nm.list_courses()
            all_files = []
            for course in courses:
                rmds = nm.list_rmd_files(course)
                for f in rmds:
                    all_files.append({"course": course, "filename": f, "path": f"notes/{course}/{f}"})
            return ok(data={"files": all_files, "courses": courses})
        except Exception as e:
            return ok(data={"files": [], "courses": [], "error": str(e)})

    @app.post("/api/data/courses")
    async def data_courses():
        """获取课程数据"""
        data = await _run_data(_read_courses_data, app.state.workspace_dir)
        return ok(data=data)

    # ─── 任务 CRUD API ──────────────────────────────────────

    @app.post("/api/data/tasks/update")
    async def task_update(req: TaskUpdateRequest):
        """更新任务（task_board.json）"""
        updates = {
            "title": req.title,
            "description": req.description,
            "due_date": req.due_date,
            "priority": req.priority,
            "status": req.status,
            "start_time": req.start_time,
            "duration": req.duration,
            "recurrence": req.recurrence,
        }
        updated, error = await _run_data(_update_task_data, app.state.workspace_dir, req.id, updates)
        if error:
            if "not found" in error.lower() and "task_board" not in error:
                return err(code=404, msg=error)
            return err(msg=error)
        return ok(data=updated)

    @app.post("/api/data/tasks/create")
    async def task_create(req: TaskCreateRequest):
        """创建任务（task_board.json）"""
        new_task = {
            "id": str(uuid.uuid4()),
            "title": req.title,
            "description": req.description,
            "due_date": req.due_date,
            "priority": req.priority,
            "status": req.status,
            "start_time": req.start_time,
            "duration": req.duration,
            "recurrence": req.recurrence,
        }
        result, error = await _run_data(_create_task_data, app.state.workspace_dir, new_task)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/tasks/delete")
    async def task_delete(req: TaskDeleteRequest):
        """删除任务（task_board.json）"""
        result, error = await _run_data(_delete_task_data, app.state.workspace_dir, req.id)
        if error:
            if "not found" in error.lower() and "task_board" not in error:
                return err(code=404, msg=error)
            return err(msg=error)
        return ok()

    # ─── 课程进度 API ──────────────────────────────────────

    @app.post("/api/data/courses/progress")
    async def course_progress(req: CourseProgressRequest):
        """获取课程进度（data/progress/{course_id}.json）"""
        data = await _run_data(_read_course_progress, app.state.workspace_dir, req.course_id)
        return ok(data=data)

    @app.post("/api/data/courses/lessonStatus")
    async def lesson_status(req: LessonStatusRequest):
        """更新课时状态（data/progress/{course_id}.json）"""
        result, error = await _run_data(_update_lesson_status, app.state.workspace_dir, req.course_id, req.lesson_number, req.status)
        if error:
            return err(msg=error)
        return ok(data=result)

    # ─── 课程表 API ──────────────────────────────────────────

    @app.get("/api/data/timetable")
    async def timetable_get():
        """获取所有课程表"""
        from ..automation.course_simulation import TimetablePersistence
        persistence = TimetablePersistence()
        timetables = persistence.load()
        result = {}
        for tid, tt in timetables.items():
            result[tid] = tt.to_dict()
        return ok(data=result)

    @app.post("/api/data/timetable/create")
    async def timetable_create(req: TimetableCreateRequest):
        """创建课程表"""
        from ..automation.course_simulation import Timetable, TimetablePersistence
        import uuid as _uuid
        persistence = TimetablePersistence()
        timetables = persistence.load()
        tt_id = f"tt_{_uuid.uuid4().hex[:8]}"
        new_tt = Timetable(
            timetable_id=tt_id,
            name=req.name,
            semester_start=req.semester_start,
            semester_end=req.semester_end,
            slots=[],
            enabled=len(timetables) == 0,  # 第一个自动启用
        )
        timetables[tt_id] = new_tt
        persistence.save(timetables)
        return ok(data=new_tt.to_dict())

    @app.post("/api/data/timetable/setActive")
    async def timetable_set_active(req: TimetableSetActiveRequest):
        """设置激活课程表"""
        from ..automation.course_simulation import TimetablePersistence
        persistence = TimetablePersistence()
        timetables = persistence.load()
        if req.timetable_id not in timetables:
            return err(msg="课程表不存在")
        for tid, tt in timetables.items():
            tt.enabled = (tid == req.timetable_id)
        persistence.save(timetables)
        return ok(data=timetables[req.timetable_id].to_dict())

    @app.post("/api/data/timetable/delete")
    async def timetable_delete(req: TimetableDeleteRequest):
        """删除课程表"""
        from ..automation.course_simulation import TimetablePersistence
        persistence = TimetablePersistence()
        timetables = persistence.load()
        if req.timetable_id not in timetables:
            return err(msg="课程表不存在")
        del timetables[req.timetable_id]
        persistence.save(timetables)
        return ok()

    @app.post("/api/data/timetable/slot/add")
    async def timetable_slot_add(req: TimetableSlotCreateRequest):
        """添加课时到课程表"""
        from ..automation.course_simulation import TimetableSlot, TimetablePersistence, COURSE_COLORS
        persistence = TimetablePersistence()
        timetables = persistence.load()
        # 找到目标课程表
        tt = None
        if req.timetable_id and req.timetable_id in timetables:
            tt = timetables[req.timetable_id]
        else:
            # 默认使用激活的课程表
            for t in timetables.values():
                if t.enabled:
                    tt = t
                    break
            if not tt and timetables:
                tt = next(iter(timetables.values()))
        if not tt:
            return err(msg="没有可用的课程表")
        # 自动分配颜色
        color = req.color
        if not color:
            existing_colors = {s.color for s in tt.slots if s.color}
            for c in COURSE_COLORS:
                if c not in existing_colors:
                    color = c
                    break
            if not color:
                color = COURSE_COLORS[len(tt.slots) % len(COURSE_COLORS)]
        slot = TimetableSlot(
            slot_id=f"slot_{uuid.uuid4().hex[:8]}",
            course_id=req.course_name,
            course_name=req.course_name,
            day_of_week=req.day_of_week,
            start_time=req.start_time,
            end_time=req.end_time,
            location=req.location,
            teacher=req.teacher,
            period_idx=req.period_idx,
            color=color,
        )
        tt.slots.append(slot)
        persistence.save(timetables)
        return ok(data=slot.to_dict())

    @app.post("/api/data/timetable/slot/delete")
    async def timetable_slot_delete(req: TimetableSlotDeleteRequest):
        """删除课时"""
        from ..automation.course_simulation import TimetablePersistence
        persistence = TimetablePersistence()
        timetables = persistence.load()
        # 找到包含该 slot 的课程表
        for tt in timetables.values():
            before = len(tt.slots)
            tt.slots = [s for s in tt.slots if s.slot_id != req.slot_id]
            if len(tt.slots) < before:
                persistence.save(timetables)
                return ok()
        return err(msg="课时不存在")

    # ─── 关键路径检测 API ─────────────────────────────────────────

    @app.get("/api/tasks/critical-path")
    async def tasks_critical_path():
        """
        关键路径检测（Critical Path Method）
        基于任务的依赖关系和持续时间，计算关键路径
        返回：关键路径上的任务序列、项目最短完成时间、各任务的时间裕度
        """
        workspace_dir = app.state.workspace_dir
        tasks = _read_tasks_data(workspace_dir) or []

        if not tasks:
            return ok(data={"critical_path": [], "project_duration": 0, "tasks_schedule": []})

        # 构建任务图
        task_map = {}
        for t in tasks:
            tid = t.get("id")
            if not tid:
                continue
            task_map[tid] = {
                "id": tid,
                "title": t.get("title", ""),
                "status": t.get("status", ""),
                "priority": t.get("priority", ""),
                "due_date": t.get("due_date", ""),
                "duration": t.get("duration", 60),  # 默认 60 分钟
                "dependencies": t.get("dependencies", []),  # 前置任务 ID 列表
                "updated_at": t.get("updated_at", ""),
            }

        # 拓扑排序 + 前向传播（计算最早开始/结束时间）
        from collections import defaultdict, deque

        in_degree = defaultdict(int)
        graph = defaultdict(list)  # adjacency: dep -> [successors]
        for tid, t in task_map.items():
            deps = t["dependencies"]
            if not isinstance(deps, list):
                deps = []
                t["dependencies"] = deps
            in_degree.setdefault(tid, 0)
            for dep_id in deps:
                if dep_id in task_map:
                    graph[dep_id].append(tid)
                    in_degree[tid] = in_degree.get(tid, 0) + 1

        # 拓扑排序
        queue = deque([tid for tid in task_map if in_degree.get(tid, 0) == 0])
        topo_order = []
        while queue:
            tid = queue.popleft()
            topo_order.append(tid)
            for succ in graph.get(tid, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # 如果有环，跳过有环的任务
        if len(topo_order) != len(task_map):
            # 移除不在拓扑序中的任务（有环）
            valid_ids = set(topo_order)
        else:
            valid_ids = set(task_map.keys())

        # 前向传播：计算最早开始时间(ES)和最早结束时间(EF)
        es = {}  # Earliest Start
        ef = {}  # Earliest Finish
        for tid in topo_order:
            t = task_map[tid]
            deps = [d for d in t["dependencies"] if d in valid_ids]
            if not deps:
                es[tid] = 0
            else:
                es[tid] = max(ef.get(d, 0) for d in deps)
            ef[tid] = es[tid] + t["duration"]

        # 项目总工期
        project_duration = max(ef.values()) if ef else 0

        # 后向传播：计算最迟开始时间(LS)和最迟结束时间(LF)
        ls = {}  # Latest Start
        lf = {}  # Latest Finish
        for tid in reversed(topo_order):
            t = task_map[tid]
            successors = [s for s in graph.get(tid, []) if s in valid_ids]
            if not successors:
                lf[tid] = project_duration
            else:
                lf[tid] = min(ls.get(s, project_duration) for s in successors)
            ls[tid] = lf[tid] - t["duration"]

        # 计算时间裕度（Total Float）
        schedule = []
        critical_path = []
        for tid in topo_order:
            t = task_map[tid]
            total_float = ls.get(tid, 0) - es.get(tid, 0)
            is_critical = total_float == 0 and t["status"] != "已完成"
            entry = {
                "id": tid,
                "title": t["title"],
                "status": t["status"],
                "priority": t["priority"],
                "due_date": t["due_date"],
                "duration": t["duration"],
                "dependencies": t["dependencies"],
                "earliest_start": es.get(tid, 0),
                "earliest_finish": ef.get(tid, 0),
                "latest_start": ls.get(tid, 0),
                "latest_finish": lf.get(tid, 0),
                "total_float": total_float,
                "is_critical": is_critical,
            }
            schedule.append(entry)
            if is_critical:
                critical_path.append(entry)

        return ok(data={
            "critical_path": critical_path,
            "project_duration": project_duration,
            "tasks_schedule": schedule,
            "total_tasks": len(task_map),
            "critical_tasks": len(critical_path),
        })

    # ─── 分页笔记 API ──────────────────────────────────────

    def _read_notebooks(workspace_dir: str):
        """读取所有笔记本列表"""
        nb_dir = Path(workspace_dir) / "data" / "notebooks"
        if not nb_dir.exists():
            return []
        result = []
        for f in sorted(nb_dir.glob("*.json")):
            try:
                nb = json.loads(f.read_text(encoding="utf-8"))
                nb["_file"] = f.name
                result.append(nb)
            except:
                pass
        return result

    def _read_notebook(workspace_dir: str, notebook_id: str):
        """读取单个笔记本"""
        nb_path = Path(workspace_dir) / "data" / "notebooks" / f"{notebook_id}.json"
        if not nb_path.exists():
            return None
        return json.loads(nb_path.read_text(encoding="utf-8"))

    def _write_notebook(workspace_dir: str, notebook_id: str, data: dict):
        """写入笔记本"""
        nb_dir = Path(workspace_dir) / "data" / "notebooks"
        nb_dir.mkdir(parents=True, exist_ok=True)
        nb_path = nb_dir / f"{notebook_id}.json"
        data["updatedAt"] = int(time.time() * 1000)
        nb_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def _delete_notebook(workspace_dir: str, notebook_id: str):
        """删除笔记本"""
        nb_path = Path(workspace_dir) / "data" / "notebooks" / f"{notebook_id}.json"
        if nb_path.exists():
            nb_path.unlink()
            return True
        return False

    @app.get("/api/notebooks")
    async def list_notebooks():
        data = await _run_data(_read_notebooks, app.state.workspace_dir)
        return ok(data=data)

    @app.get("/api/notebooks/{notebook_id}")
    async def get_notebook(notebook_id: str):
        data = await _run_data(_read_notebook, app.state.workspace_dir, notebook_id)
        if data is None:
            return ok(data=None, msg="笔记本不存在")
        return ok(data=data)

    @app.post("/api/notebooks/{notebook_id}")
    async def save_notebook(notebook_id: str, req: dict):
        data = await _run_data(_write_notebook, app.state.workspace_dir, notebook_id, req)
        return ok(data=data)

    @app.delete("/api/notebooks/{notebook_id}")
    async def del_notebook(notebook_id: str):
        result = await _run_data(_delete_notebook, app.state.workspace_dir, notebook_id)
        return ok(data={"deleted": result})

    # ─── 课程系统增强 API（移植自 CourseSystem/ResourceMgr/WorkflowLogger）──

    # ─── 增量同步 API ──────────────────────────────────────

    def _sync_items(local_items: list, server_items: list, id_field: str = "id") -> dict:
        """
        通用增量去重同步算法：
        - 按 id 匹配，按 updated_at 判断新旧
        - 返回：pull（服务器更新的，客户端需要拉取）、push（客户端更新的，服务器需要接受）、conflicts（双方都修改了）
        - 本地有但服务器没有 → push（新增）
        - 服务器有但本地没有 → pull（新增）
        - 都有，服务器更新 → pull
        - 都有，本地更新 → push
        - 都有，同时更新 → conflict
        """
        from datetime import datetime as _dt

        def _parse_time(t) -> float:
            if not t:
                return 0.0
            if isinstance(t, (int, float)):
                return float(t)
            try:
                return _dt.strptime(str(t), "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                try:
                    return _dt.strptime(str(t), "%Y-%m-%dT%H:%M:%S").timestamp()
                except Exception:
                    return 0.0

        local_map = {item.get(id_field): item for item in local_items if item.get(id_field)}
        server_map = {item.get(id_field): item for item in server_items if item.get(id_field)}

        pull = []   # 客户端需要拉取的（服务器更新或新增）
        push = []   # 服务器需要接受的（客户端更新或新增）
        conflicts = []  # 冲突的

        # 服务器有但本地没有 → pull
        for sid, sitem in server_map.items():
            if sid not in local_map:
                pull.append(sitem)

        # 本地有但服务器没有 → push
        for lid, litem in local_map.items():
            if lid not in server_map:
                push.append(litem)

        # 都有 → 比较 updated_at
        for lid in local_map:
            if lid not in server_map:
                continue
            litem = local_map[lid]
            sitem = server_map[lid]
            l_time = _parse_time(litem.get("updated_at"))
            s_time = _parse_time(sitem.get("updated_at"))

            if l_time == s_time:
                continue  # 无变化
            elif s_time > l_time:
                pull.append(sitem)  # 服务器更新
            elif l_time > s_time:
                push.append(litem)  # 客户端更新
            else:
                # 时间相同但内容不同
                conflicts.append({"local": litem, "server": sitem})

        return {"pull": pull, "push": push, "conflicts": conflicts}

    def _apply_sync_push(workspace_dir: str, data_type: str, items: list) -> dict:
        """应用客户端推送的变更到服务器"""
        if data_type == "tasks":
            tb_path = Path(workspace_dir) / "task_board.json"
            if not tb_path.exists():
                return None, "task_board.json not found"
            try:
                tasks = _json_loads(tb_path.read_text(encoding="utf-8"))
            except Exception as e:
                return None, f"Read failed: {e}"

            task_map = {t.get("id"): t for t in tasks}
            updated_count = 0
            created_count = 0
            for item in items:
                item_id = item.get("id")
                if item_id in task_map:
                    # 更新
                    task_map[item_id].update(item)
                    updated_count += 1
                else:
                    # 新增
                    tasks.append(item)
                    created_count += 1

            tb_path.write_text(_json_dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"updated": updated_count, "created": created_count}, None

        elif data_type == "bookmarks":
            bm_path = Path(workspace_dir) / "bookmarks.json"
            try:
                bookmarks = _json_loads(bm_path.read_text(encoding="utf-8")) if bm_path.exists() else []
            except Exception:
                bookmarks = []

            bm_map = {b.get("id"): b for b in bookmarks}
            updated_count = 0
            created_count = 0
            for item in items:
                item_id = item.get("id")
                if item_id in bm_map:
                    bm_map[item_id].update(item)
                    updated_count += 1
                else:
                    bookmarks.append(item)
                    created_count += 1

            bm_path.write_text(_json_dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"updated": updated_count, "created": created_count}, None

        elif data_type == "projects":
            pj_path = Path(workspace_dir) / "projects.json"
            try:
                projects = _json_loads(pj_path.read_text(encoding="utf-8")) if pj_path.exists() else []
            except Exception:
                projects = []

            pj_map = {p.get("id"): p for p in projects}
            updated_count = 0
            created_count = 0
            for item in items:
                item_id = item.get("id")
                if item_id in pj_map:
                    pj_map[item_id].update(item)
                    updated_count += 1
                else:
                    projects.append(item)
                    created_count += 1

            pj_path.write_text(_json_dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"updated": updated_count, "created": created_count}, None

        return None, f"Unknown data type: {data_type}"

    @app.post("/api/sync/compare")
    async def sync_compare(req: Request):
        """
        增量同步对比：客户端发送本地数据，服务器返回差异
        body: { "tasks": [...], "bookmarks": [...] }
        返回: { "tasks": { "pull": [...], "push": [...], "conflicts": [...] }, "bookmarks": {...} }
        """
        body = await req.json()
        result = {}

        workspace_dir = app.state.workspace_dir

        for data_type in ["tasks", "bookmarks", "projects"]:
            local_items = body.get(data_type, [])
            if data_type == "tasks":
                server_items = _read_tasks_data(workspace_dir) or []
            elif data_type == "bookmarks":
                server_items = _read_bookmarks_data(workspace_dir) or []
            elif data_type == "projects":
                server_items = _read_projects_json(workspace_dir) or []
            else:
                continue

            result[data_type] = _sync_items(local_items, server_items)

        return ok(data=result)

    @app.post("/api/sync/push")
    async def sync_push(req: Request):
        """
        推送客户端变更到服务器
        body: { "tasks": [...], "bookmarks": [...], "projects": [...] }
        """
        body = await req.json()
        result = {}

        for data_type in ["tasks", "bookmarks", "projects"]:
            items = body.get(data_type, [])
            if not items:
                result[data_type] = {"updated": 0, "created": 0}
                continue
            applied, error = await _run_data(_apply_sync_push, app.state.workspace_dir, data_type, items)
            if error:
                result[data_type] = {"error": error}
            else:
                result[data_type] = applied

        return ok(data=result)

    @app.post("/api/sync/full")
    async def sync_full(req: Request):
        """
        完整同步：对比 + 自动推送 + 返回最终数据
        1. 对比差异
        2. 自动推送客户端更新的项
        3. 返回服务器最终数据（包含推送后的结果）
        """
        body = await req.json()
        workspace_dir = app.state.workspace_dir
        result = {}

        for data_type in ["tasks", "bookmarks", "projects"]:
            local_items = body.get(data_type, [])
            if data_type == "tasks":
                server_items = _read_tasks_data(workspace_dir) or []
            elif data_type == "bookmarks":
                server_items = _read_bookmarks_data(workspace_dir) or []
            elif data_type == "projects":
                server_items = _read_projects_json(workspace_dir) or []
            else:
                continue

            diff = _sync_items(local_items, server_items)

            # 自动推送客户端更新的项（push 列表）
            if diff["push"]:
                applied, error = _apply_sync_push(workspace_dir, data_type, diff["push"])
                if not error:
                    # 重新读取服务器数据
                    if data_type == "tasks":
                        server_items = _read_tasks_data(workspace_dir) or []
                    elif data_type == "bookmarks":
                        server_items = _read_bookmarks_data(workspace_dir) or []
                    elif data_type == "projects":
                        server_items = _read_projects_json(workspace_dir) or []

            result[data_type] = {
                "pull": diff["pull"],
                "conflicts": diff["conflicts"],
                "server_data": server_items,
                "pushed": len(diff["push"]),
            }

        return ok(data=result)

    # ─── 课程系统增强 API（移植自 CourseSystem/ResourceMgr/WorkflowLogger）──

    def _get_review_due(workspace_dir: str, course_id: str):
        """同步获取待复习课时列表"""
        progress_path = Path(workspace_dir) / "data" / "progress" / f"{course_id}.json"
        if not progress_path.exists():
            return []
        try:
            progress_data = _json_loads(progress_path.read_text(encoding="utf-8"))
            rs = progress_data.get("review_schedule", {})
            from datetime import datetime, timedelta
            now = datetime.now()
            due = []
            for ln_str, info in rs.items():
                try:
                    next_r = datetime.fromisoformat(info.get("next_review", ""))
                    if next_r <= now:
                        due.append({
                            "lesson_number": int(ln_str),
                            "workload": info.get("workload", 0),
                            "interval_days": info.get("interval_days", 7),
                            "review_count": info.get("review_count", 0),
                            "overdue_days": (now - next_r).days,
                        })
                except Exception:
                    pass
            due.sort(key=lambda x: -x["workload"])
            return due
        except Exception:
            return []

    def _mark_review_done(workspace_dir: str, course_id: str, lesson_number: int, status: str):
        """同步标记复习完成"""
        from datetime import datetime, timedelta
        progress_dir = Path(workspace_dir) / "data" / "progress"
        progress_path = progress_dir / f"{course_id}.json"
        progress_data = {}
        if progress_path.exists():
            try:
                progress_data = _json_loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                progress_data = {}

        rs = progress_data.setdefault("review_schedule", {})
        ln_str = str(lesson_number)
        if ln_str in rs:
            info = rs[ln_str]
            workload = info.get("workload", 5)
            review_count = info.get("review_count", 0) + 1
            info["review_count"] = review_count
            info["last_reviewed"] = datetime.now().isoformat()
            if workload <= 5: base_days = 7
            elif workload <= 15: base_days = 4
            elif workload <= 30: base_days = 2
            else: base_days = 1
            interval_days = max(1, int(base_days * (1.5 ** min(review_count, 5))))
            info["interval_days"] = interval_days
            info["next_review"] = (datetime.now() + timedelta(days=interval_days)).isoformat()
        else:
            rs[ln_str] = {
                "workload": 5, "interval_days": 7,
                "next_review": (datetime.now() + timedelta(days=7)).isoformat(),
                "last_reviewed": datetime.now().isoformat(), "review_count": 1,
            }

        try:
            progress_dir.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(_json_dumps(progress_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, str(e)
        return progress_data, None

    def _update_review_schedule(workspace_dir: str, course_id: str, lesson_number: int, status: str):
        """同步更新复习调度"""
        from datetime import datetime, timedelta
        progress_dir = Path(workspace_dir) / "data" / "progress"
        progress_path = progress_dir / f"{course_id}.json"
        progress_data = {}
        if progress_path.exists():
            try:
                progress_data = _json_loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                progress_data = {}

        rs = progress_data.setdefault("review_schedule", {})
        ln_str = str(lesson_number)
        workload = status if isinstance(status, (int, float)) else 5
        now = datetime.now()
        if workload <= 0: interval_days = 14
        elif workload <= 5: interval_days = 7
        elif workload <= 15: interval_days = 4
        elif workload <= 30: interval_days = 2
        else: interval_days = 1
        review_count = rs.get(ln_str, {}).get("review_count", 0)
        interval_days = max(1, int(interval_days * (1.5 ** min(review_count, 5))))
        rs[ln_str] = {
            "workload": workload, "interval_days": interval_days,
            "next_review": (now + timedelta(days=interval_days)).isoformat(),
            "last_reviewed": now.isoformat(), "review_count": review_count,
        }
        try:
            progress_dir.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(_json_dumps(progress_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return None, str(e)
        return progress_data, None

    def _get_courses_stats(workspace_dir: str):
        """同步获取课程系统全局统计"""
        cs_path = Path(workspace_dir) / "courses_structured.json"
        if not cs_path.exists():
            return {}
        try:
            data = _json_loads(cs_path.read_text(encoding="utf-8"))
            courses = data.get("courses", [])
            from collections import Counter
            total_hours = sum(c.get("total_hours", 0) or 0 for c in courses)
            total_lessons = sum(len(c.get("lessons", [])) for c in courses)
            domain_dist = dict(Counter(c.get("domain", "UNKNOWN") for c in courses))
            progress_dir = Path(workspace_dir) / "data" / "progress"
            completed_lessons = 0
            for c in courses:
                cid = c.get("note_id", c.get("course_title", ""))
                pp = progress_dir / f"{cid}.json"
                if pp.exists():
                    try:
                        pd = _json_loads(pp.read_text(encoding="utf-8"))
                        lessons = pd.get("lessons", {})
                        completed_lessons += sum(1 for v in lessons.values() if v)
                    except Exception:
                        pass
            return {
                "total_courses": len(courses),
                "total_hours": total_hours,
                "total_lessons": total_lessons,
                "completed_lessons": completed_lessons,
                "domain_distribution": domain_dist,
                "completion_rate": round(completed_lessons / total_lessons * 100, 1) if total_lessons > 0 else 0,
            }
        except Exception:
            return {}

    def _create_course_data(workspace_dir: str, title: str, domain: str):
        """同步创建新课程"""
        import hashlib
        h = hashlib.md5(title.encode("utf-8")).hexdigest()[:16]
        new_course = {
            "note_id": f"new_{h}",
            "course_title": title,
            "total_hours": None,
            "domain": domain,
            "prerequisites": [],
            "positioning": "",
            "target_audience": "",
            "assessment": "",
            "sections": [],
            "lessons": [],
            "references": [],
        }
        cs_path = Path(workspace_dir) / "courses_structured.json"
        data = {"metadata": {}, "courses": []}
        if cs_path.exists():
            try:
                data = _json_loads(cs_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        for c in data.get("courses", []):
            if c.get("note_id") == new_course["note_id"] or c.get("course_title") == title:
                return None, "课程已存在"
        data.setdefault("courses", []).append(new_course)
        cs_path.write_text(_json_dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return new_course, None

    def _delete_course_data(workspace_dir: str, course_id: str):
        """同步删除课程"""
        cs_path = Path(workspace_dir) / "courses_structured.json"
        if not cs_path.exists():
            return None, "课程文件不存在"
        try:
            data = _json_loads(cs_path.read_text(encoding="utf-8"))
            before = len(data.get("courses", []))
            data["courses"] = [c for c in data.get("courses", [])
                               if c.get("note_id") != course_id and c.get("course_title") != course_id]
            if len(data["courses"]) == before:
                return None, "课程未找到"
            cs_path.write_text(_json_dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            pp = Path(workspace_dir) / "data" / "progress" / f"{course_id}.json"
            if pp.exists():
                pp.unlink()
            return True, None
        except Exception as e:
            return None, str(e)

    @app.post("/api/data/courses/review/due")
    async def courses_review_due(req: CourseProgressRequest):
        """获取待复习课时列表（间隔重复算法）"""
        data = await _run_data(_get_review_due, app.state.workspace_dir, req.course_id)
        return ok(data=data)

    @app.post("/api/data/courses/review/done")
    async def courses_review_done(req: LessonStatusRequest):
        """标记复习完成，计算下次复习时间（间隔重复）"""
        result, error = await _run_data(_mark_review_done, app.state.workspace_dir, req.course_id, req.lesson_number, req.status)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/courses/updateReview")
    async def courses_update_review(req: LessonStatusRequest):
        """根据工作量更新复习调度"""
        result, error = await _run_data(_update_review_schedule, app.state.workspace_dir, req.course_id, req.lesson_number, req.status)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.get("/api/data/courses/stats")
    async def courses_stats():
        """课程系统全局统计"""
        data = await _run_data(_get_courses_stats, app.state.workspace_dir)
        return ok(data=data)

    @app.post("/api/data/courses/create")
    async def courses_create(req: dict):
        """创建新课程"""
        title = req.get("title", "").strip()
        domain = req.get("domain", "UNKNOWN")
        if not title:
            return err(msg="课程标题不能为空")
        result, error = await _run_data(_create_course_data, app.state.workspace_dir, title, domain)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/courses/delete")
    async def courses_delete(req: dict):
        """删除课程"""
        course_id = req.get("course_id", "")
        if not course_id:
            return err(msg="course_id 不能为空")
        result, error = await _run_data(_delete_course_data, app.state.workspace_dir, course_id)
        if error:
            return err(msg=error)
        return ok()

    # ─── 资源索引 API ──────────────────────────────────────

    def _get_resources(workspace_dir: str, course_id: str):
        """同步获取课程资源列表"""
        res_path = Path(workspace_dir) / "data" / "resource_index.json"
        # 回退到根目录
        if not res_path.exists():
            res_path = Path(workspace_dir) / "resource_index.json"
        if not res_path.exists():
            return []
        try:
            data = _json_loads(res_path.read_text(encoding="utf-8"))
            return data.get(course_id, [])
        except Exception:
            return []

    def _add_resource(workspace_dir: str, course_key: str, entry: dict):
        """同步添加课程资源"""
        res_path = Path(workspace_dir) / "data" / "resource_index.json"
        if not res_path.exists():
            res_path = Path(workspace_dir) / "resource_index.json"
        data = {}
        if res_path.exists():
            try:
                data = _json_loads(res_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data.setdefault(course_key, [])
        t = entry.get("type", "")
        dk = f"{t}:{entry.get('path', entry.get('url', ''))}:{entry.get('lesson_number', '')}"
        for r in data[course_key]:
            rdk = f"{r.get('type','')}:{r.get('path', r.get('url', ''))}:{r.get('lesson_number', '')}"
            if rdk == dk:
                return {"added": False}, None
        data[course_key].append(entry)
        res_path.parent.mkdir(parents=True, exist_ok=True)
        res_path.write_text(_json_dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"added": True}, None

    def _remove_resource(workspace_dir: str, course_key: str, entry: dict):
        """同步删除课程资源"""
        res_path = Path(workspace_dir) / "data" / "resource_index.json"
        if not res_path.exists():
            res_path = Path(workspace_dir) / "resource_index.json"
        if not res_path.exists():
            return {"removed": False}, None
        try:
            data = _json_loads(res_path.read_text(encoding="utf-8"))
            entries = data.get(course_key, [])
            t = entry.get("type", "")
            dk = f"{t}:{entry.get('path', entry.get('url', ''))}:{entry.get('lesson_number', '')}"
            for i, r in enumerate(entries):
                rdk = f"{r.get('type','')}:{r.get('path', r.get('url', ''))}:{r.get('lesson_number', '')}"
                if rdk == dk:
                    entries.pop(i)
                    res_path.write_text(_json_dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    return {"removed": True}, None
            return {"removed": False}, None
        except Exception as e:
            return None, str(e)

    @app.get("/api/data/resources/{course_id}")
    async def resources_get(course_id: str):
        """获取课程资源列表"""
        data = await _run_data(_get_resources, app.state.workspace_dir, course_id)
        return ok(data=data)

    @app.post("/api/data/resources/add")
    async def resources_add(req: dict):
        """添加课程资源"""
        course_key = req.get("course_key", "")
        entry = req.get("entry", {})
        if not course_key or not entry:
            return err(msg="参数不完整")
        result, error = await _run_data(_add_resource, app.state.workspace_dir, course_key, entry)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/data/resources/remove")
    async def resources_remove(req: dict):
        """删除课程资源"""
        course_key = req.get("course_key", "")
        entry = req.get("entry", {})
        if not course_key:
            return err(msg="参数不完整")
        result, error = await _run_data(_remove_resource, app.state.workspace_dir, course_key, entry)
        if error:
            return err(msg=error)
        return ok(data=result)

    def _get_all_resources(workspace_dir: str, query: str = ""):
        """同步获取所有课程资源（可选搜索过滤）"""
        res_path = Path(workspace_dir) / "data" / "resource_index.json"
        if not res_path.exists():
            res_path = Path(workspace_dir) / "resource_index.json"
        if not res_path.exists():
            return []
        try:
            data = _json_loads(res_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        results = []
        q = query.lower() if query else ""
        for course_id, resources in data.items():
            for r in resources:
                if q:
                    label = r.get("label", "").lower()
                    path = r.get("path", "").lower()
                    url = r.get("url", "").lower()
                    if q not in label and q not in path and q not in url and q not in course_id.lower():
                        continue
                results.append({**r, "course_id": course_id})
        # 按添加时间倒序
        results.sort(key=lambda x: x.get("added_at", x.get("lesson_number", 0) or 0), reverse=True)
        return results

    @app.get("/api/data/resources")
    async def resources_all(query: str = ""):
        """获取所有课程资源（可选搜索过滤）"""
        data = await _run_data(_get_all_resources, app.state.workspace_dir, query)
        return ok(data=data)

    # ─── 内容推送 API ──────────────────────────────────────

    @app.get("/api/push/dashboard")
    async def push_dashboard():
        """内容推送：返回用户需要关注的摘要数据"""
        data = await _run_push(_get_push_dashboard, app.state.workspace_dir)
        return ok(data=data)

    # ─── 工作流日志 API ──────────────────────────────────────

    def _get_workflow_log(workspace_dir: str):
        """同步获取工作流日志"""
        log_path = Path(workspace_dir) / "data" / "workflow_log.json"
        if not log_path.exists():
            return []
        try:
            entries = _json_loads(log_path.read_text(encoding="utf-8"))
            entries.sort(key=lambda x: x.get("timestamp", ""))
            return entries[-200:]
        except Exception:
            return []

    def _add_workflow_log(workspace_dir: str, entry: dict):
        """同步添加工作流日志条目"""
        log_path = Path(workspace_dir) / "data" / "workflow_log.json"
        entries = []
        if log_path.exists():
            try:
                entries = _json_loads(log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        entries.append(entry)
        entries.sort(key=lambda x: x.get("timestamp", ""))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(_json_dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        return entry

    def _get_workflow_stats(workspace_dir: str):
        """同步获取工作流统计"""
        log_path = Path(workspace_dir) / "data" / "workflow_log.json"
        if not log_path.exists():
            return {"total_entries": 0, "total_focus_time": 0, "daily": {}}
        try:
            entries = _json_loads(log_path.read_text(encoding="utf-8"))
            total_focus_time = 0.0
            note_count = 0
            complete_count = 0
            daily = {}
            course_times = {}
            for e in entries:
                ts = e.get("timestamp", "")
                etype = e.get("type", "")
                cid = e.get("course_id", "")
                if ts:
                    day = ts[:10]
                    daily[day] = daily.get(day, 0) + 1
                if etype == "note":
                    note_count += 1
                elif etype == "lesson_complete":
                    complete_count += 1
                elif etype == "timer_stop":
                    detail = e.get("detail", "")
                    try:
                        parts = detail.replace("耗时 ", "").split()
                        if parts:
                            t_str = parts[0]
                            t_parts = t_str.split(":")
                            if len(t_parts) == 3:
                                t = int(t_parts[0]) * 3600 + int(t_parts[1]) * 60 + int(t_parts[2])
                            elif len(t_parts) == 2:
                                t = int(t_parts[0]) * 60 + int(t_parts[1])
                            else:
                                t = 0
                            total_focus_time += t
                            course_times[cid] = course_times.get(cid, 0) + t
                    except Exception:
                        pass
            return {
                "total_entries": len(entries),
                "total_focus_time": round(total_focus_time, 1),
                "total_focus_hours": round(total_focus_time / 3600, 1),
                "note_count": note_count,
                "complete_count": complete_count,
                "daily": daily,
                "course_times": course_times,
            }
        except Exception:
            return {}

    def _get_push_dashboard(workspace_dir: str):
        """聚合推送数据：待办任务、待复习课程、课程资源更新、近期截止任务"""
        result = {
            "due_tasks": [],        # 近期截止的任务
            "overdue_tasks": [],    # 已超期的任务
            "due_reviews": [],      # 待复习课时
            "recent_resources": [], # 最近添加的课程资源
            "today_stats": {},      # 今日统计
        }

        workspace = Path(workspace_dir)
        today = time.strftime("%Y-%m-%d")

        # 1. 任务推送
        tb_path = workspace / "task_board.json"
        if tb_path.exists():
            try:
                tasks = _json_loads(tb_path.read_text(encoding="utf-8"))
                if isinstance(tasks, list):
                    for task in tasks:
                        status = task.get("status", "")
                        if status in ("已完成", "done", "completed"):
                            continue
                        due_date = task.get("due_date", "")
                        if due_date:
                            if due_date < today:
                                result["overdue_tasks"].append({
                                    "id": task.get("id", ""),
                                    "title": task.get("title", ""),
                                    "due_date": due_date,
                                    "priority": task.get("priority", "中"),
                                    "overdue_days": (datetime.date.today() - datetime.date.fromisoformat(due_date)).days if len(due_date) == 10 else 0,
                                })
                            elif due_date <= today:
                                result["due_tasks"].append({
                                    "id": task.get("id", ""),
                                    "title": task.get("title", ""),
                                    "due_date": due_date,
                                    "priority": task.get("priority", "中"),
                                })
                            # 未来3天内截止
                            elif due_date <= (datetime.date.today() + datetime.timedelta(days=3)).isoformat():
                                result["due_tasks"].append({
                                    "id": task.get("id", ""),
                                    "title": task.get("title", ""),
                                    "due_date": due_date,
                                    "priority": task.get("priority", "中"),
                                })
            except Exception as e:
                logger.warning(f"Push dashboard: read tasks failed: {e}")

        # 2. 待复习课时推送
        progress_dir = workspace / "data" / "progress"
        cs_path = workspace / "courses_structured.json"
        if cs_path.exists() and progress_dir.exists():
            try:
                courses_data = _json_loads(cs_path.read_text(encoding="utf-8"))
                courses = courses_data.get("courses", []) if isinstance(courses_data, dict) else courses_data
                for course in courses:
                    course_id = course.get("note_id", course.get("id", ""))
                    course_title = course.get("course_title", course.get("title", ""))
                    pp = progress_dir / f"{course_id}.json"
                    if not pp.exists():
                        continue
                    try:
                        progress = _json_loads(pp.read_text(encoding="utf-8"))
                        review_schedule = progress.get("review_schedule", {})
                        for lesson_num, schedule in review_schedule.items():
                            if isinstance(schedule, dict):
                                next_review = schedule.get("next_review", "")
                                if next_review and next_review <= today:
                                    lesson = None
                                    for l in course.get("lessons", []):
                                        if str(l.get("lesson_number", l.get("number", ""))) == str(lesson_num):
                                            lesson = l
                                            break
                                    result["due_reviews"].append({
                                        "course_id": course_id,
                                        "course_title": course_title,
                                        "lesson_number": int(lesson_num),
                                        "lesson_title": lesson.get("lesson_title", lesson.get("title", f"课时{lesson_num}")) if lesson else f"课时{lesson_num}",
                                        "next_review": next_review,
                                    })
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Push dashboard: read reviews failed: {e}")

        # 3. 最近课程资源
        res_path = workspace / "data" / "resource_index.json"
        if res_path.exists():
            try:
                res_data = _json_loads(res_path.read_text(encoding="utf-8"))
                all_resources = []
                for course_id, resources in res_data.items():
                    for r in resources:
                        r["_course_id"] = course_id
                        all_resources.append(r)
                # 按修改时间排序，取最近10个
                all_resources.sort(key=lambda x: x.get("added_at", x.get("modified", "")), reverse=True)
                result["recent_resources"] = all_resources[:10]
            except Exception:
                pass

        # 4. 今日统计
        result["today_stats"] = {
            "overdue_tasks_count": len(result["overdue_tasks"]),
            "due_tasks_count": len(result["due_tasks"]),
            "due_reviews_count": len(result["due_reviews"]),
        }

        return result

    @app.get("/api/data/workflow/log")
    async def workflow_log_get():
        """获取工作流日志"""
        data = await _run_data(_get_workflow_log, app.state.workspace_dir)
        return ok(data=data)

    @app.post("/api/data/workflow/log")
    async def workflow_log_add(req: dict):
        """添加工作流日志条目"""
        from datetime import datetime
        entry = {
            "type": req.get("type", "action"),
            "action": req.get("action", ""),
            "course_id": req.get("course_id", ""),
            "lesson_number": req.get("lesson_number"),
            "detail": req.get("detail", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        result = await _run_data(_add_workflow_log, app.state.workspace_dir, entry)
        return ok(data=result)

    @app.get("/api/data/workflow/stats")
    async def workflow_stats_get():
        """获取工作流统计"""
        data = await _run_data(_get_workflow_stats, app.state.workspace_dir)
        return ok(data=data)

    # ─── Agent 聊天 API（连接 TS2 MCP 系统）────────────────

    # 懒加载 Agent 实例
    _web_agent = None
    _web_agent_lock = threading.Lock()

    def _get_session_preview(messages_snapshot: list) -> str:
        """从消息快照中提取适合预览的文本（优先取 user/assistant 消息）"""
        if not messages_snapshot:
            return ""
        # 从后往前找第一条 user 或 assistant 消息
        for msg in reversed(messages_snapshot):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                text = content if isinstance(content, str) else str(content)
                return text[:80]
        return ""

    def _get_web_agent(workspace_dir: str):
        """获取或创建 Web Agent 实例"""
        nonlocal _web_agent, _web_agent_lock
        if _web_agent is not None:
            return _web_agent
        with _web_agent_lock:
            if _web_agent is not None:
                return _web_agent
            try:
                from ..config import get_config_manager
                from ..llm import MultiProviderManager, SimulatorLLM
                from ..agent import Agent, AgentConfig

                config_mgr = get_config_manager()

                # 优先使用新的 ProviderConfig（支持环境变量自动检测）
                provider_configs = config_mgr.get_provider_configs_for_manager()

                # 过滤掉 simulator 和未启用的
                enabled_configs = [
                    cfg for cfg in provider_configs
                    if cfg.enabled and cfg.provider.value != 'simulator'
                ]

                if enabled_configs:
                    raw_llm = MultiProviderManager(enabled_configs)
                    class _AdapterLLM:
                        total_prompt_tokens = 0
                        total_completion_tokens = 0
                        def __init__(self, mgr):
                            self._mgr = mgr
                        def chat(self, messages, tools=None, on_token=None):
                            resp = self._mgr.chat_with_fallback(messages, tools, on_token)
                            self.total_prompt_tokens += resp.prompt_tokens
                            self.total_completion_tokens += resp.completion_tokens
                            return resp
                        def is_available(self):
                            return self._mgr.get_provider() is not None
                    llm = _AdapterLLM(raw_llm)
                    logger.info(f"Web Agent: 使用真实 LLM ({len(enabled_configs)} 个提供商)")
                else:
                    # 尝试从环境变量直接创建 OpenAI 兼容配置
                    import os
                    api_key = os.environ.get("OPENAI_API_KEY", "")
                    base_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("OPENAI_API_BASE", ""))
                    model_id = os.environ.get("TS2_MODEL_ID", "gpt-4o-mini")

                    if api_key:
                        from ..llm import ProviderConfig, ProviderType
                        env_config = ProviderConfig(
                            provider=ProviderType.OPENAI_COMPATIBLE,
                            name="env-openai",
                            api_key=api_key,
                            base_url=base_url or None,
                            model_id=model_id,
                            enabled=True,
                        )
                        raw_llm = MultiProviderManager([env_config])
                        class _AdapterLLM:
                            total_prompt_tokens = 0
                            total_completion_tokens = 0
                            def __init__(self, mgr):
                                self._mgr = mgr
                            def chat(self, messages, tools=None, on_token=None):
                                resp = self._mgr.chat_with_fallback(messages, tools, on_token)
                                self.total_prompt_tokens += resp.prompt_tokens
                                self.total_completion_tokens += resp.completion_tokens
                                return resp
                            def is_available(self):
                                return self._mgr.get_provider() is not None
                        llm = _AdapterLLM(raw_llm)
                        logger.info(f"Web Agent: 使用环境变量 LLM (model={model_id})")
                    else:
                        llm = SimulatorLLM()
                        logger.warning("Web Agent: 未找到 LLM 配置，使用模拟模式。请设置 OPENAI_API_KEY 环境变量或配置 ~/.ts2/agent_config/providers.json")

                # 获取 model_id（用于构建正确的系统提示词）
                _web_model_id = ""
                if enabled_configs:
                    _web_model_id = enabled_configs[0].model or ""
                elif api_key:
                    _web_model_id = model_id  # 环境变量中的 model_id

                agent_config = AgentConfig(
                    name="TS2 Web Agent",
                    base_dir=Path(workspace_dir),
                    workspace_root=workspace_dir,
                    mode="act",
                    model_id=_web_model_id,
                )
                # Agent.__init__ 会自动加载默认工具 + server_tools + WS2/DataHub 等
                # server_tools 已在 Agent.__init__ 中统一加载，无需手动合并
                agent = Agent(llm=llm, config=agent_config)

                # 动态注入当前工作目录 + Web 客户端连接信息
                def _web_context_injector(a, u):
                    parts = [f"[当前工作目录: {workspace_dir}]"]
                    # 注入当前连接的 Web 客户端信息
                    try:
                        ws_mgr = getattr(app.state, 'ws_manager', None)
                        if ws_mgr:
                            sessions = ws_mgr.get_sessions_info()
                            if sessions:
                                parts.append(f"[当前 Web 客户端连接数: {len(sessions)}]")
                                for s in sessions[:5]:  # 最多显示5个
                                    parts.append(
                                        f"  - app_id={s.get('app_id','?')}, "
                                        f"session={s.get('session_id','?')[:8]}, "
                                        f"type={s.get('client_type','?')}"
                                    )
                            else:
                                parts.append("[当前无 Web 客户端连接]")
                    except Exception:
                        pass
                    return "\n".join(parts)

                agent.register_context_injector(_web_context_injector)

                _web_agent = agent
                logger.info(f"Web Agent 已初始化 ({len(agent.tools)} 工具, LLM: {'已配置' if not isinstance(llm, SimulatorLLM) else '未配置(模拟模式)'})")
            except Exception as e:
                logger.warning(f"Web Agent 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                _web_agent = None
        return _web_agent

    @app.post("/api/agent/chat")
    async def agent_chat(req: AgentChatRequest):
        """Agent 聊天接口（连接 TS2 MCP 系统）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={
                "reply": "Agent 初始化失败，请检查配置文件 (config_dir: ~/.ts2/agent_config)",
                "source": "error",
            })

        try:
            # 构建多模态消息
            message = _build_multimodal_message(req.message, req.attachments)
            reply = await asyncio.wait_for(
                _run_agent(agent.chat, message, session_id=req.session_id),
                timeout=300.0
            )
            # 自动保存检查点（每5轮对话保存一次）
            try:
                msg_count = len(agent.messages)
                if msg_count > 0 and msg_count % 10 == 0:  # 每10条消息（约5轮）
                    summary = req.message[:80]
                    agent.create_checkpoint(summary=summary)
            except Exception:
                pass
            return ok(data={"reply": reply, "source": "ts2_mcp"})
        except asyncio.TimeoutError:
            logger.error("Agent chat timed out after 300s")
            return ok(data={
                "reply": "处理超时，AI 助手未在 300 秒内响应，请检查 LLM 配置或网络连接，或简化问题描述",
                "source": "timeout",
            })
        except Exception as e:
            logger.error(f"Agent chat error: {e}")
            return ok(data={
                "reply": f"处理出错：{str(e)}",
                "source": "error",
            })

    # ─── Agent SSE 流式聊天 API ──────────────────────────────

    @app.post("/api/agent/chat/stream")
    async def agent_chat_stream(req: AgentChatRequest):
        """Agent 流式聊天接口（SSE）— 参考 CLine 架构"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            async def _err():
                yield f"data: {_json_dumps_compact({'type': 'error', 'content': 'Agent 初始化失败'})}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(_err(), media_type="text/event-stream")

        message_queue = asyncio.Queue()
        main_loop = asyncio.get_event_loop()  # 捕获主事件循环

        def _on_token(token: str):
            """LLM 流式 token 回调"""
            try:
                main_loop.call_soon_threadsafe(
                    message_queue.put_nowait,
                    {"type": "token", "content": token}
                )
            except Exception as e:
                logger.warning(f"_on_token error: {e}")

        def _on_tool(name: str, args: dict):
            """工具调用开始回调"""
            try:
                main_loop.call_soon_threadsafe(
                    message_queue.put_nowait,
                    {"type": "tool_call", "name": name, "args": args}
                )
            except Exception as e:
                logger.warning(f"_on_tool error: {e}")

        def _on_tool_result(name: str, result: str):
            """工具调用结果回调"""
            try:
                # 获取检查点 hash（从中间件获取，若有变更才返回）
                cp_hash = ""
                try:
                    if hasattr(agent, '_middleware_chain') and agent._middleware_chain:
                        for mw in agent._middleware_chain._middlewares:
                            from ..middleware.shadow_checkpoint import CheckpointMiddleware
                            if isinstance(mw, CheckpointMiddleware):
                                cp_hash = mw._last_hash
                                break
                except Exception:
                    pass

                main_loop.call_soon_threadsafe(
                    message_queue.put_nowait,
                    {
                        "type": "tool_result",
                        "name": name,
                        "result": result[:500],
                        "checkpoint_hash": cp_hash,
                    }
                )
            except Exception as e:
                logger.warning(f"_on_tool_result error: {e}")

        def _run_agent_stream():
            """在线程池中运行 Agent（流式）"""
            try:
                message = _build_multimodal_message(req.message, req.attachments)
                logger.info(f"Agent stream: starting chat for message: {req.message[:50]}...")
                reply = agent.chat(
                    message,
                    on_token=_on_token,
                    on_tool=_on_tool,
                    on_tool_result=_on_tool_result,
                    session_id=req.session_id,
                )
                logger.info(f"Agent stream: chat completed, reply length={len(reply) if reply else 0}")
                main_loop.call_soon_threadsafe(
                    message_queue.put_nowait,
                    {"type": "done", "content": reply}
                )
            except Exception as e:
                logger.error(f"Agent stream error: {e}")
                import traceback
                traceback.print_exc()
                main_loop.call_soon_threadsafe(
                    message_queue.put_nowait,
                    {"type": "error", "content": str(e)}
                )

        async def _stream():
            """SSE 事件生成器"""
            agent_future = main_loop.run_in_executor(_agent_executor, _run_agent_stream)

            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(message_queue.get(), timeout=90.0)
                    except asyncio.TimeoutError:
                        yield f"data: {_json_dumps_compact({'type': 'error', 'content': '超时'})}\n\n"
                        break

                    if msg.get("type") == "done":
                        yield f"data: {_json_dumps_compact(msg)}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    elif msg.get("type") == "error":
                        yield f"data: {_json_dumps_compact(msg)}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    else:
                        yield f"data: {_json_dumps_compact(msg)}\n\n"
            except asyncio.CancelledError:
                if hasattr(agent, 'cancel'):
                    agent.cancel()
            finally:
                if not agent_future.done():
                    agent_future.cancel()

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Content-Encoding": "identity",  # 阻止 GZip 中间件压缩 SSE
            }
        )

    # ─── Agent 控制接口 ──────────────────────────────────────

    @app.post("/api/agent/cancel")
    async def agent_cancel():
        """取消当前 Agent 对话"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent and hasattr(agent, 'cancel'):
            agent.cancel()
            return ok(data={"cancelled": True})
        return ok(data={"cancelled": False})

    @app.post("/api/agent/reset")
    async def agent_reset():
        """重置 Agent 对话历史"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent:
            # reset() 内部已包含 cancel + wait 逻辑，放到线程池避免阻塞事件循环
            await asyncio.get_event_loop().run_in_executor(None, agent.reset)
            return ok(data={"reset": True})
        return ok(data={"reset": False})

    @app.get("/api/agent/status")
    async def agent_status():
        """获取 Agent 状态"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"available": False, "tools": 0})
        return ok(data={
            "available": True,
            "tools": len(agent.tools),
            "model": agent.config.model_id or "unknown",
            "messages": len(agent.messages),
            "current_session": {
                "message_count": len(agent.messages),
                "has_context": bool(agent.messages and len(agent.messages) > 1),
            },
        })

    @app.get("/api/agent/model-info")
    async def agent_model_info():
        """获取当前模型信息（含多模态能力标记）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"model": "unknown", "capabilities": {}})
        model_id = agent.config.model_id or "unknown"
        try:
            from ..llm import DEFAULT_MODEL_INFOS, ModelInfo
            info = DEFAULT_MODEL_INFOS.get(model_id)
            if info is None:
                if hasattr(agent, 'llm') and hasattr(agent.llm, 'config'):
                    info = agent.llm.config.model_info
                else:
                    info = ModelInfo(name=model_id, provider=None)
            return ok(data={
                "model": info.name,
                "provider": info.provider.value if info.provider else "unknown",
                "context_window": info.context_window,
                "max_tokens": info.max_tokens,
                "is_reasoning_model": info.is_reasoning_model,
                "capabilities": {
                    "supports_image_input": info.supports_image_input,
                    "supports_video_input": info.supports_video_input,
                    "supports_tools": info.supports_tools,
                    "supports_streaming": info.supports_streaming,
                },
                "pricing": {
                    "input_per_million": info.pricing_input,
                    "output_per_million": info.pricing_output,
                },
            })
        except Exception as e:
            return ok(data={"model": model_id, "capabilities": {}, "error": str(e)})

    @app.get("/api/models")
    async def list_models():
        """列出所有已知模型及其能力"""
        try:
            from ..llm import DEFAULT_MODEL_INFOS, PROVIDER_DEFAULT_MODELS, PROVIDER_DISPLAY_NAMES
            models = []
            for name, info in DEFAULT_MODEL_INFOS.items():
                models.append({
                    "name": info.name,
                    "provider": info.provider.value if info.provider else "unknown",
                    "provider_display": PROVIDER_DISPLAY_NAMES.get(info.provider, info.provider.value if info.provider else "unknown"),
                    "context_window": info.context_window,
                    "max_tokens": info.max_tokens,
                    "is_reasoning_model": info.is_reasoning_model,
                    "supports_image_input": info.supports_image_input,
                    "supports_video_input": info.supports_video_input,
                    "supports_tools": info.supports_tools,
                    "pricing_input": info.pricing_input,
                    "pricing_output": info.pricing_output,
                })
            providers = {}
            for pt, model_names in PROVIDER_DEFAULT_MODELS.items():
                providers[pt.value] = {
                    "display": PROVIDER_DISPLAY_NAMES.get(pt, pt.value),
                    "models": model_names,
                }
            return ok(data={"models": models, "providers": providers})
        except Exception as e:
            return ok(data={"models": [], "providers": {}, "error": str(e)})

    class RegisterModelRequest(BaseModel):
        name: str
        provider: str = "custom"
        max_tokens: int = 4096
        context_window: int = 8192
        supports_image_input: bool = False
        supports_video_input: bool = False
        supports_tools: bool = True
        is_reasoning_model: bool = False
        pricing_input: float = 0.0
        pricing_output: float = 0.0

    @app.post("/api/models/register")
    async def register_model(req: RegisterModelRequest):
        """注册自定义模型（运行时动态添加到模型信息表）"""
        try:
            from ..llm import register_custom_model, ProviderType
            provider = ProviderType(req.provider) if req.provider in [p.value for p in ProviderType] else ProviderType.CUSTOM
            info = register_custom_model(
                name=req.name, provider=provider, max_tokens=req.max_tokens,
                context_window=req.context_window, supports_image_input=req.supports_image_input,
                supports_video_input=req.supports_video_input, supports_tools=req.supports_tools,
                is_reasoning_model=req.is_reasoning_model, pricing_input=req.pricing_input,
                pricing_output=req.pricing_output,
            )
            return ok(data={"registered": True, "model": info.name, "capabilities": {
                "supports_image_input": info.supports_image_input, "supports_video_input": info.supports_video_input,
            }})
        except Exception as e:
            return err(msg=f"注册失败: {e}")

    # ─── Agent 会话管理 API ──────────────────────────────────

    @app.get("/api/agent/sessions")
    async def agent_sessions():
        """列出所有会话"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent:
            return ok(data=[])
        try:
            from ..cache import get_context_reloader
            reloader = get_context_reloader()
            # 获取所有检查点作为会话列表
            checkpoint_ids = reloader.list_checkpoints()
            sessions = []
            for cp_id in checkpoint_ids[:20]:  # 最多返回20个
                cp = reloader.restore_checkpoint(cp_id)
                if cp:
                    sessions.append({
                        "id": cp.checkpoint_id,
                        "timestamp": cp.timestamp,
                        "message_count": cp.total_messages,
                        "token_count": cp.total_tokens,
                        "summary": cp.summary or "",
                        "preview": _get_session_preview(cp.messages_snapshot),
                    })
            return ok(data=sessions)
        except Exception as e:
            logger.warning(f"List sessions error: {e}")
            return ok(data=[])

    @app.post("/api/agent/sessions/create")
    async def agent_session_create():
        """保存当前会话并创建新会话"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent:
            return ok(data={"created": False})
        try:
            # 整个操作放到线程池，避免阻塞事件循环
            def _create_session():
                # 保存当前会话为检查点
                summary = ""
                messages = agent.snapshot_messages()
                if messages:
                    for msg in reversed(messages):
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            summary = content[:100] if isinstance(content, str) else str(content)[:100]
                            break
                checkpoint = agent.create_checkpoint(summary=summary)
                # 重置对话（内部包含 cancel + wait）
                agent.reset()
                return checkpoint, summary

            checkpoint, summary = await asyncio.get_event_loop().run_in_executor(None, _create_session)
            if checkpoint:
                return ok(data={
                    "created": True,
                    "session_id": checkpoint.checkpoint_id,
                    "summary": summary,
                })
            return ok(data={"created": True, "summary": summary})
        except Exception as e:
            logger.error(f"Create session error: {e}")
            return ok(data={"created": False, "error": str(e)})

    @app.post("/api/agent/sessions/switch")
    async def agent_session_switch(req: AgentSessionSwitchRequest):
        """切换到指定会话"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent:
            return ok(data={"switched": False})
        try:
            # 整个操作放到线程池，避免阻塞事件循环
            def _switch_session():
                # 保存当前会话
                current_messages = agent.snapshot_messages()
                if current_messages:
                    summary = ""
                    for msg in reversed(current_messages):
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            summary = content[:100] if isinstance(content, str) else str(content)[:100]
                            break
                    agent.create_checkpoint(summary=summary)

                # 恢复目标会话
                success = agent.restore_checkpoint(req.session_id)
                if not success:
                    return None
                # 返回恢复后的消息列表（包含 tool 消息细节）
                restored_messages = agent.snapshot_messages()
                ui_messages = []
                for msg in restored_messages:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "system":
                        continue
                    if role == "tool":
                        # tool 消息：提取工具名和结果摘要
                        tool_call_id = msg.get("tool_call_id", "")
                        tool_content = content if isinstance(content, str) else str(content)
                        # 尝试解析 JSON 结果
                        tool_name = ""
                        try:
                            # 从前一条 assistant 消息的 tool_calls 中找工具名
                            for prev in reversed(ui_messages):
                                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                                    for tc in prev["tool_calls"]:
                                        tc_dict = tc if isinstance(tc, dict) else {}
                                        if tc_dict.get("id") == tool_call_id:
                                            tool_name = tc_dict.get("function", {}).get("name", "")
                                            break
                                    break
                        except Exception:
                            pass
                        ui_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "tool_name": tool_name,
                            "content": tool_content[:500],  # 限制长度
                        })
                    elif role == "assistant":
                        entry = {
                            "role": "assistant",
                            "content": content if isinstance(content, str) else str(content),
                        }
                        # 保留 tool_calls 信息
                        if msg.get("tool_calls"):
                            entry["tool_calls"] = msg["tool_calls"]
                        ui_messages.append(entry)
                    elif role == "user" and content:
                        ui_messages.append({
                            "role": "user",
                            "content": content if isinstance(content, str) else str(content),
                        })
                return ui_messages

            ui_messages = await asyncio.get_event_loop().run_in_executor(None, _switch_session)
            if ui_messages is not None:
                return ok(data={
                    "switched": True,
                    "session_id": req.session_id,
                    "messages": ui_messages,
                })
            else:
                return ok(data={"switched": False, "error": "会话不存在"})
        except Exception as e:
            logger.error(f"Switch session error: {e}")
            return ok(data={"switched": False, "error": str(e)})

    @app.post("/api/agent/sessions/delete")
    async def agent_session_delete(req: AgentSessionSwitchRequest):
        """删除指定会话"""
        try:
            from ..cache import get_context_reloader
            reloader = get_context_reloader()
            reloader.delete_checkpoint(req.session_id)
            return ok(data={"deleted": True})
        except Exception as e:
            return ok(data={"deleted": False, "error": str(e)})

    # ─── Swarm 子 Agent API ──────────────────────────────────

    @app.get("/api/swarm/agents")
    async def swarm_list_agents():
        """列出所有已注册的子 Agent 及其状态"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return ok(data={"agents": [], "available": False, "swarm_enabled": False})
        try:
            coordinator = agent._coordinator
            agent_names = coordinator.list_agents()
            agents_info = []
            for name in agent_names:
                spec = coordinator._specs.get(name)
                sa = coordinator._agents.get(name)
                running_tasks = []
                for tid, holder in coordinator._pending_tasks.items():
                    if holder.result and holder.result.agent_name == name:
                        running_tasks.append({"task_id": tid, "status": holder.result.status.value, "started_at": holder.result.started_at})
                info = {
                    "name": name,
                    "role": spec.role.value if spec else "custom",
                    "system_prompt": (spec.system_prompt[:80] + "...") if spec and spec.system_prompt else "",
                    "model": spec.model if spec else "",
                    "max_turns": spec.max_turns if spec else 0,
                    "allowed_tools": spec.allowed_tools if spec else None,
                    "is_busy": sa.is_busy if sa else False,
                    "status": sa._result.status.value if sa else "idle",
                    "running_tasks": running_tasks,
                }
                agents_info.append(info)
            return ok(data={"agents": agents_info, "available": True, "swarm_enabled": coordinator.swarm_enabled})
        except Exception as e:
            logger.warning(f"swarm_list_agents error: {e}")
            return ok(data={"agents": [], "available": False, "error": str(e)})

    @app.get("/api/swarm/agents/{agent_name}")
    async def swarm_get_agent(agent_name: str):
        """获取指定子 Agent 的详情"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        coordinator = agent._coordinator
        spec = coordinator._specs.get(agent_name)
        if not spec:
            return err(msg=f"子 Agent '{agent_name}' 不存在")
        sa = coordinator._agents.get(agent_name)
        result = sa._result if sa else None
        return ok(data={
            "name": spec.name, "role": spec.role.value, "system_prompt": spec.system_prompt,
            "model": spec.model, "max_turns": spec.max_turns, "allowed_tools": spec.allowed_tools,
            "denied_tools": spec.denied_tools, "is_busy": sa.is_busy if sa else False,
            "status": result.status.value if result else "idle",
            "last_result": {
                "content": result.content[:500] if result and result.content else "",
                "error": result.error if result else None,
                "duration_ms": result.duration_ms if result else 0,
                "tool_calls_count": result.tool_calls_count if result else 0,
                "prompt_tokens": result.prompt_tokens if result else 0,
                "completion_tokens": result.completion_tokens if result else 0,
                "completed_at": result.completed_at if result else 0,
            } if result and result.status.value in ("completed", "failed") else None,
        })

    class SwarmRunRequest(BaseModel):
        agent_name: str
        prompt: str
        context: Optional[Dict[str, Any]] = None
        background: bool = False

    @app.post("/api/swarm/run")
    async def swarm_run(req: SwarmRunRequest):
        """运行子 Agent（同步或后台）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        coordinator = agent._coordinator
        if req.agent_name not in coordinator._specs:
            return err(msg=f"子 Agent '{req.agent_name}' 不存在")
        if req.background:
            task_id = coordinator.run_async(req.agent_name, req.prompt, req.context)
            ws_mgr = get_ws_manager()
            await ws_mgr.broadcast("swarm_task_started", 0, "", {
                "task_id": task_id, "agent_name": req.agent_name, "prompt": req.prompt[:100],
            })
            return ok(data={"task_id": task_id, "background": True})
        else:
            def _run():
                return coordinator.run(req.agent_name, req.prompt, req.context)
            result = await asyncio.get_event_loop().run_in_executor(None, _run)
            return ok(data={
                "status": result.status.value, "content": result.content,
                "reasoning_content": result.reasoning_content, "error": result.error,
                "duration_ms": result.duration_ms, "tool_calls_count": result.tool_calls_count,
                "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
            })

    @app.post("/api/swarm/cancel/{agent_name}")
    async def swarm_cancel(agent_name: str):
        """取消子 Agent 的运行"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        agent._coordinator.cancel(agent_name)
        return ok(data={"cancelled": True, "agent_name": agent_name})

    @app.get("/api/swarm/tasks")
    async def swarm_list_tasks():
        """列出所有后台任务及其状态"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return ok(data={"tasks": []})
        coordinator = agent._coordinator
        tasks = []
        for tid, holder in list(coordinator._pending_tasks.items()):
            task_info = {"task_id": tid, "completed": holder.completed.is_set()}
            if holder.result:
                task_info.update({
                    "agent_name": holder.result.agent_name, "status": holder.result.status.value,
                    "content": holder.result.content[:300] if holder.result.content else "",
                    "error": holder.result.error, "duration_ms": holder.result.duration_ms,
                    "tool_calls_count": holder.result.tool_calls_count,
                })
            tasks.append(task_info)
        return ok(data={"tasks": tasks})

    @app.get("/api/swarm/tasks/{task_id}")
    async def swarm_get_task(task_id: str):
        """获取后台任务结果"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        coordinator = agent._coordinator
        holder = coordinator._pending_tasks.get(task_id)
        if not holder:
            return ok(data={"task_id": task_id, "status": "unknown", "completed": True})
        result = holder.result
        if not result:
            return ok(data={"task_id": task_id, "status": "running", "completed": False})
        return ok(data={
            "task_id": task_id, "status": result.status.value, "completed": holder.completed.is_set(),
            "agent_name": result.agent_name, "content": result.content,
            "reasoning_content": result.reasoning_content, "error": result.error,
            "duration_ms": result.duration_ms, "tool_calls_count": result.tool_calls_count,
            "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        })

    @app.post("/api/swarm/poll/{task_id}")
    async def swarm_poll_task(task_id: str):
        """轮询后台任务结果（等待最多 30 秒）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        coordinator = agent._coordinator
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: coordinator.poll_result(task_id, timeout=30.0)
        )
        if result is None:
            return ok(data={"task_id": task_id, "status": "running", "completed": False})
        ws_mgr = get_ws_manager()
        await ws_mgr.broadcast("swarm_task_completed", 0, "", {
            "task_id": task_id, "agent_name": result.agent_name, "status": result.status.value,
            "duration_ms": result.duration_ms, "content_preview": result.content[:200] if result.content else "",
        })
        return ok(data={
            "task_id": task_id, "status": result.status.value, "completed": True,
            "agent_name": result.agent_name, "content": result.content,
            "reasoning_content": result.reasoning_content, "error": result.error,
            "duration_ms": result.duration_ms, "tool_calls_count": result.tool_calls_count,
            "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        })

    class SwarmEnableRequest(BaseModel):
        reason: str = ""

    @app.post("/api/swarm/enable")
    async def swarm_enable(req: SwarmEnableRequest):
        """启用大规模 Swarm 集群模式（>4个并行任务需启用）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        coordinator = agent._coordinator
        if coordinator.swarm_enabled:
            return ok(data={"swarm_enabled": True, "message": "Swarm 集群模式已处于启用状态"})
        if not req.reason.strip():
            return err(msg="启用 Swarm 集群模式需要提供原因说明（如：大规模并行研究任务）")
        success = coordinator.enable_swarm(reason=req.reason)
        if success:
            return ok(data={"swarm_enabled": True, "message": f"Swarm 集群模式已启用 (原因: {req.reason})"})
        else:
            return err(msg="Swarm 启用失败：LLM 未配置")

    @app.post("/api/swarm/disable")
    async def swarm_disable():
        """禁用大规模 Swarm 集群模式"""
        agent = _get_web_agent(app.state.workspace_dir)
        if not agent or not hasattr(agent, '_coordinator') or not agent._coordinator:
            return err(msg="Swarm 系统未初始化")
        agent._coordinator.disable_swarm()
        return ok(data={"swarm_enabled": False, "message": "Swarm 集群模式已禁用（单次调用和≤4并行仍可用）"})

    # ─── Agent 检查点 API ────────────────────────────────────

    @app.get("/api/agent/checkpoints")
    async def agent_checkpoints(session_id: str = ""):
        """列出当前会话的检查点列表（优先从 SQLite，回退到 Shadow Git）

        Args:
            session_id: 前端持久化的会话 ID（query parameter），用于查询正确的检查点
        """
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"checkpoints": [], "available": False, "version": 0})
        try:
            if hasattr(agent, '_middleware_chain') and agent._middleware_chain:
                for mw in agent._middleware_chain._middlewares:
                    from ..middleware.shadow_checkpoint import CheckpointMiddleware
                    if isinstance(mw, CheckpointMiddleware):
                        # 如果前端传了 session_id，先更新中间件的 instance_id
                        if session_id and session_id != mw.instance_id:
                            mw._instance_id = session_id

                        # 优先从 SQLite 获取（~1ms）
                        commits = mw.get_checkpoints(count=50)
                        if commits:
                            # SQLite 返回的检查点已含 file_count
                            # 统一前端字段名
                            for c in commits:
                                # 映射 created_at → timestamp（前端统一用 timestamp）
                                if "created_at" in c and "timestamp" not in c:
                                    c["timestamp"] = c["created_at"]
                                if "file_count" in c and "diff_count" not in c:
                                    c["diff_count"] = c["file_count"]
                                # SQLite 的 id → hash（兼容前端）
                                if "id" in c and "hash" not in c:
                                    c["hash"] = c.get("checkpoint_hash", "") or str(c["id"])
                                if "meta" not in c:
                                    c["meta"] = {
                                        "source": c.get("source", "auto"),
                                        "step": c.get("step", 0),
                                        "tool": c.get("tool", ""),
                                        "instance": c.get("session_id", "")[:8],
                                        "duration_ms": c.get("duration_ms"),
                                    }
                            return ok(data={
                                "checkpoints": commits,
                                "available": True,
                                "instance_id": getattr(mw, 'instance_id', ''),
                                "version": mw.global_version,
                            })
                        # 回退到 Shadow Git
                        if mw.checkpointer:
                            cp = mw.checkpointer
                            git_commits = cp.get_commits(count=50)
                            for i, c in enumerate(git_commits):
                                if i < len(git_commits) - 1:
                                    # git_commits 是 DESC 排序，git_commits[i+1] 更旧
                                    c["diff_count"] = cp.get_diff_count(git_commits[i + 1]["hash"], c["hash"])
                                else:
                                    c["diff_count"] = 0
                            return ok(data={
                                "checkpoints": git_commits,
                                "available": True,
                                "instance_id": getattr(mw, 'instance_id', ''),
                                "version": 0,
                            })
        except Exception as e:
            logger.warning(f"获取检查点列表失败: {e}")
        return ok(data={"checkpoints": [], "available": False, "version": 0})

    @app.get("/api/agent/checkpoints/{commit_hash}/diff")
    async def agent_checkpoint_diff(commit_hash: str):
        """获取指定检查点自身的增量差异（该工具调用实际修改的文件）

        优先从 SQLite 快速查询，回退到 Shadow Git diff。
        """
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"diff": [], "summary": {"additions": 0, "deletions": 0, "files_changed": 0}, "error": "Agent 未就绪"})
        try:
            if hasattr(agent, '_middleware_chain') and agent._middleware_chain:
                for mw in agent._middleware_chain._middlewares:
                    from ..middleware.shadow_checkpoint import CheckpointMiddleware
                    if isinstance(mw, CheckpointMiddleware):
                        # 尝试从 SQLite 快速查询（commit_hash 可能是数字 id 或 git hash）
                        fdb = mw.fdb
                        if fdb:
                            try:
                                cp_id = int(commit_hash)
                                # 增量 diff：只返回该检查点自身的变更文件
                                diff_files = fdb.get_checkpoint_diff_files(cp_id)
                                if diff_files:
                                    # 从 Shadow Git 补充 diff 内容
                                    if mw.checkpointer:
                                        cp_git = mw.checkpointer
                                        # 获取该检查点的 git hash
                                        cp_row = fdb.get_checkpoint(cp_id)
                                        git_hash = cp_row.get("checkpoint_hash", "") if cp_row else ""
                                        for f in diff_files:
                                            if not f.get("diff"):
                                                try:
                                                    if git_hash:
                                                        f["diff"] = cp_git.get_incremental_diff_content(git_hash, f["path"], max_lines=80)
                                                    else:
                                                        # 没有 git hash，用文件当前内容生成简易 diff
                                                        import difflib
                                                        full_path = os.path.join(mw._workspace_root, f["path"]) if not os.path.isabs(f["path"]) else f["path"]
                                                        if os.path.isfile(full_path):
                                                            new_lines = open(full_path, encoding="utf-8", errors="replace").readlines()
                                                            diff = difflib.unified_diff([], new_lines, fromfile="/dev/null", tofile=f["path"])
                                                            f["diff"] = "".join(diff)
                                                except Exception:
                                                    pass
                                    total_adds = sum(f.get("additions", 0) for f in diff_files)
                                    total_dels = sum(f.get("deletions", 0) for f in diff_files)
                                    return ok(data={
                                        "diff": diff_files,
                                        "summary": {
                                            "additions": total_adds,
                                            "deletions": total_dels,
                                            "files_changed": len(diff_files),
                                        },
                                    })
                            except (ValueError, TypeError):
                                pass

                        # 回退到 Shadow Git：增量 diff（与父 commit 比较）
                        if mw.checkpointer:
                            cp = mw.checkpointer
                            diff_files = cp.get_incremental_diff(commit_hash)
                            total_adds = 0
                            total_dels = 0
                            for f in diff_files:
                                content = cp.get_incremental_diff_content(commit_hash, f["path"], max_lines=80)
                                f["diff"] = content
                                total_adds += f.get("additions", 0)
                                total_dels += f.get("deletions", 0)
                            return ok(data={
                                "diff": diff_files,
                                "summary": {
                                    "additions": total_adds,
                                    "deletions": total_dels,
                                    "files_changed": len(diff_files),
                                },
                            })
        except Exception as e:
            logger.warning(f"获取 diff 失败: {e}")
        return ok(data={"diff": [], "summary": {"additions": 0, "deletions": 0, "files_changed": 0}, "error": "无差异数据"})

    @app.get("/api/agent/checkpoints/{commit_hash}/diff-count")
    async def agent_checkpoint_diff_count(commit_hash: str):
        """快速获取指定检查点的变更文件数（优先 SQLite）"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"count": 0})
        try:
            if hasattr(agent, '_middleware_chain') and agent._middleware_chain:
                for mw in agent._middleware_chain._middlewares:
                    from ..middleware.shadow_checkpoint import CheckpointMiddleware
                    if isinstance(mw, CheckpointMiddleware):
                        # 尝试 SQLite
                        fdb = mw.fdb
                        if fdb:
                            try:
                                cp_id = int(commit_hash)
                                count = fdb.get_diff_count(cp_id)
                                return ok(data={"count": count})
                            except (ValueError, TypeError):
                                pass
                        # 回退到 Shadow Git
                        if mw.checkpointer:
                            count = mw.checkpointer.get_diff_count(commit_hash)
                            return ok(data={"count": count})
        except Exception as e:
            logger.warning(f"获取 diff-count 失败: {e}")
        return ok(data={"count": 0})

    @app.post("/api/agent/checkpoints/{commit_hash}/restore")
    async def agent_checkpoint_restore(commit_hash: str, req: Request):
        """恢复到指定检查点（files / task / taskAndFiles）"""
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        restore_type = body.get("restore_type", "files")
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"restored": False, "error": "Agent 未就绪"})
        try:
            if not (hasattr(agent, '_middleware_chain') and agent._middleware_chain):
                return ok(data={"restored": False, "error": "无中间件"})
            from ..middleware.shadow_checkpoint import CheckpointMiddleware
            from ..cache.context_reloader import get_context_reloader
            reloader = get_context_reloader()
            from ..agent import sanitize_messages

            for mw in agent._middleware_chain._middlewares:
                if isinstance(mw, CheckpointMiddleware) and mw.checkpointer:
                    cp = mw.checkpointer
                    # 恢复文件
                    if restore_type in ("files", "taskAndFiles"):
                        try:
                            cp.restore_files(commit_hash)
                        except Exception as e:
                            logger.warning(f"恢复文件快照失败: {e}")

                    # 恢复对话历史
                    restored_msgs = None
                    if restore_type in ("task", "taskAndFiles"):
                        try:
                            restored_msgs = reloader.rollback_to_checkpoint(commit_hash)
                            if restored_msgs:
                                restored_msgs = sanitize_messages(restored_msgs)
                                with agent._messages_lock:
                                    agent.messages = restored_msgs
                                mgr = getattr(agent, '_tool_group_mgr', None)
                                if mgr:
                                    mgr.reset_session()
                                agent._instance_tool_schemas = None
                                logger.info(f"检查点消息已恢复到 agent: {len(restored_msgs)} 条")
                        except Exception as e:
                            logger.warning(f"恢复对话失败: {e}")

                    # 构建前端可用的消息列表
                    ui_messages = []
                    if restored_msgs:
                        for msg in restored_msgs:
                            role = msg.get("role", "")
                            content = msg.get("content", "")
                            if role == "system":
                                continue
                            if role == "tool":
                                tool_call_id = msg.get("tool_call_id", "")
                                tool_content = content if isinstance(content, str) else str(content)
                                tool_name = ""
                                for prev in reversed(ui_messages):
                                    if prev.get("role") == "assistant" and prev.get("tool_calls"):
                                        for tc in prev["tool_calls"]:
                                            tc_dict = tc if isinstance(tc, dict) else {}
                                            if tc_dict.get("id") == tool_call_id:
                                                tool_name = tc_dict.get("function", {}).get("name", "")
                                                break
                                        break
                                ui_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "tool_name": tool_name,
                                    "content": tool_content[:500],
                                })
                            elif role == "assistant":
                                entry = {
                                    "role": "assistant",
                                    "content": content if isinstance(content, str) else str(content),
                                }
                                if msg.get("tool_calls"):
                                    entry["tool_calls"] = msg["tool_calls"]
                                ui_messages.append(entry)
                            elif role == "user" and content:
                                ui_messages.append({
                                    "role": "user",
                                    "content": content if isinstance(content, str) else str(content),
                                })

                    return ok(data={
                        "restored": True,
                        "restore_type": restore_type,
                        "commit_hash": commit_hash,
                        "restored_messages": len(restored_msgs or []),
                        "ui_messages": ui_messages,
                    })
        except Exception as e:
            logger.warning(f"恢复检查点失败: {e}")
        return ok(data={"restored": False, "error": str(e)})

    # ─── 多实例集群 API ──────────────────────────────────────

    def _scan_instances(port: int):
        """同步扫描本机其他 TS2 实例"""
        instances = []
        for p in range(6906, 6916):
            if p == port:
                continue
            try:
                import urllib.request
                req = urllib.request.urlopen(
                    f"http://127.0.0.1:{p}/api/system/version",
                    data=b'{}',
                    timeout=2,
                )
                if req.status == 200:
                    data = _json_loads(req.read().decode('utf-8'))
                    instances.append({
                        "port": p,
                        "url": f"http://127.0.0.1:{p}",
                        "version": data.get("data", {}).get("version", "unknown"),
                        "local_ip": data.get("data", {}).get("local_ip", ""),
                    })
            except Exception:
                continue
        return instances

    def _fetch_remote_file(remote_url: str, file_path: str):
        """同步从远端实例获取文件内容"""
        import urllib.request
        # 先获取文件元数据
        meta_req = urllib.request.Request(
            f"{remote_url}/api/file/getFile",
            data=_json_dumps_compact({"path": file_path}).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(meta_req, timeout=30) as resp:
            result = _json_loads(resp.read().decode('utf-8'))
        if result.get("code") != 0:
            return None, result.get("msg", "远端获取失败")
        file_data = result.get("data", {})
        content = file_data.get("content", "")
        entry = file_data.get("entry", {})
        return {"content": content, "entry": entry}, None

    def _fetch_remote_dir(remote_url: str, dir_path: str):
        """同步从远端实例获取目录列表"""
        import urllib.request
        req = urllib.request.Request(
            f"{remote_url}/api/file/readDir",
            data=_json_dumps_compact({"path": dir_path}).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json_loads(resp.read().decode('utf-8'))
        if result.get("code") != 0:
            return None, result.get("msg", "远端获取失败")
        return result.get("data", []), None

    def _fetch_remote_search(remote_url: str, query: str, subdir: str = ""):
        """同步从远端实例搜索文件"""
        import urllib.request
        req = urllib.request.Request(
            f"{remote_url}/api/file/search",
            data=_json_dumps_compact({"query": query, "subdir": subdir}).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = _json_loads(resp.read().decode('utf-8'))
        if result.get("code") != 0:
            return None, result.get("msg", "远端搜索失败")
        return result.get("data", []), None

    def _transfer_file_from_remote(remote_url: str, remote_path: str, local_path: str):
        """同步从远端实例传输文件到本地"""
        file_data, err = _fetch_remote_file(remote_url, remote_path)
        if err:
            return None, err
        content = file_data["content"]
        # 写入本地
        engine: FileSyncEngine = app.state.sync_engine
        entry = engine.put_file(local_path, content)
        if entry is None:
            return None, "本地写入失败"
        return entry.to_dict(), None

    def _batch_transfer_from_remote(remote_url: str, file_pairs: list):
        """同步批量从远端传输文件到本地

        file_pairs: [{"remote_path": "...", "local_path": "..."}, ...]
        """
        results = []
        ok_count = 0
        fail_count = 0
        for pair in file_pairs:
            remote_path = pair.get("remote_path", "")
            local_path = pair.get("local_path", remote_path)  # 默认同路径
            entry, err = _transfer_file_from_remote(remote_url, remote_path, local_path)
            if err:
                fail_count += 1
                results.append({"path": remote_path, "success": False, "error": err})
            else:
                ok_count += 1
                results.append({"path": remote_path, "success": True, "entry": entry})
        return {"ok": ok_count, "fail": fail_count, "results": results}, None

    @app.get("/api/cluster/instances")
    async def cluster_instances():
        """发现本机其他 TS2 实例"""
        instances = await _run_data(_scan_instances, app.state.port)
        # 加入自身信息
        self_info = {
            "port": app.state.port,
            "url": f"http://127.0.0.1:{app.state.port}",
            "version": "1.0.0",
            "local_ip": app.state.local_ip,
            "self": True,
            "workspace": str(app.state.workspace_dir),
        }
        return ok(data={"self": self_info, "peers": instances})

    @app.post("/api/cluster/remote/readDir")
    async def cluster_remote_read_dir(req: Request):
        """从远端实例读取目录"""
        body = await req.json()
        remote_url = body.get("remote_url", "")
        dir_path = body.get("path", "")
        if not remote_url:
            return err(msg="缺少 remote_url")
        result, error = await _run_data(_fetch_remote_dir, remote_url, dir_path)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/cluster/remote/search")
    async def cluster_remote_search(req: Request):
        """从远端实例搜索文件"""
        body = await req.json()
        remote_url = body.get("remote_url", "")
        query = body.get("query", "")
        subdir = body.get("subdir", "")
        if not remote_url or not query:
            return err(msg="缺少 remote_url 或 query")
        result, error = await _run_data(_fetch_remote_search, remote_url, query, subdir)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/cluster/transfer")
    async def cluster_transfer(req: Request):
        """从远端实例传输文件到本地（单个文件）"""
        body = await req.json()
        remote_url = body.get("remote_url", "")
        remote_path = body.get("remote_path", "")
        local_path = body.get("local_path", remote_path)
        if not remote_url or not remote_path:
            return err(msg="缺少 remote_url 或 remote_path")
        result, error = await _run_data(_transfer_file_from_remote, remote_url, remote_path, local_path)
        if error:
            return err(msg=error)
        return ok(data=result)

    @app.post("/api/cluster/transfer/batch")
    async def cluster_transfer_batch(req: Request):
        """从远端实例批量传输文件到本地"""
        body = await req.json()
        remote_url = body.get("remote_url", "")
        file_pairs = body.get("files", [])
        if not remote_url or not file_pairs:
            return err(msg="缺少 remote_url 或 files")
        result, error = await _run_data(_batch_transfer_from_remote, remote_url, file_pairs)
        if error:
            return err(msg=error)
        return ok(data=result)

    # ─── Health Check ──────────────────────────────────────

    @app.get("/api/ping")
    @app.head("/api/ping")
    async def ping():
        return ok(data={"status": "ok"})

    # ─── Mobile Bootstrap API ──────────────────────────────

    @app.get("/api/mobile/bootstrap")
    async def mobile_bootstrap():
        """移动端启动引导：一次请求获取所有模块数据"""
        workspace_dir = app.state.workspace_dir

        # 并行获取各模块数据
        tasks_data, courses_data, bookmarks_data, projects_data, agent_data, push_data = await asyncio.gather(
            _run_data(_read_tasks_data, workspace_dir),
            _run_data(_read_courses_data, workspace_dir),
            _run_data(_read_bookmarks_data, workspace_dir),
            _run_data(_read_projects_data, workspace_dir),
            _run_data(_read_agent_status, workspace_dir),
            _run_push(_get_push_dashboard, workspace_dir),
            return_exceptions=True,
        )

        return ok(data={
            "tasks": tasks_data if not isinstance(tasks_data, Exception) else [],
            "courses": courses_data if not isinstance(courses_data, Exception) else [],
            "bookmarks": bookmarks_data if not isinstance(bookmarks_data, Exception) else [],
            "projects": projects_data if not isinstance(projects_data, Exception) else [],
            "agent": agent_data if not isinstance(agent_data, Exception) else {"available": False},
            "push": push_data if not isinstance(push_data, Exception) else {},
            "server": {
                "version": "1.0.0",
                "local_ip": app.state.local_ip,
                "port": app.state.port,
                "uptime": time.time() - app.state.start_time,
            },
        })

    # ─── 启动/关闭事件 ──────────────────────────────────────

    @app.on_event("startup")
    async def on_startup():
        engine: FileSyncEngine = app.state.sync_engine
        # 捕获主事件循环引用（用于线程池安全的事件通知）
        try:
            engine._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            engine._main_loop = asyncio.get_event_loop()
        # 设置 server_tools 的主事件循环引用
        try:
            from .server_tools import set_main_loop
            set_main_loop(asyncio.get_running_loop())
        except Exception:
            pass
        # Run scan in background to avoid blocking startup
        import threading
        def _bg_scan():
            try:
                engine.scan_file_tree()
            except Exception as e:
                logger.warning(f"Background scan error: {e}")
        threading.Thread(target=_bg_scan, daemon=True).start()
        local_ip = app.state.local_ip
        logger.info(f"TS2 Server started: {host}:{port}, workspace={workspace_dir}")
        logger.info(f"LAN access: http://{local_ip}:{port}")

        # 启动定时推送任务
        async def _periodic_push():
            """每5分钟推送一次 dashboard 数据到所有 WebSocket 客户端"""
            while True:
                await asyncio.sleep(300)  # 5分钟
                try:
                    ws_mgr = app.state.ws_manager
                    if ws_mgr and ws_mgr.get_session_count() > 0:
                        push_data = await _run_push(_get_push_dashboard, app.state.workspace_dir)
                        await ws_mgr.broadcast("pushDashboard", data=push_data)
                except Exception as e:
                    logger.warning(f"Periodic push error: {e}")

        asyncio.create_task(_periodic_push())

    @app.on_event("shutdown")
    async def on_shutdown():
        engine: FileSyncEngine = app.state.sync_engine
        await engine.stop_watching()
        # 清理线程池，防止僵尸线程阻止进程退出
        _file_executor.shutdown(wait=False)
        _data_executor.shutdown(wait=False)
        _agent_executor.shutdown(wait=False)
        _push_executor.shutdown(wait=False)
        # 清理 Web Agent（释放 LLM 连接等资源）
        nonlocal _web_agent
        if _web_agent is not None:
            _web_agent = None
        logger.info("TS2 Server shutdown complete")

    # ─── PDF 智能阅读 API ──────────────────────────────────────

    from .pdf_service import extract_pdf_text, index_pdf, query_pdf

    class PdfExtractRequest(BaseModel):
        file_path: str

    class PdfIndexRequest(BaseModel):
        file_path: str

    class PdfQueryRequest(BaseModel):
        query: str
        top_k: int = 4

    @app.post("/api/pdf/extract")
    async def pdf_extract(req: PdfExtractRequest, request: Request = None):
        """提取 PDF 文本内容"""
        try:
            abs_path = sync_engine._absolute_path(req.file_path)
        except ValueError:
            if not _is_resource_path(req.file_path, app.state.workspace_dir):
                return err(msg="路径不在允许的读取目录中")
            if not await check_auth(request, load_api_config()):
                return err(msg="未授权，请提供有效 token 或授权码")
            abs_path = Path(req.file_path).resolve()
        if not os.path.isfile(abs_path):
            return err(msg=f"文件不存在: {req.file_path}")
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, extract_pdf_text, str(abs_path)
            )
            return ok(data=result)
        except Exception as e:
            return err(msg=f"PDF 提取失败: {e}")

    @app.post("/api/pdf/index")
    async def pdf_index(req: PdfIndexRequest, request: Request = None):
        """将 PDF 索引到 RAG 向量库"""
        try:
            abs_path = sync_engine._absolute_path(req.file_path)
        except ValueError:
            if not _is_resource_path(req.file_path, app.state.workspace_dir):
                return err(msg="路径不在允许的读取目录中")
            if not await check_auth(request, load_api_config()):
                return err(msg="未授权，请提供有效 token 或授权码")
            abs_path = Path(req.file_path).resolve()
        if not os.path.isfile(abs_path):
            return err(msg=f"文件不存在: {req.file_path}")
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, index_pdf, str(abs_path), app.state.workspace_dir
            )
            return ok(data=result)
        except Exception as e:
            return err(msg=f"PDF 索引失败: {e}")

    @app.post("/api/pdf/query")
    async def pdf_query(req: PdfQueryRequest):
        """对已索引 PDF 进行 RAG 查询"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, query_pdf, req.query, app.state.workspace_dir, req.top_k
            )
            return ok(data=result)
        except Exception as e:
            return err(msg=f"PDF 查询失败: {e}")

    @app.post("/api/pdf/chat")
    async def pdf_chat(req: AgentChatRequest):
        """PDF AI 对话 — 先 RAG 检索，再注入 Agent 上下文"""
        agent = _get_web_agent(app.state.workspace_dir)
        if agent is None:
            return ok(data={"reply": "Agent 未初始化", "source": "error"})

        # RAG 检索相关内容
        contexts = []
        try:
            rag_result = await asyncio.get_event_loop().run_in_executor(
                None, query_pdf, req.message, app.state.workspace_dir, 4
            )
            contexts = rag_result.get("results", [])
        except Exception:
            pass

        # 构造带 PDF 上下文的消息
        if contexts:
            context_text = "\n\n".join(
                f"[{c['file_name']} 第{c['page']}页]\n{c['content']}"
                for c in contexts
            )
            enhanced_message = (
                f"以下是与用户问题相关的 PDF 内容：\n\n{context_text}\n\n"
                f"用户问题：{req.message}\n\n请基于以上 PDF 内容回答问题。"
            )
        else:
            enhanced_message = req.message

        try:
            reply = await asyncio.wait_for(
                _run_agent(agent.chat, enhanced_message),
                timeout=300.0
            )
            return ok(data={"reply": reply, "source": "pdf_rag", "contexts": contexts})
        except asyncio.TimeoutError:
            return ok(data={"reply": "处理超时", "source": "timeout"})
        except Exception as e:
            return ok(data={"reply": f"处理出错：{e}", "source": "error"})

    # ─── /vditor/ 路由（APP 端离线时 cdn 为 /vditor，映射到 static/vditor/）────
    @app.get("/vditor/{file_path:path}")
    async def vditor_fallback(file_path: str):
        vditor_file = static_dir / "vditor" / file_path
        if vditor_file.exists() and vditor_file.is_file():
            return FileResponse(str(vditor_file))
        return HTMLResponse(content="", status_code=404)

    # ─── 静态文件挂载（必须在 catch-all 路由之前）────────────────
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ─── SPA fallback（必须在所有 API 路由和 mount 之后）──────────────
    @app.get("/{path:path}", response_class=HTMLResponse)
    async def spa_fallback(path: str):
        """SPA 路由 fallback — 非 /api/ 和非静态文件的路径返回 index.html"""
        if path.startswith("api/") or path.startswith("ws") or path.startswith("static/"):
            return HTMLResponse(content="", status_code=404)
        if "." in path.split("/")[-1]:
            return HTMLResponse(content="", status_code=404)
        index_file = static_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="", status_code=404)

    return app


def _convert_office_to_pdf(file_path: str) -> str:
    """将 Office 文件（docx/xlsx/pptx）转换为 PDF，返回 PDF 路径"""
    import tempfile
    import fitz  # PyMuPDF

    ext = os.path.splitext(file_path)[1].lower()
    pdf_path = os.path.join(tempfile.gettempdir(), "ts2_office_preview.pdf")

    if ext == ".docx":
        from docx import Document
        doc = Document(file_path)
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=595, height=842)  # A4
        y = 50
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                y += 12
                continue
            # 自动换行
            remaining = text
            while remaining:
                # 计算每行能放多少字符
                chars_per_line = 70
                line = remaining[:chars_per_line]
                remaining = remaining[chars_per_line:]
                if y > 800:
                    page = pdf_doc.new_page(width=595, height=842)
                    y = 50
                page.insert_text((50, y), line, fontsize=11, fontname="helv")
                y += 16
        pdf_doc.save(pdf_path)
        pdf_doc.close()

    elif ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        pdf_doc = fitz.open()
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            page = pdf_doc.new_page(width=842, height=595)  # 横向 A4
            page.insert_text((50, 40), f"Sheet: {sheet_name}", fontsize=14, fontname="helv")
            y = 65
            for row in ws.iter_rows(max_row=50, values_only=True):
                if y > 560:
                    page = pdf_doc.new_page(width=842, height=595)
                    y = 40
                line = "  |  ".join(str(c) if c is not None else "" for c in row)
                if line.strip(" |"):
                    page.insert_text((30, y), line[:120], fontsize=9, fontname="helv")
                    y += 14
        wb.close()
        pdf_doc.save(pdf_path)
        pdf_doc.close()

    elif ext == ".pptx":
        from pptx import Presentation
        prs = Presentation(file_path)
        pdf_doc = fitz.open()
        for slide in prs.slides:
            page = pdf_doc.new_page(width=960, height=720)
            y = 40
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text and y < 680:
                            page.insert_text((40, y), text[:100], fontsize=12, fontname="helv")
                            y += 18
        pdf_doc.save(pdf_path)
        pdf_doc.close()

    else:
        raise ValueError(f"不支持的文件类型: {ext}")

    return pdf_path


def _has_module(name: str) -> bool:
    """检测 Python 模块是否可用"""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def run_server(workspace_dir: Optional[str] = None, host: str = "0.0.0.0",
               port: int = 6906, open_browser: bool = True,
               auto_port: bool = True):
    """启动 TS2 服务器

    Args:
        auto_port: 如果为 True，当指定端口被占用时自动递增查找可用端口，
                   支持同一台机器运行多个 TS2 实例
    """
    import uvicorn

    # 自动端口检测：如果默认端口被占用，递增查找可用端口
    actual_port = port
    if auto_port:
        try:
            actual_port = find_available_port(port, host=host)
        except OSError:
            logger.error(f"端口 {port} 已被占用且无法找到可用端口")
            raise
        if actual_port != port:
            logger.info(f"端口 {port} 已被占用，自动切换到 {actual_port}")

    app = create_app(workspace_dir=workspace_dir, host=host, port=actual_port)
    local_ip = get_local_ip()

    if open_browser:
        import webbrowser
        import threading

        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{actual_port}")

        threading.Thread(target=_open, daemon=True).start()

    logger.info(f"Starting TS2 Server on http://{host}:{actual_port}")
    logger.info(f"LAN access from phone: http://{local_ip}:{actual_port}")

    # macOS/Linux 自动启用 uvloop 提升性能
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("已启用 uvloop (高性能事件循环)")
    except ImportError:
        if sys.platform == "darwin":
            logger.info("建议安装 uvloop: pip install uvloop (可显著提升 macOS 响应速度)")

    # 检测 httptools（比默认 h11 更快的 HTTP 解析器）
    try:
        import httptools  # noqa: F401
        logger.info("已启用 httptools (高性能 HTTP 解析)")
    except ImportError:
        if sys.platform == "darwin":
            logger.info("建议安装 httptools: pip install httptools (可提升 HTTP 解析速度)")

    # 检测 orjson（比标准 json 更快的序列化）
    try:
        import orjson  # noqa: F401
        logger.info("已启用 orjson (高性能 JSON 序列化)")
    except ImportError:
        if sys.platform == "darwin":
            logger.info("建议安装 orjson: pip install orjson (可提升 JSON 响应速度)")

    uvicorn.run(
        app,
        host=host,
        port=actual_port,
        log_level="info",
        # 连接保活
        timeout_keep_alive=120,
        # WebSocket 保活
        ws_ping_interval=30,
        ws_ping_timeout=15,
        # 高性能选项（自动检测，有则用）
        http="httptools" if _has_module("httptools") else "h11",
        loop="uvloop" if _has_module("uvloop") else "asyncio",
        # macOS 性能优化：启用 asyncio 的调试模式关闭（减少开销）
        # 并设置合理的缓冲区大小
        h11_max_incomplete_event_size=None,
    )


def run_server_in_thread(workspace_dir: Optional[str] = None,
                         host: str = "0.0.0.0",
                         port: int = 6906,
                         open_browser: bool = True,
                         auto_port: bool = True):
    """在后台线程中启动 TS2 服务器，返回 (uvicorn.Server, threading.Thread, actual_port)

    用于 PyInstaller 打包场景，避免 subprocess 调用 sys.executable 的兼容性问题。
    通过 server.should_exit = True 优雅停止。
    """
    import uvicorn
    from uvicorn.config import Config
    from uvicorn.server import Server

    actual_port = port
    if auto_port:
        try:
            actual_port = find_available_port(port, host=host)
        except OSError:
            logger.error(f"端口 {port} 已被占用且无法找到可用端口")
            raise
        if actual_port != port:
            logger.info(f"端口 {port} 已被占用，自动切换到 {actual_port}")

    app = create_app(workspace_dir=workspace_dir, host=host, port=actual_port)
    local_ip = get_local_ip()

    if open_browser:
        import webbrowser
        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{actual_port}")
        threading.Thread(target=_open, daemon=True).start()

    logger.info(f"Starting TS2 Server on http://{host}:{actual_port}")
    logger.info(f"LAN access from phone: http://{local_ip}:{actual_port}")

    config = Config(
        app=app,
        host=host,
        port=actual_port,
        log_level="info",
        timeout_keep_alive=120,
        ws_ping_interval=30,
        ws_ping_timeout=15,
        http="httptools" if _has_module("httptools") else "h11",
        loop="uvloop" if _has_module("uvloop") else "asyncio",
    )
    server = Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="TS2-Server")
    thread.start()
    return server, thread, actual_port


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server()

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\network.py
================================================

```python
"""
网络访问控制与防火墙管理
参考思源笔记的网络设置：允许/禁止公用网络访问、自动配置防火墙规则
跨平台支持：Windows / macOS / Linux
"""

import logging
import platform
import socket
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_DIR = Path.home() / ".ts2"
CONFIG_FILE = CONFIG_DIR / "network_settings.json"

FIREWALL_RULE_NAME = "TS2 Server"


class NetworkSettings:
    """网络访问设置（参考思源笔记的网络配置）"""

    def __init__(self):
        self.allow_lan: bool = True          # 允许局域网访问
        self.allow_public_network: bool = True  # 允许公用网络访问
        self.allow_usb: bool = True           # 允许 USB 连接（adb reverse）
        self.host: str = "0.0.0.0"           # 监听地址
        self.port: int = 6906                # 监听端口
        self.firewall_configured: bool = False  # 防火墙是否已配置
        self._load()

    def _load(self):
        """加载配置"""
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.allow_lan = data.get("allow_lan", self.allow_lan)
            self.allow_public_network = data.get("allow_public_network", self.allow_public_network)
            self.allow_usb = data.get("allow_usb", self.allow_usb)
            self.host = data.get("host", self.host)
            self.port = data.get("port", self.port)
            self.firewall_configured = data.get("firewall_configured", self.firewall_configured)
        except Exception as e:
            logger.warning(f"Load network settings failed: {e}")

    def save(self):
        """保存配置"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "allow_lan": self.allow_lan,
            "allow_public_network": self.allow_public_network,
            "allow_usb": self.allow_usb,
            "host": self.host,
            "port": self.port,
            "firewall_configured": self.firewall_configured,
        }
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_effective_host(self) -> str:
        """根据设置返回实际监听地址"""
        if not self.allow_lan and not self.allow_public_network:
            return "127.0.0.1"
        return self.host

    def to_dict(self) -> dict:
        return {
            "allow_lan": self.allow_lan,
            "allow_public_network": self.allow_public_network,
            "allow_usb": self.allow_usb,
            "host": self.get_effective_host(),
            "port": self.port,
            "firewall_configured": self.firewall_configured,
            "platform": platform.system(),
        }


def get_all_network_interfaces() -> List[Dict[str, str]]:
    """获取所有网络接口及 IP 地址"""
    interfaces = []
    try:
        hostname = socket.gethostname()
        # 获取所有 IP 地址
        addrs = socket.getaddrinfo(hostname, None)
        seen = set()
        for addr in addrs:
            ip = addr[4][0]
            if ip in seen or ip.startswith("127.") or ":" in ip:
                continue
            seen.add(ip)
            interfaces.append({
                "ip": ip,
                "family": "IPv4",
            })
    except Exception as e:
        logger.warning(f"Get network interfaces failed: {e}")
    return interfaces


def get_network_profiles() -> List[Dict[str, str]]:
    """获取网络配置文件类别（仅 Windows）"""
    profiles = []
    if platform.system() != "Windows":
        return profiles
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-NetConnectionProfile | Select-Object Name, NetworkCategory, IPv4Connectivity | ConvertTo-Json"],
            capture_output=True, timeout=10
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if text:
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                profiles.append({
                    "name": item.get("Name", ""),
                    "category": item.get("NetworkCategory", ""),
                    "connectivity": item.get("IPv4Connectivity", ""),
                })
    except Exception as e:
        logger.warning(f"Get network profiles failed: {e}")
    return profiles


def configure_firewall(port: int, allow: bool = True) -> Tuple[bool, str]:
    """
    配置防火墙规则（跨平台）
    
    Returns:
        (success, message)
    """
    system = platform.system()

    if system == "Windows":
        return _configure_firewall_windows(port, allow)
    elif system == "Darwin":
        return _configure_firewall_macos(port, allow)
    elif system == "Linux":
        return _configure_firewall_linux(port, allow)
    else:
        return False, f"Unsupported platform: {system}"


def _configure_firewall_windows(port: int, allow: bool) -> Tuple[bool, str]:
    """Windows 防火墙配置"""
    action = "allow" if allow else "block"
    direction = "in"
    logger.info(f"[防火墙] 开始配置 Windows 防火墙, port={port}, allow={allow}")

    try:
        # 检查规则是否已存在
        check = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}"],
            capture_output=True, timeout=5
        )
        stdout_text = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
        stderr_text = check.stderr.decode("utf-8", errors="replace") if check.stderr else ""
        rule_exists = "No rules match" not in stdout_text and check.returncode == 0
        logger.info(f"[防火墙] 规则检查结果: exists={rule_exists}, stdout_len={len(stdout_text)}")

        if allow:
            if rule_exists:
                # 规则已存在：更新端口和 profile（确保所有网络类型都被放行）
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "set", "rule",
                     f"name={FIREWALL_RULE_NAME}", "new",
                     f"dir={direction}", f"action={action}",
                     "protocol=TCP", f"localport={port}",
                     "profile=domain,private,public"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                logger.info(f"[防火墙] 更新规则: returncode={result.returncode}, stdout={stdout[:100]}, stderr={stderr[:100]}")
                if result.returncode == 0:
                    return True, f"防火墙规则已更新（端口 {port}/TCP，覆盖域/专用/公用网络）"
                else:
                    return False, f"更新防火墙规则失败: {stderr.strip() or stdout.strip()}"
            else:
                # 规则不存在：新增
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "add", "rule",
                     f"name={FIREWALL_RULE_NAME}", f"dir={direction}", f"action={action}",
                     "protocol=TCP", f"localport={port}",
                     "profile=domain,private,public"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                logger.info(f"[防火墙] 添加规则: returncode={result.returncode}, stdout={stdout[:100]}, stderr={stderr[:100]}")
                if result.returncode == 0:
                    return True, f"防火墙规则已添加（端口 {port}/TCP，覆盖域/专用/公用网络）"
                else:
                    if "requires elevation" in stderr.lower() or "access is denied" in stderr.lower():
                        return False, "需要管理员权限。请以管理员身份运行程序，或手动执行：\nnetsh advfirewall firewall add rule name=\"TS2 Server\" dir=in action=allow protocol=TCP localport={port} profile=domain,private,public".format(port=port)
                    return False, f"添加防火墙规则失败: {stderr.strip() or stdout.strip()}"
        else:
            if rule_exists:
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule",
                     f"name={FIREWALL_RULE_NAME}"],
                    capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
                logger.info(f"[防火墙] 删除规则: returncode={result.returncode}, stdout={stdout[:100]}")
                if result.returncode == 0:
                    return True, "防火墙规则已删除"
                return False, f"删除防火墙规则失败: {stdout.strip()}"
            return True, "无需删除（规则不存在）"

    except subprocess.TimeoutExpired:
        return False, "防火墙配置超时"
    except Exception as e:
        logger.exception("[防火墙] 配置异常")
        return False, f"防火墙配置失败: {e}"


def _configure_firewall_macos(port: int, allow: bool) -> Tuple[bool, str]:
    """macOS 防火墙配置（pfctl）"""
    try:
        anchor_name = "ts2_server"

        if allow:
            # 添加 pf 规则允许端口
            rule = f"pass in proto tcp from any to any port {port}\n"
            result = subprocess.run(
                ["sudo", "pfctl", "-ef", anchor_name, "-f", "-"],
                input=rule.encode(), capture_output=True, timeout=10
            )
            # macOS 防火墙通常默认允许，主要确保应用不被阻止
            # 检查应用防火墙
            check = subprocess.run(
                ["sudo", "/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                capture_output=True, timeout=5
            )
            output = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
            if "enabled" in output.lower():
                return True, f"macOS 防火墙已启用，端口 {port} 需要在系统设置中允许 Python"
            return True, f"macOS 防火墙未启用，端口 {port} 可直接访问"
        else:
            return True, "macOS 防火墙规则已移除"

    except subprocess.TimeoutExpired:
        return False, "防火墙配置超时"
    except Exception as e:
        return False, f"macOS 防火墙配置失败: {e}"


def _configure_firewall_linux(port: int, allow: bool) -> Tuple[bool, str]:
    """Linux 防火墙配置（iptables/ufw/firewalld）"""
    messages = []

    # 尝试 ufw
    try:
        check_ufw = subprocess.run(["which", "ufw"], capture_output=True, timeout=3)
        if check_ufw.returncode == 0:
            if allow:
                result = subprocess.run(
                    ["sudo", "ufw", "allow", f"{port}/tcp"],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    messages.append(f"ufw: 端口 {port}/TCP 已放行")
                else:
                    messages.append("ufw: 需要 sudo 权限")
            else:
                subprocess.run(["sudo", "ufw", "delete", "allow", f"{port}/tcp"],
                               capture_output=True, timeout=10)
                messages.append("ufw: 规则已删除")
    except Exception:
        pass

    # 尝试 firewalld
    try:
        check_firewalld = subprocess.run(["which", "firewall-cmd"], capture_output=True, timeout=3)
        if check_firewalld.returncode == 0:
            if allow:
                result = subprocess.run(
                    ["sudo", "firewall-cmd", "--permanent", "--add-port", f"{port}/tcp"],
                    capture_output=True, timeout=10
                )
                subprocess.run(["sudo", "firewall-cmd", "--reload"],
                               capture_output=True, timeout=10)
                if result.returncode == 0:
                    messages.append(f"firewalld: 端口 {port}/TCP 已放行")
                else:
                    messages.append("firewalld: 需要 sudo 权限")
            else:
                subprocess.run(["sudo", "firewall-cmd", "--permanent", "--remove-port", f"{port}/tcp"],
                               capture_output=True, timeout=10)
                subprocess.run(["sudo", "firewall-cmd", "--reload"],
                               capture_output=True, timeout=10)
                messages.append("firewalld: 规则已删除")
    except Exception:
        pass

    # 尝试 iptables
    try:
        check_iptables = subprocess.run(["which", "iptables"], capture_output=True, timeout=3)
        if check_iptables.returncode == 0 and not messages:
            if allow:
                result = subprocess.run(
                    ["sudo", "iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0:
                    messages.append(f"iptables: 端口 {port}/TCP 已放行")
                else:
                    messages.append("iptables: 需要 sudo 权限")
            else:
                subprocess.run(
                    ["sudo", "iptables", "-D", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                    capture_output=True, timeout=10
                )
                messages.append("iptables: 规则已删除")
    except Exception:
        pass

    if messages:
        return True, "; ".join(messages)
    return False, "未找到可用的防火墙工具（ufw/firewalld/iptables）"


def set_network_profile_private() -> Tuple[bool, str]:
    """
    将 Windows 网络配置文件设为"专用"（允许局域网发现和访问）
    参考思源笔记：自动将网络设为专用以允许局域网访问
    """
    if platform.system() != "Windows":
        return True, "非 Windows 平台，无需设置"

    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Set-NetConnectionProfile -NetworkCategory Private"],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            return True, "网络配置文件已设为专用"
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        if "access denied" in stderr.lower() or "requires elevation" in stderr.lower():
            return False, "需要管理员权限设置网络类别"
        return False, f"设置失败: {stderr.strip()}"
    except Exception as e:
        return False, f"设置失败: {e}"


def check_network_access(port: int) -> Dict[str, any]:
    """
    检查网络访问状态
    返回各接口的可访问性
    """
    result = {
        "localhost_accessible": False,
        "lan_accessible": False,
        "interfaces": get_all_network_interfaces(),
        "profiles": get_network_profiles(),
        "firewall_rule_exists": False,
        "recommendations": [],
    }

    # 检查 localhost
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", port))
        s.close()
        result["localhost_accessible"] = True
    except Exception:
        result["recommendations"].append("服务器未在 localhost 启动")

    # 检查局域网 IP
    for iface in result["interfaces"]:
        ip = iface["ip"]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((ip, port))
            s.close()
            result["lan_accessible"] = True
            iface["accessible"] = True
        except Exception:
            iface["accessible"] = False
            result["recommendations"].append(f"无法通过 {ip} 访问服务器")

    # 检查防火墙规则
    if platform.system() == "Windows":
        try:
            check = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={FIREWALL_RULE_NAME}"],
                capture_output=True, timeout=5
            )
            stdout_text = check.stdout.decode("utf-8", errors="replace") if check.stdout else ""
            result["firewall_rule_exists"] = "No rules match" not in stdout_text and check.returncode == 0
        except Exception:
            pass

    # 生成建议
    if not result["lan_accessible"]:
        if not result["firewall_rule_exists"]:
            result["recommendations"].append("防火墙规则未配置，请点击\"配置防火墙\"按钮")
        for profile in result["profiles"]:
            if profile.get("category") == "Public":
                result["recommendations"].append(
                    f"网络 \"{profile['name']}\" 是公用网络，建议设为专用网络以允许局域网访问"
                )

    return result

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\pdf_service.py
================================================

```python
"""PDF 智能阅读服务 — 文本提取 + RAG 索引 + 问答"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..rag.rag_engine import RAGEngine
from ..rag.document_loader import PdfDocumentLoader

logger = logging.getLogger(__name__)

# 全局 RAG 引擎（懒加载）
_pdf_rag: Optional[RAGEngine] = None


def get_pdf_rag(workspace_dir: str) -> RAGEngine:
    """获取或初始化 PDF RAG 引擎"""
    global _pdf_rag
    if _pdf_rag is None:
        from ..rag.vector_store import ChromaVectorStore, SimpleVectorStore

        persist_dir = os.path.join(workspace_dir, ".ts2_data", "chroma_pdf")
        os.makedirs(persist_dir, exist_ok=True)

        try:
            vector_store = ChromaVectorStore(
                persist_directory=persist_dir,
                collection_name="ts2_pdf_docs"
            )
        except (ImportError, Exception) as e:
            logger.warning(f"ChromaDB 不可用，回退到 SimpleVectorStore: {e}")
            vector_store = SimpleVectorStore(persist_directory=Path(persist_dir))

        _pdf_rag = RAGEngine(vector_store=vector_store)
    return _pdf_rag


def extract_pdf_text(file_path: str) -> Dict[str, Any]:
    """提取 PDF 文本，返回按页组织的内容"""
    loader = PdfDocumentLoader()
    documents = loader.load(file_path)

    pages = []
    for doc in documents:
        pages.append({
            "page": doc.metadata.get("page_number", 0),
            "text": doc.content,
            "is_scanned": doc.metadata.get("is_scanned", False),
        })

    return {
        "file_path": file_path,
        "total_pages": documents[0].metadata.get("total_pages", 0) if documents else 0,
        "pages": pages,
    }


def index_pdf(file_path: str, workspace_dir: str) -> Dict[str, Any]:
    """将 PDF 索引到 RAG 引擎"""
    rag = get_pdf_rag(workspace_dir)
    doc_ids = rag.add_file(file_path)
    return {
        "file_path": file_path,
        "chunk_count": len(doc_ids),
        "doc_ids": doc_ids,
    }


def query_pdf(query: str, workspace_dir: str, top_k: int = 4) -> Dict[str, Any]:
    """对已索引的 PDF 内容进行 RAG 查询"""
    rag = get_pdf_rag(workspace_dir)
    results = rag.retrieve_with_scores(query, top_k=top_k)

    contexts = []
    for doc, score in results:
        contexts.append({
            "content": doc.content,
            "score": round(score, 4),
            "source": doc.source,
            "page": doc.metadata.get("page_number", 0),
            "file_name": doc.metadata.get("file_name", ""),
        })

    return {
        "query": query,
        "results": contexts,
    }

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\server_tools.py
================================================

```python
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

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\stream_bridge.py
================================================

```python
import asyncio
import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class StreamBridge:
    """SSE 流式桥接 — 封装 Agent → SSE 的完整生命周期

    职责:
    - 管理 per-session 的 asyncio.Queue
    - 生成线程安全的回调函数 (_on_token/_on_tool/_on_tool_result)
    - 在 ThreadPoolExecutor 中运行 agent.chat()
    - 提供异步生成器 _stream() 用于 StreamingResponse
    - 处理取消、超时、客户端断开
    """

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None, queue_timeout: float = 300.0):
        self._executor = executor or ThreadPoolExecutor(max_workers=2)
        self._queue_timeout = queue_timeout
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, session_id: str, agent: Any, message: str) -> "StreamSession":
        session = StreamSession(
            session_id=session_id,
            agent=agent,
            message=message,
            executor=self._executor,
            queue_timeout=self._queue_timeout,
        )
        self._active_sessions[session_id] = {
            "session": session,
            "created_at": time.time(),
        }
        return session

    def close_session(self, session_id: str):
        self._active_sessions.pop(session_id, None)

    def get_session_count(self) -> int:
        return len(self._active_sessions)

    def cleanup_stale_sessions(self, max_age: float = 300.0):
        now = time.time()
        stale = [sid for sid, info in self._active_sessions.items()
                 if now - info["created_at"] > max_age]
        for sid in stale:
            logger.info(f"StreamBridge: cleaning stale session {sid}")
            try:
                info = self._active_sessions.pop(sid, None)
                if info:
                    info["session"].cancel()
            except Exception:
                pass


class StreamSession:
    """单次 SSE 流式会话的生命周期管理"""

    def __init__(self, session_id: str, agent: Any, message: str,
                 executor: ThreadPoolExecutor, queue_timeout: float = 90.0):
        self.session_id = session_id
        self.agent = agent
        self.message = message
        self._executor = executor
        self._queue_timeout = queue_timeout
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._main_loop = asyncio.get_event_loop()
        self._cancelled = False
        self._started_at = time.time()
        self._token_count = 0
        self._tool_count = 0

    @property
    def elapsed(self) -> float:
        return time.time() - self._started_at

    def _put(self, data: dict):
        try:
            self._main_loop.call_soon_threadsafe(
                self._message_queue.put_nowait, data
            )
        except Exception as e:
            logger.warning(f"StreamSession._put error: {e}")

    def make_on_token(self) -> Callable[[str], None]:
        def _on_token(token: str):
            if self._cancelled:
                return
            self._token_count += 1
            self._put({"type": "token", "content": token})
        return _on_token

    def make_on_tool(self) -> Callable[[str, dict], None]:
        def _on_tool(name: str, args: dict):
            if self._cancelled:
                return
            self._tool_count += 1
            self._put({"type": "tool_call", "name": name, "args": args})
        return _on_tool

    def make_on_tool_result(self) -> Callable[[str, str], None]:
        def _on_tool_result(name: str, result: str):
            if self._cancelled:
                return
            cp_hash = ""
            try:
                if hasattr(self.agent, '_middleware_chain') and self.agent._middleware_chain:
                    for mw in self.agent._middleware_chain._middlewares:
                        from ..middleware.shadow_checkpoint import CheckpointMiddleware
                        if isinstance(mw, CheckpointMiddleware):
                            cp_id = getattr(mw, '_last_checkpoint_id', 0)
                            if cp_id and cp_id > 0:
                                cp_hash = str(cp_id)
                            break
            except Exception:
                pass
            self._put({
                "type": "tool_result",
                "name": name,
                "result": result[:500],
                "checkpoint_hash": cp_hash,
            })
        return _on_tool_result

    def cancel(self):
        self._cancelled = True
        try:
            if hasattr(self.agent, 'cancel'):
                self.agent.cancel()
        except Exception:
            pass

    async def stream(self) -> AsyncGenerator:
        """异步生成器 — 产生 SSE 格式化事件字符串"""
        agent_future = self._main_loop.run_in_executor(
            self._executor, self._run_agent
        )
        try:
            while not self._cancelled:
                try:
                    msg = await asyncio.wait_for(
                        self._message_queue.get(), timeout=self._queue_timeout
                    )
                except asyncio.TimeoutError:
                    yield self._format_event({"type": "error", "content": "超时"})
                    yield "[DONE]"
                    break

                if msg.get("type") == "done":
                    yield self._format_event(msg)
                    yield "[DONE]"
                    break
                elif msg.get("type") == "error":
                    yield self._format_event(msg)
                    yield "[DONE]"
                    break
                else:
                    yield self._format_event(msg)
        except asyncio.CancelledError:
            self.cancel()
        finally:
            if not agent_future.done():
                agent_future.cancel()

    def _run_agent(self):
        """在 executor 线程中运行 agent.chat()"""
        try:
            logger.info(
                f"StreamSession[{self.session_id}]: starting, "
                f"message={self.message[:50]}..."
            )
            reply = self.agent.chat(
                self.message,
                on_token=self.make_on_token(),
                on_tool=self.make_on_tool(),
                on_tool_result=self.make_on_tool_result(),
                session_id=self.session_id,
            )
            logger.info(
                f"StreamSession[{self.session_id}]: completed, "
                f"reply_len={len(reply) if reply else 0}, "
                f"tokens={self._token_count}, tools={self._tool_count}, "
                f"elapsed={self.elapsed:.1f}s"
            )
            self._put({"type": "done", "content": reply})
        except Exception as e:
            logger.error(f"StreamSession[{self.session_id}]: error: {e}")
            traceback.print_exc()
            self._put({"type": "error", "content": str(e)})

    @staticmethod
    def _format_event(data: dict) -> str:
        """将 dict 格式化为 SSE data: 行"""
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return f"data: {raw}\n\n"

    def get_stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "elapsed": self.elapsed,
            "token_count": self._token_count,
            "tool_count": self._tool_count,
            "cancelled": self._cancelled,
        }


try:
    from typing import AsyncGenerator
except ImportError:
    AsyncGenerator = Any

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\sync.py
================================================

```python
"""
文件同步引擎
参考思源笔记的同步机制 + better-sync-siyuan 的增量同步模式：
- 同步锁（acquireAllLocks/releaseAllLocks）防止并发
- 同步状态管理（SyncStatus 枚举）
- 冲突检测（基于时间戳比较，创建冲突副本）
- 同步历史记录（记录每次同步时间和变更）
- 增量变更检测（hash + mtime）
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import IntEnum

logger = logging.getLogger(__name__)


# ─── 同步状态枚举（参考 better-sync SyncStatus）──────────────────

class SyncStatus(IntEnum):
    """同步状态"""
    None_ = 0
    InProgress = 1
    Failed = 2
    DoneWithConflict = 3
    Done = 4


class SyncFileOperationType(IntEnum):
    """同步文件操作类型（参考 better-sync SyncFileOperationType）"""
    Sync = 0          # 双向同步
    Delete = 1        # 删除
    DeleteAndSync = 2 # 删除后同步（类型不匹配时）
    HandleConflictAndSync = 3  # 冲突处理后同步
    MoveDocs = 4      # 移动文档


@dataclass
class FileEntry:
    """文件条目"""
    path: str  # 相对于工作区的路径
    name: str
    is_dir: bool
    size: int = 0
    modified: float = 0.0
    hash: str = ""
    ext: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncEvent:
    """同步事件"""
    event_type: str  # created, modified, deleted, renamed
    path: str
    old_path: str = ""  # 仅用于 renamed
    timestamp: float = 0.0
    hash: str = ""
    size: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncChange:
    """增量同步变更记录"""
    type: str  # created, modified, deleted, conflict
    path: str
    hash: str = ""
    size: int = 0
    operation: str = ""  # Sync, Delete, HandleConflictAndSync
    conflict_path: str = ""  # 冲突副本路径


@dataclass
class SyncHistoryEntry:
    """同步历史条目"""
    timestamp: float
    status: str  # Done, DoneWithConflict, Failed
    synced_count: int = 0
    conflict_count: int = 0
    deleted_count: int = 0
    duration: float = 0.0
    changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class FileSyncEngine:
    """
    文件同步引擎

    参考 siyuan-android + better-sync-siyuan 的同步架构：
    1. 文件树扫描和索引
    2. 文件变更检测（基于 hash + mtime）
    3. 文件读写操作
    4. 目录操作
    5. 变更事件分发（通过 WebSocket）
    6. 同步锁（参考 better-sync acquireAllLocks/releaseAllLocks）
    7. 同步状态管理（参考 better-sync SyncStatus）
    8. 冲突检测与处理（参考 better-sync ConflictHandler）
    9. 同步历史记录（参考 better-sync SyncHistory）
    """

    # 支持的文件类型
    EDITABLE_EXTENSIONS = {
        ".md", ".rmd", ".txt", ".tex", ".bib",
        ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
        ".r", ".R", ".cpp", ".c", ".h", ".java", ".go", ".rs",
        ".html", ".css", ".xml", ".svg",
        ".sh", ".bat", ".ps1",
        ".sql", ".graphql",
    }

    # 忽略的目录/文件
    IGNORE_PATTERNS = {
        "__pycache__", ".git", ".svn", ".hg", "node_modules",
        ".DS_Store", "Thumbs.db", ".env", ".venv", "venv",
        ".idea", ".vscode", "*.pyc", ".cache",
        "build", ".codex", "Output", "agent_config",
    }

    # 仅暴露这些顶级目录（安全限制，不暴露源代码）
    EXPOSED_DIRS = {"Notes", "bookmarks", "data", "datahub", "projects"}

    # 根目录下允许暴露的特定文件
    EXPOSED_ROOT_FILES = {"bookmarks.json", "courses_structured.json", "task_board.json"}

    # 同步历史文件名
    SYNC_HISTORY_FILE = ".ts2_sync_history.json"

    # 冲突副本后缀
    CONFLICT_SUFFIX = ".conflict"

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._file_index: Dict[str, FileEntry] = {}
        self._last_scan_time: float = 0.0
        self._watching = False
        self._watch_task: Optional[asyncio.Task] = None
        self._on_change_callback = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # 同步锁（参考 better-sync acquireAllLocks/releaseAllLocks + siyuan-android syncing 互斥）
        self._sync_lock = asyncio.Lock()
        self._sync_status: SyncStatus = SyncStatus.None_

        # 同步历史（参考 better-sync SyncHistory）
        self._sync_history: List[SyncHistoryEntry] = []
        self._last_sync_time: float = 0.0
        self._load_sync_history()

        # 同步冷却：避免移动端频繁触发同步
        self._min_sync_interval: float = 10.0  # 最小同步间隔（秒）
        self._last_sync_attempt_time: float = 0.0

    # ─── 同步锁管理（参考 better-sync）─────────────────────────

    def acquire_sync_lock(self) -> bool:
        """尝试获取同步锁（非阻塞），参考 siyuan-android 的 syncing 互斥"""
        if self._sync_lock.locked():
            return False
        # 注意：asyncio.Lock 需要 await，这里用状态标记
        if self._sync_status == SyncStatus.InProgress:
            return False
        self._sync_status = SyncStatus.InProgress
        return True

    def release_sync_lock(self):
        """释放同步锁"""
        self._sync_status = SyncStatus.None_

    def get_sync_status(self) -> SyncStatus:
        """获取当前同步状态"""
        return self._sync_status

    def set_sync_status(self, status: SyncStatus):
        """设置同步状态"""
        self._sync_status = status

    # ─── 同步历史管理（参考 better-sync SyncHistory）───────────

    def _load_sync_history(self):
        """加载同步历史"""
        history_path = self.workspace_dir / self.SYNC_HISTORY_FILE
        if not history_path.exists():
            return
        try:
            data = json.loads(history_path.read_text(encoding="utf-8"))
            for entry_data in data.get("history", []):
                self._sync_history.append(SyncHistoryEntry(
                    timestamp=entry_data.get("timestamp", 0),
                    status=entry_data.get("status", ""),
                    synced_count=entry_data.get("synced_count", 0),
                    conflict_count=entry_data.get("conflict_count", 0),
                    deleted_count=entry_data.get("deleted_count", 0),
                    duration=entry_data.get("duration", 0),
                    changes=entry_data.get("changes", []),
                ))
            self._last_sync_time = data.get("last_sync_time", 0)
            # 只保留最近 50 条
            self._sync_history = self._sync_history[-50:]
        except Exception as e:
            logger.warning(f"Load sync history failed: {e}")

    def _save_sync_history(self):
        """保存同步历史"""
        history_path = self.workspace_dir / self.SYNC_HISTORY_FILE
        try:
            data = {
                "last_sync_time": self._last_sync_time,
                "history": [h.to_dict() for h in self._sync_history[-50:]],
            }
            history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Save sync history failed: {e}")

    def add_sync_history(self, entry: SyncHistoryEntry):
        """添加同步历史条目"""
        self._sync_history.append(entry)
        self._last_sync_time = entry.timestamp
        self._save_sync_history()

    def get_sync_history(self, limit: int = 20) -> List[dict]:
        """获取同步历史"""
        return [h.to_dict() for h in self._sync_history[-limit:]]

    # ─── 冲突检测（参考 better-sync ConflictHandler）───────────

    def detect_conflict(self, rel_path: str, client_modified: float) -> bool:
        """
        检测冲突：当客户端修改时间与服务器端修改时间都晚于上次同步时间时，
        且两者不同，则存在冲突。
        
        参考 better-sync detectConflict:
        if file.timestamp > lastSyncTime for BOTH remotes AND timestamps differ => conflict
        """
        old_entry = self._file_index.get(rel_path)
        if old_entry is None:
            return False
        if self._last_sync_time <= 0:
            return False
        # 服务器端文件在上次同步后被修改，客户端也声称修改了
        server_modified = old_entry.modified
        if server_modified > self._last_sync_time and client_modified > self._last_sync_time:
            # 两端都在上次同步后修改了，可能冲突
            return True
        return False

    def create_conflict_copy(self, rel_path: str) -> Optional[str]:
        """
        创建冲突副本文件。
        
        参考 better-sync createConflictFile: 创建一个带时间戳的冲突副本
        """
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists():
            return None

        timestamp_str = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        stem = abs_path.stem
        suffix = abs_path.suffix
        conflict_name = f"{stem} - Conflict {timestamp_str}{suffix}{self.CONFLICT_SUFFIX}"
        conflict_path = abs_path.parent / conflict_name

        try:
            shutil.copy2(abs_path, conflict_path)
            conflict_rel = self._relative_path(conflict_path)
            logger.info(f"Created conflict copy: {conflict_rel}")
            return conflict_rel
        except (OSError, PermissionError) as e:
            logger.error(f"Create conflict copy failed: {e}")
            return None

    # ─── 增量同步核心（参考 better-sync syncHandler）───────────

    def perform_incremental_sync(self, mobile_switch: bool = False) -> Tuple[List[SyncChange], SyncStatus]:
        """
        执行增量同步（参考 better-sync syncHandler + siyuan-android syncData）
        
        流程：
        1. 检查同步锁（参考 siyuan-android syncing 互斥）
        2. 扫描变更
        3. 检测冲突（参考 better-sync detectConflict）
        4. 创建冲突副本（参考 better-sync createConflictFile）
        5. 更新索引
        6. 记录同步历史（参考 better-sync SyncHistory）
        
        Args:
            mobile_switch: 是否来自移动端切换（参考 siyuan-android mobileSwitch）
        
        Returns:
            (changes, status) 变更列表和同步状态
        """
        start_time = time.time()

        # 0. 冷却检查：避免移动端频繁触发同步
        now = time.time()
        if mobile_switch and (now - self._last_sync_attempt_time) < self._min_sync_interval:
            logger.info(f"Sync cooldown: {now - self._last_sync_attempt_time:.1f}s < {self._min_sync_interval}s, skipping")
            return [], SyncStatus.None_
        self._last_sync_attempt_time = now

        # 1. 检查同步锁
        if not self.acquire_sync_lock():
            logger.info("Sync already in progress, skipping")
            return [], SyncStatus.InProgress

        conflict_count = 0
        deleted_count = 0
        changes: List[SyncChange] = []

        try:
            # 2. 扫描变更
            current_paths = set()
            target = self.workspace_dir
            if target.exists():
                for item in target.rglob("*"):
                    if self._should_ignore(item):
                        continue
                    rel_path = self._relative_path(item)
                    current_paths.add(rel_path)

                    if item.is_dir():
                        continue

                    try:
                        stat = item.stat()
                        new_hash = self._compute_hash(item)
                        old_entry = self._file_index.get(rel_path)

                        if old_entry is None:
                            # 新文件
                            changes.append(SyncChange(
                                type="created", path=rel_path,
                                hash=new_hash, size=stat.st_size,
                                operation="Sync",
                            ))
                        elif old_entry.hash != new_hash or old_entry.modified != stat.st_mtime:
                            # 3. 冲突检测
                            if self._last_sync_time > 0 and old_entry.modified > self._last_sync_time:
                                # 服务器端文件在上次同步后被修改过，可能是冲突
                                # 参考 better-sync: HandleConflictAndSync
                                conflict_path = self.create_conflict_copy(rel_path)
                                if conflict_path:
                                    conflict_count += 1
                                    changes.append(SyncChange(
                                        type="conflict", path=rel_path,
                                        hash=new_hash, size=stat.st_size,
                                        operation="HandleConflictAndSync",
                                        conflict_path=conflict_path,
                                    ))
                                else:
                                    changes.append(SyncChange(
                                        type="modified", path=rel_path,
                                        hash=new_hash, size=stat.st_size,
                                        operation="Sync",
                                    ))
                            else:
                                changes.append(SyncChange(
                                    type="modified", path=rel_path,
                                    hash=new_hash, size=stat.st_size,
                                    operation="Sync",
                                ))
                    except (OSError, PermissionError):
                        continue

                # 检测删除
                for path in list(self._file_index.keys()):
                    if path not in current_paths:
                        changes.append(SyncChange(
                            type="deleted", path=path,
                            operation="Delete",
                        ))
                        deleted_count += 1
                        del self._file_index[path]

            # 4. 更新索引
            self.scan_file_tree()

            # 5. 确定同步状态
            if conflict_count > 0:
                status = SyncStatus.DoneWithConflict
            else:
                status = SyncStatus.Done

            self._sync_status = status

            # 6. 记录同步历史
            duration = time.time() - start_time
            history_entry = SyncHistoryEntry(
                timestamp=time.time(),
                status=status.name,
                synced_count=len(changes),
                conflict_count=conflict_count,
                deleted_count=deleted_count,
                duration=duration,
                changes=[{"type": c.type, "path": c.path, "operation": c.operation} for c in changes],
            )
            self.add_sync_history(history_entry)

            logger.info(f"Incremental sync completed: {len(changes)} changes, {conflict_count} conflicts, {duration:.1f}s")

            return changes, status

        except Exception as e:
            self._sync_status = SyncStatus.Failed
            logger.error(f"Incremental sync failed: {e}")
            return changes, SyncStatus.Failed

        finally:
            self.release_sync_lock()

    def set_change_callback(self, callback):
        """设置文件变更回调（用于通知 WebSocket）"""
        self._on_change_callback = callback
        # 在设置回调时捕获主事件循环
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def _fire_change_event(self, event):
        """触发变更事件，兼容主线程和线程池调用"""
        if not self._on_change_callback:
            return
        loop = self._main_loop or asyncio.get_event_loop()
        try:
            asyncio.get_running_loop()
            # 已在事件循环中，直接 create_task
            asyncio.create_task(self._on_change_callback(event))
        except RuntimeError:
            # 不在事件循环中（线程池），用 run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(self._on_change_callback(event), loop)

    def _should_ignore(self, path: Path) -> bool:
        """检查路径是否应该被忽略"""
        parts = path.parts
        for part in parts:
            if part in self.IGNORE_PATTERNS:
                return True
            for pattern in self.IGNORE_PATTERNS:
                if "*" in pattern:
                    import fnmatch
                    if fnmatch.fnmatch(part, pattern):
                        return True
        return False

    def _is_exposed(self, rel_path: str) -> bool:
        """检查路径是否在暴露范围内"""
        if not self.EXPOSED_DIRS:
            return True
        # 根目录下的特定文件
        if "/" not in rel_path:
            if rel_path in self.EXPOSED_DIRS:
                return True
            if rel_path in self.EXPOSED_ROOT_FILES:
                return True
            return False
        # 子路径：检查顶级目录是否在 EXPOSED_DIRS 中
        top_dir = rel_path.split("/")[0]
        return top_dir in self.EXPOSED_DIRS

    def _relative_path(self, abs_path: Path) -> str:
        """获取相对路径"""
        try:
            return str(abs_path.relative_to(self.workspace_dir)).replace("\\", "/")
        except ValueError:
            return str(abs_path).replace("\\", "/")

    def _absolute_path(self, rel_path: str) -> Path:
        """获取绝对路径。如果 rel_path 本身是绝对路径（资源索引场景），直接返回。"""
        p = Path(rel_path)
        if p.is_absolute():
            return p.resolve()
        # 安全检查：防止路径遍历
        abs_path = (self.workspace_dir / rel_path).resolve()
        try:
            abs_path.relative_to(self.workspace_dir)
        except ValueError:
            raise ValueError(f"Path traversal detected: {rel_path}")
        return abs_path

    def _compute_hash(self, file_path: Path) -> str:
        """计算文件 MD5 hash"""
        try:
            h = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def scan_file_tree(self, subdir: str = "", compute_hash: bool = False) -> List[FileEntry]:
        """扫描文件树（仅暴露允许的目录）"""
        target = self.workspace_dir / subdir if subdir else self.workspace_dir
        if not target.exists():
            return []

        entries = []
        try:
            for item in sorted(target.rglob("*")):
                if self._should_ignore(item):
                    continue
                rel_path = self._relative_path(item)
                if not self._is_exposed(rel_path):
                    continue
                entry = FileEntry(
                    path=rel_path,
                    name=item.name,
                    is_dir=item.is_dir(),
                    ext=item.suffix.lower() if item.suffix else "",
                )
                if not item.is_dir():
                    try:
                        stat = item.stat()
                        entry.size = stat.st_size
                        entry.modified = stat.st_mtime
                        if compute_hash:
                            entry.hash = self._compute_hash(item)
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except (OSError, PermissionError) as e:
            logger.warning(f"Scan error: {e}")

        # 更新索引
        for entry in entries:
            self._file_index[entry.path] = entry
        self._last_scan_time = time.time()

        return entries

    def read_dir(self, rel_path: str = "") -> List[FileEntry]:
        """读取目录内容（仅一层，仅暴露允许的目录）"""
        target = self.workspace_dir / rel_path if rel_path else self.workspace_dir
        if not target.exists() or not target.is_dir():
            return []

        entries = []
        try:
            for item in sorted(target.iterdir()):
                if self._should_ignore(item):
                    continue
                rel = self._relative_path(item)
                if not self._is_exposed(rel):
                    continue
                entry = FileEntry(
                    path=rel,
                    name=item.name,
                    is_dir=item.is_dir(),
                    ext=item.suffix.lower() if item.suffix else "",
                )
                if not item.is_dir():
                    try:
                        stat = item.stat()
                        entry.size = stat.st_size
                        entry.modified = stat.st_mtime
                    except (OSError, PermissionError):
                        continue
                entries.append(entry)
        except (OSError, PermissionError) as e:
            logger.warning(f"Read dir error: {e}")

        return entries

    def get_file(self, rel_path: str) -> Optional[Tuple[str, FileEntry]]:
        """获取文件内容和元信息（仅暴露允许的路径）"""
        if not self._is_exposed(rel_path):
            return None
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists() or abs_path.is_dir():
            return None

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            stat = abs_path.stat()
            entry = FileEntry(
                path=rel_path,
                name=abs_path.name,
                is_dir=False,
                size=stat.st_size,
                modified=stat.st_mtime,
                hash=self._compute_hash(abs_path),
                ext=abs_path.suffix.lower(),
            )
            return content, entry
        except (OSError, PermissionError) as e:
            logger.debug(f"Read file error: {e}")
            return None

    def put_file(self, rel_path: str, content: str) -> Optional[FileEntry]:
        """写入文件（仅允许写入暴露范围内的路径）"""
        if not self._is_exposed(rel_path):
            logger.warning(f"Write blocked (not exposed): {rel_path}")
            return None
        abs_path = self._absolute_path(rel_path)

        # 确保父目录存在
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            is_new = not abs_path.exists()
            abs_path.write_text(content, encoding="utf-8")
            stat = abs_path.stat()
            entry = FileEntry(
                path=rel_path,
                name=abs_path.name,
                is_dir=False,
                size=stat.st_size,
                modified=stat.st_mtime,
                hash=self._compute_hash(abs_path),
                ext=abs_path.suffix.lower(),
            )
            self._file_index[rel_path] = entry

            # 触发变更通知
            if self._on_change_callback:
                event = SyncEvent(
                    event_type="created" if is_new else "modified",
                    path=rel_path,
                    timestamp=time.time(),
                    hash=entry.hash,
                    size=entry.size,
                )
                self._fire_change_event(event)

            return entry
        except (OSError, PermissionError) as e:
            logger.error(f"Write file error: {e}")
            return None

    def remove_file(self, rel_path: str) -> bool:
        """删除文件"""
        abs_path = self._absolute_path(rel_path)
        if not abs_path.exists():
            return False

        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            else:
                abs_path.unlink()

            self._file_index.pop(rel_path, None)

            if self._on_change_callback:
                event = SyncEvent(
                    event_type="deleted",
                    path=rel_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)

            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Remove file error: {e}")
            return False

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """重命名/移动文件"""
        old_abs = self._absolute_path(old_path)
        new_abs = self._absolute_path(new_path)

        if not old_abs.exists():
            return False

        # 确保目标父目录存在
        new_abs.parent.mkdir(parents=True, exist_ok=True)

        try:
            old_abs.rename(new_abs)

            # 更新索引
            self._file_index.pop(old_path, None)
            stat = new_abs.stat()
            entry = FileEntry(
                path=new_path,
                name=new_abs.name,
                is_dir=new_abs.is_dir(),
                size=stat.st_size if not new_abs.is_dir() else 0,
                modified=stat.st_mtime,
                ext=new_abs.suffix.lower() if new_abs.suffix else "",
            )
            self._file_index[new_path] = entry

            if self._on_change_callback:
                event = SyncEvent(
                    event_type="renamed",
                    path=new_path,
                    old_path=old_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)

            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Rename file error: {e}")
            return False

    def create_dir(self, rel_path: str) -> bool:
        """创建目录"""
        abs_path = self._absolute_path(rel_path)
        try:
            abs_path.mkdir(parents=True, exist_ok=True)
            if self._on_change_callback:
                event = SyncEvent(
                    event_type="created",
                    path=rel_path,
                    timestamp=time.time(),
                )
                self._fire_change_event(event)
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Create dir error: {e}")
            return False

    def search_files(self, query: str, subdir: str = "") -> List[FileEntry]:
        """搜索文件（按名称匹配）"""
        query_lower = query.lower()
        results = []
        entries = self.scan_file_tree(subdir)
        for entry in entries:
            if query_lower in entry.name.lower() or query_lower in entry.path.lower():
                results.append(entry)
        return results

    def get_file_stats(self) -> dict:
        """获取文件统计信息"""
        total_files = 0
        total_dirs = 0
        total_size = 0
        extensions: Dict[str, int] = {}

        for entry in self._file_index.values():
            if entry.is_dir:
                total_dirs += 1
            else:
                total_files += 1
                total_size += entry.size
                ext = entry.ext or "other"
                extensions[ext] = extensions.get(ext, 0) + 1

        return {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
            "total_size_human": self._human_size(total_size),
            "extensions": extensions,
            "last_scan": self._last_scan_time,
        }

    @staticmethod
    def _human_size(size: int) -> str:
        """人类可读的文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    async def start_watching(self, interval: float = 2.0):
        """启动文件变更监听"""
        if self._watching:
            return
        self._watching = True
        self._watch_task = asyncio.create_task(self._watch_loop(interval))
        logger.info(f"File watching started for {self.workspace_dir}")

    async def stop_watching(self):
        """停止文件变更监听"""
        self._watching = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        logger.info("File watching stopped")

    async def _watch_loop(self, interval: float):
        """文件变更监听循环"""
        while self._watching:
            try:
                await self._detect_changes()
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
            await asyncio.sleep(interval)

    async def _detect_changes(self):
        """检测文件变更"""
        changes = []
        current_paths = set()

        target = self.workspace_dir
        if not target.exists():
            return

        for item in target.rglob("*"):
            if self._should_ignore(item):
                continue
            rel_path = self._relative_path(item)
            current_paths.add(rel_path)

            if item.is_dir():
                continue

            try:
                stat = item.stat()
                new_hash = self._compute_hash(item)
                old_entry = self._file_index.get(rel_path)

                if old_entry is None:
                    # 新文件
                    changes.append(SyncEvent(
                        event_type="created",
                        path=rel_path,
                        timestamp=time.time(),
                        hash=new_hash,
                        size=stat.st_size,
                    ))
                elif old_entry.hash != new_hash or old_entry.modified != stat.st_mtime:
                    # 修改的文件
                    changes.append(SyncEvent(
                        event_type="modified",
                        path=rel_path,
                        timestamp=time.time(),
                        hash=new_hash,
                        size=stat.st_size,
                    ))
            except (OSError, PermissionError):
                continue

        # 检测删除的文件
        for path in list(self._file_index.keys()):
            if path not in current_paths:
                changes.append(SyncEvent(
                    event_type="deleted",
                    path=path,
                    timestamp=time.time(),
                ))
                del self._file_index[path]

        # 通知变更
        if changes and self._on_change_callback:
            for event in changes:
                await self._on_change_callback(event)

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\tunnel.py
================================================

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frp 隧道管理器 — 将本地端口通过 frp 暴露到公网

配置方式：
1. VPS 上配置 frps.ini:
   [common]
   bind_port = 7000
   token = your_token
   # 分配 privileged ports 需要 root
   # privilege_allow_ports = 6906-6910

2. 本地配置 frpc.ini（或通过 API 动态生成）:
   [common]
   server_addr = VPS公网IP
   server_port = 7000
   token = your_token

   [ts2]
   type = tcp
   local_ip = 127.0.0.1
   local_port = 6906
   remote_port = 6906

3. 启动 frpc: ./frpc -c frpc.ini
"""

import logging
import socket
import select
import subprocess
import threading
import time
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_DIR = Path.home() / ".ts2"
CONFIG_FILE = CONFIG_DIR / "tunnel_settings.json"


@dataclass
class TunnelSettings:
    """隧道配置（支持 frp / serveo / bore）"""
    enabled: bool = False           # 是否启用隧道
    tunnel_type: str = "frp"       # 隧道类型: frp | serveo | bore | localtunnel
    server_addr: str = ""          # frps 服务器地址（VPS 公网 IP，frp 专用）
    server_port: int = 7000        # frps 控制端口
    token: str = ""                # frps 认证 token
    local_port: int = 6906         # 本地 TS2 端口
    remote_port: int = 6906        # 远程端口
    subdomain: str = ""             # 子域名（serveo 专用）
    frpc_path: str = ""            # frpc 可执行文件路径（留空则自动查找）
    bore_path: str = ""            # bore 可执行文件路径（留空则自动查找）
    cf_token: str = ""             # Cloudflare Tunnel Token
    cf_domain: str = ""            # Cloudflare 绑定域名（可选）
    auto_start: bool = False        # 是否随 TS2 启动

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(data: dict) -> "TunnelSettings":
        return TunnelSettings(
            enabled=data.get("enabled", False),
            tunnel_type=data.get("tunnel_type", "frp"),
            server_addr=data.get("server_addr", ""),
            server_port=data.get("server_port", 7000),
            token=data.get("token", ""),
            local_port=data.get("local_port", 6906),
            remote_port=data.get("remote_port", 6906),
            subdomain=data.get("subdomain", ""),
            frpc_path=data.get("frpc_path", ""),
            bore_path=data.get("bore_path", ""),
            cf_token=data.get("cf_token", ""),
            cf_domain=data.get("cf_domain", ""),
            auto_start=data.get("auto_start", False),
        )


class TunnelManager:
    """隧道管理器（支持 frp / serveo / bore）"""

    def __init__(self):
        self._settings = self._load_settings()
        self._tunnel_type = self._settings.tunnel_type or "frp"
        self._frpc_procobj: Optional[subprocess.Popen] = None
        self._ssh_procobj: Optional[subprocess.Popen] = None  # serveo
        self._bore_procobj: Optional[subprocess.Popen] = None  # bore (binary)
        self._bore_sock: Optional[socket.socket] = None       # bore (Python)
        self._bore_remote_port: int = 0                        # bore 分配的远程端口
        self._lt_procobj: Optional[subprocess.Popen] = None   # localtunnel
        self._cf_procobj: Optional[subprocess.Popen] = None   # cloudflared
        self._status = "stopped"      # stopped | running | error
        self._public_url: str = ""
        self._start_time: Optional[float] = None
        self._error_msg: str = ""
        self._monitor_thread: Optional[threading.Thread] = None
        self._subdomain: str = ""      # serveo subdomain

    # ── 配置持久化 ──────────────────────────────────────

    def _load_settings(self) -> TunnelSettings:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return TunnelSettings.from_dict(data)
            except Exception as e:
                logger.warning(f"加载隧道配置失败: {e}")
        return TunnelSettings()

    def _save_settings(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self._settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_settings(self) -> dict:
        return self._settings.to_dict()

    def update_settings(self, **kwargs) -> dict:
        for key, value in kwargs.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
        self._save_settings()
        return self._settings.to_dict()

    # ── frpc 可执行文件查找 ──────────────────────────────

    def _find_frpc(self) -> Optional[str]:
        """自动查找 frpc 可执行文件"""
        # 优先使用配置中的路径
        if self._settings.frpc_path and Path(self._settings.frpc_path).exists():
            return self._settings.frpc_path

        # 在 PATH 中查找
        for name in ("frpc", "frpc.exe"):
            for dir_ in os.environ.get("PATH", "").split(os.pathsep):
                path = Path(dir_).parent / name
                if path.exists():
                    return str(path)
                # 也查找在 PATH/frpc 下
                path2 = Path(dir_) / name
                if path2.exists():
                    return str(path2)

        # 查找 TS2 目录下的 frpc
        candidates = [
            Path.home() / "frp" / "frpc",
            Path.home() / "frp" / "frpc.exe",
            Path.home() / ".ts2" / "frpc",
            Path.home() / ".ts2" / "frpc.exe",
            Path(__file__).parent.parent.parent / "frp" / "frpc",
            Path(__file__).parent.parent.parent / "frp" / "frpc.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)

        return None

    # ── frpc.ini 生成 ──────────────────────────────────

    def _generate_frpc_ini(self) -> str:
        """生成 frpc.ini 配置文件内容"""
        lines = [
            "[common]",
            f"server_addr = {self._settings.server_addr}",
            f"server_port = {self._settings.server_port}",
            f"token = {self._settings.token}",
            "",
            "[ts2]",
            "type = tcp",
            "local_ip = 127.0.0.1",
            f"local_port = {self._settings.local_port}",
            f"remote_port = {self._settings.remote_port}",
        ]
        return "\n".join(lines)

    def _write_frpc_ini(self) -> Path:
        """写入 frpc.ini 到临时文件"""
        ini_path = CONFIG_DIR / "frpc.ini"
        ini_path.write_text(self._generate_frpc_ini(), encoding="utf-8")
        return ini_path

    # ── frpc 进程管理 ─────────────────────────────────

    def _parse_public_url(self, line: str) -> Optional[str]:
        """从 frpc 输出中解析公网访问地址"""
        # TCP 类型: "success" 开头的日志行
        # 示例: [WARN] [client.go:83] [xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx] 
        #        tcp port 6906 -> 127.0.0.1:6906
        # 直接用 IP:PORT 访问
        if "->" in line and "tcp" in line.lower():
            addr = self._settings.server_addr
            port = self._settings.remote_port
            return f"http://{addr}:{port}"
        return None

    def _monitor_frpc(self, proc: subprocess.Popen):
        """监控 frpc 进程输出"""
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                logger.debug(f"[frpc] {line}")

                # 检测连接成功
                if "login to server success" in line.lower() or "start proxy success" in line.lower():
                    self._status = "running"
                    self._public_url = f"http://{self._settings.server_addr}:{self._settings.remote_port}"
                    logger.info(f"frp 隧道已建立: {self._public_url}")

                # 解析实际地址
                url = self._parse_public_url(line)
                if url:
                    self._public_url = url

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "disconnected" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"frp 隧道异常: {line}")
        except Exception as e:
            logger.error(f"frpc 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── serveo 启动 ──────────────────────────────────

    def _start_serveo(self) -> Dict[str, Any]:
        """通过 SSH 到 serveo.net 建立隧道（无需 VPS，无需下载）"""
        import random as _rand

        local_port = self._settings.local_port
        subdomain = self._settings.subdomain or f"ts2-{_rand.randint(10000, 99999)}"
        self._subdomain = subdomain

        # SSH 参数：
        # -o ServerAliveInterval=60  保活
        # -o StrictHostKeyChecking=no 自动接受 host key
        # -o ExitOnForwardFailure=yes 确保端口转发成功
        # -R 转发格式: [子域名:]端口:主机:主机端口
        #   如果指定了子域名，serveo 会分配 subdomain.serveo.net
        cmd = [
            "ssh",
            "-o", "ServerAliveInterval=60",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ExitOnForwardFailure=yes",
            # 转发格式：[子域名:]端口:本地IP:本地端口
            "-R", f"{subdomain}:{local_port}:127.0.0.1:{local_port}",
            "-N",  # 不执行远程命令
            f"{subdomain}@serveo.net",
        ]

        logger.info(f"启动 serveo 隧道: {' '.join(cmd)}")

        try:
            self._ssh_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            # 启动监控线程
            self._monitor_thread = threading.Thread(
                target=self._monitor_serveo,
                args=(self._ssh_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 15 秒）
            for i in range(30):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._ssh_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"SSH 进程已退出（返回码: {self._ssh_procobj.returncode}）\n可能原因：\n1. 校园网限制了外网 SSH 连接（端口 22）\n2. serveo.net 连接被阻断\n建议尝试 bore 方案",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "隧道启动超时（serveo.net 可能无响应）",
            }

        except Exception as e:
            logger.exception("启动 serveo 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 serveo 失败: {e}",
            }

    def _monitor_serveo(self, proc: subprocess.Popen):
        """监控 serveo SSH 连接，解析公网 URL"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[serveo] {line}")

                # serveo 成功时输出类似：
                # "Forwarding HTTP traffic from https://xxx.serveo.net"
                # "Forwarding TCP traffic from port xxx"
                if "Forwarding" in line and ("serveo.net" in line or "port" in line):
                    self._status = "running"
                    # 提取 URL
                    import re as _re
                    m = _re.search(r'https?://[\w\-\.]+\.serveo\.net', line)
                    if m:
                        self._public_url = m.group(0)
                    else:
                        # 提取端口
                        m2 = _re.search(r'port\s+(\d+)', line)
                        if m2:
                            port = m2.group(1)
                            self._public_url = f"https://{self._subdomain}.serveo.net:{port}"
                    logger.info(f"serveo 隧道已建立: {self._public_url}")

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "denied" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"serveo 隧道异常: {line}")

        except Exception as e:
            logger.error(f"serveo 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── bore 启动 ───────────────────────────────────

    def _find_bore(self) -> Optional[str]:
        """查找 bore 可执行文件"""
        if self._settings.bore_path and Path(self._settings.bore_path).exists():
            return self._settings.bore_path

        for name in ("bore", "bore.exe"):
            for dir_ in os.environ.get("PATH", "").split(os.pathsep):
                path = Path(dir_) / name
                if path.exists():
                    return str(path)

        candidates = [
            Path.home() / "bore" / "bore",
            Path.home() / ".local" / "bin" / "bore",
            Path.home() / ".ts2" / "bore",
            Path(__file__).parent.parent.parent / "bore" / "bore",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    def _start_bore(self) -> Dict[str, Any]:
        """通过 bore.pub 建立隧道（纯 Python 实现，无需 bore 二进制）"""
        import struct as _struct

        BORE_HOST = "bore.pub"
        BORE_PORT = 7835
        local_port = self._settings.local_port

        try:
            # 连接到 bore.pub
            logger.info(f"连接 bore.pub:{BORE_PORT} ...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((BORE_HOST, BORE_PORT))

            # 发送本地端口（4 字节大端序）
            sock.sendall(_struct.pack("!I", local_port))
            logger.info(f"已发送本地端口: {local_port}")

            # 接收远程端口（4 字节大端序）
            data = sock.recv(4)
            if len(data) < 4:
                sock.close()
                return {"success": False, "status": "error", "message": "bore 服务器响应无效"}

            remote_port = _struct.unpack("!I", data)[0]
            logger.info(f"bore 分配远程端口: {remote_port}")

            # bore.pub 的公网地址格式
            self._public_url = f"bore://{BORE_HOST}:{remote_port}"
            self._status = "running"
            self._start_time = time.time()

            # 保存 socket 以便 stop() 关闭
            self._bore_sock = sock

            # 启动数据转发线程（relay）
            self._bore_remote_port = remote_port

            def _relay():
                """将 bore 连接的数据转发到本地服务"""
                try:
                    local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    local_sock.connect(("127.0.0.1", local_port))
                    local_sock.setblocking(False)
                    sock.setblocking(False)

                    while True:
                        try:
                            r, _, _ = select.select([sock, local_sock], [], [], 5)
                            if not r:
                                # 超时，检查连接是否还活着
                                continue
                            for s in r:
                                data = s.recv(4096)
                                if not data:
                                    # 连接关闭
                                    return
                                other = local_sock if s is sock else sock
                                other.sendall(data)
                        except BlockingIOError:
                            continue
                        except Exception:
                            return
                except Exception as e:
                    logger.debug(f"bore relay 结束: {e}")
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    try:
                        local_sock.close()
                    except Exception:
                        pass

            # bore 只建立隧道，实际数据由外部连接
            # 通知成功（外部通过 bore://host:port 访问）
            return {
                "success": True,
                "status": "running",
                "public_url": f"bore://{BORE_HOST}:{remote_port}",
                "message": f"隧道已建立，访问 bore://{BORE_HOST}:{remote_port}",
            }

        except Exception as e:
            logger.exception("bore Python 隧道失败")
            self._status = "error"
            self._error_msg = str(e)
            return {
                "success": False,
                "status": "error",
                "message": f"bore 隧道失败: {e}",
            }

    def _start_bore_binary(self) -> Dict[str, Any]:
        """通过 bore 二进制建立隧道（fallback 方案）"""
        bore_path = self._find_bore()
        if not bore_path:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 bore 可执行文件\n\n请下载 bore:\n1. 从 GitHub 下载: https://github.com/ekzhang/bore/releases\n2. Windows: 下载 bore.exe，放在 PATH 中或指定 bore_path",
                "download_url": "https://github.com/ekzhang/bore/releases",
            }

        local_port = self._settings.local_port

        cmd = [bore_path, "tcp", str(local_port)]

        logger.info(f"启动 bore 隧道: {' '.join(cmd)}")

        try:
            self._bore_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_bore,
                args=(self._bore_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 15 秒）
            for i in range(30):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._bore_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"bore 进程已退出（返回码: {self._bore_procobj.returncode}）",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "bore 隧道启动超时",
            }

        except Exception as e:
            logger.exception("启动 bore 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 bore 失败: {e}",
            }

    # ── localtunnel 启动 ───────────────────────────────

    def _start_localtunnel(self) -> Dict[str, Any]:
        """通过 localtunnel (npx localtunnel) 建立隧道，无需 VPS"""
        local_port = self._settings.local_port

        # Windows 上 subprocess 找不到 npx，需要用 npx.cmd 或 shell=True
        npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
        cmd = [npx_cmd, "--yes", "localtunnel@2.0.2", "--port", str(local_port)]

        logger.info(f"启动 localtunnel: {' '.join(cmd)}")

        try:
            self._lt_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_localtunnel,
                args=(self._lt_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            # 等待连接（最多 30 秒，localtunnel 首次可能需要下载包）
            for i in range(60):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._lt_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"localtunnel 进程已退出（返回码: {self._lt_procobj.returncode}）",
                    }

            # 超时但进程仍在运行，可能只是输出延迟，返回 starting 状态
            return {
                "success": True,
                "status": "starting",
                "public_url": self._public_url,
                "message": "localtunnel 正在启动中，请稍后刷新查看状态",
            }

        except Exception as e:
            logger.exception("启动 localtunnel 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 localtunnel 失败: {e}",
            }

    def _monitor_localtunnel(self, proc: subprocess.Popen):
        """监控 localtunnel 连接，解析公网 URL"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[lt] {line}")

                # localtunnel 成功时输出： "your url is: https://xxxx.loca.lt"
                if "your url is:" in line.lower():
                    url = line.split("your url is:", 1)[-1].strip()
                    self._public_url = url
                    self._status = "running"
                    logger.info(f"localtunnel 隧道已建立: {url}")

                # 检测错误
                if "error" in line.lower() or "failed" in line.lower() or "denied" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"localtunnel 异常: {line}")

        except Exception as e:
            logger.error(f"localtunnel 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    def _monitor_bore(self, proc: subprocess.Popen):
        """监控 bore 连接"""
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = str(raw).strip()
                if not line:
                    continue
                logger.debug(f"[bore] {line}")

                # bore 成功时输出类似：
                # "Listening on 0.0.0.0:<N> -> tunnel.robe.io:<N>"
                # "Connected to tunnel.robe.io:<port>"
                if "listening" in line.lower() or "connected" in line.lower():
                    self._status = "running"
                    # 提取端口
                    import re as _re
                    m = _re.search(r':(\d{4,5})', line)
                    if m:
                        port = m.group(1)
                        self._public_url = f"bore://:{port} (请用 bore 客户端连接)"
                    logger.info(f"bore 隧道已建立: {line}")

                if "error" in line.lower() or "failed" in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"bore 隧道异常: {line}")

        except Exception as e:
            logger.error(f"bore 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── Cloudflare Tunnel ──────────────────────────────────

    def _find_cloudflared(self) -> Optional[str]:
        """查找 cloudflared 可执行文件"""
        # 常见路径
        candidates = ["cloudflared"]
        if os.name == "nt":
            candidates.extend([
                "cloudflared.exe",
                os.path.expanduser("~\\scoop\\shims\\cloudflared.exe"),
                os.path.expanduser("~\\AppData\\Local\\cloudflared\\cloudflared.exe"),
                "C:\\Program Files\\cloudflared\\cloudflared.exe",
            ])
        else:
            candidates.extend([
                "/usr/local/bin/cloudflared",
                "/usr/bin/cloudflared",
                os.path.expanduser("~/bin/cloudflared"),
            ])
        for c in candidates:
            try:
                result = subprocess.run([c, "version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    def _start_cloudflare(self) -> Dict[str, Any]:
        """启动 Cloudflare Tunnel"""
        cf_token = self._settings.cf_token
        if not cf_token:
            return {
                "success": False,
                "status": "error",
                "message": "未配置 Cloudflare Tunnel Token\n\n请参考:\n1. 登录 Cloudflare Zero Trust 控制台\n2. 创建 Tunnel 并获取 Token\n3. 在设置中填入 Token",
            }

        cloudflared = self._find_cloudflared()
        if not cloudflared:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 cloudflared\n\n安装方式:\nWindows: winget install Cloudflare.cloudflared\nLinux: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
                "download_url": "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/",
            }

        local_port = self._settings.local_port

        try:
            cmd = [cloudflared, "tunnel", "--no-autoupdate", "run", "--token", cf_token]

            self._cf_procobj = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )

            # 启动监控线程
            threading.Thread(target=self._monitor_cloudflare, daemon=True).start()

            # 等待连接（最多 30 秒）
            for i in range(60):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"Cloudflare 隧道已建立: {self._public_url}",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": "error",
                        "message": self._error_msg or "Cloudflare 隧道启动失败",
                    }

            # 超时但进程仍在运行
            if self._cf_procobj and self._cf_procobj.poll() is None:
                self._status = "starting"
                return {
                    "success": True,
                    "status": "starting",
                    "public_url": self._public_url,
                    "message": "Cloudflare 隧道正在启动中，请稍后刷新查看状态",
                }

            return {
                "success": False,
                "status": "error",
                "message": "Cloudflare 隧道启动超时",
            }

        except FileNotFoundError:
            return {"success": False, "status": "error", "message": "cloudflared 未找到"}
        except Exception as e:
            return {"success": False, "status": "error", "message": str(e)}

    def _monitor_cloudflare(self):
        """监控 cloudflared 进程输出"""
        proc = self._cf_procobj
        if not proc or not proc.stdout:
            return

        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                logger.info(f"[cloudflared] {line}")

                # 检测连接成功
                if "registered tunnel connection" in line.lower() or "connection" in line.lower() and "registered" in line.lower():
                    self._status = "running"
                    self._start_time = time.time()
                    # 如果有配置域名，使用配置的域名
                    if self._settings.cf_domain:
                        self._public_url = f"https://{self._settings.cf_domain}"
                    # 否则尝试从日志中提取
                    elif not self._public_url:
                        self._public_url = "Cloudflare Tunnel (域名在 Cloudflare 控制台查看)"

                # 检测错误
                if "error" in line.lower() and "registered" not in line.lower():
                    self._status = "error"
                    self._error_msg = line
                    logger.warning(f"cloudflared 异常: {line}")

        except Exception as e:
            logger.error(f"cloudflared 监控异常: {e}")
            self._status = "error"
            self._error_msg = str(e)

    # ── 启动/停止 ─────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        """启动隧道（根据 tunnel_type 自动分发）"""
        # 检查是否已在运行
        for proc in (self._frpc_procobj, self._ssh_procobj, self._bore_procobj, self._lt_procobj, self._cf_procobj):
            if proc and proc.poll() is None:
                return {
                    "success": True,
                    "status": self._status,
                    "public_url": self._public_url,
                    "message": "隧道已在运行",
                }

        tunnel_type = self._tunnel_type

        if tunnel_type == "serveo":
            return self._start_serveo()
        elif tunnel_type == "bore":
            return self._start_bore()
        elif tunnel_type == "localtunnel":
            return self._start_localtunnel()
        elif tunnel_type == "cloudflare":
            return self._start_cloudflare()
        else:
            return self._start_frp()

    def _start_frp(self) -> Dict[str, Any]:
        """启动 frp 隧道（需要 VPS）"""
        if not self._settings.server_addr:
            return {
                "success": False,
                "status": "error",
                "message": "未配置 frps 服务器地址（server_addr）",
            }

        frpc_path = self._find_frpc()
        if not frpc_path:
            return {
                "success": False,
                "status": "error",
                "message": "未找到 frpc 可执行文件\n\n请下载 frpc:\n1. 从 GitHub 下载: https://github.com/fatedier/frp/releases\n2. 放在 PATH 中，或在设置中指定 frpc_path\n3. Windows 用户下载 .exe 版本",
                "download_url": "https://github.com/fatedier/frp/releases",
            }

        ini_path = self._write_frpc_ini()
        logger.info(f"启动 frpc: {frpc_path} -c {ini_path}")

        try:
            self._frpc_procobj = subprocess.Popen(
                [frpc_path, "-c", str(ini_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._status = "starting"
            self._start_time = time.time()
            self._error_msg = ""

            self._monitor_thread = threading.Thread(
                target=self._monitor_frpc,
                args=(self._frpc_procobj,),
                daemon=True,
            )
            self._monitor_thread.start()

            for i in range(20):
                time.sleep(0.5)
                if self._status == "running":
                    return {
                        "success": True,
                        "status": self._status,
                        "public_url": self._public_url,
                        "message": f"隧道已建立",
                    }
                if self._status == "error":
                    return {
                        "success": False,
                        "status": self._status,
                        "error": self._error_msg,
                        "message": f"隧道启动失败: {self._error_msg}",
                    }
                if self._frpc_procobj.poll() is not None:
                    return {
                        "success": False,
                        "status": "error",
                        "message": f"frpc 进程已退出（返回码: {self._frpc_procobj.returncode}）",
                    }

            return {
                "success": False,
                "status": self._status,
                "message": "隧道启动超时",
            }

        except Exception as e:
            logger.exception("启动 frpc 失败")
            return {
                "success": False,
                "status": "error",
                "message": f"启动 frpc 失败: {e}",
            }

    def stop(self) -> Dict[str, Any]:
        """停止所有类型的隧道"""
        for proc, name in [
            (self._frpc_procobj, "frpc"),
            (self._ssh_procobj, "serveo"),
            (self._bore_procobj, "bore"),
            (self._lt_procobj, "localtunnel"),
            (self._cf_procobj, "cloudflared"),
        ]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                except Exception as e:
                    logger.warning(f"停止 {name} 失败: {e}")

        # 关闭 Python bore socket
        if getattr(self, "_bore_sock", None):
            try:
                self._bore_sock.close()
            except Exception:
                pass
            self._bore_sock = None

        self._frpc_procobj = None
        self._ssh_procobj = None
        self._bore_procobj = None
        self._lt_procobj = None
        self._cf_procobj = None
        self._status = "stopped"
        self._public_url = ""
        self._start_time = None
        self._error_msg = ""
        return {"success": True, "status": "stopped", "message": "隧道已停止"}

    def get_status(self) -> Dict[str, Any]:
        """获取隧道状态"""
        # 检查各进程状态
        for proc, name, err_prefix in [
            (self._frpc_procobj, "frp", "frpc"),
            (self._ssh_procobj, "serveo", "serveo SSH"),
            (self._bore_procobj, "bore", "bore"),
            (self._lt_procobj, "localtunnel", "localtunnel"),
            (self._cf_procobj, "cloudflared", "cloudflared"),
        ]:
            if proc and proc.poll() is not None:
                self._status = "error"
                self._error_msg = f"{err_prefix} 进程已退出（返回码: {proc.returncode}）"

        return {
            "status": self._status,
            "public_url": self._public_url,
            "tunnel_type": self._tunnel_type,
            "server_addr": self._settings.server_addr,
            "local_port": self._settings.local_port,
            "remote_port": self._settings.remote_port,
            "uptime": round(time.time() - self._start_time, 1) if self._start_time else 0,
            "error": self._error_msg,
            "enabled": self._settings.enabled,
            "auto_start": self._settings.auto_start,
        }

    def restart(self) -> Dict[str, Any]:
        """重启隧道"""
        self.stop()
        time.sleep(1)
        return self.start()


# 全局单例
_tunnel_manager: Optional[TunnelManager] = None


def get_tunnel_manager() -> TunnelManager:
    global _tunnel_manager
    if _tunnel_manager is None:
        _tunnel_manager = TunnelManager()
    return _tunnel_manager

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\py\ws.py
================================================

```python
"""
WebSocket 实时推送管理器
参考思源笔记 melody WebSocket 架构：按 app/type 分组会话，支持广播/定向推送
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ClientSession:
    """WebSocket 客户端会话"""
    ws: Any  # WebSocket 连接对象
    app_id: str = ""
    session_id: str = ""
    client_type: str = "main"  # main, filetree, editor, sync
    connected_at: float = 0.0
    subscriptions: Set[str] = field(default_factory=set)  # 订阅的路径/事件

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "session_id": self.session_id,
            "client_type": self.client_type,
            "connected_at": self.connected_at,
            "subscriptions": list(self.subscriptions),
        }


class WebSocketManager:
    """
    WebSocket 连接管理器

    参考思源笔记的 WebSocket 架构：
    - 按 app_id 分组管理会话
    - 支持按 type 广播（main, filetree, editor, sync）
    - 支持定向推送和排除自身广播
    - 事件格式：{"cmd": "...", "code": 0, "msg": "", "data": {}}
    """

    def __init__(self):
        # {app_id: {session_id: ClientSession}}
        self._sessions: Dict[str, Dict[str, ClientSession]] = {}
        self._lock = asyncio.Lock()

    async def add_session(self, ws, app_id: str, session_id: str, client_type: str = "main") -> ClientSession:
        """添加 WebSocket 会话"""
        session = ClientSession(
            ws=ws,
            app_id=app_id,
            session_id=session_id,
            client_type=client_type,
            connected_at=time.time(),
        )
        async with self._lock:
            if app_id not in self._sessions:
                self._sessions[app_id] = {}
            self._sessions[app_id][session_id] = session
        logger.info(f"WS session added: app={app_id}, id={session_id}, type={client_type}")
        return session

    async def remove_session(self, app_id: str, session_id: str):
        """移除 WebSocket 会话"""
        async with self._lock:
            if app_id in self._sessions:
                self._sessions[app_id].pop(session_id, None)
                if not self._sessions[app_id]:
                    del self._sessions[app_id]
        logger.info(f"WS session removed: app={app_id}, id={session_id}")

    async def subscribe(self, app_id: str, session_id: str, path: str):
        """订阅路径变更通知"""
        async with self._lock:
            if app_id in self._sessions and session_id in self._sessions[app_id]:
                self._sessions[app_id][session_id].subscriptions.add(path)

    async def unsubscribe(self, app_id: str, session_id: str, path: str):
        """取消订阅"""
        async with self._lock:
            if app_id in self._sessions and session_id in self._sessions[app_id]:
                self._sessions[app_id][session_id].subscriptions.discard(path)

    def _build_event(self, cmd: str, code: int = 0, msg: str = "", data: Any = None) -> dict:
        """构建事件消息"""
        return {"cmd": cmd, "code": code, "msg": msg, "data": data}

    async def _send_to_session(self, session: ClientSession, event: dict):
        """发送事件到指定会话"""
        try:
            await session.ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to send to session {session.session_id}: {e}")

    async def broadcast(self, cmd: str, code: int = 0, msg: str = "", data: Any = None):
        """广播到所有会话"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_sessions in self._sessions.values():
                for session in app_sessions.values():
                    await self._send_to_session(session, event)

    async def broadcast_by_type(self, client_type: str, cmd: str, code: int = 0,
                                 msg: str = "", data: Any = None):
        """按类型广播"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_sessions in self._sessions.values():
                for session in app_sessions.values():
                    if session.client_type == client_type:
                        await self._send_to_session(session, event)

    async def broadcast_by_app(self, app_id: str, cmd: str, code: int = 0,
                                msg: str = "", data: Any = None):
        """按 app 广播"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            if app_id in self._sessions:
                for session in self._sessions[app_id].values():
                    await self._send_to_session(session, event)

    async def broadcast_exclude_session(self, exclude_app_id: str, exclude_session_id: str,
                                         cmd: str, code: int = 0, msg: str = "",
                                         data: Any = None):
        """广播排除指定会话（用于编辑同步：通知其他客户端）"""
        event = self._build_event(cmd, code, msg, data)
        async with self._lock:
            for app_id, app_sessions in self._sessions.items():
                for session_id, session in app_sessions.items():
                    if app_id == exclude_app_id and session_id == exclude_session_id:
                        continue
                    await self._send_to_session(session, event)

    async def notify_path_change(self, path: str, change_type: str, source_app: str = "",
                                  source_session: str = "", data: Any = None):
        """
        通知路径变更（文件修改/新增/删除）

        只推送给订阅了该路径的会话，排除变更源
        """
        event = self._build_event("filechange", 0, "", {
            "path": path,
            "type": change_type,  # created, modified, deleted, renamed
            "data": data,
            "timestamp": time.time(),
        })
        async with self._lock:
            for app_id, app_sessions in self._sessions.items():
                for session_id, session in app_sessions.items():
                    # 排除变更源
                    if app_id == source_app and session_id == source_session:
                        continue
                    # 检查订阅匹配
                    if self._match_subscription(path, session.subscriptions):
                        await self._send_to_session(session, event)

    def _match_subscription(self, path: str, subscriptions: Set[str]) -> bool:
        """检查路径是否匹配订阅"""
        if not subscriptions:
            return True  # 无订阅 = 接收所有
        for sub in subscriptions:
            if path.startswith(sub) or sub in path:
                return True
        return False

    async def push_msg(self, msg: str, timeout: int = 5000):
        """推送消息通知"""
        await self.broadcast("msg", 0, msg, {"id": f"msg_{int(time.time()*1000)}", "closeTimeout": timeout})

    async def push_err_msg(self, msg: str, timeout: int = 7000):
        """推送错误消息"""
        await self.broadcast("msg", -1, msg, {"id": f"err_{int(time.time()*1000)}", "closeTimeout": timeout})

    async def push_progress(self, code: int, current: int, total: int, msg: str = ""):
        """推送进度"""
        await self.broadcast("progress", code, msg, {"current": current, "total": total})

    async def push_statusbar(self, msg: str):
        """推送状态栏消息"""
        await self.broadcast("statusbar", 0, msg)

    async def push_reload_filetree(self):
        """推送文件树刷新"""
        await self.broadcast_by_type("filetree", "reloadFiletree")

    async def push_reload_editor(self, path: str):
        """推送编辑器刷新"""
        await self.broadcast_by_type("editor", "reloadEditor", data={"path": path})

    def get_session_count(self) -> int:
        """获取当前连接数"""
        count = 0
        for app_sessions in self._sessions.values():
            count += len(app_sessions)
        return count

    def get_sessions_info(self) -> List[dict]:
        """获取所有会话信息"""
        result = []
        for app_id, app_sessions in self._sessions.items():
            for session_id, session in app_sessions.items():
                result.append(session.to_dict())
        return result


# 全局 WebSocket 管理器
_ws_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager

```

