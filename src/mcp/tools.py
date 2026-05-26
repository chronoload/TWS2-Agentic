#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具系统 - 基于 CoreCoder 设计
包含文件操作、编辑、搜索等常用工具

优化内容:
- 结构化结果支持 (ToolResult dataclass)
- 结果大小限制与自动截断
- JSON/human-readable 双模式输出
"""

import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 999999


def safe_truncate(text: str, max_chars: int, suffix: str = None) -> tuple:
    """
    安全截断文本，避免在格式中间截断
    
    返回: (截断后文本, 是否截断, 原始长度)
    """
    if not text or len(text) <= max_chars:
        return text, False, len(text)
    
    suffix = suffix or f"\n\n... [已截断, 原始 {len(text)} 字符]"
    suffix_len = len(suffix)
    available = max_chars - suffix_len - 50
    
    if available <= 0:
        return text[:max_chars] + "...", True, len(text)
    
    truncated_content = text[:available]
    
    lines = truncated_content.split('\n')
    if len(lines) > 1:
        lines = lines[:-1]
        truncated_content = '\n'.join(lines)
        if len(truncated_content) > max_chars - len(suffix) - 20:
            truncated_content = truncated_content[:max_chars - len(suffix) - 20]
    
    result = truncated_content.strip() + suffix
    return result, True, len(text)


@dataclass
class ToolResult:
    """结构化工具结果 - 可解析, 支持 JSON 和文本双模式"""
    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: str = ""
    truncated: bool = False
    original_length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """人类可读的字符串表示"""
        parts = []
        if self.message:
            parts.append(self.message)
        if self.error:
            parts.append(f"❌ {self.error}")
        if self.truncated:
            parts.append(f"\n⚠️ 结果过长，已截断（原始 {self.original_length} 字符）")
        return "\n".join(parts)

    def to_json(self) -> str:
        """JSON 表示 - 可被下游解析"""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def ok(cls, data: Optional[Dict[str, Any]] = None, message: str = "",
           metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        return cls(success=True, data=data or {}, message=message,
                   metadata=metadata or {})

    @classmethod
    def err(cls, error: str, data: Optional[Dict[str, Any]] = None) -> "ToolResult":
        return cls(success=False, error=error, data=data or {})

    @classmethod
    def from_text(cls, text: str, max_chars: int = MAX_TOOL_RESULT_CHARS) -> "ToolResult":
        """从纯文本创建, 自动安全截断"""
        original_length = len(text)
        if original_length <= max_chars:
            message = text
            truncated = False
        else:
            message, truncated, _ = safe_truncate(text, max_chars)
        return cls(success=True, message=message, truncated=truncated,
                   original_length=original_length,
                   data={"text": message, "original_length": original_length})


class Tool(ABC):
    """工具基类"""
    name: str
    description: str
    parameters: Dict[str, Any]
    max_result_chars: int = MAX_TOOL_RESULT_CHARS

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """执行工具, 返回字符串结果"""
        pass

    def execute_structured(self, **kwargs) -> ToolResult:
        """执行工具并返回结构化结果 (可重写以提供更好的结构化数据)"""
        text_result = self.execute(**kwargs)
        return ToolResult.from_text(text_result, self.max_result_chars)

    def schema(self) -> Dict[str, Any]:
        """返回 OpenAI 兼容的工具 schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _truncate_error(self, text: str, max_chars: Optional[int] = None) -> str:
        """截断错误信息"""
        limit = max_chars or self.max_result_chars
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n\n... [已截断, 原始 {len(text)} 字符]"


class ReadFileTool(Tool):
    name = "read_file"
    description = """读取文件内容，支持多种读取模式：
    - 默认：读取全部内容（自动截断）
    - lines: 读取前N行
    - start_line/end_line: 读取指定范围
    - tail: 读取尾部N行"""
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
            "lines": {"type": "integer", "description": "读取前N行，不指定则读取全部"},
            "start_line": {"type": "integer", "description": "起始行号（从1开始）"},
            "end_line": {"type": "integer", "description": "结束行号（包含）"},
            "tail": {"type": "integer", "description": "读取尾部N行"},
            "max_chars": {"type": "integer", "description": "最大字符数，超过则截断"},
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str, encoding: str = "utf-8", 
                lines: Optional[int] = None,
                start_line: Optional[int] = None,
                end_line: Optional[int] = None,
                tail: Optional[int] = None,
                max_chars: Optional[int] = None) -> str:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}").to_json()
            
            content = full_path.read_text(encoding=encoding)
            all_lines = content.splitlines()
            total_lines = len(all_lines)
            
            read_lines = all_lines
            
            # 处理不同读取模式
            mode_desc = ""
            if tail is not None and tail > 0:
                read_lines = all_lines[-tail:]
                mode_desc = f"尾部{tail}行"
            elif start_line is not None and end_line is not None:
                start = max(0, start_line - 1)
                end = min(total_lines, end_line)
                read_lines = all_lines[start:end]
                mode_desc = f"第{start_line}-{end_line}行"
            elif lines is not None and lines > 0:
                read_lines = all_lines[:lines]
                mode_desc = f"前{lines}行"
            else:
                mode_desc = f"全部{total_lines}行"
            
            display_content = "\n".join(read_lines)
            
            # 处理字符截断（安全截断）
            char_limit = max_chars or self.max_result_chars
            original_len = len(display_content)
            if original_len > char_limit:
                display_content, truncated, _ = safe_truncate(display_content, char_limit)
            else:
                truncated = False
            
            result = f"--- {path} ({mode_desc}) ---\n{display_content}"
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total_lines": total_lines,
                    "read_lines": len(read_lines),
                    "read_range": mode_desc,
                    "content": display_content,
                    "original_length": original_len,
                    "truncated": truncated,
                },
                message=result,
                truncated=truncated,
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"读取文件失败：{e}").to_json()

    def execute_structured(self, path: str, encoding: str = "utf-8",
                         lines: Optional[int] = None,
                         start_line: Optional[int] = None,
                         end_line: Optional[int] = None,
                         tail: Optional[int] = None,
                         max_chars: Optional[int] = None) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}")
            
            content = full_path.read_text(encoding=encoding)
            all_lines = content.splitlines()
            total_lines = len(all_lines)
            
            read_lines = all_lines
            mode_desc = ""
            
            if tail is not None and tail > 0:
                read_lines = all_lines[-tail:]
                mode_desc = f"尾部{tail}行"
            elif start_line is not None and end_line is not None:
                start = max(0, start_line - 1)
                end = min(total_lines, end_line)
                read_lines = all_lines[start:end]
                mode_desc = f"第{start_line}-{end_line}行"
            elif lines is not None and lines > 0:
                read_lines = all_lines[:lines]
                mode_desc = f"前{lines}行"
            else:
                mode_desc = f"全部{total_lines}行"
            
            display_content = "\n".join(read_lines)
            original_content_length = len(display_content)
            char_limit = max_chars or self.max_result_chars
            truncated = original_content_length > char_limit
            if truncated:
                display_content = display_content[:char_limit] + f"\n\n... [已截断, 原始 {original_content_length} 字符]"
            
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total_lines": total_lines,
                    "read_lines": len(read_lines),
                    "read_range": mode_desc,
                    "content": display_content,
                    "original_length": original_content_length,
                    "truncated": truncated,
                },
                message=f"--- {path} ({mode_desc}) ---\n{display_content}",
                truncated=truncated,
                original_length=original_content_length,
            )
        except Exception as e:
            return ToolResult.err(f"读取文件失败：{e}")


class WriteFileTool(Tool):
    name = "write_file"
    description = "写入文件内容，支持创建/覆盖/追加模式"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
            "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
            "mode": {"type": "string", "description": "写入模式：create=创建/覆盖(默认), append=追加到末尾"},
            "open_after": {"type": "boolean", "description": "写入后是否用默认编辑器打开，默认 false"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str, content: str, encoding: str = "utf-8", mode: str = "create", open_after: bool = False) -> str:
        result = self.execute_structured(path, content, encoding, mode, open_after)
        return result.to_json()

    def execute_structured(self, path: str, content: str, encoding: str = "utf-8", mode: str = "create", open_after: bool = False) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                existing = ""
                if full_path.exists():
                    existing = full_path.read_text(encoding=encoding)
                    if existing and not existing.endswith('\n'):
                        existing += '\n'
                full_path.write_text(existing + content, encoding=encoding)
                total_lines = (existing + content).splitlines()
                appended_lines = content.splitlines()
                message = f"✅ 已追加到 {path} ({len(appended_lines)} 行追加，总计 {len(total_lines)} 行)"
            else:
                full_path.write_text(content, encoding=encoding)
                line_count = len(content.splitlines())
                message = f"✅ 已写入 {path} ({line_count} 行)"

            if open_after:
                try:
                    import subprocess
                    import platform
                    system = platform.system()
                    if system == "Windows":
                        os.startfile(str(full_path))
                    elif system == "Darwin":
                        subprocess.run(["open", str(full_path)], check=True)
                    else:
                        subprocess.run(["xdg-open", str(full_path)], check=True)
                    message += "\n📖 已在默认编辑器中打开文件"
                except Exception as e:
                    message += f"\n⚠️ 尝试打开文件时出错: {e}"

            return ToolResult.ok(
                data={"path": path, "mode": mode, "open_after": open_after},
                message=message
            )
        except Exception as e:
            return ToolResult.err(f"写入文件失败：{e}")


class EditFileTool(Tool):
    name = "edit_file"
    description = "编辑文件，支持搜索替换、插入行、追加内容、删除行等多种模式"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "mode": {
                "type": "string",
                "enum": ["replace", "insert", "append", "delete_lines", "undo"],
                "description": "编辑模式：replace=搜索替换(默认), insert=在指定行号前插入, append=文件末尾追加, delete_lines=删除指定行范围, undo=恢复上次编辑的备份"
            },
            "old_str": {"type": "string", "description": "[replace模式] 要替换的旧内容"},
            "new_str": {"type": "string", "description": "[replace/insert/append模式] 新内容"},
            "line_number": {"type": "integer", "description": "[insert模式] 在此行号前插入内容（从1开始）"},
            "start_line": {"type": "integer", "description": "[delete_lines模式] 删除起始行号（从1开始，包含）"},
            "end_line": {"type": "integer", "description": "[delete_lines模式] 删除结束行号（包含）"},
            "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
            "backup": {"type": "boolean", "description": "是否创建 .bak 备份文件，默认 false"},
            "open_after": {"type": "boolean", "description": "编辑后是否用默认编辑器打开，默认 false"},
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, **kwargs) -> str:
        result = self.execute_structured(**kwargs)
        return result.to_json()

    def execute_structured(self, path: str, mode: str = "replace",
                           old_str: Optional[str] = None, new_str: Optional[str] = None,
                           line_number: Optional[int] = None,
                           start_line: Optional[int] = None, end_line: Optional[int] = None,
                           encoding: str = "utf-8", backup: bool = False,
                           open_after: bool = False) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)

            if mode == "undo":
                result = self._do_undo(full_path, path, encoding)
            else:
                if not full_path.exists():
                    return ToolResult.err(f"文件不存在：{path}")

                content = full_path.read_text(encoding=encoding)
                all_lines = content.splitlines(keepends=True)
                total_lines = len(all_lines)

                if mode == "replace":
                    result = self._do_replace(full_path, path, content, all_lines, total_lines,
                                              old_str, new_str, encoding, backup)
                elif mode == "insert":
                    result = self._do_insert(full_path, path, content, all_lines, total_lines,
                                           new_str, line_number, encoding, backup)
                elif mode == "append":
                    result = self._do_append(full_path, path, content, total_lines,
                                           new_str, encoding, backup)
                elif mode == "delete_lines":
                    result = self._do_delete_lines(full_path, path, content, all_lines, total_lines,
                                                 start_line, end_line, encoding, backup)
                else:
                    return ToolResult.err(f"未知编辑模式：{mode}，支持 replace/insert/append/delete_lines/undo")
            
            if open_after and result.success:
                try:
                    import subprocess
                    import platform
                    system = platform.system()
                    if system == "Windows":
                        os.startfile(str(full_path))
                    elif system == "Darwin":
                        subprocess.run(["open", str(full_path)], check=True)
                    else:
                        subprocess.run(["xdg-open", str(full_path)], check=True)
                    result.message += "\n📖 已在默认编辑器中打开文件"
                except Exception as e:
                    result.message += f"\n⚠️ 尝试打开文件时出错: {e}"
            
            return result
        except Exception as e:
            return ToolResult.err(f"编辑文件失败：{e}")

    def _do_replace(self, full_path, path, content, all_lines, total_lines,
                     old_str, new_str, encoding, backup) -> ToolResult:
        if not old_str:
            return ToolResult.err("replace 模式需要 old_str 参数")
        if new_str is None:
            new_str = ""

        count = content.count(old_str)
        if count == 0:
            return ToolResult.err("未找到匹配内容")
        if count > 1:
            return ToolResult.err(f"找到 {count} 处匹配，请更精确地选择替换内容")

        match_pos = content.index(old_str)
        match_line = content[:match_pos].count('\n') + 1

        if backup:
            self._create_backup(full_path)

        new_content = content.replace(old_str, new_str)
        full_path.write_text(new_content, encoding=encoding)

        diff = self._generate_unified_diff(old_str, new_str, match_line)
        context = self._get_context(all_lines, total_lines, match_line, new_str.count('\n') + 1)

        return ToolResult.ok(
            data={
                "path": path,
                "mode": "replace",
                "replacements": 1,
                "match_line": match_line,
                "diff": diff,
                "context": context,
            },
            message=f"✅ 已替换 {path} (第{match_line}行)\n--- 变更 ---\n{diff}\n--- 上下文 ---\n{context}"
        )

    def _do_insert(self, full_path, path, content, all_lines, total_lines,
                    new_str, line_number, encoding, backup) -> ToolResult:
        if new_str is None:
            return ToolResult.err("insert 模式需要 new_str 参数")
        if line_number is None:
            return ToolResult.err("insert 模式需要 line_number 参数")
        if line_number < 1 or line_number > total_lines + 1:
            return ToolResult.err(f"行号超出范围：{line_number}，文件共 {total_lines} 行")

        if backup:
            self._create_backup(full_path)

        insert_text = new_str if new_str.endswith('\n') else new_str + '\n'
        insert_idx = line_number - 1
        all_lines.insert(insert_idx, insert_text)
        new_content = ''.join(all_lines)
        full_path.write_text(new_content, encoding=encoding)

        diff = self._generate_unified_diff("", new_str, line_number)
        context = self._get_context(all_lines, len(all_lines), line_number, new_str.count('\n') + 1)

        return ToolResult.ok(
            data={
                "path": path,
                "mode": "insert",
                "inserted_at_line": line_number,
                "lines_inserted": new_str.count('\n') + 1,
                "total_lines": len(all_lines),
                "diff": diff,
                "context": context,
            },
            message=f"✅ 已在第{line_number}行前插入内容到 {path} ({new_str.count(chr(10))+1}行)\n--- 变更 ---\n{diff}\n--- 上下文 ---\n{context}"
        )

    def _do_append(self, full_path, path, content, total_lines,
                    new_str, encoding, backup) -> ToolResult:
        if new_str is None:
            return ToolResult.err("append 模式需要 new_str 参数")

        if backup:
            self._create_backup(full_path)

        append_text = new_str
        if content and not content.endswith('\n'):
            append_text = '\n' + append_text
        if not append_text.endswith('\n'):
            append_text += '\n'

        new_content = content + append_text
        full_path.write_text(new_content, encoding=encoding)

        new_total = new_content.count('\n') + (1 if not new_content.endswith('\n') else 0)
        start_line = total_lines + 1

        diff = self._generate_unified_diff("", new_str, start_line)

        return ToolResult.ok(
            data={
                "path": path,
                "mode": "append",
                "appended_at_line": start_line,
                "lines_appended": new_str.count('\n') + 1,
                "total_lines": new_total,
                "diff": diff,
            },
            message=f"✅ 已追加内容到 {path} (从第{start_line}行开始, {new_str.count(chr(10))+1}行)\n--- 变更 ---\n{diff}"
        )

    def _do_delete_lines(self, full_path, path, content, all_lines, total_lines,
                          start_line, end_line, encoding, backup) -> ToolResult:
        if start_line is None or end_line is None:
            return ToolResult.err("delete_lines 模式需要 start_line 和 end_line 参数")
        if start_line < 1 or end_line > total_lines or start_line > end_line:
            return ToolResult.err(f"行范围无效：{start_line}-{end_line}，文件共 {total_lines} 行")

        if backup:
            self._create_backup(full_path)

        deleted_text = ''.join(all_lines[start_line - 1:end_line])
        del all_lines[start_line - 1:end_line]
        new_content = ''.join(all_lines)
        full_path.write_text(new_content, encoding=encoding)

        diff = self._generate_unified_diff(deleted_text, "", start_line)
        context = self._get_context(all_lines, len(all_lines), max(1, start_line - 1), 3)

        return ToolResult.ok(
            data={
                "path": path,
                "mode": "delete_lines",
                "deleted_range": f"{start_line}-{end_line}",
                "lines_deleted": end_line - start_line + 1,
                "total_lines": len(all_lines),
                "diff": diff,
                "context": context,
            },
            message=f"✅ 已删除 {path} 第{start_line}-{end_line}行 ({end_line-start_line+1}行)\n--- 变更 ---\n{diff}\n--- 上下文 ---\n{context}"
        )

    def _create_backup(self, full_path: Path):
        backup_path = full_path.with_suffix(full_path.suffix + '.bak')
        import shutil
        shutil.copy2(full_path, backup_path)

    def _do_undo(self, full_path, path, encoding) -> ToolResult:
        backup_path = full_path.with_suffix(full_path.suffix + '.bak')
        if not backup_path.exists():
            return ToolResult.err(f"没有找到备份文件：{backup_path.name}")
        try:
            import shutil
            shutil.copy2(str(backup_path), str(full_path))
            content = full_path.read_text(encoding=encoding)
            line_count = len(content.splitlines())
            return ToolResult.ok(
                data={"path": path, "mode": "undo", "restored_lines": line_count},
                message=f"✅ 已从备份恢复 {path} ({line_count} 行)"
            )
        except Exception as e:
            return ToolResult.err(f"恢复备份失败：{e}")

    def _get_context(self, all_lines, total_lines, center_line, context_radius=3):
        start = max(0, center_line - context_radius - 1)
        end = min(total_lines, center_line + context_radius)
        lines = all_lines[start:end]
        result = []
        for i, line in enumerate(lines):
            line_no = start + i + 1
            marker = ">>>" if line_no == center_line else "   "
            result.append(f"{marker} {line_no:4d} | {line.rstrip()}")
        return '\n'.join(result)

    def _generate_unified_diff(self, old: str, new: str, start_line: int = 1) -> str:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        result = []
        for i, line in enumerate(old_lines):
            result.append(f"- {start_line + i:4d} | {line.rstrip()}")
        if old_lines and new_lines:
            result.append("      ---")
        for i, line in enumerate(new_lines):
            result.append(f"+ {start_line + i:4d} | {line.rstrip()}")
        return '\n'.join(result)


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "列出目录内容，支持递归、详情显示和文件过滤"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，默认为当前目录"},
            "recursive": {"type": "boolean", "description": "是否递归列出子目录，默认 false"},
            "show_details": {"type": "boolean", "description": "是否显示文件大小和修改时间，默认 false"},
            "pattern": {"type": "string", "description": "文件名过滤模式（glob），如 *.py"},
            "max_depth": {"type": "integer", "description": "递归最大深度，默认 3"},
        },
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str = ".", recursive: bool = False,
                show_details: bool = False, pattern: str = "",
                max_depth: int = 3) -> str:
        result = self.execute_structured(path, recursive, show_details, pattern, max_depth)
        return result.to_json()

    def execute_structured(self, path: str = ".", recursive: bool = False,
                           show_details: bool = False, pattern: str = "",
                           max_depth: int = 3) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"目录不存在：{path}")
            if not full_path.is_dir():
                return ToolResult.err(f"不是目录：{path}")

            dirs = []
            files = []
            lines = []

            def _format_size(size: int) -> str:
                if size < 1024:
                    return f"{size}B"
                elif size < 1024 * 1024:
                    return f"{size/1024:.1f}KB"
                elif size < 1024 * 1024 * 1024:
                    return f"{size/(1024*1024):.1f}MB"
                else:
                    return f"{size/(1024*1024*1024):.1f}GB"

            def _list_dir(current: Path, depth: int = 0):
                if depth > max_depth:
                    return
                try:
                    items = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                except PermissionError:
                    lines.append("  " * depth + "⚠️ [无权限]")
                    return

                for item in items:
                    if item.name.startswith(".") and depth > 0:
                        continue
                    rel = str(item.relative_to(full_path))
                    if item.is_dir():
                        dirs.append(rel)
                        prefix = "📁"
                        detail = ""
                        if show_details:
                            try:
                                mtime = item.stat().st_mtime
                                from datetime import datetime as _dt
                                detail = f"  [{_dt.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}]"
                            except:
                                pass
                        lines.append("  " * depth + f"{prefix} {item.name}{detail}")
                        if recursive:
                            _list_dir(item, depth + 1)
                    else:
                        if pattern and not item.match(pattern):
                            continue
                        files.append(rel)
                        prefix = "📄"
                        detail = ""
                        if show_details:
                            try:
                                stat = item.stat()
                                size_str = _format_size(stat.st_size)
                                from datetime import datetime as _dt
                                mtime_str = _dt.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                                detail = f"  [{size_str}, {mtime_str}]"
                            except:
                                pass
                        lines.append("  " * depth + f"{prefix} {item.name}{detail}")

            _list_dir(full_path)

            text = f"--- {path} ({len(dirs)} 目录, {len(files)} 文件) ---\n" + "\n".join(lines)
            return ToolResult.ok(
                data={"path": path, "directories": dirs, "files": files,
                      "total_dirs": len(dirs), "total_files": len(files)},
                message=text
            )
        except Exception as e:
            return ToolResult.err(f"列出目录失败：{e}")


class GrepTool(Tool):
    name = "grep"
    description = "在文件中搜索内容，支持正则、大小写忽略、上下文行"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索模式（正则表达式）"},
            "path": {"type": "string", "description": "搜索路径，默认为当前目录"},
            "extension": {"type": "string", "description": "文件扩展名过滤，如 .py, .md"},
            "ignore_case": {"type": "boolean", "description": "是否忽略大小写，默认 false"},
            "context_lines": {"type": "integer", "description": "显示匹配行前后各N行上下文，默认 0"},
            "max_results": {"type": "integer", "description": "最大匹配结果数，默认 50"},
        },
        "required": ["pattern"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, pattern: str, path: str = ".", extension: str = "",
                ignore_case: bool = False, context_lines: int = 0,
                max_results: int = 50) -> str:
        result = self.execute_structured(pattern, path, extension, ignore_case, context_lines, max_results)
        return result.to_json()

    def execute_structured(self, pattern: str, path: str = ".", extension: str = "",
                           ignore_case: bool = False, context_lines: int = 0,
                           max_results: int = 50) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"路径不存在：{path}")

            flags = re.IGNORECASE if ignore_case else 0
            pattern_re = re.compile(pattern, flags)
            results = []
            match_count = 0
            file_count = 0

            def search_file(file_path: Path):
                nonlocal match_count, file_count
                try:
                    content = file_path.read_text(errors="ignore")
                    all_lines = content.splitlines()
                    found = False
                    for i, line in enumerate(all_lines):
                        if pattern_re.search(line):
                            if not found:
                                found = True
                                file_count += 1
                            if match_count < max_results:
                                if context_lines > 0:
                                    ctx_start = max(0, i - context_lines)
                                    ctx_end = min(len(all_lines), i + context_lines + 1)
                                    ctx_lines = []
                                    for j in range(ctx_start, ctx_end):
                                        marker = ">>>" if j == i else "   "
                                        ctx_lines.append(f"  {marker} {j+1:4d} | {all_lines[j]}")
                                    results.append(f"{file_path}:\n" + "\n".join(ctx_lines))
                                else:
                                    results.append(f"{file_path}:{i+1}: {line}")
                            match_count += 1
                            if match_count >= max_results + 1:
                                return True
                except Exception:
                    pass
                return False

            if full_path.is_file():
                search_file(full_path)
            else:
                for item in full_path.rglob("*" + extension if extension else "*"):
                    if item.is_file() and not item.name.startswith("."):
                        if search_file(item):
                            break

            if match_count == 0:
                return ToolResult.ok(
                    data={"pattern": pattern, "total_matches": 0, "total_files": 0, "results": []},
                    message=f"未找到匹配：{pattern}"
                )

            text = f"--- 搜索结果：{pattern} ---\n"
            text += "\n".join(results[:max_results])
            if match_count > max_results:
                text += f"\n\n... 还有 {match_count - max_results} 处匹配（共 {file_count} 个文件）"

            return ToolResult.ok(
                data={
                    "pattern": pattern,
                    "total_matches": match_count,
                    "total_files": file_count,
                    "showing": min(match_count, max_results),
                    "results": results[:max_results],
                },
                message=text
            )
        except Exception as e:
            return ToolResult.err(f"搜索失败：{e}")


class GlobTool(Tool):
    name = "glob"
    description = "使用 glob 模式查找文件，支持递归和文件信息"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "glob 模式，如 *.py, **/*.md"},
            "path": {"type": "string", "description": "搜索路径，默认为当前目录"},
            "show_details": {"type": "boolean", "description": "是否显示文件大小，默认 false"},
        },
        "required": ["pattern"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, pattern: str, path: str = ".", show_details: bool = False) -> str:
        result = self.execute_structured(pattern, path, show_details)
        return result.to_json()

    def execute_structured(self, pattern: str, path: str = ".", show_details: bool = False) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"路径不存在：{path}")

            files = sorted(full_path.glob(pattern))
            if not files:
                return ToolResult.ok(
                    data={"pattern": pattern, "total": 0, "results": []},
                    message=f"未找到匹配：{pattern}"
                )

            def _fmt_size(size: int) -> str:
                if size < 1024:
                    return f"{size}B"
                elif size < 1024 * 1024:
                    return f"{size/1024:.1f}KB"
                else:
                    return f"{size/(1024*1024):.1f}MB"

            rel_files = []
            display_lines = []
            for f in files[:200]:
                try:
                    rel = str(f.relative_to(self.base_dir))
                except ValueError:
                    rel = str(f)
                rel_files.append(rel)
                if show_details and f.is_file():
                    try:
                        size = _fmt_size(f.stat().st_size)
                        display_lines.append(f"  {rel}  [{size}]")
                    except:
                        display_lines.append(f"  {rel}")
                else:
                    display_lines.append(f"  {rel}")

            text = f"--- 查找结果：{pattern} ({len(files)} 个) ---\n"
            text += "\n".join(display_lines)
            if len(files) > 200:
                text += f"\n\n... 还有 {len(files) - 200} 个文件"

            return ToolResult.ok(
                data={"pattern": pattern, "total": len(files), "results": rel_files[:200]},
                message=text
            )
        except Exception as e:
            return ToolResult.err(f"glob 查找失败：{e}")


class CalculateTool(Tool):
    name = "calculate"
    description = "数学计算，支持 Python 表达式和 numpy/scipy"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式，如 2+2, sin(pi/2), np.linalg.norm([3,4])"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 5"},
        },
        "required": ["expression"],
    }

    def execute(self, expression: str, timeout: int = 5) -> str:
        result = self.execute_structured(expression, timeout)
        return result.to_json()

    def execute_structured(self, expression: str, timeout: int = 5) -> ToolResult:
        try:
            import math
            safe_namespace = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
            safe_namespace["pi"] = math.pi
            safe_namespace["e"] = math.e

            try:
                import numpy as np
                safe_namespace["np"] = np
                safe_namespace["numpy"] = np
            except ImportError:
                pass

            try:
                import scipy
                safe_namespace["scipy"] = scipy
            except ImportError:
                pass

            import signal

            def _timeout_handler(signum, frame):
                raise TimeoutError(f"计算超时（{timeout}秒）")

            old_handler = None
            try:
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout)
            except (AttributeError, ValueError):
                pass

            try:
                result = eval(expression, {"__builtins__": {}}, safe_namespace)
            finally:
                try:
                    signal.alarm(0)
                    if old_handler is not None:
                        signal.signal(signal.SIGALRM, old_handler)
                except (AttributeError, ValueError):
                    pass

            try:
                result_str = str(result)
                if hasattr(result, '__len__') and not isinstance(result, str):
                    if len(result_str) > 500:
                        result_str = result_str[:500] + f"... (长度={len(result)})"
            except:
                result_str = str(result)

            return ToolResult.ok(
                data={"expression": expression, "result": result_str},
                message=f"{expression} = {result_str}"
            )
        except TimeoutError as e:
            return ToolResult.err(str(e))
        except Exception as e:
            return ToolResult.err(f"计算失败：{e}")


class WebSearchTool(Tool):
    name = "web_search"
    description = "网络搜索（需要配置）"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "num_results": {"type": "integer", "description": "结果数量，默认 10"},
        },
        "required": ["query"],
    }

    def execute(self, query: str, num_results: int = 10) -> str:
        try:
            from duckduckgo_search import DDGS
            results = list(DDGS().text(query, max_results=num_results))
            lines = [f"--- 搜索：{query} ---"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', '')}")
                lines.append(f"   {r.get('href', '')}")
                lines.append(f"   {r.get('body', '')[:150]}...")
                lines.append("")

            return ToolResult.ok(
                data={
                    "query": query,
                    "num_results": len(results),
                    "results": [
                        {"title": r.get("title", ""), "url": r.get("href", ""),
                         "snippet": r.get("body", "")[:300]}
                        for r in results
                    ],
                },
                message="\n".join(lines)
            ).to_json()
        except ImportError:
            return ToolResult.err(
                "需要安装 duckduckgo-search 才能使用网络搜索\n运行：pip install duckduckgo-search"
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"搜索失败：{e}").to_json()


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "获取网页内容并转为文本，支持 URL 抓取"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的网页 URL"},
            "max_chars": {"type": "integer", "description": "最大字符数，默认 10000"},
        },
        "required": ["url"],
    }

    def execute(self, url: str, max_chars: int = 10000) -> str:
        result = self.execute_structured(url, max_chars)
        return result.to_json()

    def execute_structured(self, url: str, max_chars: int = 10000) -> ToolResult:
        try:
            import urllib.request
            import re as _re

            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            text = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
            text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
            text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
            text = _re.sub(r'<p[^>]*>', '\n', text, flags=_re.IGNORECASE)
            text = _re.sub(r'<[^>]+>', '', text)
            text = _re.sub(r'&nbsp;', ' ', text)
            text = _re.sub(r'&amp;', '&', text)
            text = _re.sub(r'&lt;', '<', text)
            text = _re.sub(r'&gt;', '>', text)
            text = _re.sub(r'&#\d+;', '', text)
            text = _re.sub(r'\n\s*\n', '\n\n', text)
            text = text.strip()

            original_len = len(text)
            truncated = original_len > max_chars
            if truncated:
                text = text[:max_chars] + f"\n\n... [已截断，原始 {original_len} 字符]"

            return ToolResult.ok(
                data={"url": url, "content": text, "original_length": original_len, "truncated": truncated},
                message=f"--- {url} ---\n{text}"
            )
        except Exception as e:
            return ToolResult.err(f"获取网页失败：{e}")


class AnalyzePaperTool(Tool):
    name = "analyze_paper"
    description = "分析科研论文（PDF/DOCX/MD），支持元数据提取和分页读取"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "论文文件路径"},
            "start_page": {"type": "integer", "description": "起始页码（从1开始，仅PDF）"},
            "end_page": {"type": "integer", "description": "结束页码（仅PDF）"},
            "extract_metadata": {"type": "boolean", "description": "是否提取元数据（标题/作者等），默认 false"},
        },
        "required": ["file_path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, file_path: str, start_page: Optional[int] = None,
                end_page: Optional[int] = None, extract_metadata: bool = False) -> str:
        result = self.execute_structured(file_path, start_page, end_page, extract_metadata)
        return result.to_json()

    def execute_structured(self, file_path: str, start_page: Optional[int] = None,
                           end_page: Optional[int] = None, extract_metadata: bool = False) -> ToolResult:
        try:
            full_path = self.base_dir / Path(file_path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{file_path}")

            metadata = {}
            if extract_metadata:
                metadata = self._extract_metadata(full_path)

            text = self._extract_text(full_path, start_page, end_page)
            if not text:
                return ToolResult.err("无法提取文本内容")

            truncated = len(text) > self.max_result_chars
            preview = text[:self.max_result_chars]

            data = {
                "file_path": file_path,
                "original_length": len(text),
                "preview": preview,
                "truncated": truncated,
            }
            if metadata:
                data["metadata"] = metadata

            header = f"--- 分析论文：{file_path} ---"
            if metadata:
                header += "\n" + "\n".join(f"  {k}: {v}" for k, v in metadata.items() if v)
                header += "\n"

            return ToolResult.ok(data=data, message=f"{header}\n{preview}")
        except Exception as e:
            return ToolResult.err(f"分析论文失败：{e}")

    def _extract_text(self, path: Path, start_page=None, end_page=None) -> str:
        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                try:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        pages = reader.pages
                        total = len(pages)
                        s = max(0, (start_page or 1) - 1)
                        e = min(total, end_page or total)
                        return "\n".join([pages[i].extract_text() or "" for i in range(s, e)])
                except ImportError:
                    return "提示：需要安装 PyPDF2 才能读取 PDF\n运行：pip install PyPDF2"
            elif ext in [".docx", ".doc"]:
                try:
                    from docx import Document
                    doc = Document(path)
                    return "\n".join([p.text for p in doc.paragraphs])
                except ImportError:
                    return "提示：需要安装 python-docx 才能读取 DOCX\n运行：pip install python-docx"
            else:
                return path.read_text(errors="ignore")
        except Exception as e:
            return f"提取文本失败：{e}"

    def _extract_metadata(self, path: Path) -> dict:
        meta = {}
        ext = path.suffix.lower()
        if ext == ".pdf":
            try:
                import PyPDF2
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    info = reader.metadata
                    if info:
                        meta["title"] = info.get("/Title", "")
                        meta["author"] = info.get("/Author", "")
                        meta["subject"] = info.get("/Subject", "")
                        meta["creator"] = info.get("/Creator", "")
                    meta["total_pages"] = len(reader.pages)
            except:
                pass
        elif ext in [".docx", ".doc"]:
            try:
                from docx import Document
                doc = Document(path)
                props = doc.core_properties
                meta["title"] = props.title or ""
                meta["author"] = props.author or ""
                meta["created"] = str(props.created) if props.created else ""
                meta["modified"] = str(props.modified) if props.modified else ""
            except:
                pass
        meta["file_size"] = path.stat().st_size
        return meta


class OpenFileTool(Tool):
    name = "open_file"
    description = "用系统默认程序打开文件（如 PDF 用阅读器、图片用查看器等）。仅打开文件，不返回内容。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要打开的文件路径"},
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def execute(self, path: str) -> str:
        result = self.execute_structured(path)
        return result.to_json()

    def execute_structured(self, path: str) -> ToolResult:
        import subprocess
        import platform

        target = Path(path)
        if not target.is_absolute():
            target = self.base_dir / target

        if not target.exists():
            return ToolResult.err(f"文件不存在: {target}")

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(target))
            elif system == "Darwin":
                subprocess.run(["open", str(target)], check=True)
            else:
                subprocess.run(["xdg-open", str(target)], check=True)

            return ToolResult.ok(
                data={"path": str(target), "opened": True},
                message=f"✅ 已用系统默认方式打开: {target.name}"
            )
        except Exception as e:
            return ToolResult.err(f"打开文件失败: {e}")


class TerminalTool(Tool):
    name = "terminal_open"
    description = "打开新的终端窗口（可选：在指定目录打开，或执行命令后保持打开）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "工作目录（可选）"},
            "command": {"type": "string", "description": "要在终端中执行的命令（可选）"},
            "keep_open": {"type": "boolean", "description": "命令执行后是否保持终端打开，默认 true"},
        },
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def execute(self, path: Optional[str] = None, command: Optional[str] = None, keep_open: bool = True) -> str:
        result = self.execute_structured(path, command, keep_open)
        return result.to_json()

    def execute_structured(self, path: Optional[str] = None, command: Optional[str] = None, keep_open: bool = True) -> ToolResult:
        import subprocess
        import platform
        import sys

        working_dir = self.base_dir
        if path:
            p = Path(path)
            if p.is_absolute():
                working_dir = p
            else:
                working_dir = self.base_dir / p
        
        working_dir.mkdir(parents=True, exist_ok=True)

        try:
            system = platform.system()
            
            if system == "Windows":
                cmd_parts = ["cmd", "/k"] if keep_open else ["cmd", "/c"]
                if command:
                    cmd_parts.append(command)
                subprocess.Popen(cmd_parts, cwd=str(working_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)
                
            elif system == "Darwin":
                script = f'cd "{working_dir}"'
                if command:
                    script += f'; {command}'
                if keep_open:
                    script += '; exec bash'
                applescript = f'tell application "Terminal" to do script "{script}"'
                subprocess.run(["osascript", "-e", applescript], check=True)
                
            else:
                shell = os.environ.get("SHELL", "bash")
                if command:
                    if keep_open:
                        script = f"{command}; exec {shell}"
                    else:
                        script = command
                    subprocess.Popen([shell, "-c", script], cwd=str(working_dir))
                else:
                    subprocess.Popen([shell], cwd=str(working_dir))

            return ToolResult.ok(
                data={"path": str(working_dir), "command": command, "keep_open": keep_open},
                message=f"✅ 已打开终端" + (f" 并执行: {command}" if command else "")
            )
        except Exception as e:
            return ToolResult.err(f"打开终端失败: {e}")


class DiffFilesTool(Tool):
    name = "diff_files"
    description = "比较两个文件的差异"
    parameters = {
        "type": "object",
        "properties": {
            "path_a": {"type": "string", "description": "第一个文件路径"},
            "path_b": {"type": "string", "description": "第二个文件路径"},
            "context_lines": {"type": "integer", "description": "上下文行数，默认 3"},
        },
        "required": ["path_a", "path_b"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path_a: str, path_b: str, context_lines: int = 3) -> str:
        result = self.execute_structured(path_a, path_b, context_lines)
        return result.to_json()

    def execute_structured(self, path_a: str, path_b: str, context_lines: int = 3) -> ToolResult:
        try:
            import difflib
            full_a = self.base_dir / Path(path_a)
            full_b = self.base_dir / Path(path_b)
            if not full_a.exists():
                return ToolResult.err(f"文件不存在：{path_a}")
            if not full_b.exists():
                return ToolResult.err(f"文件不存在：{path_b}")

            lines_a = full_a.read_text(errors="ignore").splitlines(keepends=True)
            lines_b = full_b.read_text(errors="ignore").splitlines(keepends=True)

            diff = difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=path_b, n=context_lines)
            diff_text = "".join(diff)

            if not diff_text:
                return ToolResult.ok(
                    data={"path_a": path_a, "path_b": path_b, "has_diff": False},
                    message=f"✅ {path_a} 和 {path_b} 内容完全相同"
                )

            if len(diff_text) > self.max_result_chars:
                diff_text = diff_text[:self.max_result_chars] + "\n... [diff 已截断]"

            return ToolResult.ok(
                data={"path_a": path_a, "path_b": path_b, "has_diff": True},
                message=f"--- 差异：{path_a} vs {path_b} ---\n{diff_text}"
            )
        except Exception as e:
            return ToolResult.err(f"比较文件失败：{e}")


class MoveFileTool(Tool):
    name = "move_file"
    description = "移动或重命名文件"
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源文件路径"},
            "destination": {"type": "string", "description": "目标文件路径"},
        },
        "required": ["source", "destination"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, source: str, destination: str) -> str:
        result = self.execute_structured(source, destination)
        return result.to_json()

    def execute_structured(self, source: str, destination: str) -> ToolResult:
        try:
            import shutil
            src = self.base_dir / Path(source)
            dst = self.base_dir / Path(destination)
            if not src.exists():
                return ToolResult.err(f"源文件不存在：{source}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ToolResult.ok(
                data={"source": source, "destination": destination},
                message=f"✅ 已移动: {source} → {destination}"
            )
        except Exception as e:
            return ToolResult.err(f"移动文件失败：{e}")


class CopyFileTool(Tool):
    name = "copy_file"
    description = "复制文件"
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源文件路径"},
            "destination": {"type": "string", "description": "目标文件路径"},
        },
        "required": ["source", "destination"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, source: str, destination: str) -> str:
        result = self.execute_structured(source, destination)
        return result.to_json()

    def execute_structured(self, source: str, destination: str) -> ToolResult:
        try:
            import shutil
            src = self.base_dir / Path(source)
            dst = self.base_dir / Path(destination)
            if not src.exists():
                return ToolResult.err(f"源文件不存在：{source}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            return ToolResult.ok(
                data={"source": source, "destination": destination},
                message=f"✅ 已复制: {source} → {destination}"
            )
        except Exception as e:
            return ToolResult.err(f"复制文件失败：{e}")


class FileInfoTool(Tool):
    name = "file_info"
    description = "获取文件元数据（大小、修改时间、编码检测等）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str) -> str:
        result = self.execute_structured(path)
        return result.to_json()

    def execute_structured(self, path: str) -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}")

            stat = full_path.stat()
            from datetime import datetime as _dt

            info = {
                "path": str(full_path),
                "name": full_path.name,
                "suffix": full_path.suffix,
                "size_bytes": stat.st_size,
                "size_readable": self._fmt_size(stat.st_size),
                "is_file": full_path.is_file(),
                "is_dir": full_path.is_dir(),
                "created": _dt.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "modified": _dt.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "accessed": _dt.fromtimestamp(stat.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
            }

            if full_path.is_file():
                try:
                    content = full_path.read_bytes()[:4096]
                    info["encoding"] = self._detect_encoding(content)
                    info["line_count"] = len(full_path.read_text(errors="ignore").splitlines())
                except:
                    pass

            lines = [f"--- 文件信息：{path} ---"]
            for k, v in info.items():
                lines.append(f"  {k}: {v}")

            return ToolResult.ok(data=info, message="\n".join(lines))
        except Exception as e:
            return ToolResult.err(f"获取文件信息失败：{e}")

    def _fmt_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size/(1024*1024):.1f} MB"
        else:
            return f"{size/(1024*1024*1024):.1f} GB"

    def _detect_encoding(self, raw: bytes) -> str:
        try:
            import chardet
            result = chardet.detect(raw)
            return result.get("encoding", "unknown")
        except ImportError:
            pass
        if raw.startswith(b'\xef\xbb\xbf'):
            return "utf-8-sig"
        if raw.startswith(b'\xff\xfe'):
            return "utf-16-le"
        if raw.startswith(b'\xfe\xff'):
            return "utf-16-be"
        try:
            raw.decode("utf-8")
            return "utf-8"
        except:
            pass
        return "ascii/latin-1 (猜测)"


class CLITool(Tool):
    name = "cli_execute"
    description = "执行命令行命令（注意：仅用于安全的、非破坏性的命令）"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 30"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
            "open_terminal": {"type": "boolean", "description": "是否在新终端窗口中执行，默认 false"},
            "keep_terminal_open": {"type": "boolean", "description": "命令执行后是否保持终端打开，默认 true"},
        },
        "required": ["command"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, command: str, timeout: int = 30, cwd: Optional[str] = None, open_terminal: bool = False, keep_terminal_open: bool = True) -> str:
        result = self.execute_structured(command, timeout, cwd, open_terminal, keep_terminal_open)
        return result.to_json()

    def execute_structured(self, command: str, timeout: int = 30, cwd: Optional[str] = None, open_terminal: bool = False, keep_terminal_open: bool = True) -> ToolResult:
        try:
            if open_terminal:
                return self._execute_in_terminal(command, cwd, keep_terminal_open)
            
            import subprocess
            import platform
            import shlex

            working_dir = cwd or str(self.base_dir)
            
            shell = platform.system() == "Windows"
            
            if not shell:
                args = shlex.split(command)
            else:
                args = command

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                shell=shell
            )

            output = []
            if result.stdout:
                output.append(f"--- stdout ---\n{result.stdout}")
            if result.stderr:
                output.append(f"--- stderr ---\n{result.stderr}")

            output_text = "\n".join(output) if output else "(无输出)"

            if len(output_text) > self.max_result_chars:
                output_text = output_text[:self.max_result_chars] + "\n... [输出已截断]"

            data = {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

            if result.returncode == 0:
                return ToolResult.ok(
                    data=data,
                    message=f"✅ 命令执行成功 (返回码: 0)\n\n{output_text}"
                )
            else:
                return ToolResult.ok(
                    data=data,
                    message=f"⚠️ 命令执行完成 (返回码: {result.returncode})\n\n{output_text}"
                )
        except subprocess.TimeoutExpired:
            return ToolResult.err(f"命令执行超时 ({timeout}秒)")
        except Exception as e:
            return ToolResult.err(f"执行命令失败：{e}")

    def _execute_in_terminal(self, command: str, cwd: Optional[str], keep_open: bool) -> ToolResult:
        import subprocess
        import platform

        working_dir = self.base_dir
        if cwd:
            p = Path(cwd)
            if p.is_absolute():
                working_dir = p
            else:
                working_dir = self.base_dir / p
        
        working_dir.mkdir(parents=True, exist_ok=True)

        try:
            system = platform.system()
            
            if system == "Windows":
                cmd_parts = ["cmd", "/k"] if keep_open else ["cmd", "/c"]
                cmd_parts.append(command)
                subprocess.Popen(cmd_parts, cwd=str(working_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)
                
            elif system == "Darwin":
                script = f'cd "{working_dir}"; {command}'
                if keep_open:
                    script += '; exec bash'
                applescript = f'tell application "Terminal" to do script "{script}"'
                subprocess.run(["osascript", "-e", applescript], check=True)
                
            else:
                shell = os.environ.get("SHELL", "bash")
                if keep_open:
                    script = f"{command}; exec {shell}"
                else:
                    script = command
                subprocess.Popen([shell, "-c", script], cwd=str(working_dir))

            return ToolResult.ok(
                data={"command": command, "in_terminal": True, "keep_open": keep_open},
                message=f"🖥️ 已在新终端中执行命令: {command}"
            )
        except Exception as e:
            return ToolResult.err(f"在终端执行失败: {e}")


class ConfigTool(Tool):
    name = "config_manage"
    description = "管理系统配置（API密钥、模型配置、MCP配置等）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list_providers, get_settings, update_setting, list_skills",
                "enum": ["list_providers", "get_settings", "update_setting", "list_skills"]
            },
            "key": {"type": "string", "description": "设置键名（update_setting 时需要）"},
            "value": {"type": "string", "description": "设置值（update_setting 时需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, action: str, key: Optional[str] = None, value: Optional[str] = None) -> str:
        result = self.execute_structured(action, key, value)
        return result.to_json()

    def execute_structured(self, action: str, key: Optional[str] = None, value: Optional[str] = None) -> ToolResult:
        try:
            from .config import get_config_manager
            config_mgr = get_config_manager()

            if action == "list_providers":
                providers = config_mgr.get_all_provider_configs()
                lines = ["--- 模型提供商配置 ---"]
                for p in providers:
                    status = "✅" if p.enabled else "❌"
                    lines.append(f"{status} {p.name} ({p.provider.value}) - 模型: {p.model}")
                return ToolResult.ok(
                    data={"providers": [{"name": p.name, "provider": p.provider.value, "model": p.model, "enabled": p.enabled} for p in providers]},
                    message="\n".join(lines)
                )
            
            elif action == "get_settings":
                settings = config_mgr.settings
                lines = ["--- 系统设置 ---"]
                for k, v in settings.items():
                    lines.append(f"  {k}: {v}")
                return ToolResult.ok(
                    data={"settings": settings},
                    message="\n".join(lines) if settings else "暂无设置"
                )
            
            elif action == "update_setting":
                if key is None:
                    return ToolResult.err("update_setting 需要 key 参数")
                config_mgr.set_setting(key, value or "")
                return ToolResult.ok(
                    data={"key": key, "value": value},
                    message=f"✅ 已设置 {key} = {value}"
                )
            
            elif action == "list_skills":
                skills = config_mgr.skill_configs
                lines = ["--- 技能配置 ---"]
                for s in skills:
                    status = "✅" if s.enabled else "❌"
                    lines.append(f"{status} {s.name} - {s.description}")
                return ToolResult.ok(
                    data={"skills": [{"name": s.name, "description": s.description, "enabled": s.enabled} for s in skills]},
                    message="\n".join(lines)
                )
            
            else:
                return ToolResult.err(f"未知操作：{action}")
        except Exception as e:
            return ToolResult.err(f"配置管理失败：{e}")


class SkillTool(Tool):
    name = "skill_manager"
    description = "技能管理系统 - 列出可用技能、获取技能详情、执行技能"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list, get_details, execute",
                "enum": ["list", "get_details", "execute"]
            },
            "skill_name": {"type": "string", "description": "技能名称（get_details 和 execute 时需要）"},
            "parameters": {"type": "object", "description": "技能执行参数（execute 时需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._skill_registry: Dict[str, Callable] = {}

    def execute(self, action: str, skill_name: Optional[str] = None, parameters: Optional[Dict[str, Any]] = None) -> str:
        result = self.execute_structured(action, skill_name, parameters)
        return result.to_json()

    def execute_structured(self, action: str, skill_name: Optional[str] = None, parameters: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            from .config import get_config_manager
            config_mgr = get_config_manager()

            if action == "list":
                enabled_skills = config_mgr.get_enabled_skills()
                disabled_skills = [s for s in config_mgr.skill_configs.values() if not s.enabled]
                
                lines = ["=== 已启用的技能 ==="]
                for s in enabled_skills:
                    lines.append(f"✅ {s.name}: {s.description}")
                    if s.parameters:
                        lines.append(f"   参数: {json.dumps(s.parameters, ensure_ascii=False)}")
                
                if disabled_skills:
                    lines.append("\n=== 已禁用的技能 ===")
                    for s in disabled_skills:
                        lines.append(f"❌ {s.name}: {s.description}")
                
                data = {
                    "enabled": [{"name": s.name, "description": s.description, "type": s.type} for s in enabled_skills],
                    "disabled": [{"name": s.name, "description": s.description, "type": s.type} for s in disabled_skills],
                }
                
                return ToolResult.ok(
                    data=data,
                    message="\n".join(lines)
                )
            
            elif action == "get_details":
                if not skill_name:
                    return ToolResult.err("get_details 需要 skill_name 参数")
                
                skill_config = config_mgr.skill_configs.get(skill_name)
                if not skill_config:
                    return ToolResult.err(f"技能 '{skill_name}' 不存在")
                
                details = {
                    "name": skill_config.name,
                    "description": skill_config.description,
                    "type": skill_config.type,
                    "enabled": skill_config.enabled,
                    "parameters": skill_config.parameters,
                    "dependencies": skill_config.dependencies,
                    "handler_path": skill_config.handler_path,
                    "metadata": skill_config.metadata,
                }
                
                lines = [f"=== 技能详情: {skill_name} ==="]
                lines.append(f"描述: {skill_config.description}")
                lines.append(f"类型: {skill_config.type}")
                lines.append(f"状态: {'启用' if skill_config.enabled else '禁用'}")
                if skill_config.parameters:
                    lines.append(f"参数定义: {json.dumps(skill_config.parameters, ensure_ascii=False, indent=2)}")
                if skill_config.dependencies:
                    lines.append(f"依赖: {', '.join(skill_config.dependencies)}")
                if skill_config.handler_path:
                    lines.append(f"处理器路径: {skill_config.handler_path}")
                
                return ToolResult.ok(
                    data=details,
                    message="\n".join(lines)
                )
            
            elif action == "execute":
                if not skill_name:
                    return ToolResult.err("execute 需要 skill_name 参数")
                
                skill_config = config_mgr.skill_configs.get(skill_name)
                if not skill_config:
                    return ToolResult.err(f"技能 '{skill_name}' 不存在")
                
                if not skill_config.enabled:
                    return ToolResult.err(f"技能 '{skill_name}' 已禁用")
                
                result = self._execute_skill(skill_config, parameters or {})
                
                if result["success"]:
                    return ToolResult.ok(
                        data=result["data"],
                        message=result["message"]
                    )
                else:
                    return ToolResult.err(result["message"])
            
            else:
                return ToolResult.err(f"未知操作：{action}，支持的操作为：list, get_details, execute")
        
        except Exception as e:
            return ToolResult.err(f"技能管理失败：{e}")

    def _execute_skill(self, skill_config, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能"""
        try:
            # 内置技能处理
            if skill_config.type == "builtin" or skill_config.name in [
                "read_file", "write_file", "edit_file", "list_directory",
                "grep", "glob", "calculate", "web_search", "fetch_url",
                "analyze_paper", "open_file", "diff_files", "move_file",
                "copy_file", "file_info", "cli_execute", "config_manage",
                "sub_agent", "hub_search", "hub_lightweight_crawl",
                "hub_discover_subscriptions"
            ]:
                return self._execute_builtin_skill(skill_config.name, parameters)
            
            # 自定义技能处理
            elif skill_config.handler_path:
                return self._execute_custom_skill(skill_config, parameters)
            
            else:
                return {
                    "success": False,
                    "message": f"技能 '{skill_config.name}' 没有可执行的处理器"
                }
        
        except Exception as e:
            return {
                "success": False,
                "message": f"执行技能失败：{e}"
            }

    def _execute_builtin_skill(self, skill_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行内置技能"""
        return {
            "success": True,
            "data": {"skill": skill_name, "parameters": parameters},
            "message": f"内置技能 '{skill_name}' 应通过对应的工具调用。参数：{json.dumps(parameters, ensure_ascii=False)}"
        }

    def _execute_custom_skill(self, skill_config, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行自定义技能"""
        try:
            if skill_config.handler_path:
                module_path, func_name = skill_config.handler_path.rsplit('.', 1)
                module = __import__(module_path, fromlist=[func_name])
                handler = getattr(module, func_name)
                result = handler(parameters)
                
                return {
                    "success": True,
                    "data": result if isinstance(result, dict) else {"result": result},
                    "message": f"技能 '{skill_config.name}' 执行成功"
                }
            else:
                return {
                    "success": False,
                    "message": f"技能 '{skill_config.name}' 没有配置处理器路径"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"执行自定义技能失败：{e}"
            }

    def register_skill_handler(self, skill_name: str, handler_func: Callable):
        """注册技能处理器"""
        self._skill_registry[skill_name] = handler_func

    def unregister_skill_handler(self, skill_name: str):
        """取消注册技能处理器"""
        if skill_name in self._skill_registry:
            del self._skill_registry[skill_name]

    def list_skill_handlers(self) -> List[str]:
        """列出已注册的技能处理器"""
        return list(self._skill_registry.keys())


class RAGTool(Tool):
    """RAG（检索增强生成）工具 - 文档向量化存储和检索"""
    name = "rag_retrieval"
    description = "RAG检索系统 - 添加文档到向量库、检索相关内容"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：add_file, add_directory, retrieve, query, get_count, list_documents, clear",
                "enum": ["add_file", "add_directory", "retrieve", "query", "get_count", "list_documents", "clear"]
            },
            "file_path": {"type": "string", "description": "文件路径（add_file 时需要）"},
            "directory_path": {"type": "string", "description": "目录路径（add_directory 时需要）"},
            "query": {"type": "string", "description": "查询文本（retrieve/query 时需要）"},
            "top_k": {"type": "integer", "description": "返回结果数量（默认4）"},
            "metadata": {"type": "object", "description": "元数据（add_file 时可选）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._rag_engine = None

    def _get_rag_engine(self):
        """获取或初始化 RAG 引擎"""
        if self._rag_engine is None:
            try:
                from .rag.rag_engine import RAGEngine
                persist_dir = self.base_dir / "rag_data"
                persist_dir.mkdir(exist_ok=True)
                self._rag_engine = RAGEngine(persist_directory=persist_dir)
            except Exception as e:
                logger.warning(f"RAG引擎初始化失败: {e}")
                return None
        return self._rag_engine

    def execute(self, action: str, file_path: Optional[str] = None, directory_path: Optional[str] = None,
                query: Optional[str] = None, top_k: int = 4, metadata: Optional[Dict[str, Any]] = None) -> str:
        result = self.execute_structured(action, file_path, directory_path, query, top_k, metadata)
        return result.to_json()

    def execute_structured(self, action: str, file_path: Optional[str] = None, directory_path: Optional[str] = None,
                          query: Optional[str] = None, top_k: int = 4, metadata: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            rag_engine = self._get_rag_engine()
            if rag_engine is None:
                return ToolResult.err("RAG引擎初始化失败")

            if action == "add_file":
                if not file_path:
                    return ToolResult.err("add_file 需要 file_path 参数")
                
                file_path_obj = Path(file_path)
                if not file_path_obj.is_absolute():
                    file_path_obj = self.base_dir / file_path_obj
                
                if not file_path_obj.exists():
                    return ToolResult.err(f"文件不存在: {file_path}")
                
                chunk_ids = rag_engine.add_file(file_path_obj, metadata=metadata)
                return ToolResult.ok(
                    data={"file": str(file_path_obj), "chunk_ids": chunk_ids, "chunk_count": len(chunk_ids)},
                    message=f"✅ 已添加文件: {file_path_obj.name}，生成 {len(chunk_ids)} 个文本块"
                )
            
            elif action == "add_directory":
                if not directory_path:
                    return ToolResult.err("add_directory 需要 directory_path 参数")
                
                dir_path = Path(directory_path)
                if not dir_path.is_absolute():
                    dir_path = self.base_dir / dir_path
                
                if not dir_path.exists() or not dir_path.is_dir():
                    return ToolResult.err(f"目录不存在: {directory_path}")
                
                result = rag_engine.add_directory(dir_path)
                return ToolResult.ok(
                    data={"directory": str(dir_path), "result": result},
                    message=f"✅ 已添加目录: {directory_path}，共 {result['file_count']} 个文件，{result['chunk_count']} 个文本块"
                )
            
            elif action == "retrieve":
                if not query:
                    return ToolResult.err("retrieve 需要 query 参数")
                
                results = rag_engine.retrieve_with_scores(query, top_k=top_k)
                lines = [f"=== 检索到 {len(results)} 个相关片段 ==="]
                for i, (doc, score) in enumerate(results, 1):
                    content_preview = doc.page_content[:200].replace('\n', ' ')
                    lines.append(f"\n【片段 {i}】(相似度: {score:.3f})")
                    lines.append(f"内容: {content_preview}...")
                    if doc.metadata:
                        lines.append(f"元数据: {json.dumps(doc.metadata, ensure_ascii=False)}")
                
                return ToolResult.ok(
                    data={"query": query, "results": [(doc.page_content, score) for doc, score in results]},
                    message="\n".join(lines)
                )
            
            elif action == "query":
                if not query:
                    return ToolResult.err("query 需要 query 参数")
                
                result = rag_engine.query(query, top_k=top_k)
                lines = [f"=== 查询结果 ({result['count']} 个文档) ==="]
                for doc_info in result["documents"]:
                    lines.append(f"\n【来源: {doc_info['source']}】")
                    lines.append(f"内容: {doc_info['content'][:300]}...")
                
                return ToolResult.ok(
                    data=result,
                    message="\n".join(lines)
                )
            
            elif action == "get_count":
                count = rag_engine.get_document_count()
                return ToolResult.ok(
                    data={"document_count": count},
                    message=f"📊 向量库中共有 {count} 个文档"
                )
            
            elif action == "list_documents":
                docs = rag_engine.get_all_documents()
                lines = [f"=== 所有文档 ({len(docs)} 个) ==="]
                for i, doc in enumerate(docs, 1):
                    lines.append(f"\n【{i}】{doc.source}")
                    lines.append(f"内容预览: {doc.page_content[:100]}...")
                
                return ToolResult.ok(
                    data={"documents": [{"source": doc.source, "id": doc.id} for doc in docs]},
                    message="\n".join(lines)
                )
            
            elif action == "clear":
                rag_engine.clear()
                return ToolResult.ok(
                    data={"status": "cleared"},
                    message="✅ 已清空向量库中的所有文档"
                )
            
            else:
                return ToolResult.err(f"未知操作：{action}")
        
        except Exception as e:
            return ToolResult.err(f"RAG操作失败: {e}")


class SandboxTool(Tool):
    """沙箱执行工具 - 安全执行命令"""
    name = "sandbox_execute"
    description = "沙箱安全执行 - 在受限环境中执行命令"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "allow_network": {"type": "boolean", "description": "是否允许网络访问", "default": False},
            "max_time": {"type": "integer", "description": "最大执行时间（秒）", "default": 30},
            "open_terminal": {"type": "boolean", "description": "是否在新终端窗口中执行，默认 false"},
            "keep_terminal_open": {"type": "boolean", "description": "命令执行后是否保持终端打开，默认 true"},
        },
        "required": ["command"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, command: str, allow_network: bool = False, max_time: int = 30, open_terminal: bool = False, keep_terminal_open: bool = True) -> str:
        result = self.execute_structured(command, allow_network, max_time, open_terminal, keep_terminal_open)
        return result.to_json()

    def execute_structured(self, command: str, allow_network: bool = False, max_time: int = 30, open_terminal: bool = False, keep_terminal_open: bool = True) -> ToolResult:
        try:
            if open_terminal:
                return self._execute_in_terminal(command, keep_terminal_open)
            
            try:
                from .sandbox.executor import SandboxExecutor
                from .sandbox.policy import SandboxPolicy
                
                policy = SandboxPolicy(
                    allow_network=allow_network,
                    max_execution_time=max_time
                )
                executor = SandboxExecutor(policy=policy, cwd=str(self.base_dir))
                
                result = executor.execute(command)
                
                output_lines = [
                    f"$ {command}",
                    result.stdout or "(无输出)",
                ]
                if result.stderr:
                    output_lines.append(f"错误: {result.stderr}")
                output_lines.append(f"[返回码: {result.exit_code}]")
                if result.timed_out:
                    output_lines.append("[超时]")
                output_lines.append(f"[耗时: {result.duration_ms}ms]")
                
                if result.success:
                    return ToolResult.ok(
                        data={
                            "command": command,
                            "exit_code": result.exit_code,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "duration_ms": result.duration_ms,
                        },
                        message="\n".join(output_lines)
                    )
                else:
                    return ToolResult.ok(
                        data={
                            "command": command,
                            "exit_code": result.exit_code,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "duration_ms": result.duration_ms,
                            "error": result.error,
                            "timed_out": result.timed_out,
                        },
                        message="\n".join(output_lines)
                    )
            except ImportError:
                # 如果没有沙箱模块，退回到普通的CLI执行
                logger.warning("沙箱模块未找到，使用普通CLI执行")
                from .tools import CLITool
                cli_tool = CLITool(base_dir=self.base_dir)
                return cli_tool.execute_structured(command=command)
        
        except Exception as e:
            return ToolResult.err(f"沙箱执行失败: {e}")

    def _execute_in_terminal(self, command: str, keep_open: bool) -> ToolResult:
        import subprocess
        import platform

        working_dir = self.base_dir
        working_dir.mkdir(parents=True, exist_ok=True)

        try:
            system = platform.system()
            
            if system == "Windows":
                cmd_parts = ["cmd", "/k"] if keep_open else ["cmd", "/c"]
                cmd_parts.append(command)
                subprocess.Popen(cmd_parts, cwd=str(working_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)
                
            elif system == "Darwin":
                script = f'cd "{working_dir}"; {command}'
                if keep_open:
                    script += '; exec bash'
                applescript = f'tell application "Terminal" to do script "{script}"'
                subprocess.run(["osascript", "-e", applescript], check=True)
                
            else:
                shell = os.environ.get("SHELL", "bash")
                if keep_open:
                    script = f"{command}; exec {shell}"
                else:
                    script = command
                subprocess.Popen([shell, "-c", script], cwd=str(working_dir))

            return ToolResult.ok(
                data={"command": command, "in_terminal": True, "keep_open": keep_open, "sandbox": False},
                message=f"🖥️ 已在新终端中执行命令: {command}\n(注意：终端模式下安全限制可能较宽松)"
            )
        except Exception as e:
            return ToolResult.err(f"在终端执行失败: {e}")


class MCPClientTool(Tool):
    """MCP客户端工具 - 管理外部MCP服务"""
    name = "mcp_client"
    description = "MCP客户端管理 - 列出可用工具、调用MCP服务"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list_tools, call_tool, get_status",
                "enum": ["list_tools", "call_tool", "get_status"]
            },
            "tool_name": {"type": "string", "description": "工具名称（call_tool 时需要）"},
            "arguments": {"type": "object", "description": "工具参数（call_tool 时需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._client_manager = None

    def _get_client_manager(self):
        """获取或初始化 MCP 客户端管理器"""
        if self._client_manager is None:
            try:
                from .mcp_client.client import MCPClientManager
                self._client_manager = MCPClientManager()
            except Exception as e:
                logger.warning(f"MCP客户端初始化失败: {e}")
                return None
        return self._client_manager

    def execute(self, action: str, tool_name: Optional[str] = None, arguments: Optional[Dict[str, Any]] = None) -> str:
        result = self.execute_structured(action, tool_name, arguments)
        return result.to_json()

    def execute_structured(self, action: str, tool_name: Optional[str] = None, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            client_mgr = self._get_client_manager()
            if client_mgr is None:
                return ToolResult.err("MCP客户端管理器初始化失败")

            if action == "list_tools":
                tools = client_mgr.list_tools()
                lines = ["=== 可用的 MCP 工具 ==="]
                for tool in tools:
                    name = tool.get("name", "未知")
                    desc = tool.get("description", "无描述")
                    lines.append(f"• {name}: {desc}")
                
                return ToolResult.ok(
                    data={"tools": tools, "count": len(tools)},
                    message="\n".join(lines) if lines else "暂无可用的 MCP 工具"
                )
            
            elif action == "call_tool":
                if not tool_name:
                    return ToolResult.err("call_tool 需要 tool_name 参数")
                
                result = client_mgr.call_tool(tool_name, arguments or {})
                return ToolResult.ok(
                    data={"tool": tool_name, "arguments": arguments, "result": result},
                    message=f"✅ MCP 工具 '{tool_name}' 执行成功"
                )
            
            elif action == "get_status":
                clients = client_mgr.list_clients()
                lines = ["=== MCP 客户端状态 ==="]
                for name, info in clients.items():
                    state = info.state.value
                    lines.append(f"• {name}: {state}")
                    if info.error:
                        lines.append(f"  错误: {info.error}")
                
                return ToolResult.ok(
                    data={"clients": {name: {"state": info.state.value, "error": info.error} for name, info in clients.items()}},
                    message="\n".join(lines) if lines else "暂无连接的 MCP 客户端"
                )
            
            else:
                return ToolResult.err(f"未知操作：{action}")
        
        except Exception as e:
            return ToolResult.err(f"MCP客户端操作失败: {e}")


class WorkflowTool(Tool):
    """工作流管理工具 - 定义、执行、管理工作流"""
    name = "workflow"
    description = "工作流管理 - 定义工作流、启动工作流、查看状态、取消、日志"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：define, start, status, pause, resume, cancel, list, logs, step_results",
                "enum": ["define", "start", "status", "pause", "resume", "cancel", "list", "logs", "step_results"]
            },
            "workflow_id": {"type": "string", "description": "工作流 ID（除 list 和 define 外的操作需要）"},
            "instance_id": {"type": "string", "description": "实例 ID（status, pause, resume 需要）"},
            "definition": {"type": "object", "description": "工作流定义对象（define 需要）"},
            "input_data": {"type": "object", "description": "输入数据（start 需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from .workflow_engine import get_workflow_engine
            db_path = self.base_dir / "data" / "workflow.db"
            self._engine = get_workflow_engine(db_path)
        return self._engine

    def execute(self, action: str, workflow_id: Optional[str] = None, 
                instance_id: Optional[str] = None, definition: Optional[Dict] = None,
                input_data: Optional[Dict] = None) -> str:
        result = self.execute_structured(action, workflow_id, instance_id, definition, input_data)
        return result.to_json()

    def execute_structured(self, action: str, workflow_id: Optional[str] = None,
                          instance_id: Optional[str] = None, definition: Optional[Dict] = None,
                          input_data: Optional[Dict] = None) -> ToolResult:
        try:
            from .workflow_engine import WorkflowDefinition, StepDefinition, StepType
            
            engine = self._get_engine()
            
            if action == "define":
                if not workflow_id or not definition:
                    return ToolResult.err("define 需要 workflow_id 和 definition")
                
                steps = [StepDefinition.from_dict(s) for s in definition.get("steps", [])]
                wf_def = WorkflowDefinition(
                    workflow_id=workflow_id,
                    name=definition.get("name", workflow_id),
                    description=definition.get("description", ""),
                    version=definition.get("version", "1.0"),
                    steps=steps,
                    entry_step=definition.get("entry_step"),
                    checkpoint_after=set(definition.get("checkpoint_after", [])),
                )
                engine.persistence.save_definition(wf_def)
                return ToolResult.ok(
                    data={"workflow_id": workflow_id},
                    message=f"✅ 工作流定义保存成功: {wf_def.name}"
                )
                
            elif action == "start":
                if not workflow_id:
                    return ToolResult.err("start 需要 workflow_id")
                
                wf_def = engine.persistence.get_definition(workflow_id)
                if not wf_def:
                    return ToolResult.err(f"工作流不存在: {workflow_id}")
                
                inst_id = engine.start_workflow(wf_def, input_data or {})
                return ToolResult.ok(
                    data={"instance_id": inst_id},
                    message=f"🚀 工作流启动成功: {wf_def.name}\n实例 ID: {inst_id}"
                )
                
            elif action == "status":
                if not instance_id:
                    return ToolResult.err("status 需要 instance_id")
                
                status = engine.get_status(instance_id)
                if not status:
                    return ToolResult.err(f"实例不存在: {instance_id}")
                
                lines = [f"📊 工作流状态: {status['workflow_id']}"]
                lines.append(f"状态: {status['status']}")
                lines.append(f"当前步骤: {status.get('current_step', '-')}")
                lines.append(f"进度: {status.get('progress', 0)*100:.0f}%")
                lines.append(f"启动时间: {status.get('started_at', '-')}")
                
                return ToolResult.ok(
                    data=status,
                    message="\n".join(lines)
                )
                
            elif action == "pause":
                if not instance_id:
                    return ToolResult.err("pause 需要 instance_id")
                
                if engine.pause_workflow(instance_id):
                    return ToolResult.ok(
                        data={"instance_id": instance_id},
                        message="⏸️ 工作流已暂停"
                    )
                else:
                    return ToolResult.err(f"暂停失败，实例可能不存在或未在运行: {instance_id}")
                
            elif action == "resume":
                if not instance_id:
                    return ToolResult.err("resume 需要 instance_id")
                
                if engine.resume_workflow(instance_id):
                    return ToolResult.ok(
                        data={"instance_id": instance_id},
                        message="▶️ 工作流已恢复"
                    )
                else:
                    return ToolResult.err(f"恢复失败，实例可能不存在或不可恢复: {instance_id}")
                
            elif action == "cancel":
                if not instance_id:
                    return ToolResult.err("cancel 需要 instance_id")
                
                if engine.cancel_workflow(instance_id):
                    return ToolResult.ok(
                        data={"instance_id": instance_id},
                        message="🚫 工作流已取消"
                    )
                else:
                    return ToolResult.err(f"取消失败，实例可能不存在或未在运行: {instance_id}")
                
            elif action == "logs":
                if not instance_id:
                    return ToolResult.err("logs 需要 instance_id")
                
                logs = engine.get_logs(instance_id, limit=20)
                if not logs:
                    return ToolResult.ok(message="暂无日志")
                
                lines = [f"📋 工作流日志 ({instance_id[:8]}):"]
                for log in reversed(logs):
                    level = log.get("log_level", "info")
                    ts = log.get("created_at", "")[11:19]
                    step = log.get("step_name", "")
                    step_info = f"[{step}] " if step else ""
                    lines.append(f"  {ts} {step_info}{log.get('message', '')}")
                
                return ToolResult.ok(
                    data={"logs": logs},
                    message="\n".join(lines)
                )
                
            elif action == "step_results":
                if not instance_id:
                    return ToolResult.err("step_results 需要 instance_id")
                
                step_results = engine.get_step_results(instance_id)
                if not step_results:
                    return ToolResult.ok(message="暂无步骤结果")
                
                lines = [f"📊 步骤结果 ({instance_id[:8]}):"]
                for sid, sr in step_results.items():
                    status = sr.get("status", "")
                    icon = {"completed": "✅", "running": "🔄", "failed": "❌"}.get(status, "❓")
                    lines.append(f"  {icon} {sid}: {status}")
                    if sr.get("error"):
                        lines.append(f"     错误: {sr['error']}")
                
                return ToolResult.ok(
                    data={"step_results": step_results},
                    message="\n".join(lines)
                )
                
            elif action == "list":
                defs = engine.persistence.list_definitions()
                instances = engine.persistence.list_instances()
                
                lines = ["📋 工作流定义:"]
                if defs:
                    for d in defs:
                        lines.append(f"  • {d['workflow_id']} - {d['name']}")
                else:
                    lines.append("  (暂无定义)")
                
                lines.append("\n🔄 最近运行实例:")
                if instances:
                    for i in instances[:10]:
                        lines.append(f"  • {i['instance_id']} - {i['workflow_id']} - {i['status']}")
                else:
                    lines.append("  (暂无运行)")
                
                return ToolResult.ok(
                    data={"definitions": defs, "instances": instances},
                    message="\n".join(lines)
                )
                
            else:
                return ToolResult.err(f"未知操作: {action}")
        
        except Exception as e:
            import traceback
            logger.error(f"Workflow tool error: {e}")
            logger.error(traceback.format_exc())
            return ToolResult.err(f"工作流操作失败: {e}")


class ApprovalTool(Tool):
    """审批管理工具 - 查看和处理待审批的请求"""
    name = "approval"
    description = "审批管理 - 查看待审批、批准/拒绝请求、设置审批模式"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list_pending, approve, deny, always_approve, set_mode",
                "enum": ["list_pending", "approve", "deny", "always_approve", "set_mode"]
            },
            "request_id": {"type": "string", "description": "请求 ID（approve, deny, always_approve 需要）"},
            "mode": {"type": "string", "description": "审批模式（set_mode 需要）：suggest, auto_edit, full_auto",
                     "enum": ["suggest", "auto_edit", "full_auto"]},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._manager = None

    def _get_manager(self):
        if self._manager is None:
            from .harness import ApprovalManager, ApprovalMode
            self._manager = ApprovalManager(mode=ApprovalMode.SUGGEST)
        return self._manager

    def execute(self, action: str, request_id: Optional[str] = None, mode: Optional[str] = None) -> str:
        result = self.execute_structured(action, request_id, mode)
        return result.to_json()

    def execute_structured(self, action: str, request_id: Optional[str] = None,
                          mode: Optional[str] = None) -> ToolResult:
        try:
            from .harness import ApprovalManager, ApprovalMode, ApprovalDecision
            
            mgr = self._get_manager()
            
            if action == "list_pending":
                pending = mgr.get_pending()
                
                lines = ["⏳ 待审批请求:"]
                if pending:
                    for req in pending:
                        lines.append(f"  [{req.id}] {req.tool_name}")
                        lines.append(f"    风险等级: {req.risk_level}")
                        if req.reason:
                            lines.append(f"    原因: {req.reason}")
                else:
                    lines.append("  (暂无待审批)")
                
                return ToolResult.ok(
                    data={"pending": [{"id": r.id, "tool": r.tool_name, "risk": r.risk_level} for r in pending]},
                    message="\n".join(lines)
                )
                
            elif action in ("approve", "deny", "always_approve"):
                if not request_id:
                    return ToolResult.err(f"{action} 需要 request_id")
                
                decision_map = {
                    "approve": ApprovalDecision.APPROVE,
                    "deny": ApprovalDecision.DENY,
                    "always_approve": ApprovalDecision.ALWAYS_APPROVE,
                }
                
                mgr.decide(request_id, decision_map[action])
                
                msg = {
                    "approve": "✅ 请求已批准",
                    "deny": "❌ 请求已拒绝",
                    "always_approve": "✅ 请求已批准，此类请求将自动通过",
                }[action]
                
                return ToolResult.ok(
                    data={"request_id": request_id, "action": action},
                    message=msg
                )
                
            elif action == "set_mode":
                if not mode:
                    return ToolResult.err("set_mode 需要 mode 参数")
                
                mode_map = {
                    "suggest": ApprovalMode.SUGGEST,
                    "auto_edit": ApprovalMode.AUTO_EDIT,
                    "full_auto": ApprovalMode.FULL_AUTO,
                }
                mgr._mode = mode_map[mode]
                
                mode_desc = {
                    "suggest": "建议模式 - 所有操作需要审批",
                    "auto_edit": "自动编辑模式 - 仅敏感操作需要审批",
                    "full_auto": "全自动模式 - 无需审批",
                }
                
                return ToolResult.ok(
                    data={"mode": mode},
                    message=f"🔧 审批模式已设置: {mode_desc[mode]}"
                )
                
            else:
                return ToolResult.err(f"未知操作: {action}")
        
        except Exception as e:
            return ToolResult.err(f"审批操作失败: {e}")


class ExtensionSkillTool(Tool):
    """扩展技能管理工具 - 基于新的 MCP 扩展系统"""
    name = "extension_skill"
    description = "扩展技能管理 - 管理 MCP 扩展系统中的技能"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list, get, execute, load, export",
                "enum": ["list", "get", "execute", "load", "export"]
            },
            "skill_name": {"type": "string", "description": "技能名称"},
            "file_path": {"type": "string", "description": "技能文件路径（load, export 需要）"},
            "parameters": {"type": "object", "description": "执行技能时的参数"},
            "category": {"type": "string", "description": "分类（list 需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._registry = None

    def _get_registry(self):
        if self._registry is None:
            from .extensions.skills import get_skill_registry
            self._registry = get_skill_registry()
        return self._registry

    def execute(self, action: str, skill_name: Optional[str] = None,
                file_path: Optional[str] = None,
                parameters: Optional[Dict] = None,
                category: Optional[str] = None) -> str:
        result = self.execute_structured(action, skill_name, file_path, parameters, category)
        return result.to_json()

    def execute_structured(self, action: str, skill_name: Optional[str] = None,
                          file_path: Optional[str] = None,
                          parameters: Optional[Dict] = None,
                          category: Optional[str] = None) -> ToolResult:
        try:
            registry = self._get_registry()
            
            if action == "list":
                skills = registry.list_skills(category)
                lines = ["📋 技能列表:"]
                for skill in skills:
                    status = "✅" if skill.enabled else "❌"
                    lines.append(f"  {status} {skill.name} - {skill.description} ({skill.category}")
                return ToolResult.ok(
                    data={"skills": [{"name": s.name, "description": s.description, "category": s.category, "enabled": s.enabled} for s in skills]},
                    message="\n".join(lines)
                )
            
            elif action == "get":
                if not skill_name:
                    return ToolResult.err("get 需要 skill_name")
                skill = registry.get_skill(skill_name)
                if not skill:
                    return ToolResult.err(f"技能 '{skill_name}' 不存在")
                return ToolResult.ok(
                    data={"name": skill.name, "description": skill.description, "parameters": [p.__dict__ for p in skill.parameters]},
                    message=f"技能 '{skill.name}: {skill.description}"
                )
            
            elif action == "execute":
                if not skill_name:
                    return ToolResult.err("execute 需要 skill_name")
                import asyncio
                result = asyncio.run(registry.execute_skill(skill_name, **(parameters or {})))
                return ToolResult.ok(
                    data={"result": result},
                    message=f"技能执行结果: {result}"
                )
            
            elif action == "load":
                if not file_path:
                    return ToolResult.err("load 需要 file_path")
                path = Path(file_path)
                if not path.is_file():
                    return ToolResult.ok(message="成功加载技能文件")
                else:
                    return ToolResult.err("文件不存在")
            
            elif action == "export":
                if not skill_name or not file_path:
                    return ToolResult.err("export 需要 skill_name 和 file_path")
                path = Path(file_path)
                registry.export_skill(skill_name, path)
                return ToolResult.ok(message=f"已导出技能")
            
            else:
                return ToolResult.err(f"未知操作")
        
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error(traceback.format_exc())
            return ToolResult.err(f"技能操作失败: {e}")


class SessionTool(Tool):
    """会话管理工具 - 管理多个对话会话"""
    name = "session"
    description = "会话管理 - 创建、切换、管理多个对话会话"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：list, create, set_active, get, add_message, delete",
                "enum": ["list", "create", "set_active", "get", "add_message", "delete"]
            },
            "name": {"type": "string", "description": "会话名称（create 需要）"},
            "session_id": {"type": "string", "description": "会话 ID（set_active, get, add_message, delete 需要）"},
            "role": {"type": "string", "description": "消息角色（add_message 需要）"},
            "content": {"type": "string", "description": "消息内容（add_message 需要）"},
        },
        "required": ["action"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self._manager = None

    def _get_manager(self):
        if self._manager is None:
            from .extensions.unified_session import get_unified_session_manager
            self._manager = get_unified_session_manager()
        return self._manager

    def execute(self, action: str, name: Optional[str] = None,
                session_id: Optional[str] = None,
                role: Optional[str] = None,
                content: Optional[str] = None) -> str:
        result = self.execute_structured(action, name, session_id, role, content)
        return result.to_json()

    def execute_structured(self, action: str, name: Optional[str] = None,
                        session_id: Optional[str] = None,
                        role: Optional[str] = None,
                        content: Optional[str] = None) -> ToolResult:
        try:
            manager = self._get_manager()
            
            if action == "list":
                sessions = manager.list_sessions()
                active_id = manager.get_active_session_id()
                lines = ["💬 会话列表:"]
                for s in sessions:
                    marker = "👉" if s.session_id == active_id else "  "
                    task_info = " 🔄" if s.has_running_tasks else ""
                    lines.append(f"  {marker} {s.title} ({s.message_count} 条消息, {s.turn_count} 轮){task_info}")
                return ToolResult.ok(
                    data={"sessions": [s.to_dict() for s in sessions], "active_session_id": active_id},
                    message="\n".join(lines)
                )
            
            elif action == "create":
                if not name:
                    return ToolResult.err("create 需要 name")
                sid = manager.create_session(name)
                if sid:
                    return ToolResult.ok(
                        data={"session_id": sid, "name": name},
                        message=f"已创建会话: {name}"
                    )
                else:
                    return ToolResult.err("创建会话失败")
            
            elif action == "set_active":
                if not session_id:
                    return ToolResult.err("set_active 需要 session_id")
                if manager.set_active_session(session_id):
                    session = manager.get_session(session_id)
                    title = session.get("title", session_id) if session else session_id
                    return ToolResult.ok(
                        data={"session_id": session_id},
                        message=f"已切换到会话: {title}"
                    )
                else:
                    return ToolResult.err("会话不存在")
            
            elif action == "get":
                if session_id:
                    session = manager.get_session(session_id)
                else:
                    session = manager.get_active_session()
                if not session:
                    return ToolResult.err("没有活动会话")
                title = session.get("title", "未命名")
                msg_count = len(session.get("messages", []))
                return ToolResult.ok(
                    data=session,
                    message=f"当前会话: {title} ({msg_count} 条消息)"
                )
            
            elif action == "add_message":
                if not role or not content:
                    return ToolResult.err("add_message 需要 role 和 content")
                if not session_id:
                    active_id = manager.get_active_session_id()
                    if not active_id:
                        return ToolResult.err("没有活动会话，请指定 session_id")
                    session_id = active_id
                if manager.add_message(session_id, role, content):
                    return ToolResult.ok(message="已添加消息")
                else:
                    return ToolResult.err("添加消息失败")
            
            elif action == "delete":
                if not session_id:
                    return ToolResult.err("delete 需要 session_id")
                if manager.delete_session(session_id):
                    return ToolResult.ok(message="已删除会话")
                else:
                    return ToolResult.err("会话不存在")
            
            else:
                return ToolResult.err(f"未知操作: {action}")
        
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error(traceback.format_exc())
            return ToolResult.err(f"会话操作失败: {e}")


def get_tools(base_dir: Optional[Path] = None, enabled_only: bool = False) -> List[Tool]:
    """获取所有工具
    Args:
        base_dir: 基础目录
        enabled_only: 是否只返回启用的工具
    """
    all_tools = [
        ReadFileTool(base_dir),
        WriteFileTool(base_dir),
        EditFileTool(base_dir),
        ListDirectoryTool(base_dir),
        GrepTool(base_dir),
        GlobTool(base_dir),
        CalculateTool(),
        WebSearchTool(),
        FetchUrlTool(),
        AnalyzePaperTool(base_dir),
        OpenFileTool(base_dir),
        DiffFilesTool(base_dir),
        MoveFileTool(base_dir),
        CopyFileTool(base_dir),
        FileInfoTool(base_dir),
        CLITool(base_dir),
        ConfigTool(base_dir),
        SkillTool(base_dir),
        RAGTool(base_dir),
        SandboxTool(base_dir),
        MCPClientTool(base_dir),
        TerminalTool(base_dir),
        WorkflowTool(base_dir),
        ApprovalTool(base_dir),
        ExtensionSkillTool(base_dir),
        SessionTool(base_dir),
    ]

    try:
        from .scholar.server import ScholarMCPServer
        scholar_server = ScholarMCPServer()
        all_tools.extend(scholar_server.get_scholar_tools())
    except Exception:
        pass

    try:
        from .automation.engine import AutomationTool
        all_tools.append(AutomationTool(base_dir))
    except Exception:
        pass
    
    if enabled_only:
        try:
            from .config import get_config_manager
            config_mgr = get_config_manager()
            # 确保默认配置存在
            config_mgr.init_default_tool_configs(all_tools)
            enabled_names = [t.name for t in config_mgr.get_enabled_tools()]
            return [tool for tool in all_tools if tool.name in enabled_names]
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"获取启用的工具失败，返回所有工具: {e}")
            return all_tools
    return all_tools
