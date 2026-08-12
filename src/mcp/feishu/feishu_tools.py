from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..tools import Tool

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _find_feishu_cli() -> Optional[str]:
    return shutil.which("feishu-cli")


def _run_cli(*args: str, timeout: int = 60, input_data: Optional[str] = None) -> Dict[str, Any]:
    cli = _find_feishu_cli()
    if cli is None:
        return {"error": "feishu-cli not found. Install from https://github.com/riba2534/feishu-cli"}

    cmd = [cli] + list(args)
    env = os.environ.copy()
    if "FEISHU_APP_ID" not in env:
        env["FEISHU_APP_ID"] = os.getenv("FEISHU_APP_ID", "")
    if "FEISHU_APP_SECRET" not in env:
        env["FEISHU_APP_SECRET"] = os.getenv("FEISHU_APP_SECRET", "")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8', errors='replace',
            timeout=timeout,
            env=env,
            input=input_data,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode != 0:
            return {"error": error or output, "returncode": result.returncode}

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"output": output}
    except subprocess.TimeoutExpired:
        return {"error": f"feishu-cli timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _check_feishu_cli() -> bool:
    return _find_feishu_cli() is not None


class FeishuDocReadTool(Tool):
    name = "feishu_doc_read"
    description = "读取飞书文档内容并导出为 Markdown（通过 feishu-cli）"
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID 或 URL"},
            "output_path": {"type": "string", "description": "输出文件路径（可选）", "default": ""},
            "download_images": {"type": "boolean", "description": "是否下载图片", "default": True},
        },
        "required": ["doc_id"],
    }
    category = "feishu"
    keywords = ["feishu", "document", "read", "export", "markdown"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        doc_id = kwargs.get("doc_id", "").strip()
        if not doc_id:
            return json.dumps({"error": "doc_id is required"}, ensure_ascii=False)

        args = ["doc", "export", doc_id]
        output_path = kwargs.get("output_path", "").strip()
        if output_path:
            args.extend(["-o", output_path])
        if kwargs.get("download_images", True):
            args.append("--download-images")

        result = _run_cli(*args, timeout=120)
        return json.dumps(result, ensure_ascii=False)


class FeishuDocWriteTool(Tool):
    name = "feishu_doc_write"
    description = "创建飞书文档或更新文档内容（通过 feishu-cli import/content-update）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "操作: create 或 update", "default": "create"},
            "file_path": {"type": "string", "description": "本地 Markdown 文件路径（create 时使用）"},
            "title": {"type": "string", "description": "文档标题（create 时使用）", "default": ""},
            "doc_id": {"type": "string", "description": "文档 ID（update 时使用）"},
            "mode": {"type": "string", "description": "更新模式: append/overwrite/replace_range", "default": "append"},
            "markdown_content": {"type": "string", "description": "Markdown 内容（update 时使用）"},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "document", "write", "create", "update", "import"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "create").strip()

        if action == "create":
            file_path = kwargs.get("file_path", "").strip()
            if not file_path:
                return json.dumps({"error": "file_path is required for create"}, ensure_ascii=False)
            args = ["doc", "import", file_path]
            title = kwargs.get("title", "").strip()
            if title:
                args.extend(["--title", title])
            args.append("--upload-images")
            result = _run_cli(*args, timeout=180)
            return json.dumps(result, ensure_ascii=False)

        elif action == "update":
            doc_id = kwargs.get("doc_id", "").strip()
            if not doc_id:
                return json.dumps({"error": "doc_id is required for update"}, ensure_ascii=False)
            content = kwargs.get("markdown_content", "")
            mode = kwargs.get("mode", "append")
            args = ["doc", "content-update", doc_id, "--mode", mode, "--markdown", content]
            result = _run_cli(*args, timeout=120)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuMsgTool(Tool):
    name = "feishu_msg"
    description = "发送/读取/搜索飞书消息（通过 feishu-cli msg）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: send/reply/history/list/get/search",
                "default": "send",
            },
            "chat_id": {"type": "string", "description": "聊天 ID（send/list 时使用）"},
            "message_id": {"type": "string", "description": "消息 ID（reply/get 时使用）"},
            "text": {"type": "string", "description": "消息内容（send/reply 时使用）"},
            "user_email": {"type": "string", "description": "用户邮箱（history 查私聊时使用）", "default": ""},
            "query": {"type": "string", "description": "搜索关键词（search 时使用）", "default": ""},
            "limit": {"type": "integer", "description": "消息数量限制", "default": 20},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "message", "send", "read", "search", "chat"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "send").strip()
        limit = kwargs.get("limit", 20)

        if action == "send":
            chat_id = kwargs.get("chat_id", "").strip()
            text = kwargs.get("text", "")
            if not chat_id or not text:
                return json.dumps({"error": "chat_id and text are required"}, ensure_ascii=False)
            result = _run_cli("msg", "send", chat_id, "--text", text)
            return json.dumps(result, ensure_ascii=False)

        elif action == "reply":
            message_id = kwargs.get("message_id", "").strip()
            text = kwargs.get("text", "")
            if not message_id or not text:
                return json.dumps({"error": "message_id and text are required"}, ensure_ascii=False)
            result = _run_cli("msg", "reply", message_id, "--text", text)
            return json.dumps(result, ensure_ascii=False)

        elif action == "history":
            chat_id = kwargs.get("chat_id", "").strip()
            user_email = kwargs.get("user_email", "").strip()
            args = ["msg", "history"]
            if user_email:
                args.extend(["--user-email", user_email])
            elif chat_id:
                args.extend(["--chat-id", chat_id])
            else:
                return json.dumps({"error": "chat_id or user_email is required"}, ensure_ascii=False)
            args.extend(["--limit", str(limit), "--output", "json"])
            result = _run_cli(*args, timeout=60)
            return json.dumps(result, ensure_ascii=False)

        elif action == "list":
            chat_id = kwargs.get("chat_id", "").strip()
            if not chat_id:
                return json.dumps({"error": "chat_id is required"}, ensure_ascii=False)
            result = _run_cli("msg", "list", chat_id, "--limit", str(limit), "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "get":
            message_id = kwargs.get("message_id", "").strip()
            if not message_id:
                return json.dumps({"error": "message_id is required"}, ensure_ascii=False)
            result = _run_cli("msg", "get", message_id, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "search":
            query = kwargs.get("query", "").strip()
            if not query:
                return json.dumps({"error": "query is required"}, ensure_ascii=False)
            result = _run_cli("msg", "search", query, "--limit", str(limit), "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuSheetTool(Tool):
    name = "feishu_sheet"
    description = "操作飞书电子表格（通过 feishu-cli sheet）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: read/write/create/list/append",
                "default": "read",
            },
            "spreadsheet_token": {"type": "string", "description": "表格 token"},
            "sheet_id": {"type": "string", "description": "Sheet ID", "default": ""},
            "range": {"type": "string", "description": "范围（如 Sheet1!A1:C10）", "default": ""},
            "data": {"type": "string", "description": "写入数据（JSON 格式）", "default": ""},
            "title": {"type": "string", "description": "标题（create 时使用）", "default": ""},
        },
        "required": ["action", "spreadsheet_token"],
    }
    category = "feishu"
    keywords = ["feishu", "sheet", "spreadsheet", "excel", "table"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "read").strip()
        token = kwargs.get("spreadsheet_token", "").strip()
        if not token:
            return json.dumps({"error": "spreadsheet_token is required"}, ensure_ascii=False)

        if action == "read":
            range_str = kwargs.get("range", "").strip()
            args = ["sheet", "read", token]
            if range_str:
                args.extend(["--range", range_str])
            args.extend(["--output", "json"])
            result = _run_cli(*args, timeout=60)
            return json.dumps(result, ensure_ascii=False)

        elif action == "write":
            range_str = kwargs.get("range", "").strip()
            data = kwargs.get("data", "").strip()
            if not range_str or not data:
                return json.dumps({"error": "range and data are required"}, ensure_ascii=False)
            result = _run_cli("sheet", "write", token, "--range", range_str, "--data", data)
            return json.dumps(result, ensure_ascii=False)

        elif action == "list":
            result = _run_cli("sheet", "list", token, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "append":
            data = kwargs.get("data", "").strip()
            if not data:
                return json.dumps({"error": "data is required"}, ensure_ascii=False)
            result = _run_cli("sheet", "append", token, "--data", data)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuBitableTool(Tool):
    name = "feishu_bitable"
    description = "操作飞书多维表格（通过 feishu-cli bitable）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: list_tables/list_records/get_record/create_record",
                "default": "list_tables",
            },
            "base_token": {"type": "string", "description": "多维表格 base token"},
            "table_id": {"type": "string", "description": "表 ID", "default": ""},
            "record_id": {"type": "string", "description": "记录 ID", "default": ""},
            "fields": {"type": "string", "description": "字段数据（JSON 格式，create_record 时使用）", "default": ""},
        },
        "required": ["action", "base_token"],
    }
    category = "feishu"
    keywords = ["feishu", "bitable", "multidimensional", "database"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list_tables").strip()
        base_token = kwargs.get("base_token", "").strip()
        if not base_token:
            return json.dumps({"error": "base_token is required"}, ensure_ascii=False)

        if action == "list_tables":
            result = _run_cli("bitable", "table", "list", "--base-token", base_token, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "list_records":
            table_id = kwargs.get("table_id", "").strip()
            if not table_id:
                return json.dumps({"error": "table_id is required"}, ensure_ascii=False)
            result = _run_cli("bitable", "record", "list", "--base-token", base_token, "--table-id", table_id, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "get_record":
            table_id = kwargs.get("table_id", "").strip()
            record_id = kwargs.get("record_id", "").strip()
            if not table_id or not record_id:
                return json.dumps({"error": "table_id and record_id are required"}, ensure_ascii=False)
            result = _run_cli("bitable", "record", "get", "--base-token", base_token, "--table-id", table_id, "--record-id", record_id, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "create_record":
            table_id = kwargs.get("table_id", "").strip()
            fields = kwargs.get("fields", "").strip()
            if not table_id or not fields:
                return json.dumps({"error": "table_id and fields are required"}, ensure_ascii=False)
            result = _run_cli("bitable", "record", "create", "--base-token", base_token, "--table-id", table_id, "--fields", fields)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuDriveTool(Tool):
    name = "feishu_drive"
    description = "操作飞书云盘（上传/下载/搜索/移动文件，通过 feishu-cli drive）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: upload/download/search/list/move",
                "default": "list",
            },
            "file_path": {"type": "string", "description": "本地文件路径（upload 时使用）"},
            "folder_token": {"type": "string", "description": "文件夹 token", "default": ""},
            "file_token": {"type": "string", "description": "文件 token（download/move 时使用）"},
            "query": {"type": "string", "description": "搜索关键词（search 时使用）", "default": ""},
            "output_path": {"type": "string", "description": "下载输出路径（download 时使用）", "default": ""},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "drive", "file", "upload", "download", "search"]
    risk_level = "medium"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list").strip()

        if action == "upload":
            file_path = kwargs.get("file_path", "").strip()
            folder_token = kwargs.get("folder_token", "").strip()
            if not file_path:
                return json.dumps({"error": "file_path is required"}, ensure_ascii=False)
            args = ["drive", "upload", file_path]
            if folder_token:
                args.extend(["--folder-token", folder_token])
            result = _run_cli(*args, timeout=120)
            return json.dumps(result, ensure_ascii=False)

        elif action == "download":
            file_token = kwargs.get("file_token", "").strip()
            output_path = kwargs.get("output_path", "").strip()
            if not file_token:
                return json.dumps({"error": "file_token is required"}, ensure_ascii=False)
            args = ["drive", "download", file_token]
            if output_path:
                args.extend(["-o", output_path])
            result = _run_cli(*args, timeout=120)
            return json.dumps(result, ensure_ascii=False)

        elif action == "search":
            query = kwargs.get("query", "").strip()
            if not query:
                return json.dumps({"error": "query is required"}, ensure_ascii=False)
            result = _run_cli("drive", "search", query, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "list":
            folder_token = kwargs.get("folder_token", "").strip()
            args = ["file", "list"]
            if folder_token:
                args.extend(["--folder-token", folder_token])
            args.extend(["--output", "json"])
            result = _run_cli(*args, timeout=60)
            return json.dumps(result, ensure_ascii=False)

        elif action == "move":
            file_token = kwargs.get("file_token", "").strip()
            folder_token = kwargs.get("folder_token", "").strip()
            if not file_token or not folder_token:
                return json.dumps({"error": "file_token and folder_token are required"}, ensure_ascii=False)
            result = _run_cli("drive", "move", file_token, "--folder-token", folder_token)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuCalendarTool(Tool):
    name = "feishu_calendar"
    description = "操作飞书日历（通过 feishu-cli calendar）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: list/create/get/search",
                "default": "list",
            },
            "calendar_id": {"type": "string", "description": "日历 ID", "default": ""},
            "event_id": {"type": "string", "description": "事件 ID", "default": ""},
            "summary": {"type": "string", "description": "事件标题（create 时使用）", "default": ""},
            "start_time": {"type": "string", "description": "开始时间 RFC3339（create 时使用）", "default": ""},
            "end_time": {"type": "string", "description": "结束时间 RFC3339（create 时使用）", "default": ""},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "calendar", "event", "schedule"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list").strip()

        if action == "list":
            result = _run_cli("calendar", "list", "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "create":
            summary = kwargs.get("summary", "").strip()
            start_time = kwargs.get("start_time", "").strip()
            end_time = kwargs.get("end_time", "").strip()
            if not summary or not start_time or not end_time:
                return json.dumps({"error": "summary, start_time, end_time are required"}, ensure_ascii=False)
            args = ["calendar", "create-event", "--summary", summary, "--start-time", start_time, "--end-time", end_time]
            result = _run_cli(*args)
            return json.dumps(result, ensure_ascii=False)

        elif action == "get":
            event_id = kwargs.get("event_id", "").strip()
            if not event_id:
                return json.dumps({"error": "event_id is required"}, ensure_ascii=False)
            result = _run_cli("calendar", "get-event", event_id, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "search":
            query = kwargs.get("summary", "").strip()
            if not query:
                return json.dumps({"error": "summary (query) is required"}, ensure_ascii=False)
            result = _run_cli("calendar", "search-event", "--query", query, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuWikiTool(Tool):
    name = "feishu_wiki"
    description = "操作飞书知识库（通过 feishu-cli wiki）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: list_spaces/list_nodes/get/export",
                "default": "list_spaces",
            },
            "space_id": {"type": "string", "description": "知识库空间 ID", "default": ""},
            "node_token": {"type": "string", "description": "节点 token", "default": ""},
            "output_path": {"type": "string", "description": "导出路径（export 时使用）", "default": ""},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "wiki", "knowledge", "space"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "list_spaces").strip()

        if action == "list_spaces":
            result = _run_cli("wiki", "space", "list", "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "list_nodes":
            space_id = kwargs.get("space_id", "").strip()
            if not space_id:
                return json.dumps({"error": "space_id is required"}, ensure_ascii=False)
            result = _run_cli("wiki", "node", "list", "--space-id", space_id, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "get":
            node_token = kwargs.get("node_token", "").strip()
            if not node_token:
                return json.dumps({"error": "node_token is required"}, ensure_ascii=False)
            result = _run_cli("wiki", "node", "get", node_token, "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "export":
            node_token = kwargs.get("node_token", "").strip()
            output_path = kwargs.get("output_path", "").strip()
            if not node_token:
                return json.dumps({"error": "node_token is required"}, ensure_ascii=False)
            args = ["wiki", "export", node_token]
            if output_path:
                args.extend(["-o", output_path])
            result = _run_cli(*args, timeout=120)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuAuthTool(Tool):
    name = "feishu_auth"
    description = "飞书认证管理（登录/检查/状态，通过 feishu-cli auth）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: status/check/login",
                "default": "status",
            },
            "scope": {"type": "string", "description": "检查/登录的 scope（check/login 时使用）", "default": ""},
        },
        "required": ["action"],
    }
    category = "feishu"
    keywords = ["feishu", "auth", "login", "oauth", "token"]
    risk_level = "low"

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "status").strip()

        if action == "status":
            result = _run_cli("auth", "status", "--output", "json")
            return json.dumps(result, ensure_ascii=False)

        elif action == "check":
            scope = kwargs.get("scope", "").strip()
            if not scope:
                return json.dumps({"error": "scope is required for check"}, ensure_ascii=False)
            result = _run_cli("auth", "check", "--scope", scope)
            return json.dumps(result, ensure_ascii=False)

        elif action == "login":
            scope = kwargs.get("scope", "").strip()
            if not scope:
                return json.dumps({"error": "scope is required for login"}, ensure_ascii=False)
            result = _run_cli("auth", "login", "--scope", scope, "--json", timeout=120)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False)


class FeishuApiTool(Tool):
    name = "feishu_api"
    description = "飞书 API 透传命令（直接调用任意飞书 OpenAPI 端点，通过 feishu-cli api）"
    parameters = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "description": "HTTP 方法: GET/POST/PUT/DELETE"},
            "path": {"type": "string", "description": "API 路径（如 /open-apis/im/v1/messages）"},
            "params": {"type": "string", "description": "Query 参数 JSON", "default": ""},
            "data": {"type": "string", "description": "请求体 JSON", "default": ""},
            "as_user": {"type": "boolean", "description": "是否使用 User Token", "default": False},
        },
        "required": ["method", "path"],
    }
    category = "feishu"
    keywords = ["feishu", "api", "raw", "proxy", "passthrough"]
    risk_level = "high"

    def execute(self, **kwargs) -> str:
        method = kwargs.get("method", "GET").strip().upper()
        path = kwargs.get("path", "").strip()
        if not path:
            return json.dumps({"error": "path is required"}, ensure_ascii=False)

        args = ["api", method, path]
        params = kwargs.get("params", "").strip()
        if params:
            args.extend(["--params", params])
        data = kwargs.get("data", "").strip()
        if data:
            args.extend(["--data", data])
        if kwargs.get("as_user", False):
            args.extend(["--as", "user"])
        args.append("--output")
        args.append("json")

        result = _run_cli(*args, timeout=60)
        return json.dumps(result, ensure_ascii=False)


def get_feishu_tools() -> List[Tool]:
    if not _check_feishu_cli():
        logger.info("feishu-cli not found in PATH, skipping Feishu tools")
        return []
    return [
        FeishuDocReadTool(),
        FeishuDocWriteTool(),
        FeishuMsgTool(),
        FeishuSheetTool(),
        FeishuBitableTool(),
        FeishuDriveTool(),
        FeishuCalendarTool(),
        FeishuWikiTool(),
        FeishuAuthTool(),
        FeishuApiTool(),
    ]
