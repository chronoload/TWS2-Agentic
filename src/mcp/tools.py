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
from typing import Dict, List, Any, Optional, Union
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
            char_limit = max_chars or self.max_result_chars
            truncated = len(display_content) > char_limit
            if truncated:
                display_content = display_content[:char_limit] + f"\n\n... [已截断, 原始 {len(display_content)} 字符]"
            
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total_lines": total_lines,
                    "read_lines": len(read_lines),
                    "read_range": mode_desc,
                    "content": display_content,
                    "original_length": len(display_content),
                    "truncated": truncated,
                },
                message=f"--- {path} ({mode_desc}) ---\n{display_content}",
                truncated=truncated,
                original_length=len(display_content),
            )
        except Exception as e:
            return ToolResult.err(f"读取文件失败：{e}")


class WriteFileTool(Tool):
    name = "write_file"
    description = "写入文件内容，文件不存在则创建，存在则覆盖"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
            "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str, content: str, encoding: str = "utf-8") -> str:
        try:
            full_path = self.base_dir / Path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding=encoding)
            line_count = len(content.splitlines())
            return ToolResult.ok(
                data={"path": path, "line_count": line_count},
                message=f"成功：已写入 {path} ({line_count} 行)"
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"写入文件失败：{e}").to_json()

    def execute_structured(self, path: str, content: str, encoding: str = "utf-8") -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding=encoding)
            line_count = len(content.splitlines())
            return ToolResult.ok(
                data={"path": path, "line_count": line_count},
                message=f"成功：已写入 {path} ({line_count} 行)"
            )
        except Exception as e:
            return ToolResult.err(f"写入文件失败：{e}")


class EditFileTool(Tool):
    name = "edit_file"
    description = "通过搜索替换编辑文件，需要精确匹配 old_str"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_str": {"type": "string", "description": "要替换的旧内容"},
            "new_str": {"type": "string", "description": "新内容"},
            "encoding": {"type": "string", "description": "文件编码，默认 utf-8"},
        },
        "required": ["path", "old_str", "new_str"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str, old_str: str, new_str: str, encoding: str = "utf-8") -> str:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}").to_json()

            content = full_path.read_text(encoding=encoding)

            count = content.count(old_str)
            if count == 0:
                return ToolResult.err(f"未找到匹配内容").to_json()
            if count > 1:
                return ToolResult.err(f"找到 {count} 处匹配，请更精确地选择替换内容").to_json()

            new_content = content.replace(old_str, new_str)
            full_path.write_text(new_content, encoding=encoding)

            diff = self._generate_diff(old_str, new_str)
            return ToolResult.ok(
                data={"path": path, "replacements": 1, "diff": diff},
                message=f"成功：已编辑 {path}\n--- 变更 ---\n{diff}"
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"编辑文件失败：{e}").to_json()

    def execute_structured(self, path: str, old_str: str, new_str: str, encoding: str = "utf-8") -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{path}")

            content = full_path.read_text(encoding=encoding)
            count = content.count(old_str)
            if count == 0:
                return ToolResult.err(f"未找到匹配内容")
            if count > 1:
                return ToolResult.err(f"找到 {count} 处匹配，请更精确地选择替换内容")

            new_content = content.replace(old_str, new_str)
            full_path.write_text(new_content, encoding=encoding)
            diff = self._generate_diff(old_str, new_str)
            return ToolResult.ok(
                data={"path": path, "replacements": 1, "diff": diff},
                message=f"成功：已编辑 {path}\n--- 变更 ---\n{diff}"
            )
        except Exception as e:
            return ToolResult.err(f"编辑文件失败：{e}")

    def _generate_diff(self, old: str, new: str) -> str:
        lines = []
        old_lines = old.splitlines()
        new_lines = new.splitlines()

        lines.extend([f"- {line}" for line in old_lines])
        lines.append("---")
        lines.extend([f"+ {line}" for line in new_lines])

        return "\n".join(lines)


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "列出目录内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，默认为当前目录"},
        },
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, path: str = ".") -> str:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"目录不存在：{path}").to_json()
            if not full_path.is_dir():
                return ToolResult.err(f"不是目录：{path}").to_json()

            items = []
            for item in sorted(full_path.iterdir()):
                prefix = "📁" if item.is_dir() else "📄"
                items.append(f"{prefix} {item.name}")

            result = f"--- {path} ---\n" + "\n".join(items)
            return ToolResult.from_text(result, self.max_result_chars).to_json()
        except Exception as e:
            return ToolResult.err(f"列出目录失败：{e}").to_json()

    def execute_structured(self, path: str = ".") -> ToolResult:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"目录不存在：{path}")
            if not full_path.is_dir():
                return ToolResult.err(f"不是目录：{path}")

            dirs, files = [], []
            for item in sorted(full_path.iterdir()):
                if item.is_dir():
                    dirs.append(item.name)
                else:
                    files.append(item.name)

            return ToolResult.ok(
                data={"path": path, "directories": dirs, "files": files},
                message=f"--- {path} ---\n" + "\n".join(
                    [f"📁 {d}" for d in dirs] + [f"📄 {f}" for f in files]
                )
            )
        except Exception as e:
            return ToolResult.err(f"列出目录失败：{e}")


class GrepTool(Tool):
    name = "grep"
    description = "在目录中搜索内容"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索模式（正则表达式）"},
            "path": {"type": "string", "description": "搜索路径，默认为当前目录"},
            "extension": {"type": "string", "description": "文件扩展名过滤，如 .py, .md"},
        },
        "required": ["pattern"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, pattern: str, path: str = ".", extension: str = "") -> str:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"路径不存在：{path}").to_json()

            results = []
            pattern_re = re.compile(pattern)
            match_count = 0
            file_count = 0
            max_results = 50

            def search_file(file_path: Path):
                nonlocal match_count, file_count
                try:
                    content = file_path.read_text(errors="ignore")
                    found = False
                    for i, line in enumerate(content.splitlines(), 1):
                        if pattern_re.search(line):
                            if not found:
                                found = True
                                file_count += 1
                            if match_count < max_results:
                                results.append(f"{file_path}:{i}: {line}")
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
                return ToolResult.from_text(f"未找到匹配：{pattern}").to_json()

            text = f"--- 搜索结果：{pattern} ---\n"
            text += "\n".join(results[:50])
            if match_count > 50:
                text += f"\n\n... 还有 {match_count - 50} 处匹配（共 {file_count} 个文件）"

            return ToolResult.ok(
                data={
                    "pattern": pattern,
                    "total_matches": match_count,
                    "total_files": file_count,
                    "showing": min(match_count, 50),
                    "results": results[:50],
                },
                message=text
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"搜索失败：{e}").to_json()


class GlobTool(Tool):
    name = "glob"
    description = "使用 glob 模式查找文件"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "glob 模式，如 *.py, **/*.md"},
            "path": {"type": "string", "description": "搜索路径，默认为当前目录"},
        },
        "required": ["pattern"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, pattern: str, path: str = ".") -> str:
        try:
            full_path = self.base_dir / Path(path)
            if not full_path.exists():
                return ToolResult.err(f"路径不存在：{path}").to_json()

            files = sorted(full_path.glob(pattern))
            if not files:
                return ToolResult.from_text(f"未找到匹配：{pattern}").to_json()

            rel_files = []
            for f in files[:100]:
                try:
                    rel_files.append(str(f.relative_to(self.base_dir)))
                except ValueError:
                    rel_files.append(str(f))

            text = f"--- 查找结果：{pattern} ({len(files)} 个)---\n"
            text += "\n".join(rel_files)
            if len(files) > 100:
                text += f"\n\n... 还有 {len(files) - 100} 个文件"

            return ToolResult.ok(
                data={
                    "pattern": pattern,
                    "total": len(files),
                    "results": rel_files[:100],
                },
                message=text
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"glob 查找失败：{e}").to_json()


class CalculateTool(Tool):
    name = "calculate"
    description = "数学计算，支持 Python 表达式"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式，如 2 + 2, sin(pi/2)"},
        },
        "required": ["expression"],
    }

    def execute(self, expression: str) -> str:
        try:
            import math
            safe_namespace = {
                k: v for k, v in math.__dict__.items()
                if not k.startswith("_")
            }
            safe_namespace["pi"] = math.pi
            safe_namespace["e"] = math.e

            result = eval(expression, {"__builtins__": {}}, safe_namespace)
            return ToolResult.ok(
                data={"expression": expression, "result": result},
                message=f"{expression} = {result}"
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"计算失败：{e}").to_json()


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


class AnalyzePaperTool(Tool):
    name = "analyze_paper"
    description = "分析科研论文（PDF/DOCX/MD）"
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "论文文件路径"},
        },
        "required": ["file_path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()

    def execute(self, file_path: str) -> str:
        try:
            full_path = self.base_dir / Path(file_path)
            if not full_path.exists():
                return ToolResult.err(f"文件不存在：{file_path}").to_json()

            text = self._extract_text(full_path)
            if not text:
                return ToolResult.err("无法提取文本内容").to_json()

            truncated = len(text) > self.max_result_chars
            preview = text[:self.max_result_chars]

            return ToolResult.ok(
                data={
                    "file_path": file_path,
                    "original_length": len(text),
                    "preview": preview,
                    "truncated": truncated,
                },
                message=f"--- 分析论文：{file_path} ---\n\n{preview}"
            ).to_json()
        except Exception as e:
            return ToolResult.err(f"分析论文失败：{e}").to_json()

    def _extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                try:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        return "\n".join([page.extract_text() or "" for page in reader.pages])
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


class OpenFileTool(Tool):
    """用系统默认方式打开文件"""
    name = "open_file"
    description = """用系统默认程序打开文件（如 PDF 用阅读器、图片用查看器、文档用 Office 等）。
适用于需要查看文件原始格式（如 PDF 排版、图片、视频等）的场景。
注意：此工具仅打开文件，不返回文件内容。"""
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要打开的文件路径（绝对路径或相对于工作目录的路径）",
            },
        },
        "required": ["path"],
    }

    def __init__(self, base_dir: Optional[Path] = None):
        super().__init__()
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def execute(self, path: str) -> str:
        import subprocess
        import sys
        import platform

        # 解析路径
        target = Path(path)
        if not target.is_absolute():
            target = self.base_dir / target

        if not target.exists():
            return f'{{"success":false,"error":"文件不存在: {target}"}}'

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(target))
            elif system == "Darwin":  # macOS
                subprocess.run(["open", str(target)], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", str(target)], check=True)

            return f'{{"success":true,"message":"已用系统默认方式打开: {target.name}"}}'
        except Exception as e:
            return f'{{"success":false,"error":"打开文件失败: {e}"}}'


def get_tools(base_dir: Optional[Path] = None) -> List[Tool]:
    """获取所有工具"""
    return [
        ReadFileTool(base_dir),
        WriteFileTool(base_dir),
        EditFileTool(base_dir),
        ListDirectoryTool(base_dir),
        GrepTool(base_dir),
        GlobTool(base_dir),
        CalculateTool(),
        WebSearchTool(),
        AnalyzePaperTool(base_dir),
        OpenFileTool(base_dir),
    ]
