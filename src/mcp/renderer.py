#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一渲染增强模块 — 为所有 Text/ScrolledText 组件提供增强渲染能力

功能：
1. Markdown 完整渲染（表格/链接/列表/标题/引用/代码块）
2. 代码块语法高亮（Python/JSON/Bash/SQL 等）
3. LaTeX 数学公式渲染（集成 tex_to_utf8）
4. 表格格式化显示

用法：
    from mcp.renderer import EnhancedRenderer
    renderer = EnhancedRenderer(text_widget)
    renderer.render_markdown(text)
    renderer.render_code(code, language="python")
"""

import re
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# ── 可选依赖 ──

try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

try:
    from pygments import highlight as pygments_highlight
    from pygments.lexers import PythonLexer, JsonLexer, BashLexer, SqlLexer, TextLexer
    from pygments.formatters import get_formatter_by_name
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

try:
    import tex_to_utf8 as tex_module
    HAS_TEX = True
except ImportError:
    HAS_TEX = False


# ── 语言到 Lexer 的映射 ──

_LEXER_MAP = {
    "python": PythonLexer,
    "json": JsonLexer,
    "bash": BashLexer,
    "sh": BashLexer,
    "shell": BashLexer,
    "sql": SqlLexer,
}

# ── Pygments Token 到 Tkinter tag 的颜色映射 ──

_PYGMENTS_COLORS = {
    # 关键字
    "Keyword": "#ff79c6",
    "Keyword.Constant": "#ff79c6",
    "Keyword.Declaration": "#ff79c6",
    "Keyword.Namespace": "#ff79c6",
    "Keyword.Pseudo": "#ff79c6",
    "Keyword.Reserved": "#ff79c6",
    "Keyword.Type": "#ff79c6",
    # 字符串
    "String": "#f1fa8c",
    "String.Double": "#f1fa8c",
    "String.Single": "#f1fa8c",
    "String.Doc": "#6272a4",
    "String.Escape": "#f1fa8c",
    # 数字
    "Number": "#bd93f9",
    "Number.Float": "#bd93f9",
    "Number.Integer": "#bd93f9",
    # 注释
    "Comment": "#6272a4",
    "Comment.Single": "#6272a4",
    "Comment.Multiline": "#6272a4",
    "Comment.Preproc": "#ff79c6",
    # 函数名
    "Name.Function": "#50fa7b",
    "Name.Class": "#50fa7b",
    "Name.Decorator": "#50fa7b",
    # 变量
    "Name.Variable": "#8be9fd",
    "Name.Builtin": "#8be9fd",
    "Name.Constant": "#bd93f9",
    # 操作符
    "Operator": "#ff79c6",
    "Operator.Word": "#ff79c6",
    # 其他
    "Text": "#f8f8f2",
    "Punctuation": "#f8f8f2",
    "Literal": "#bd93f9",
}


class EnhancedRenderer:
    """统一渲染器 — 为 Tkinter Text/ScrolledText 提供增强渲染能力"""

    def __init__(self, text_widget, dark_mode: bool = False):
        """
        Args:
            text_widget: tkinter Text 或 ScrolledText 组件
            dark_mode: 是否使用暗色主题
        """
        self.text = text_widget
        self.dark_mode = dark_mode
        self._tag_counter = 0
        self._setup_default_tags()

    def _setup_default_tags(self):
        """设置默认的文本样式标签"""
        # 代码块背景
        bg_color = "#1e1e1e" if self.dark_mode else "#f6f8fa"
        fg_color = "#f8f8f2" if self.dark_mode else "#24292e"
        
        self.text.tag_config("code_block",
                             background=bg_color,
                             foreground=fg_color,
                             font=("Consolas", 10),
                             spacing1=6,
                             spacing3=6)
        
        self.text.tag_config("code_lang_label",
                             background=bg_color,
                             foreground="#6272a4",
                             font=("Segoe UI", 9, "bold"))
        
        # Markdown 元素样式
        self.text.tag_config("md_h1", font=("Microsoft YaHei UI", 16, "bold"),
                             foreground="#1a1a2e", spacing1=12, spacing3=6)
        self.text.tag_config("md_h2", font=("Microsoft YaHei UI", 14, "bold"),
                             foreground="#16213e", spacing1=10, spacing3=4)
        self.text.tag_config("md_h3", font=("Microsoft YaHei UI", 12, "bold"),
                             foreground="#0f3460", spacing1=8, spacing3=4)
        self.text.tag_config("md_h4", font=("Microsoft YaHei UI", 11, "bold"),
                             foreground="#533483", spacing1=6, spacing3=2)
        
        self.text.tag_config("md_bold", font=("", 10, "bold"))
        self.text.tag_config("md_italic", font=("", 10, "italic"))
        self.text.tag_config("md_inline_code",
                             background="#f6f8fa",
                             foreground="#e83e8c",
                             font=("Consolas", 10))
        self.text.tag_config("md_link", foreground="#0366d6",
                             font=("", 10, "underline"))
        self.text.tag_config("md_quote", foreground="#6a737d",
                             font=("", 10, "italic"))
        self.text.tag_config("md_list", foreground="#24292e",
                             font=("Microsoft YaHei UI", 10),
                             lmargin1=20, lmargin2=30)
        self.text.tag_config("md_table", font=("Consolas", 10),
                             background="#f6f8fa", spacing1=2)
        self.text.tag_config("md_hr", foreground="#e1e4e8",
                             font=("", 6))
        
        # 数学公式样式
        self.text.tag_config("math_inline",
                             foreground="#0066cc",
                             font=("Consolas", 11))
        self.text.tag_config("math_display",
                             foreground="#0066cc",
                             font=("Consolas", 12),
                             spacing1=8, spacing3=8)

    def render_markdown(self, text: str, start_index: str = "1.0"):
        """渲染 Markdown 文本到 Text 组件
        
        Args:
            text: Markdown 格式的文本
            start_index: 插入起始位置
        """
        self.text.config(state="normal")
        self._render_markdown_lines(text.split("\n"), start_index)
        self.text.config(state="disabled")

    def _render_markdown_lines(self, lines: List[str], start_index: str):
        """逐行渲染 Markdown"""
        in_code_block = False
        code_lang = ""
        code_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # 检测代码块开始
            if line.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_lang = line[3:].strip().lower()
                    code_lines = []
                    i += 1
                    continue
                else:
                    # 代码块结束，渲染
                    self._render_code_block("\n".join(code_lines), code_lang)
                    in_code_block = False
                    code_lang = ""
                    code_lines = []
                    i += 1
                    continue
            
            if in_code_block:
                code_lines.append(line)
                i += 1
                continue
            
            # 渲染普通 Markdown 行
            self._render_md_line(line)
            i += 1

    def _render_md_line(self, line: str):
        """渲染单行 Markdown"""
        # 水平线
        if re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', line.strip()):
            self.text.insert("end", "─" * 50 + "\n", "md_hr")
            return
        
        # 标题
        if line.startswith("#### "):
            self.text.insert("end", line[5:] + "\n", "md_h4")
            return
        elif line.startswith("### "):
            self.text.insert("end", line[4:] + "\n", "md_h3")
            return
        elif line.startswith("## "):
            self.text.insert("end", line[3:] + "\n", "md_h2")
            return
        elif line.startswith("# "):
            self.text.insert("end", line[2:] + "\n", "md_h1")
            return
        
        # 引用
        if line.startswith("> "):
            self.text.insert("end", "▎ " + line[2:] + "\n", "md_quote")
            return
        
        # 列表
        if re.match(r'^[-*+] ', line):
            self.text.insert("end", "• " + line[2:] + "\n", "md_list")
            return
        if re.match(r'^\d+\. ', line):
            self.text.insert("end", line + "\n", "md_list")
            return
        
        # 普通行：处理内联 Markdown
        self._render_inline_markdown(line + "\n")

    def _render_inline_markdown(self, text: str):
        """渲染内联 Markdown 元素（粗体、斜体、代码、链接、数学公式）"""
        # 使用正则分割文本，分别应用不同样式
        # 顺序很重要：代码 > 数学公式 > 粗体/斜体 > 链接
        
        parts = []
        last_end = 0
        
        # 匹配模式（按优先级）
        patterns = [
            (r'`([^`]+)`', 'inline_code'),        # 内联代码
            (r'\$\$([\s\S]*?)\$\$', 'math_display'),  # 显示数学
            (r'\$([^$]+?)\$', 'math_inline'),      # 内联数学
            (r'\*\*(.+?)\*\*', 'bold'),            # 粗体
            (r'\*(.+?)\*', 'italic'),              # 斜体
            (r'\[([^\]]+)\]\(([^)]+)\)', 'link'),  # 链接
        ]
        
        # 简化的实现：逐个处理
        result = text
        
        # 处理内联代码
        result = re.sub(r'`([^`]+)`', lambda m: f'\x00CODE:{m.group(1)}\x00', result)
        # 处理数学公式
        result = re.sub(r'\$\$([\s\S]*?)\$\$', lambda m: f'\x00MATH_DISPLAY:{m.group(1)}\x00', result)
        result = re.sub(r'\$([^$]+?)\$', lambda m: f'\x00MATH:{m.group(1)}\x00', result)
        # 处理粗体
        result = re.sub(r'\*\*(.+?)\*\*', lambda m: f'\x00BOLD:{m.group(1)}\x00', result)
        # 处理斜体
        result = re.sub(r'\*(.+?)\*', lambda m: f'\x00ITALIC:{m.group(1)}\x00', result)
        # 处理链接
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'\x00LINK:{m.group(1)}|{m.group(2)}\x00', result)
        
        # 分割并插入
        segments = result.split('\x00')
        for segment in segments:
            if segment.startswith("CODE:"):
                self.text.insert("end", segment[5:], "md_inline_code")
            elif segment.startswith("MATH_DISPLAY:"):
                formula = segment[13:]
                if HAS_TEX:
                    formula = tex_module.TeXToUTF8().translate_for_display(
                        f"$${formula}$$", enable_translation=True)
                self.text.insert("end", "\n" + formula + "\n", "math_display")
            elif segment.startswith("MATH:"):
                formula = segment[5:]
                if HAS_TEX:
                    formula = tex_module.TeXToUTF8().translate_for_display(
                        f"${formula}$", enable_translation=True)
                self.text.insert("end", formula, "math_inline")
            elif segment.startswith("BOLD:"):
                self.text.insert("end", segment[5:], "md_bold")
            elif segment.startswith("ITALIC:"):
                self.text.insert("end", segment[7:], "md_italic")
            elif segment.startswith("LINK:"):
                parts = segment[5:].split("|", 1)
                label = parts[0]
                url = parts[1] if len(parts) > 1 else ""
                self.text.insert("end", label, "md_link")
            else:
                self.text.insert("end", segment)

    def render_code(self, code: str, language: str = "python", 
                    start_index: str = "end", show_line_numbers: bool = True):
        """渲染带语法高亮的代码块
        
        Args:
            code: 代码文本
            language: 编程语言
            start_index: 插入起始位置
            show_line_numbers: 是否显示行号
        """
        if HAS_PYGMENTS:
            self._render_code_pygments(code, language, show_line_numbers)
        else:
            self._render_code_plain(code, language)

    def _render_code_pygments(self, code: str, language: str, 
                               show_line_numbers: bool):
        """使用 Pygments 进行语法高亮"""
        lexer_cls = _LEXER_MAP.get(language.lower(), TextLexer)
        lexer = lexer_cls()
        
        # 代码块开始
        self.text.insert("end", f" [{language.upper()}] \n", "code_lang_label")
        
        # 按行处理代码，逐行应用语法高亮
        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            if show_line_numbers:
                self.text.insert("end", f"{line_num:4d}  ", "code_lang_label")
            
            # 简单的词法分析着色（轻量级实现）
            self._apply_syntax_colors(line, lexer)
            self.text.insert("end", "\n")

    def _apply_syntax_colors(self, line: str, lexer):
        """对单行代码应用语法颜色"""
        try:
            from pygments.token import Token
            tokens = list(lexer.get_tokens(line))
            
            for token_type, value in tokens:
                if not value:
                    continue
                
                # 获取 token 的字符串表示
                token_str = str(token_type)
                color = _PYGMENTS_COLORS.get(token_str, "#f8f8f2" if self.dark_mode else "#24292e")
                
                # 创建临时 tag
                tag_name = f"syn_{self._tag_counter}"
                self._tag_counter += 1
                self.text.tag_config(tag_name, foreground=color,
                                     font=("Consolas", 10))
                self.text.insert("end", value, tag_name)
        except Exception as e:
            logger.debug(f"语法高亮失败: {e}")
            self.text.insert("end", line)

    def _render_code_plain(self, code: str, language: str):
        """无 Pygments 时的纯代码渲染"""
        self.text.insert("end", f" [{language.upper()}] \n", "code_lang_label")
        self.text.insert("end", code + "\n", "code_block")

    def render_table(self, headers: List[str], rows: List[List[str]], 
                     start_index: str = "end"):
        """渲染表格
        
        Args:
            headers: 表头列表
            rows: 数据行列表
            start_index: 插入起始位置
        """
        if not headers or not rows:
            return
        
        # 计算列宽
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # 添加一些间距
        col_widths = [w + 2 for w in col_widths]
        
        # 渲染表头
        header_line = ""
        for i, h in enumerate(headers):
            header_line += h.ljust(col_widths[i])
        self.text.insert("end", header_line + "\n", ("md_bold", "md_table"))
        
        # 渲染分隔线
        sep_line = ""
        for w in col_widths:
            sep_line += "─" * w
        self.text.insert("end", sep_line + "\n", "md_table")
        
        # 渲染数据行
        for row in rows:
            row_line = ""
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    row_line += str(cell).ljust(col_widths[i])
            self.text.insert("end", row_line + "\n", "md_table")

    def render_math(self, formula: str, display_mode: bool = True, 
                    start_index: str = "end"):
        """渲染数学公式
        
        Args:
            formula: LaTeX 公式
            display_mode: 是否显示模式（独立行）
            start_index: 插入起始位置
        """
        if HAS_TEX:
            rendered = tex_module.TeXToUTF8().translate_for_display(
                formula, enable_translation=True)
        else:
            rendered = formula
        
        tag = "math_display" if display_mode else "math_inline"
        if display_mode:
            self.text.insert("end", "\n" + rendered + "\n", tag)
        else:
            self.text.insert("end", rendered, tag)

    def clear(self):
        """清空渲染内容"""
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")


class MarkdownRenderer:
    """Markdown 渲染器 — 更简单的 API，适用于快速渲染场景"""

    def __init__(self, text_widget, dark_mode: bool = False):
        self.renderer = EnhancedRenderer(text_widget, dark_mode)

    def render(self, markdown_text: str):
        """渲染完整的 Markdown 文本"""
        self.renderer.render_markdown(markdown_text)

    def render_code(self, code: str, language: str = "python"):
        """渲染代码块"""
        self.renderer.render_code(code, language)

    def render_table(self, headers: List[str], rows: List[List[str]]):
        """渲染表格"""
        self.renderer.render_table(headers, rows)


def create_renderer(text_widget, dark_mode: bool = False) -> EnhancedRenderer:
    """工厂函数：创建渲染器实例"""
    return EnhancedRenderer(text_widget, dark_mode)
