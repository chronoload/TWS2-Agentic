#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent GUI 界面 - 完整版本
包含聊天、配置、工具查看等功能
完全集成 WS2 系统

功能:
- 对话侧边分块导航（按轮次自动分块）
- 自动从对话生成标题
- 调试工具（消息查看、API 调用日志）
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading
import time
import json

from .agent import Agent, create_agent
from .config import get_config_manager
from .config_ui import show_enhanced_config_dialog


class AgentChatUI:
    """Agent 聊天界面"""

    def __init__(self, parent, base_dir: Optional[Path] = None, ws2_system=None, project_manager=None, task_manager=None):
        self.parent = parent
        self.base_dir = base_dir
        self.ws2_system = ws2_system
        self.project_manager = project_manager
        self.task_manager = task_manager
        self.config_manager = get_config_manager()
        self.agent: Optional[Agent] = None
        self._is_processing = False

        # === 对话分块导航（快速跳转） ===
        self._blocks: List[Dict[str, Any]] = []  # 每个块: {role, content, timestamp}
        self._current_block_idx = -1
        self._session_title = "新会话"
        self._title_generated = False
        self._show_all_blocks = True  # True=显示全部, False=只显示选中块

        # === 调试日志 ===
        self._debug_log: List[str] = []

        self.frame = ttk.Frame(parent)
        self._create_widgets()
        self._init_agent()

    def _create_widgets(self):
        """创建界面组件"""
        # ========== 主布局：左侧导航 + 右侧聊天 ==========
        main_paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # ========== 左侧：对话导航面板（固定宽度 260px） ==========
        nav_container = ttk.Frame(main_paned, width=260)
        main_paned.add(nav_container, weight=0)
        nav_container.pack_propagate(False)  # 固定宽度

        nav_frame = ttk.LabelFrame(nav_container, text="📑 对话导航", padding=5)
        nav_frame.pack(fill=tk.BOTH, expand=True)

        # 标题显示
        title_frame = ttk.Frame(nav_frame)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        self.title_var = tk.StringVar(value="新会话")
        ttk.Label(title_frame, textvariable=self.title_var,
                  font=("Microsoft YaHei UI", 10, "bold"),
                  foreground="#0066cc", wraplength=220).pack(fill=tk.X)

        # 分块列表（核心导航组件）
        self.nav_listbox = tk.Listbox(
            nav_frame,
            width=30,
            height=25,
            font=("Microsoft YaHei UI", 9),
            selectmode=tk.SINGLE,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.nav_listbox.pack(fill=tk.BOTH, expand=True, pady=2)
        self.nav_listbox.bind("<<ListboxSelect>>", self._on_nav_select)

        # 导航按钮
        nav_btn_frame = ttk.Frame(nav_frame)
        nav_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(nav_btn_frame, text="⬆ 上一块", command=self._nav_prev).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        ttk.Button(nav_btn_frame, text="⬇ 下一块", command=self._nav_next).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)

        # 跳转模式切换
        jump_btn_frame = ttk.Frame(nav_frame)
        jump_btn_frame.pack(fill=tk.X, pady=2)
        self._jump_mode_var = tk.StringVar(value="全部")
        ttk.Button(jump_btn_frame, text="📄 全部",
                   command=lambda: self._set_jump_mode("全部")).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        ttk.Button(jump_btn_frame, text="🔍 选中",
                   command=lambda: self._set_jump_mode("选中")).pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)

        # ========== 右侧：聊天面板 ==========
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        # 控制栏
        control_frame = ttk.LabelFrame(right_frame, text="控制", padding=10)
        control_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(control_frame, text="⚙️ 配置", command=self._open_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="🔄 新会话", command=self._new_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="📋 工具列表", command=self._show_tools).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="🗑️ 清空", command=self._clear_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="🐛 调试", command=self._show_debug).pack(side=tk.LEFT, padx=2)

        status_frame = ttk.Frame(control_frame)
        status_frame.pack(side=tk.RIGHT)
        ttk.Label(status_frame, text="API:").pack(side=tk.LEFT, padx=2)
        self.api_var = tk.StringVar(value="初始化中...")
        ttk.Label(status_frame, textvariable=self.api_var, foreground="#0066cc").pack(side=tk.LEFT)
        ttk.Label(status_frame, text="  |  状态:").pack(side=tk.LEFT, padx=2)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

        # 聊天区
        chat_frame = ttk.LabelFrame(right_frame, text="聊天", padding=10)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        self.chat_text = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            state=tk.DISABLED,
        )
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        self.chat_text.tag_config("system", foreground="#666666", font=("Microsoft YaHei UI", 10, "italic"))
        self.chat_text.tag_config("user", foreground="#0066cc", font=("Microsoft YaHei UI", 10, "bold"))
        self.chat_text.tag_config("assistant", foreground="#009933")
        self.chat_text.tag_config("tool", foreground="#993300")
        self.chat_text.tag_config("reasoning", foreground="#996600", font=("Microsoft YaHei UI", 9, "italic"))
        self.chat_text.tag_config("block_sep", foreground="#cccccc", font=("", 6))
        self.chat_text.tag_config("debug", foreground="#999999", font=("Consolas", 8))

        # 输入区
        input_frame = ttk.Frame(right_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=2)

        self.input_text = tk.Text(
            input_frame,
            height=3,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
        )
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.input_text.bind("<Control-Return>", lambda e: self._send_message())
        self.input_text.bind("<Shift-Return>", lambda e: None)

        send_btn = ttk.Button(input_frame, text="发送", width=10, command=self._send_message)
        send_btn.pack(side=tk.LEFT, padx=5, fill=tk.Y)

    # ==================== 对话分块导航 ====================

    def _add_block(self, role: str, content: str):
        """添加一个对话块到导航"""
        block = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
        }
        self._blocks.append(block)
        self._current_block_idx = len(self._blocks) - 1

        # 更新导航列表
        label = self._block_label(block)
        self.nav_listbox.insert(tk.END, label)
        self.nav_listbox.selection_clear(0, tk.END)
        self.nav_listbox.selection_set(tk.END)
        self.nav_listbox.see(tk.END)

        # 自动生成标题（前 3 个块后）
        if not self._title_generated and len(self._blocks) >= 3:
            self._auto_generate_title()

    def _block_label(self, block: dict) -> str:
        """生成块的显示标签"""
        role_map = {"user": "👤", "assistant": "🤖", "system": "⚙️", "tool": "🔧", "reasoning": "💭"}
        icon = role_map.get(block["role"], "📄")
        content = block["content"][:30].replace("\n", " ")
        return f"{icon} {content}"

    def _on_nav_select(self, event):
        """导航选择事件 - 快速跳转到对应块"""
        selection = self.nav_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx < 0 or idx >= len(self._blocks):
            return
        self._current_block_idx = idx

        if self._show_all_blocks:
            # 显示全部模式：滚动到对应块
            tag_name = f"block_{idx}"
            try:
                self.chat_text.see(tag_name)
            except tk.TclError:
                pass
        else:
            # 仅选中块模式：重建聊天区，只显示这个块
            self._rebuild_chat_display()

    def _set_jump_mode(self, mode: str):
        """设置跳转模式：全部 / 选中"""
        if mode == "全部":
            self._show_all_blocks = True
            self._rebuild_chat_display()
        else:
            self._show_all_blocks = False
            if self._current_block_idx >= 0:
                self._rebuild_chat_display()

    def _nav_prev(self):
        """上一块"""
        if self._current_block_idx > 0:
            self._current_block_idx -= 1
            self.nav_listbox.selection_clear(0, tk.END)
            self.nav_listbox.selection_set(self._current_block_idx)
            self.nav_listbox.see(self._current_block_idx)
            self._jump_to_block(self._current_block_idx)

    def _nav_next(self):
        """下一块"""
        if self._current_block_idx < len(self._blocks) - 1:
            self._current_block_idx += 1
            self.nav_listbox.selection_clear(0, tk.END)
            self.nav_listbox.selection_set(self._current_block_idx)
            self.nav_listbox.see(self._current_block_idx)
            self._jump_to_block(self._current_block_idx)

    def _jump_to_block(self, idx: int):
        """跳转到指定块（根据当前模式）"""
        if self._show_all_blocks:
            # 显示全部模式：滚动到对应块
            tag_name = f"block_{idx}"
            try:
                self.chat_text.see(tag_name)
            except tk.TclError:
                pass
        else:
            # 仅选中块模式：重建聊天区
            self._rebuild_chat_display()

    def _auto_generate_title(self):
        """自动从对话内容生成标题"""
        # 取前 3 个非系统消息的内容生成标题
        meaningful = [b for b in self._blocks if b["role"] in ("user", "assistant")]
        if not meaningful:
            return

        # 取第一条用户消息的前 40 个字符作为标题
        for b in meaningful:
            if b["role"] == "user":
                title = b["content"][:40].strip().replace("\n", " ")
                if title:
                    self._session_title = title
                    self.title_var.set(title)
                    self._title_generated = True
                    return

        # 兜底：取第一条有意义的内容
        first = meaningful[0]["content"][:40].strip().replace("\n", " ")
        if first:
            self._session_title = first
            self.title_var.set(first)
            self._title_generated = True

    # ==================== 调试工具 ====================

    def _log_debug(self, message: str):
        """记录调试日志"""
        timestamp = time.strftime("%H:%M:%S")
        self._debug_log.append(f"[{timestamp}] {message}")
        # 保留最近 500 条
        if len(self._debug_log) > 500:
            self._debug_log = self._debug_log[-500:]

    def _show_debug(self):
        """显示调试窗口"""
        debug_window = tk.Toplevel(self.parent)
        debug_window.title("🐛 调试工具")
        debug_window.geometry("900x600")

        # Notebook 标签页
        notebook = ttk.Notebook(debug_window)
        notebook.pack(fill=tk.BOTH, expand=True)

        # === Tab 1: API 调用日志 ===
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="API 日志")

        log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
        )
        log_text.pack(fill=tk.BOTH, expand=True)
        log_text.tag_config("error", foreground="red")
        log_text.tag_config("warn", foreground="orange")
        log_text.tag_config("info", foreground="green")

        log_text.config(state=tk.NORMAL)
        for line in self._debug_log:
            log_text.insert(tk.END, line + "\n")
        log_text.config(state=tk.DISABLED)
        log_text.see(tk.END)

        # === Tab 2: 消息查看器 ===
        msg_frame = ttk.Frame(notebook)
        notebook.add(msg_frame, text="消息查看器")

        msg_text = scrolledtext.ScrolledText(
            msg_frame, wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
        )
        msg_text.pack(fill=tk.BOTH, expand=True)

        if self.agent and self.agent.messages:
            msg_text.config(state=tk.NORMAL)
            for i, m in enumerate(self.agent.messages):
                role = m.get("role", "?")
                content = m.get("content", "")
                tool_calls = m.get("tool_calls", [])
                tool_call_id = m.get("tool_call_id", "")

                msg_text.insert(tk.END, f"─── 消息 #{i} ───\n", "header")
                msg_text.insert(tk.END, f"  role: {role}\n")
                if tool_call_id:
                    msg_text.insert(tk.END, f"  tool_call_id: {tool_call_id}\n")
                if tool_calls:
                    msg_text.insert(tk.END, f"  tool_calls: {json.dumps(tool_calls, ensure_ascii=False, indent=2)[:500]}\n")
                if content:
                    content_preview = content[:200].replace("\n", "\\n")
                    msg_text.insert(tk.END, f"  content: {content_preview}\n")
                    if len(content) > 200:
                        msg_text.insert(tk.END, f"  ... ({len(content)} 字符)\n")
                msg_text.insert(tk.END, "\n")
            msg_text.tag_config("header", foreground="#0066cc", font=("Consolas", 9, "bold"))
            msg_text.config(state=tk.DISABLED)
        else:
            msg_text.config(state=tk.NORMAL)
            msg_text.insert(tk.END, "（无消息）")
            msg_text.config(state=tk.DISABLED)

        # === Tab 3: 对话块 ===
        block_frame = ttk.Frame(notebook)
        notebook.add(block_frame, text="对话块")

        block_text = scrolledtext.ScrolledText(
            block_frame, wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
        )
        block_text.pack(fill=tk.BOTH, expand=True)

        block_text.config(state=tk.NORMAL)
        block_text.insert(tk.END, f"标题: {self._session_title}\n\n")
        for i, b in enumerate(self._blocks):
            label = self._block_label(b)
            block_text.insert(tk.END, f"#{i}: {label}\n")
        block_text.config(state=tk.DISABLED)

        # 刷新按钮
        ttk.Button(debug_window, text="🔄 刷新",
                   command=lambda: self._refresh_debug(debug_window)).pack(pady=5)

    def _refresh_debug(self, window):
        """刷新调试窗口"""
        window.destroy()
        self._show_debug()

    # ==================== 核心聊天逻辑 ====================

    def _init_agent(self):
        """初始化 Agent"""
        try:
            self.agent = create_agent(
                base_dir=self.base_dir,
                ws2_system=self.ws2_system,
                project_manager=self.project_manager,
                task_manager=self.task_manager
            )
            self._update_api_status()
            self._log_debug(f"Agent 初始化成功，工具数: {len(self.agent.tools)}")
            self._append_message("system", "✨ WS2 Agent 已就绪！\n点击「⚙️ 配置」设置 API 和工具。\n试试问我：「查看课程总览」、「列出所有课程」、「查看书签」...")
        except Exception as e:
            self._log_debug(f"Agent 初始化失败: {e}")
            self._append_message("system", f"⚠️ 初始化失败：{e}")

    def _append_message(self, role: str, content: str):
        """添加消息到聊天区（每个块独立存储，支持快速跳转）"""
        # 先添加到块列表
        self._add_block(role, content)

        # 如果当前是"显示全部"模式，追加到聊天区
        if self._show_all_blocks:
            self._render_block_to_chat(len(self._blocks) - 1)

    def _render_block_to_chat(self, idx: int):
        """将指定块渲染到聊天区末尾"""
        if idx < 0 or idx >= len(self._blocks):
            return
        block = self._blocks[idx]
        role = block["role"]
        content = block["content"]

        self.chat_text.config(state=tk.NORMAL)

        # 添加分块标记（用于导航定位）
        tag_name = f"block_{idx}"
        self.chat_text.mark_set(tag_name, tk.END)
        self.chat_text.mark_gravity(tag_name, tk.LEFT)

        # 块分隔线
        if idx > 0:
            self.chat_text.insert(tk.END, f"─── 对话块 {idx} ───\n", "block_sep")

        prefix = {
            "system": "【系统】\n",
            "user": "【你】\n",
            "assistant": "【助手】\n",
            "tool": "【工具】\n",
            "reasoning": "",
        }.get(role, f"【{role}】\n")

        self.chat_text.insert(tk.END, prefix, role)
        self.chat_text.insert(tk.END, content + "\n\n", role)
        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _rebuild_chat_display(self):
        """根据当前模式重建聊天区显示"""
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

        if self._show_all_blocks:
            # 显示全部块
            for i in range(len(self._blocks)):
                self._render_block_to_chat(i)
        else:
            # 只显示选中块
            if 0 <= self._current_block_idx < len(self._blocks):
                self._render_block_to_chat(self._current_block_idx)

    def _send_message(self):
        """发送消息"""
        user_input = self.input_text.get("1.0", tk.END).strip()
        if not user_input or self._is_processing:
            return

        self.input_text.delete("1.0", tk.END)
        self._append_message("user", user_input)
        self._is_processing = True
        self.status_var.set("思考中...")
        self.input_text.config(state=tk.DISABLED)

        self._log_debug(f"发送消息: {user_input[:50]}...")

        thread = threading.Thread(target=self._process_message, args=(user_input,))
        thread.daemon = True
        thread.start()

    def _process_message(self, user_input: str):
        """在后台处理消息"""
        try:
            accumulated_reasoning = []
            accumulated_content = []
            reasoning_started = False
            content_started = False

            def on_token(token: str, token_type: str = "content"):
                nonlocal reasoning_started, content_started
                if token_type == "reasoning":
                    if not reasoning_started:
                        self.parent.after(0, lambda: self._append_message("reasoning", "💭 思考中..."))
                        reasoning_started = True
                    accumulated_reasoning.append(token)
                else:
                    if not content_started:
                        if reasoning_started:
                            full_reasoning = "".join(accumulated_reasoning)
                            self.parent.after(0, lambda r=full_reasoning: self._append_message("reasoning", f"💭 思考过程：\n{r}"))
                            self.parent.after(0, lambda: self._append_message("reasoning", "---"))
                        content_started = True
                    accumulated_content.append(token)

            def on_tool(name: str, args: dict):
                self.parent.after(0, lambda: self._append_message("tool", f"调用工具：{name}\n参数：{args}"))
                self._log_debug(f"工具调用: {name}({json.dumps(args, ensure_ascii=False)[:100]})")

            response = self.agent.chat(user_input, on_token=on_token, on_tool=on_tool)

            self.parent.after(0, lambda: self._on_response(response))
        except Exception as exc:
            self._log_debug(f"处理消息错误: {exc}")
            self.parent.after(0, lambda e=exc: self._on_error(str(e)))

    def _on_response(self, response: str):
        """处理响应"""
        self._append_message("assistant", response)
        self._log_debug(f"收到响应: {response[:50]}...")
        self._finish_processing()

    def _on_error(self, error: str):
        """处理错误"""
        self._append_message("system", f"❌ 错误：{error}")
        self._log_debug(f"错误: {error}")
        self._finish_processing()

    def _finish_processing(self):
        """结束处理"""
        self._is_processing = False
        self.status_var.set("就绪")
        self.input_text.config(state=tk.NORMAL)
        self.input_text.focus()

    def _open_config(self):
        """打开配置对话框"""
        show_enhanced_config_dialog(self.parent)
        self._update_api_status()
        self._append_message("system", "配置已更新，正在重新初始化 Agent...")
        self._init_agent()

    def _update_api_status(self):
        """更新 API 状态"""
        configs = self.config_manager.provider_configs or []
        enabled_configs = [c for c in configs if c.enabled]
        if enabled_configs:
            self.api_var.set(enabled_configs[0].name)
        else:
            self.api_var.set("使用模拟器")

    def _new_session(self):
        """新会话"""
        if self.agent:
            self.agent.reset()
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

        # 重置导航
        self._blocks.clear()
        self._current_block_idx = -1
        self.nav_listbox.delete(0, tk.END)
        self._session_title = "新会话"
        self.title_var.set("新会话")
        self._title_generated = False

        self._append_message("system", "已创建新会话。")

    def _clear_history(self):
        """清空历史"""
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

        self._blocks.clear()
        self._current_block_idx = -1
        self.nav_listbox.delete(0, tk.END)

        self._append_message("system", "历史已清空。")

    def _show_tools(self):
        """显示工具列表"""
        if not self.agent:
            return

        tool_window = tk.Toplevel(self.parent)
        tool_window.title("可用工具")
        tool_window.geometry("800x700")

        text = scrolledtext.ScrolledText(tool_window, wrap=tk.WORD, font=("Consolas", 9))
        text.pack(fill=tk.BOTH, expand=True)

        # WS2 总览与统计工具
        text.insert(tk.END, "【WS2 总览与统计工具】\n\n", "ws2")
        ws2_overview = ["ws2_get_overview", "ws2_get_domain_stats", "ws2_list_domains", "ws2_get_progress_by_domain"]
        for name in ws2_overview:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 课程管理工具
        text.insert(tk.END, "\n【WS2 课程管理工具】\n\n", "ws2")
        ws2_course = ["ws2_list_courses", "ws2_search_courses", "ws2_get_course_detail", "ws2_create_course", "ws2_remove_course", "ws2_find_duplicates"]
        for name in ws2_course:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 课时学习工具
        text.insert(tk.END, "\n【WS2 课时学习工具】\n\n", "ws2")
        ws2_lesson = ["ws2_mark_lesson_complete", "ws2_get_next_lesson", "ws2_get_course_progress"]
        for name in ws2_lesson:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 复习调度工具
        text.insert(tk.END, "\n【WS2 复习调度工具】\n\n", "ws2")
        ws2_review = ["ws2_get_review_schedule", "ws2_mark_review_done"]
        for name in ws2_review:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 资源管理工具
        text.insert(tk.END, "\n【WS2 资源管理工具】\n\n", "ws2")
        ws2_resource = ["ws2_get_resources"]
        for name in ws2_resource:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 书签管理工具
        text.insert(tk.END, "\n【WS2 书签管理工具】\n\n", "ws2")
        ws2_bookmark = ["ws2_list_bookmarks", "ws2_search_bookmarks", "ws2_list_bookmark_categories", "ws2_add_bookmark"]
        for name in ws2_bookmark:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 笔记管理工具
        text.insert(tk.END, "\n【WS2 笔记管理工具】\n\n", "ws2")
        ws2_note = ["ws2_list_notes", "ws2_read_note", "ws2_write_note"]
        for name in ws2_note:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 项目管理工具
        text.insert(tk.END, "\n【WS2 项目管理工具】\n\n", "ws2")
        ws2_project = ["ws2_list_projects", "ws2_create_project"]
        for name in ws2_project:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 任务看板工具
        text.insert(tk.END, "\n【WS2 任务看板工具】\n\n", "ws2")
        ws2_task = ["ws2_list_tasks", "ws2_add_task", "ws2_update_task"]
        for name in ws2_task:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # WS2 数据库管理工具
        text.insert(tk.END, "\n【WS2 数据库管理工具】\n\n", "ws2")
        ws2_db = ["ws2_reload_all_sources", "ws2_add_db_path", "ws2_get_db_paths"]
        for name in ws2_db:
            tool = next((t for t in self.agent.tools if t.name == name), None)
            if tool:
                text.insert(tk.END, f"- {tool.name}\n", "tool_name")
                text.insert(tk.END, f"  {tool.description}\n\n")

        # 技能系统
        text.insert(tk.END, "\n【技能系统】\n\n", "general")
        from .config import get_config_manager
        config_mgr = get_config_manager()
        skills = config_mgr.get_enabled_skills()
        if skills:
            text.insert(tk.END, "已启用的技能：\n")
            for skill in skills:
                status = "✅" if skill.enabled else "❌"
                text.insert(tk.END, f"- {status} {skill.name}\n", "tool_name")
                text.insert(tk.END, f"  {skill.description}\n")
        else:
            text.insert(tk.END, "暂无启用的技能\n")
        text.insert(tk.END, "\n提示：通过 skill_manager 工具可以管理和执行技能\n\n")

        # 通用工具
        text.insert(tk.END, "\n【通用工具】\n\n", "general")
        general_tools = [t for t in self.agent.tools if not t.name.startswith("ws2_")]
        for tool in general_tools:
            text.insert(tk.END, f"- {tool.name}\n", "tool_name")
            text.insert(tk.END, f"  {tool.description}\n\n")

        text.tag_config("ws2", foreground="#0066cc", font=("", 10, "bold"))
        text.tag_config("general", foreground="#009933", font=("", 10, "bold"))
        text.tag_config("tool_name", foreground="#333333", font=("", 9, "bold"))
        text.config(state=tk.DISABLED)