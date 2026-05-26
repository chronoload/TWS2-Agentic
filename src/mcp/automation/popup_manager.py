#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk

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
        self.popup_id = popup_id
        self.config = config or {}
        self.title = self.config.get("title", "📚 学习助手")
        self._window: Optional[tk.Tk] = None
        self._message_text: Optional[tk.Text] = None
        self._input_entry: Optional[tk.Entry] = None
        self._messages: List[Dict[str, str]] = []
        self._paused = False
        self._on_send: Optional[Callable[[str], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._memory = LongTermMemory()
        self._alive = False
        self._agent = agent
        self._llm = llm
        self._ws2_system = ws2_system

    def show(self, parent: tk.Tk = None):
        if self._window is not None:
            try:
                self._window.lift()
                self._window.focus_force()
                return
            except tk.TclError:
                self._window = None

        self._window = tk.Toplevel(parent) if parent else tk.Tk()
        self._window.title(self.title)
        self._window.geometry("700x600")
        self._window.resizable(True, True)
        self._window.configure(bg=self.BG_COLOR)
        self._window.attributes("-topmost", True)

        screen_w = self._window.winfo_screenwidth()
        screen_h = self._window.winfo_screenheight()
        x = (screen_w - 700) // 2
        y = (screen_h - 600) // 2
        self._window.geometry(f"700x600+{x}+{y}")

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
        self._create_chat_area()
        self._create_input_area()

        self._alive = True
        self._load_history()

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

    def _create_chat_area(self):
        container = tk.Frame(self._window, bg=self.BG_COLOR)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._message_text = tk.Text(
            container, wrap=tk.WORD, state=tk.DISABLED,
            font=("Microsoft YaHei UI", 10),
            bg="#ffffff", fg=self.TEXT_COLOR,
            insertbackground=self.PRIMARY_COLOR,
            relief=tk.FLAT, padx=14, pady=14,
            spacing1=6, spacing3=6
        )
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._message_text.yview)
        self._message_text.configure(yscrollcommand=scrollbar.set)
        self._message_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            self._message_text.yview_scroll(int(-1 * (event.delta // 120)), "units")
        
        self._message_text.bind("<MouseWheel>", _on_mousewheel)
        container.bind("<MouseWheel>", _on_mousewheel)

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

    def _create_input_area(self):
        container = tk.Frame(self._window, bg=self.CARD_COLOR, relief=tk.FLAT, bd=1)
        container.pack(fill=tk.X, padx=12, pady=(0, 12))

        top_bar = tk.Frame(container, bg=self.CARD_COLOR)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Label(top_bar, text="输入问题或指令...", font=("Microsoft YaHei UI", 8),
                 bg=self.CARD_COLOR, fg="#9ca3af").pack(side=tk.LEFT)

        input_frame = tk.Frame(container, bg=self.CARD_COLOR)
        input_frame.pack(fill=tk.X, padx=10, pady=(4, 10))

        self._input_entry = tk.Entry(
            input_frame, font=("Microsoft YaHei UI", 10),
            bg="#f9fafb", fg=self.TEXT_COLOR,
            insertbackground=self.PRIMARY_COLOR,
            relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground="#e5e7eb", highlightcolor=self.PRIMARY_COLOR
        )
        self._input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=8)
        self._input_entry.bind("<Return>", lambda e: self._on_send_click())

        send_btn = tk.Button(
            input_frame, text="发送", font=("Microsoft YaHei UI", 9, "bold"),
            bg=self.PRIMARY_COLOR, fg="white", relief=tk.FLAT,
            activebackground="#2563eb", activeforeground="white",
            cursor="hand2", padx=16, pady=6,
            command=self._on_send_click
        )
        send_btn.pack(side=tk.RIGHT)

    def _load_history(self):
        entries = self._memory.load_recent(self.popup_id, limit=30)
        if entries:
            self._append_to_area("system", "📂 已恢复上次对话记忆")
            for entry in entries:
                self._append_to_area(entry.role, entry.content, entry.timestamp)

    def _append_to_area(self, role: str, content: str, timestamp: str = None):
        if self._message_text is None:
            return
        try:
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

    def _append_dict_as_cards(self, data: dict):
        if not data:
            return

        for idx, (key, value) in enumerate(data.items()):
            if idx > 0:
                self._message_text.insert(tk.END, "\n")
            
            key_display = {
                "success": "✅ 成功",
                "error": "❌ 错误",
                "data": "📊 数据",
                "results": "📋 结果",
                "message": "💬 消息",
                "count": "🔢 数量",
                "title": "📝 标题",
                "content": "📄 内容",
                "url": "🔗 链接",
                "authors": "👥 作者",
                "year": "📅 年份",
                "abstract": "📖 摘要",
                "doi": "🔖 DOI",
                "source": "📍 来源",
            }.get(key.lower(), f"📋 {key}")
            
            self._message_text.insert(tk.END, key_display, ("bold", "assistant_bg"))
            self._message_text.insert(tk.END, "\n", "assistant_bg")
            
            if isinstance(value, dict):
                self._message_text.insert(tk.END, "  ┌─", ("assistant", "assistant_bg"))
                self._message_text.insert(tk.END, "\n", "assistant_bg")
                for k, v in value.items():
                    self._message_text.insert(tk.END, f"  │ • {k}: ", ("assistant", "assistant_bg"))
                    if isinstance(v, list):
                        self._message_text.insert(tk.END, f"[{len(v)}项]", ("assistant", "assistant_bg"))
                    elif isinstance(v, str) and len(v) > 50:
                        self._message_text.insert(tk.END, f"{v[:50]}...", ("assistant", "assistant_bg"))
                    else:
                        self._message_text.insert(tk.END, str(v), ("assistant", "assistant_bg"))
                    self._message_text.insert(tk.END, "\n", "assistant_bg")
                self._message_text.insert(tk.END, "  └─", ("assistant", "assistant_bg"))
                self._message_text.insert(tk.END, "\n", "assistant_bg")
            elif isinstance(value, list):
                if len(value) > 3:
                    self._message_text.insert(tk.END, f"  [{len(value)}项] ", ("assistant", "assistant_bg"))
                    for item in value[:3]:
                        if isinstance(item, dict):
                            title = item.get("title", item.get("name", ""))
                            self._message_text.insert(tk.END, f"• {title[:30]}  ", ("assistant", "assistant_bg"))
                        else:
                            self._message_text.insert(tk.END, f"• {str(item)[:30]}  ", ("assistant", "assistant_bg"))
                    self._message_text.insert(tk.END, f"...等{len(value)}项", ("assistant", "assistant_bg"))
                else:
                    for item in value:
                        if isinstance(item, dict):
                            title = item.get("title", item.get("name", str(item)[:30]))
                            self._message_text.insert(tk.END, f"  • {title}\n", ("assistant", "assistant_bg"))
                        else:
                            self._message_text.insert(tk.END, f"  • {item}\n", ("assistant", "assistant_bg"))
            elif isinstance(value, str) and len(value) > 200:
                self._message_text.insert(tk.END, f"  {value[:200]}...\n", ("assistant", "assistant_bg"))
                self._message_text.insert(tk.END, f"  📎 [{len(value)}字符]", ("assistant", "assistant_bg"))
            else:
                self._message_text.insert(tk.END, f"  {value}", ("assistant", "assistant_bg"))

    def _append_list_as_cards(self, data: list):
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
        self._memory.store_message(self.popup_id, role, content)
        if self._alive and self._window is not None:
            try:
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
            
        try:
            self.show_message("system", "正在思考中...")
            
            if self._agent and hasattr(self._agent, 'chat'):
                def async_chat():
                    try:
                        context = self._memory.get_context(self.popup_id)
                        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                        if context:
                            messages.append({"role": "system", "content": f"对话历史：\n{context}"})
                        messages.append({"role": "user", "content": message})
                        
                        response = self._agent.chat(messages)
                        
                        if hasattr(response, 'content') and response.content:
                            self._window.after(0, lambda r=response.content: (
                                self._pop_last_system_message(),
                                self.show_message("assistant", r)
                            ))
                        
                        if hasattr(response, 'tool_calls') and response.tool_calls:
                            tool_lines = []
                            for t in response.tool_calls:
                                tool_lines.append(f"🔧 {t.name}")
                                if t.arguments:
                                    try:
                                        if isinstance(t.arguments, str):
                                            args_dict = json.loads(t.arguments)
                                        elif isinstance(t.arguments, dict):
                                            args_dict = t.arguments
                                        else:
                                            args_dict = {"raw": str(t.arguments)}
                                        for k, v in args_dict.items():
                                            tool_lines.append(f"   • {k}: {str(v)[:100]}")
                                    except:
                                        tool_lines.append(f"   • 参数: {str(t.arguments)[:100]}")
                            
                            self._window.after(0, lambda tc=response.tool_calls, tl=tool_lines: (
                                self._pop_last_system_message(),
                                self.show_message("assistant", "🤖 我将执行以下工具来帮你：\n" + "\n".join(tl))
                            ))
                    except Exception as e:
                        self._window.after(0, lambda err=str(e): (
                            self._pop_last_system_message(),
                            self.show_message("assistant", f"处理请求时出错：{err}")
                        ))
                
                threading.Thread(target=async_chat, daemon=True).start()
            elif self._agent and hasattr(self._agent, 'process'):
                def async_process():
                    try:
                        response = self._agent.process(message)
                        self._window.after(0, lambda r=response: (
                            self._pop_last_system_message(),
                            self.show_message("assistant", r)
                        ))
                    except Exception as e:
                        self._window.after(0, lambda err=str(e): (
                            self._pop_last_system_message(),
                            self.show_message("assistant", f"处理请求时出错：{err}")
                        ))
                
                threading.Thread(target=async_process, daemon=True).start()
            elif self._llm and hasattr(self._llm, 'generate'):
                def async_generate():
                    try:
                        context = self._memory.get_context(self.popup_id)
                        prompt = f"{SYSTEM_PROMPT}\n\n对话历史：\n{context}\n\n用户：{message}\n\n助手："
                        response = self._llm.generate(prompt)
                        self._window.after(0, lambda r=response: (
                            self._pop_last_system_message(),
                            self.show_message("assistant", r)
                        ))
                    except Exception as e:
                        self._window.after(0, lambda err=str(e): (
                            self._pop_last_system_message(),
                            self.show_message("assistant", f"处理请求时出错：{err}")
                        ))
                
                threading.Thread(target=async_generate, daemon=True).start()
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
        except Exception as e:
            logger.error(f"处理用户消息失败: {e}", exc_info=True)
            self.show_message("assistant", f"抱歉，处理请求时出错：{str(e)}")
        
        if self._on_send:
            try:
                self._on_send(message)
            except Exception as e:
                logger.error(f"On send callback failed: {e}", exc_info=True)

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
        text = self._input_entry.get().strip()
        if text:
            self._input_entry.delete(0, tk.END)
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
