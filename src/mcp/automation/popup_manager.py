#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

# 渲染增强模块
try:
    from ..renderer import create_renderer, HAS_ENHANCED_RENDERER
except ImportError:
    try:
        from mcp.renderer import create_renderer, HAS_ENHANCED_RENDERER
    except ImportError:
        HAS_ENHANCED_RENDERER = False
        create_renderer = None

try:
    import tkinter as tk
    from tkinter import ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    tk = None
    ttk = None

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个学习助手。你擅长解答各类学科问题、解释科学概念、"
    "辅导课程内容、推荐学习资源、整理学习计划。请用清晰、准确、友好的方式回答问题。"
    "当收到推送通知时，请帮助用户理解和复习相关内容。"
)

POPUP_DB_NAME = "learning_assistant_memory.db"


@dataclass
class MemoryEntry:
    role: str
    content: str
    timestamp: str


class LongTermMemory:
    def __init__(self, db_dir: str = None):
        if db_dir is None:
            db_dir = os.path.join(os.path.expanduser("~"), ".ts2")
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, POPUP_DB_NAME)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                popup_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.commit()

    def store_message(self, popup_id: str, role: str, content: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages (popup_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (popup_id, role, content, datetime.now().isoformat())
        )
        conn.commit()

    def load_recent(self, popup_id: str, limit: int = 50) -> List[MemoryEntry]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE popup_id = ? ORDER BY id DESC LIMIT ?",
            (popup_id, limit)
        ).fetchall()
        entries = []
        for r in reversed(rows):
            entries.append(MemoryEntry(
                role=r["role"], content=r["content"], timestamp=r["timestamp"]
            ))
        return entries

    def get_context(self, popup_id: str) -> str:
        entries = self.load_recent(popup_id, limit=30)
        parts = []
        for entry in entries:
            prefix = {"user": "用户", "assistant": "助手", "notification": "通知"}.get(
                entry.role, entry.role
            )
            parts.append(f"{prefix}: {entry.content}")
        return "\n".join(parts)


class LearningAssistantPopup:
    """学习助手弹窗，复用 TS2 的 Agent 系统"""

    BG_COLOR = "#f5f7fa"
    CARD_COLOR = "#ffffff"
    PRIMARY_COLOR = "#3b82f6"
    TEXT_COLOR = "#2d3748"
    SUBTLE_COLOR = "#6b7280"
    BORDER_COLOR = "#e2e8f0"

    def __init__(self, popup_id: str, config: Dict[str, Any] = None, agent=None, llm=None, ws2_system=None):
        if not HAS_TKINTER:
            raise RuntimeError("tkinter 不可用，无法创建弹窗")
        self.popup_id = popup_id
        self.config = config or {}
        self.title = self.config.get("title", "📚 学习助手")
        self._window: Optional[Any] = None
        self._message_text: Optional[Any] = None
        self._input_entry: Optional[Any] = None
        self._messages: List[Dict[str, str]] = []
        self._paused = False
        self._on_send: Optional[Callable[[str], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._memory = LongTermMemory()
        self._alive = False
        self._is_processing = False
        self._should_stop = False
        self._chat_thread = None
        self._agent = agent
        self._llm = llm
        self._ws2_system = ws2_system

    def show(self, parent: Any = None):
        if self._window is not None:
            try:
                self._window.lift()
                self._window.focus_force()
                return
            except tk.TclError:
                self._window = None

        self._window = tk.Toplevel(parent) if parent else tk.Tk()
        self._window.title(self.title)
        self._window.geometry("1050x900")
        self._window.resizable(True, True)
        self._window.configure(bg=self.BG_COLOR)
        self._window.attributes("-topmost", True)

        screen_w = self._window.winfo_screenwidth()
        screen_h = self._window.winfo_screenheight()
        x = (screen_w - 1050) // 2
        y = (screen_h - 900) // 2
        self._window.geometry(f"1050x900+{x}+{y}")

        self._window.protocol("WM_DELETE_WINDOW", self._on_close_click)

        self._show_loading()

        self._window.after(50, lambda: self._delayed_create(parent))

    def _show_loading(self):
        loading_frame = tk.Frame(self._window, bg=self.BG_COLOR)
        loading_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            loading_frame, text="📚", font=("Segoe UI Symbol", 48),
            bg=self.BG_COLOR, fg=self.PRIMARY_COLOR
        ).pack(pady=(100, 20))

        loading_label = tk.Label(
            loading_frame, text="正在加载学习助手...",
            font=("Microsoft YaHei UI", 12),
            bg=self.BG_COLOR, fg=self.TEXT_COLOR
        )
        loading_label.pack(pady=10)

        self._loading_label = loading_label

        dots = ["."]
        def animate_dots():
            if hasattr(self, '_loading_label') and self._loading_label.winfo_exists():
                dots[0] = dots[0] + "." if len(dots[0]) < 4 else "."
                self._loading_label.configure(text=f"正在加载学习助手{dots[0]}")
                self._window.after(300, animate_dots)

        animate_dots()

        self._loading_frame = loading_frame

    def _delayed_create(self, parent):
        if self._loading_frame and self._loading_frame.winfo_exists():
            for widget in self._loading_frame.winfo_children():
                widget.destroy()
            self._loading_frame.destroy()

        self._create_header()
        self._create_main_content()

        self._alive = True
        self._load_history()

        # 标记聊天区域已就绪
        self._chat_ready = True

        # 处理延迟添加的欢迎消息
        if hasattr(self, '_pending_welcome') and self._pending_welcome:
            self._append_to_area("system", self._pending_welcome)
            self._pending_welcome = None

        self._window.after(100, lambda: self._refresh_ui())

    def _refresh_ui(self):
        try:
            if self._window and self._window.winfo_exists():
                self._window.update_idletasks()
        except Exception:
            pass

    def _create_header(self):
        header = tk.Frame(self._window, bg=self.PRIMARY_COLOR, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=self.PRIMARY_COLOR)
        title_frame.pack(side=tk.LEFT, padx=16, fill=tk.Y)

        tk.Label(title_frame, text="📚", font=("Segoe UI Symbol", 20),
                 bg=self.PRIMARY_COLOR, fg="white").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(title_frame, text="学习助手", font=("Microsoft YaHei UI", 14, "bold"),
                 bg=self.PRIMARY_COLOR, fg="white").pack(side=tk.LEFT)

        btn_frame = tk.Frame(header, bg=self.PRIMARY_COLOR)
        btn_frame.pack(side=tk.RIGHT, padx=12, fill=tk.Y)

        self._topmost_var = tk.BooleanVar(value=True)
        self._topmost_btn = tk.Checkbutton(
            btn_frame, text="📌", variable=self._topmost_var,
            bg=self.PRIMARY_COLOR, fg="white", selectcolor=self.PRIMARY_COLOR,
            activebackground=self.PRIMARY_COLOR, activeforeground="white",
            indicatoron=False, relief=tk.FLAT,
            command=self._toggle_topmost
        )
        self._topmost_btn.pack(side=tk.LEFT, padx=4)
        if hasattr(self, '_window') and self._window:
            self._window.attributes("-topmost", True)

        self._pause_btn = tk.Label(
            btn_frame, text="⏸", font=("Segoe UI Symbol", 16),
            bg=self.PRIMARY_COLOR, fg="white", cursor="hand2"
        )
        self._pause_btn.pack(side=tk.LEFT, padx=4)
        self._pause_btn.bind("<Button-1>", lambda e: self._toggle_pause())

        self._close_btn = tk.Label(
            btn_frame, text="✕", font=("", 18),
            bg=self.PRIMARY_COLOR, fg="white", cursor="hand2"
        )
        self._close_btn.pack(side=tk.LEFT, padx=4)
        self._close_btn.bind("<Button-1>", lambda e: self._on_close_click())

    def _toggle_topmost(self):
        if self._window and self._window.winfo_exists():
            self._window.attributes("-topmost", self._topmost_var.get())

    def _create_main_content(self):
        """主布局：用 PanedWindow 分割聊天区和输入区"""
        self._paned = ttk.PanedWindow(self._window, orient=tk.VERTICAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 上部分：聊天区（权重 8）
        self._chat_pane = tk.Frame(self._paned, bg=self.BG_COLOR)
        self._paned.add(self._chat_pane, weight=8)

        chat_container = tk.Frame(self._chat_pane, bg=self.BG_COLOR)
        chat_container.pack(fill=tk.BOTH, expand=True)

        self._message_text = tk.Text(
            chat_container, wrap=tk.WORD, state=tk.DISABLED,
            font=("Microsoft YaHei UI", 10),
            bg="#ffffff", fg=self.TEXT_COLOR,
            insertbackground=self.PRIMARY_COLOR,
            relief=tk.FLAT, padx=14, pady=14,
            spacing1=6, spacing3=6
        )
        scrollbar = ttk.Scrollbar(chat_container, orient=tk.VERTICAL, command=self._message_text.yview)
        self._message_text.configure(yscrollcommand=scrollbar.set)
        self._message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 右键菜单：按段复制
        self._message_text.bind("<Button-3>", self._show_chat_context_menu)

        def _on_mousewheel(event):
            self._message_text.yview_scroll(int(-1 * (event.delta // 120)), "units")
        self._message_text.bind("<MouseWheel>", _on_mousewheel)
        chat_container.bind("<MouseWheel>", _on_mousewheel)

        self._message_text.tag_config("time", foreground="#a0aec0", font=("Consolas", 8))
        self._message_text.tag_config("user_bg", background="#e6f4ff", spacing1=10, spacing3=10)
        self._message_text.tag_config("assistant_bg", background="#ffffff", spacing1=10, spacing3=10)
        self._message_text.tag_config("notification_bg", background="#fffbe6", spacing1=10, spacing3=10)
        self._message_text.tag_config("system_bg", background="#f5f7fa", spacing1=10, spacing3=10)
        self._message_text.tag_config("user", foreground="#1e40af", font=("Microsoft YaHei UI", 10))
        self._message_text.tag_config("assistant", foreground="#059669", font=("Microsoft YaHei UI", 10))
        self._message_text.tag_config("notification", foreground="#92400e", font=("Microsoft YaHei UI", 10, "bold"))
        self._message_text.tag_config("system", foreground="#6b7280", font=("Microsoft YaHei UI", 9))
        self._message_text.tag_config("icon_user", foreground="#3b82f6", font=("Segoe UI Symbol", 12))
        self._message_text.tag_config("icon_assistant", foreground="#10b981", font=("Segoe UI Symbol", 12))
        self._message_text.tag_config("icon_notification", foreground="#f59e0b", font=("Segoe UI Symbol", 12))
        self._message_text.tag_config("icon_system", foreground="#6b7280", font=("Segoe UI Symbol", 12))
        self._message_text.tag_config("bold", font=("Microsoft YaHei UI", 10, "bold"))
        self._message_text.tag_config("code", font=("Consolas", 9), background="#f3f4f6")
        self._message_text.tag_config("md_link", foreground="#0366d6", font=("", 10, "underline"))

        # 初始化增强渲染器
        self._renderer = None
        if HAS_ENHANCED_RENDERER and create_renderer:
            try:
                self._renderer = create_renderer(self._message_text)
            except Exception as e:
                logger.debug(f"popup_manager 渲染器初始化失败: {e}")

        self._chat_ready = True

        # 下部分：输入区（权重 2）
        self._input_pane = tk.Frame(self._paned, bg=self.CARD_COLOR)
        self._paned.add(self._input_pane, weight=2)

        # 在 input_pane 内创建输入框
        top_bar = tk.Frame(self._input_pane, bg=self.CARD_COLOR)
        top_bar.pack(fill=tk.X, padx=8, pady=(4, 2))
        input_hint = self.config.get("input_hint", "输入问题或指令...")
        tk.Label(top_bar, text=input_hint, font=("Microsoft YaHei UI", 8),
                 bg=self.CARD_COLOR, fg="#9ca3af").pack(side=tk.LEFT)

        self._input_frame = tk.Frame(self._input_pane, bg=self.CARD_COLOR)
        self._input_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 6))

        self._input_text = tk.Text(
            self._input_frame, font=("Microsoft YaHei UI", 10),
            bg="#f9fafb", fg=self.TEXT_COLOR,
            insertbackground=self.PRIMARY_COLOR,
            relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground="#e5e7eb", highlightcolor=self.PRIMARY_COLOR,
            wrap=tk.WORD,
            height=4,
            padx=8, pady=8,
        )
        self._input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        self._input_text.bind("<Return>", self._on_input_return)
        self._input_text.bind("<KeyRelease>", self._auto_resize_input)

        # 右侧发送按钮（处理中自动切换为停止）
        btn_col = tk.Frame(self._input_frame, bg=self.CARD_COLOR)
        btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))

        self._send_btn = tk.Button(
            btn_col, text="发送", font=("Microsoft YaHei UI", 9, "bold"),
            bg=self.PRIMARY_COLOR, fg="white", relief=tk.FLAT,
            activebackground="#2563eb", activeforeground="white",
            cursor="hand2", padx=12, pady=4,
            command=self._on_send_click
        )
        self._send_btn.pack(fill=tk.BOTH, expand=True)

        self._input_entry = self._input_text

    def _create_chat_area(self):
        """已废弃，由 _create_main_content 替代"""
        pass

    def _auto_resize_input(self, event=None):
        """根据内容行数自动调整输入框高度"""
        if not hasattr(self, '_input_text') or self._input_text is None:
            return
        try:
            content = self._input_text.get("1.0", tk.END).strip()
            lines = content.count('\n') + 1
            max_lines = 8  # 最多显示 8 行
            lines = min(lines, max_lines)
            current_height = self._input_text.cget("height")
            if current_height != lines:
                self._input_text.config(height=lines)
        except Exception:
            pass

    def _on_input_return(self, event):
        """Enter 发送，Shift+Enter 换行"""
        if event.state & 0x1:  # Shift 按下
            return  # 允许换行
        self._on_send_click()
        return "break"  # 阻止默认换行行为

    def _load_history(self):
        """加载历史（已禁用持久化，每次弹窗为全新会话）"""
        pass

    # ─── 右键菜单：按段复制 ───

    def _show_chat_context_menu(self, event):
        """显示聊天区域右键菜单"""
        try:
            menu = tk.Menu(self._message_text, tearoff=0)

            # 检查是否有选中的文本
            try:
                selected_text = self._message_text.get(tk.SEL_FIRST, tk.SEL_LAST)
                has_selection = bool(selected_text.strip())
            except tk.TclError:
                has_selection = False
                selected_text = ""

            if has_selection:
                menu.add_command(label="📋 复制选中", command=lambda: self._copy_text(selected_text))
                menu.add_separator()

            # 按段复制：右键所在位置的消息
            menu.add_command(label="📄 按段复制", command=lambda: self._copy_block_at_cursor(event.x, event.y))
            menu.add_separator()

            menu.add_command(label="📋 复制全部", command=self._copy_all_messages)
            menu.post(event.x_root, event.y_root)
        except Exception as e:
            print(f"右键菜单错误: {e}")

    def _copy_text(self, text):
        """复制文本到剪贴板"""
        try:
            self._message_text.clipboard_clear()
            self._message_text.clipboard_append(text)
        except Exception as e:
            print(f"复制失败: {e}")

    def _copy_block_at_cursor(self, click_x, click_y):
        """复制右键点击所在位置的整个对话块"""
        try:
            click_pos = self._message_text.index(f"@{click_x},{click_y}")
            line_num = int(click_pos.split(".")[0])

            content = self._message_text.get("1.0", tk.END)
            lines = content.split("\n")

            # 块起始标记：角色图标
            icon_prefixes = ("👤", "🤖", "📢", "⚙️")

            # 向上找块开始：遇到角色图标行
            start_line = line_num - 1
            for i in range(line_num - 1, -1, -1):
                line = lines[i].strip()
                if any(line.startswith(p) for p in icon_prefixes):
                    start_line = i
                    break

            # 向下找块结束：遇到下一个角色图标行
            end_line = len(lines)
            for i in range(line_num, len(lines)):
                line = lines[i].strip()
                if any(line.startswith(p) for p in icon_prefixes):
                    end_line = i
                    break

            block_text = "\n".join(lines[start_line:end_line]).strip()
            if block_text:
                # 清理时间戳（HH:MM:SS 格式）
                import re
                block_text = re.sub(r'\d{2}:\d{2}:\d{2}\s*', '', block_text)
                self._message_text.clipboard_clear()
                self._message_text.clipboard_append(block_text)
        except Exception as e:
            print(f"按段复制失败: {e}")

    def _copy_all_messages(self):
        """复制全部对话到剪贴板"""
        try:
            entries = self._memory.load_recent(self.popup_id, limit=100)
            lines = []
            for entry in entries:
                role_map = {"user": "你", "assistant": "助手", "system": "系统", "notification": "通知"}
                role = role_map.get(entry.role, entry.role)
                lines.append(f"【{role}】\n{entry.content}")
            all_text = "\n\n".join(lines)
            if all_text:
                self._message_text.clipboard_clear()
                self._message_text.clipboard_append(all_text)
        except Exception as e:
            print(f"复制全部失败: {e}")

    def _append_to_area(self, role: str, content: str, timestamp: str = None):
        # 聊天区域未就绪时，缓存欢迎消息
        if self._message_text is None:
            if role == "system":
                self._pending_welcome = content
            return
        if not getattr(self, '_chat_ready', False) and role == "system" and content and not timestamp:
            self._pending_welcome = content
            return
        try:
            logger.debug(f"[popup_manager] _append_to_area called, content type={type(content)}, content[:150]={str(content)[:150]}")
            self._message_text.configure(state=tk.NORMAL)

            ts = timestamp or datetime.now().isoformat()
            ts_short = ts[11:19] if len(ts) > 19 else ts[-8:]

            icon_tag = {
                "user": "icon_user",
                "assistant": "icon_assistant",
                "notification": "icon_notification",
                "system": "icon_system"
            }.get(role, "icon_system")

            bg_tag = {
                "user": "user_bg",
                "assistant": "assistant_bg",
                "notification": "notification_bg",
                "system": "system_bg"
            }.get(role, "system_bg")

            text_tag = role if role in ("user", "assistant", "notification", "system") else "system"

            icon_char = {
                "user": "👤",
                "assistant": "🤖",
                "notification": "📢",
                "system": "⚙️"
            }.get(role, "•")

            self._message_text.insert(tk.END, f"\n", bg_tag)
            self._message_text.insert(tk.END, f" {ts_short} ", "time")
            self._message_text.insert(tk.END, icon_char, icon_tag)

            prefix = {
                "user": " 你: ",
                "assistant": " 助手: ",
                "notification": " ",
                "system": " "
            }.get(role, " ")

            self._message_text.insert(tk.END, prefix, text_tag)

            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    self._append_dict_as_cards(parsed)
                elif isinstance(parsed, list):
                    self._append_list_as_cards(parsed)
                else:
                    self._message_text.insert(tk.END, content, (text_tag, bg_tag))
            except (json.JSONDecodeError, TypeError, ValueError):
                # 不是 JSON，使用增强渲染
                if self._renderer:
                    self._render_popup_content(content, text_tag, bg_tag)
                else:
                    self._message_text.insert(tk.END, content, (text_tag, bg_tag))

            self._message_text.insert(tk.END, "\n", bg_tag)
        except Exception as e:
            logger.error(f"Append message failed: {e}", exc_info=True)
        finally:
            if self._message_text is not None:
                try:
                    self._message_text.configure(state=tk.DISABLED)
                    self._message_text.see(tk.END)
                except Exception:
                    pass

    def _render_popup_content(self, content: str, text_tag: str, bg_tag: str):
        """渲染 popup 聊天内容 — 支持 Markdown 内联元素和代码块"""
        # 提取代码块
        code_block_pattern = r'```(\w*)\n([\s\S]*?)```'
        code_blocks = list(re.finditer(code_block_pattern, content))

        if not code_blocks:
            self._insert_popup_inline_md(content, text_tag, bg_tag)
            return

        # 分段渲染
        last_end = 0
        for match in code_blocks:
            if match.start() > last_end:
                self._insert_popup_inline_md(content[last_end:match.start()], text_tag, bg_tag)

            lang = match.group(1) or "text"
            code = match.group(2)
            if self._renderer:
                self._renderer.render_code(code, lang)
                self._message_text.insert(tk.END, "\n")

            last_end = match.end()

        if last_end < len(content):
            self._insert_popup_inline_md(content[last_end:], text_tag, bg_tag)

    def _insert_popup_inline_md(self, text: str, text_tag: str, bg_tag: str):
        """在 popup 中插入带内联 Markdown 的文本"""
        patterns = [
            (r'`([^`]+)`', 'code'),
            (r'\*\*(.+?)\*\*', 'bold'),
            (r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', 'italic'),
            (r'\[([^\]]+)\]\(([^)]+)\)', 'link'),
        ]

        remaining = text
        while remaining:
            earliest_match = None
            earliest_start = len(remaining)
            earliest_type = None

            for pattern, tag_name in patterns:
                match = re.search(pattern, remaining)
                if match and match.start() < earliest_start:
                    earliest_match = match
                    earliest_start = match.start()
                    earliest_type = tag_name

            if earliest_match:
                if earliest_start > 0:
                    self._message_text.insert(tk.END, remaining[:earliest_start], (text_tag, bg_tag))

                groups = earliest_match.groups()
                if earliest_type == 'code':
                    self._message_text.insert(tk.END, groups[0], ("code",))
                elif earliest_type == 'bold':
                    self._message_text.insert(tk.END, groups[0], ("bold", bg_tag))
                elif earliest_type == 'italic':
                    self._message_text.insert(tk.END, groups[0], (bg_tag,))
                elif earliest_type == 'link':
                    self._message_text.insert(tk.END, groups[0], ("md_link",))

                remaining = remaining[earliest_match.end():]
            else:
                self._message_text.insert(tk.END, remaining, (text_tag, bg_tag))
                break

    def _append_dict_as_cards(self, data: dict):
        if not data:
            return
        
        # 检查是否是工具结果结构（包含 success, data, message, error）
        if "success" in data or "data" in data:
            self._append_tool_result(data)
            return
        
        # 检查是否是待办任务列表或状态总结类的数据
        if any(key in data for key in ["tasks", "todos", "task_list", "summary", "status", "items"]):
            self._append_structured_data(data)
            return
        
        # 检查是否是单个任务或状态项目
        if any(key in data for key in ["title", "name", "status", "priority", "due_date", "description", "id"]):
            self._append_task_or_item(data)
            return
    
    def _append_tool_result(self, data: dict):
        """美化显示工具结果结构"""
        # 先显示成功状态和消息
        if "success" in data:
            success = data["success"]
            icon = "✅" if success else "❌"
            self._message_text.insert(tk.END, f"{icon} 操作结果", ("bold", "assistant_bg"))
            self._message_text.insert(tk.END, "\n", "assistant_bg")
        
        if "message" in data and data["message"]:
            # 如果有现成的友好消息，直接显示
            self._message_text.insert(tk.END, f"{data['message']}\n", ("assistant", "assistant_bg"))
        
        if "error" in data and data["error"]:
            self._message_text.insert(tk.END, f"❌ 错误: {data['error']}\n", ("assistant", "assistant_bg"))
        
        # 然后处理 data 字段
        if "data" in data and data["data"]:
            sub_data = data["data"]
            self._message_text.insert(tk.END, "\n📊 详细数据\n", ("bold", "assistant_bg"))
            self._message_text.insert(tk.END, "────────────────────────\n", "assistant_bg")
            
            if isinstance(sub_data, dict):
                # 检查是否有 tasks 字段（任务列表结构）
                if "tasks" in sub_data and isinstance(sub_data["tasks"], list):
                    task_list = sub_data["tasks"]
                    if task_list:
                        for idx, task in enumerate(task_list, 1):
                            self._append_task_as_card(task, idx)
                    
                    if "total" in sub_data:
                        self._message_text.insert(tk.END, f"\n📈 总计: {sub_data['total']} 项\n", ("assistant", "assistant_bg"))
                    
                    if "filtered_by_status" in sub_data and sub_data["filtered_by_status"]:
                        self._message_text.insert(tk.END, "🔍 已按状态筛选\n", ("assistant", "assistant_bg"))
                else:
                    # 普通数据字典
                    for key, value in sub_data.items():
                        key_display = self._beautify_key(key)
                        value_display = self._beautify_value(value)
                        self._message_text.insert(tk.END, f"  {key_display}: {value_display}\n", ("assistant", "assistant_bg"))
            elif isinstance(sub_data, list):
                # 数据列表
                for idx, item in enumerate(sub_data, 1):
                    if isinstance(item, dict):
                        if any(k in item for k in ["title", "name", "status"]):
                            self._append_task_as_card(item, idx)
                        else:
                            self._message_text.insert(tk.END, f"  {idx}. {self._beautify_value(item)}\n", ("assistant", "assistant_bg"))
                    else:
                        self._message_text.insert(tk.END, f"  {idx}. {self._beautify_value(item)}\n", ("assistant", "assistant_bg"))
                self._message_text.insert(tk.END, f"\n📈 总计: {len(sub_data)} 项\n", ("assistant", "assistant_bg"))
            else:
                # 其他数据
                self._message_text.insert(tk.END, f"  {self._beautify_value(sub_data)}\n", ("assistant", "assistant_bg"))
            
            self._message_text.insert(tk.END, "────────────────────────\n", "assistant_bg")
        
        if "truncated" in data and data["truncated"]:
            self._message_text.insert(tk.END, f"\n⚠️ 结果已截断 (原始 {data.get('original_length', '')} 字符)\n", ("assistant", "assistant_bg"))
    
    def _beautify_key(self, key: str) -> str:
        """美化键名显示"""
        key_map = {
            'id': '编号',
            'title': '标题',
            'name': '名称',
            'status': '状态',
            'description': '描述',
            'content': '内容',
            'priority': '优先级',
            'due_date': '截止日期',
            'start_time': '开始时间',
            'end_time': '结束时间',
            'created_at': '创建时间',
            'updated_at': '更新时间',
            'created': '创建时间',
            'updated': '更新时间',
            'date': '日期',
            'time': '时间',
            'type': '类型',
            'category': '分类',
            'tags': '标签',
            'notes': '备注',
            'tasks': '任务',
            'total': '总计',
            'filtered_by_status': '筛选状态'
        }
        
        if key.lower() in key_map:
            return f"【{key_map[key.lower()]}】"
        
        result = []
        for i, char in enumerate(key):
            if char.isupper() and i > 0 and key[i-1].islower():
                result.append(' ')
            elif char == '_':
                result.append(' ')
            else:
                result.append(char)
        
        beautified = ''.join(result).title()
        return f"【{beautified}】"
    
    def _beautify_value(self, value, max_length: int = None) -> str:
        """美化值显示"""
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "✅ 是" if value else "❌ 否"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            if len(value) == 0:
                return "-"
            elif len(value) <= 3:
                return ", ".join(str(v) for v in value)
            else:
                return f"{len(value)} 项 (前3项: {', '.join(str(v) for v in value[:3])}...)"
        if isinstance(value, dict):
            if len(value) == 0:
                return "-"
            else:
                simple_keys = ["title", "name", "status"]
                if len(value) <= 3 and any(k in value for k in simple_keys):
                    parts = []
                    if "status" in value:
                        status = value["status"]
                        icon = "✅" if status == "done" else "🔄" if status == "in_progress" else "⭕"
                        parts.append(f"{icon}")
                    if "title" in value:
                        parts.append(str(value["title"]))
                    elif "name" in value:
                        parts.append(str(value["name"]))
                    return ' '.join(parts) if parts else f"对象 (含 {len(value)} 个键)"
                else:
                    return f"对象 (含 {len(value)} 个键)"
        
        s = str(value).strip()
        if not s:
            return "-"
        
        if max_length and len(s) > max_length:
            s = s[:max_length-3] + "..."
        
        return s
    
        # 普通字典显示
        for idx, (key, value) in enumerate(data.items()):
            if idx > 0:
                self._message_text.insert(tk.END, "\n")
            
            key_display = self._beautify_key(key)
            value_display = self._beautify_value(value)
            
            self._message_text.insert(tk.END, key_display, ("bold", "assistant_bg"))
            self._message_text.insert(tk.END, "\n", "assistant_bg")
            self._message_text.insert(tk.END, f"  {value_display}", ("assistant", "assistant_bg"))
    
    def _append_structured_data(self, data: dict):
        """显示结构化数据，如待办任务列表、状态总结等"""
        self._message_text.insert(tk.END, "📊 数据概览", ("bold", "assistant_bg"))
        self._message_text.insert(tk.END, "\n", "assistant_bg")
        self._message_text.insert(tk.END, "────────────────────────\n", "assistant_bg")
        
        for key, value in data.items():
            if key in ["tasks", "todos", "task_list", "items"] and isinstance(value, list):
                self._message_text.insert(tk.END, f"\n📋 {key.title()} ({len(value)}项):\n", ("bold", "assistant_bg"))
                for idx, item in enumerate(value, 1):
                    if isinstance(item, dict):
                        self._append_task_as_card(item, idx)
                    else:
                        self._message_text.insert(tk.END, f"  {idx}. {str(item)}\n", ("assistant", "assistant_bg"))
            elif key == "summary" or key == "status":
                if isinstance(value, dict):
                    self._message_text.insert(tk.END, f"\n📊 {key.title()}:\n", ("bold", "assistant_bg"))
                    for k, v in value.items():
                        self._message_text.insert(tk.END, f"  • {k}: {v}\n", ("assistant", "assistant_bg"))
                else:
                    self._message_text.insert(tk.END, f"\n📊 {key.title()}: {value}\n", ("assistant", "assistant_bg"))
            else:
                self._message_text.insert(tk.END, f"\n📋 {key}: {value}\n", ("assistant", "assistant_bg"))
        
        self._message_text.insert(tk.END, "\n────────────────────────\n", "assistant_bg")
    
    def _append_task_or_item(self, item: dict):
        """显示单个任务或项目"""
        self._append_task_as_card(item, None)
    
    def _append_task_as_card(self, item: dict, index: int = None):
        """以卡片形式显示任务"""
        if index is not None:
            self._message_text.insert(tk.END, f"\n  {index}. ", ("assistant", "assistant_bg"))
        else:
            self._message_text.insert(tk.END, "\n  ", ("assistant", "assistant_bg"))
        
        # 图标
        status = (item.get("status") or "").lower()
        status_icon = "✅" if status in ["done", "completed", "已完成", "完成"] else "⏳" if status in ["in_progress", "doing", "进行中"] else "📋"
        
        # 标题
        title = item.get("title", item.get("name", "未命名"))
        self._message_text.insert(tk.END, f"{status_icon} {title}", ("bold", "assistant_bg"))
        
        # 元数据
        meta_parts = []
        if item.get("priority"):
            priority = item["priority"]
            priority_display = "🔴高" if str(priority).lower() in ["high", "高", "1"] else "🟡中" if str(priority).lower() in ["medium", "中", "2"] else "🟢低"
            meta_parts.append(priority_display)
        if item.get("status"):
            meta_parts.append(f"状态: {item['status']}")
        if item.get("due_date"):
            meta_parts.append(f"📅{item['due_date']}")
        
        if meta_parts:
            self._message_text.insert(tk.END, f" ({', '.join(meta_parts)})", ("assistant", "assistant_bg"))
        
        # 描述
        if item.get("description") and str(item["description"]).strip():
            desc = str(item["description"])
            if len(desc) > 100:
                self._message_text.insert(tk.END, f"\n     📝 {desc[:100]}...", ("assistant", "assistant_bg"))
            else:
                self._message_text.insert(tk.END, f"\n     📝 {desc}", ("assistant", "assistant_bg"))

    def _append_list_as_cards(self, data: list):
        if not data:
            return
        
        if data and isinstance(data[0], dict):
            if any(key in data[0] for key in ["title", "name", "status", "priority", "due_date", "id", "task_id"]):
                self._message_text.insert(tk.END, "📋 任务列表", ("bold", "assistant_bg"))
                self._message_text.insert(tk.END, "\n", "assistant_bg")
                self._message_text.insert(tk.END, "────────────────────────\n", "assistant_bg")
                for idx, item in enumerate(data, 1):
                    if isinstance(item, dict):
                        self._append_task_as_card(item, idx)
                self._message_text.insert(tk.END, "\n────────────────────────\n", "assistant_bg")
                return
        
        for idx, item in enumerate(data):
            self._message_text.insert(tk.END, "\n", "assistant_bg")
            if isinstance(item, dict):
                icon = "📄"
                if item.get("url"):
                    url = item["url"].lower()
                    if "arxiv" in url:
                        icon = "📝"
                    elif "github" in url:
                        icon = "🐙"
                    elif "doi" in url:
                        icon = "🔗"
                
                title = item.get("title", item.get("name", f"项目{idx + 1}"))
                self._message_text.insert(tk.END, f"{icon} {title}", ("bold", "assistant_bg"))
                
                meta_items = []
                if item.get("year"):
                    meta_items.append(f"📅 {item['year']}")
                if item.get("authors"):
                    authors = item["authors"]
                    if isinstance(authors, list):
                        authors = ", ".join(str(a)[:20] for a in authors[:2])
                    meta_items.append(f"👥 {authors[:40]}")
                if item.get("count"):
                    meta_items.append(f"🔢 {item['count']}")
                if item.get("source"):
                    meta_items.append(f"📍 {item['source']}")
                
                if meta_items:
                    self._message_text.insert(tk.END, f" ({', '.join(meta_items)})", ("assistant", "assistant_bg"))
                
                if item.get("url"):
                    self._message_text.insert(tk.END, f"\n   🔗 {item['url'][:60]}{'...' if len(item['url']) > 60 else ''}", ("assistant", "assistant_bg"))
                
                if item.get("content"):
                    content = item["content"]
                    if len(content) > 150:
                        self._message_text.insert(tk.END, f"\n   📄 {content[:150]}...", ("assistant", "assistant_bg"))
                    else:
                        self._message_text.insert(tk.END, f"\n   📄 {content}", ("assistant", "assistant_bg"))
            else:
                item_str = str(item)
                if len(item_str) > 80:
                    self._message_text.insert(tk.END, f"  • {item_str[:80]}...", ("assistant", "assistant_bg"))
                else:
                    self._message_text.insert(tk.END, f"  • {item_str}", ("assistant", "assistant_bg"))

    def show_message(self, role: str, content: str):
        self._messages.append({"role": role, "content": content})
        # 不再持久化到 SQLite，每次弹窗为全新会话
        if self._alive and self._window is not None:
            try:
                # DEBUG: 打印传入的content前100字符
                logger.debug(f"[popup_manager] show_message role={role}, content_preview={content[:100] if len(content) > 100 else content}")
                self._window.after(0, self._append_to_area, role, content)
            except Exception as e:
                logger.error(f"Show message after failed: {e}", exc_info=True)
                self._append_to_area(role, content)

    def push_notification(self, title: str, content: str):
        if self._paused:
            return
        msg = f"{title}\n{content}"
        self.show_message("notification", msg)

    def send_user_message(self, message: str):
        self.show_message("user", message)
        
        if not self._alive:
            return
        
        # 设置处理状态
        self._is_processing = True
        self._should_stop = False
        self._update_input_state(processing=True)
        
        try:
            self.show_message("system", "正在思考中...")
            
            if self._agent and hasattr(self._agent, 'chat'):
                # 注入弹窗环境感知到 ContextProvider
                self._inject_popup_context()
                
                def async_chat():
                    try:
                        # on_token 回调用于流式接收，同时支持停止检查
                        token_buffer = []
                        
                        def on_token(token: str):
                            # 停止检查（最高优先级）
                            if self._should_stop:
                                return
                            token_buffer.append(token)
                            # 将新收到的 token 显示在 UI 上
                            try:
                                self._window.after(0, lambda t=token: self._append_streaming_text(t))
                            except Exception:
                                pass
                        
                        # 使用 agent.chat() 走完整的工具调用循环
                        response = self._agent.chat(message, on_token=on_token)
                        
                        # 停止后处理
                        if self._should_stop:
                            self._window.after(0, lambda: (
                                self._pop_last_system_message(),
                                self.show_message("assistant", "🛑 操作已被你停止"),
                                self._finish_processing(),
                            ))
                            return
                        
                        # 移除 "正在思考中..." 提示
                        self._window.after(0, self._pop_last_system_message)
                        
                        # 显示回复
                        if response:
                            # agent.chat() 返回 str，直接使用
                            content_to_show = response if isinstance(response, str) else getattr(response, 'content', str(response))
                            if content_to_show and token_buffer:
                                # 已经有流式显示，只保存到内存
                                self._messages.append({"role": "assistant", "content": content_to_show})
                            elif content_to_show:
                                self._window.after(0, lambda r=content_to_show: self.show_message("assistant", r))
                        
                        # 获取最近工具调用信息
                        if hasattr(self._agent, 'messages') and self._agent.messages:
                            tool_calls_info = []
                            for msg in self._agent.messages[-10:]:
                                if msg.get("role") == "tool":
                                    tc_id = msg.get("tool_call_id", "")
                                    for prev_msg in self._agent.messages:
                                        if prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                                            for tc in prev_msg["tool_calls"]:
                                                if tc.get("id") == tc_id:
                                                    tool_calls_info.append({
                                                        "name": tc.get("function", {}).get("name", tc.get("name", "")),
                                                        "arguments": tc.get("function", {}).get("arguments", tc.get("arguments", {})),
                                                    })
                                                    break
                            
                            if tool_calls_info:
                                tool_lines = []
                                for tc in tool_calls_info:
                                    tool_lines.append(f"🔧 {tc['name']}")
                                    try:
                                        args = tc['arguments']
                                        if isinstance(args, str):
                                            args = json.loads(args)
                                        if isinstance(args, dict):
                                            for k, v in args.items():
                                                tool_lines.append(f"   • {k}: {str(v)[:100]}")
                                    except Exception:
                                        tool_lines.append(f"   • 参数: {str(tc['arguments'])[:100]}")
                                
                                self._window.after(0, lambda tl=tool_lines: self.show_message(
                                "system", "🤖 已执行工具：\n" + "\n".join(tl)
                            ))

                        # 显示检查点信息
                        try:
                            if hasattr(self._agent, '_middleware_chain') and self._agent._middleware_chain:
                                for mw in self._agent._middleware_chain._middlewares:
                                    from ..middleware.shadow_checkpoint import CheckpointMiddleware
                                    if isinstance(mw, CheckpointMiddleware) and mw.checkpointer:
                                        cp = mw.checkpointer
                                        commits = cp.get_commits(count=3)
                                        if commits:
                                            cp_lines = ["📋 检查点摘要："]
                                            for c in commits[:3]:
                                                raw = c['message'].replace('TS2 checkpoint: ', '')
                                                # 解析新格式 [instance][seq] tool_name
                                                m = re.match(r'^\[([^\]]+)\]\[(\d+)\]\s*(.*)', raw)
                                                if m:
                                                    seq = m.group(2)
                                                    tool = m.group(3)
                                                    cp_lines.append(f"   #{seq} {tool}")
                                                else:
                                                    cp_lines.append(f"   {c['hash'][:8]} {raw}")
                                            self._window.after(0, lambda cl=cp_lines: self.show_message(
                                                "system", "\n".join(cl)
                                            ))
                                        break
                        except Exception:
                            pass
                    except Exception as e:
                        if self._should_stop:
                            self._window.after(0, lambda: (
                                self._pop_last_system_message(),
                                self.show_message("assistant", "🛑 操作已被你停止"),
                                self._finish_processing(),
                            ))
                        else:
                            self._window.after(0, lambda err=str(e): (
                                self._pop_last_system_message(),
                                self.show_message("assistant", f"处理请求时出错：{err}"),
                                self._finish_processing(),
                            ))
                    finally:
                        # 确保无论如何都恢复状态
                        self._window.after(0, self._finish_processing)
                
                self._chat_thread = threading.Thread(target=async_chat, daemon=True)
                self._chat_thread.start()
            elif self._agent and hasattr(self._agent, 'process'):
                def async_process():
                    try:
                        response = self._agent.process(message)
                        if self._should_stop:
                            self._window.after(0, lambda: (
                                self._pop_last_system_message(),
                                self.show_message("assistant", "🛑 操作已被你停止"),
                                self._finish_processing(),
                            ))
                            return
                        self._window.after(0, lambda r=response: (
                            self._pop_last_system_message(),
                            self.show_message("assistant", r),
                            self._finish_processing(),
                        ))
                    except Exception as e:
                        self._window.after(0, lambda err=str(e): (
                            self._pop_last_system_message(),
                            self.show_message("assistant", f"处理请求时出错：{err}"),
                            self._finish_processing(),
                        ))
                
                self._chat_thread = threading.Thread(target=async_process, daemon=True)
                self._chat_thread.start()
            elif self._llm and hasattr(self._llm, 'generate'):
                def async_generate():
                    try:
                        sys_prompt = getattr(getattr(self, '_agent', None), 'config', None)
                        sys_prompt = getattr(sys_prompt, 'system_prompt', None) or SYSTEM_PROMPT
                        # 直接使用 agent 的消息历史，不再从 SQLite 读取
                        if self._agent and hasattr(self._agent, 'messages'):
                            history_lines = []
                            for msg in self._agent.messages:
                                role = msg.get("role", "")
                                content = msg.get("content", "")
                                if role in ("user", "assistant") and content:
                                    prefix = "用户" if role == "user" else "助手"
                                    history_lines.append(f"{prefix}: {content[:200]}")
                            context = "\n".join(history_lines[-10:])
                        else:
                            context = ""
                        prompt = f"{sys_prompt}\n\n对话历史：\n{context}\n\n用户：{message}\n\n助手："
                        
                        # LLM 级别的 on_token 支持停止
                        token_buffer = []
                        def on_token(token: str):
                            if self._should_stop:
                                raise KeyboardInterrupt("用户停止")
                            token_buffer.append(token)
                            try:
                                self._window.after(0, lambda t=token: self._append_streaming_text(t))
                            except Exception:
                                pass
                        
                        response = self._llm.generate(prompt, system_prompt=SYSTEM_PROMPT)
                        
                        self._window.after(0, lambda r=response: (
                            self._pop_last_system_message(),
                            self.show_message("assistant", r),
                            self._finish_processing(),
                        ))
                    except KeyboardInterrupt:
                        self._window.after(0, lambda: (
                            self._pop_last_system_message(),
                            self.show_message("assistant", "🛑 操作已被你停止"),
                            self._finish_processing(),
                        ))
                    except Exception as e:
                        self._window.after(0, lambda err=str(e): (
                            self._pop_last_system_message(),
                            self.show_message("assistant", f"处理请求时出错：{err}"),
                            self._finish_processing(),
                        ))
                
                self._chat_thread = threading.Thread(target=async_generate, daemon=True)
                self._chat_thread.start()
            else:
                self._pop_last_system_message()
                self.show_message("assistant", 
                    f"我收到了你的问题：{message}\n\n"
                    "💡 当前处于模拟模式，Agent 系统尚未连接。\n"
                    "可用的管理功能：\n"
                    "• 课程系统\n"
                    "• 自动化任务\n"
                    "• 学术搜索\n"
                    "请配置 API 后重新连接。"
                )
                self._finish_processing()
        except Exception as e:
            logger.error(f"处理用户消息失败: {e}", exc_info=True)
            self.show_message("assistant", f"抱歉，处理请求时出错：{str(e)}")
            self._finish_processing()
        
        if self._on_send:
            try:
                self._on_send(message)
            except Exception as e:
                logger.error(f"On send callback failed: {e}", exc_info=True)

    def _append_streaming_text(self, token: str):
        """流式追加文本到当前 assistant 消息"""
        if not self._message_text or not self._alive:
            return
        try:
            self._message_text.configure(state=tk.NORMAL)
            self._message_text.insert(tk.END, token, ("assistant", "assistant_bg"))
            self._message_text.configure(state=tk.DISABLED)
            self._message_text.see(tk.END)
        except Exception:
            pass

    def _update_input_state(self, processing: bool):
        """更新输入区域状态（参考 agent_assistant.py 的 UI 状态管理）"""
        if self._window is None:
            return
        try:
            if processing:
                self._input_entry.config(state=tk.DISABLED)
                # 发送按钮变停止
                if hasattr(self, '_send_btn') and self._send_btn:
                    self._send_btn.config(
                        text="🛑 停止",
                        bg="#ef4444",
                        command=self._stop_processing
                    )
            else:
                self._input_entry.config(state=tk.NORMAL)
                if hasattr(self, '_send_btn') and self._send_btn:
                    self._send_btn.config(
                        text="发送",
                        bg=self.PRIMARY_COLOR,
                        command=self._on_send_click
                    )
        except Exception:
            pass

    def _finish_processing(self):
        """完成处理，恢复 UI 状态"""
        self._is_processing = False
        self._should_stop = False
        self._chat_thread = None
        self._update_input_state(processing=False)

    def _stop_processing(self):
        """停止处理 — 参考 agent_assistant.py 的实现"""
        if not self._is_processing:
            return
        
        self._should_stop = True
        
        # 取消 LLM 请求
        if self._llm and hasattr(self._llm, 'cancel'):
            try:
                self._llm.cancel()
            except Exception:
                pass
        
        # 取消 Agent 请求
        if self._agent and hasattr(self._agent, 'cancel'):
            try:
                self._agent.cancel()
            except Exception:
                pass
        
        # 更新 UI 状态
        self._update_input_state(processing=False)
        self.show_message("system", "🛑 正在停止...")

    def _pop_last_system_message(self):
        if self._messages and len(self._messages) > 0 and self._messages[-1]["role"] == "system":
            self._messages.pop()
    
    def set_agent(self, agent):
        self._agent = agent
    
    def set_llm(self, llm):
        self._llm = llm
    
    def set_ws2_system(self, system):
        self._ws2_system = system

    def _on_send_click(self):
        if self._input_entry is None:
            return
        # 兼容 tk.Entry 和 tk.Text
        if hasattr(self._input_entry, 'get'):
            try:
                # tk.Text 需要指定范围
                text = self._input_entry.get("1.0", tk.END).strip()
            except Exception:
                text = self._input_entry.get().strip()
        else:
            text = ""
        if text:
            # 兼容 tk.Entry 和 tk.Text 清空
            try:
                self._input_entry.delete("1.0", tk.END)  # tk.Text
            except Exception:
                self._input_entry.delete(0, tk.END)  # tk.Entry
            self.send_user_message(text)

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._pause_btn:
            try:
                self._pause_btn.configure(
                    text="▶" if self._paused else "⏸"
                )
            except Exception:
                pass
        self._append_to_area("system", "提醒已暂停 ⏸" if self._paused else "提醒已恢复 ▶")

    def _on_close_click(self):
        self._alive = False
        # 清理正在进行的请求
        self._stop_processing()
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    def is_alive(self) -> bool:
        return self._alive

    def set_on_send(self, callback: Callable[[str], None]):
        self._on_send = callback

    def set_on_close(self, callback: Callable[[], None]):
        self._on_close = callback

    def get_context(self) -> str:
        return self._memory.get_context(self.popup_id)

    def _inject_popup_context(self):
        """将弹窗环境感知注入到 agent 的 ContextProvider Others 层"""
        if not self._agent or not hasattr(self._agent, '_context_provider'):
            return
        try:
            from ..prompt.context_provider import ContextSection
            provider = self._agent._context_provider
            if not provider:
                return

            # 构建弹窗环境感知摘要
            parts = []
            parts.append(f"交互方式: 弹窗助手 (popup_id={self.popup_id})")
            if self.config.get("title"):
                parts.append(f"弹窗标题: {self.config['title']}")
            if self._ws2_system:
                parts.append("系统状态: 已连接 TS2 主系统")

            content = "\n".join(parts)
            section = ContextSection(
                source="popup_environment",
                label="环境感知（弹窗助手）",
                content=content,
                priority=25,
                layer="others",
            )

            # 清除之前的弹窗环境注入
            provider._dynamic_providers = [
                p for p in provider._dynamic_providers
                if getattr(p, '__source__', '') != 'popup_environment'
            ]

            def _popup_env_provider(agent=None, user_input=""):
                return section
            _popup_env_provider.__source__ = 'popup_environment'
            provider.register_dynamic(_popup_env_provider)
        except Exception:
            pass


class PopupManager:
    _instance: Optional["PopupManager"] = None
    _init_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._assistants: Dict[str, LearningAssistantPopup] = {}
        self._agent = None
        self._llm = None
        self._ws2_system = None

    @classmethod
    def get_instance(cls) -> "PopupManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def set_agent(self, agent):
        self._agent = agent
        # 更新现有助手
        for assistant in self._assistants.values():
            assistant.set_agent(agent)
    
    def set_llm(self, llm):
        self._llm = llm
        # 更新现有助手
        for assistant in self._assistants.values():
            assistant.set_llm(llm)
    
    def set_ws2_system(self, system):
        self._ws2_system = system
        # 更新现有助手
        for assistant in self._assistants.values():
            assistant.set_ws2_system(system)

    def create_assistant(self, popup_id: str, config: Dict[str, Any] = None) -> LearningAssistantPopup:
        with self._lock:
            if popup_id in self._assistants and self._assistants[popup_id].is_alive():
                return self._assistants[popup_id]
            assistant = LearningAssistantPopup(popup_id, config, agent=self._agent, llm=self._llm, ws2_system=self._ws2_system)
            assistant.set_on_close(lambda pid=popup_id: self._on_assistant_closed(pid))
            self._assistants[popup_id] = assistant
            return assistant

    def get_assistant(self, popup_id: str) -> Optional[LearningAssistantPopup]:
        with self._lock:
            return self._assistants.get(popup_id)

    def push_to_assistant(self, popup_id: str, title: str, content: str) -> bool:
        with self._lock:
            assistant = self._assistants.get(popup_id)
            if assistant and assistant.is_alive():
                assistant.push_notification(title, content)
                return True
        return False

    def close_assistant(self, popup_id: str) -> bool:
        with self._lock:
            assistant = self._assistants.pop(popup_id, None)
            if assistant:
                try:
                    assistant._on_close_click()
                except Exception:
                    pass
                return True
        return False

    def list_active(self) -> List[str]:
        with self._lock:
            return [
                pid for pid, a in self._assistants.items()
                if a.is_alive()
            ]

    def _on_assistant_closed(self, popup_id: str):
        with self._lock:
            if popup_id in self._assistants and not self._assistants[popup_id].is_alive():
                del self._assistants[popup_id]


__all__ = ["PopupManager", "LearningAssistantPopup", "LongTermMemory"]
