#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专家Agent弹窗 - 面板专属AI助手弹窗

基于 LearningAssistantPopup 改造，支持专家Agent配置
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

try:
    import tkinter as tk
    from tkinter import ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    tk = None
    ttk = None

logger = logging.getLogger(__name__)


class SpecialistPopupButton:
    """
    专家Agent弹窗按钮
    
    可以放置在任何面板的工具栏中，点击后弹出专家Agent对话窗口
    """
    
    def __init__(
        self,
        parent,
        specialist_config,
        agent=None,
        llm=None,
        ws2_system=None,
        course_tracker=None,
        command: Optional[Callable] = None,
    ):
        self.parent = parent
        self.config = specialist_config
        self._agent = agent
        self._llm = llm
        self._ws2_system = ws2_system
        self._course_tracker = course_tracker
        self._command = command
        self._button = None
        self._popup = None
        
    def create_button(self, toolbar_frame) -> tk.Widget:
        """在工具栏中创建按钮"""
        if not HAS_TKINTER:
            return None
            
        btn = tk.Button(
            toolbar_frame,
            text=f"{self.config.icon} {self.config.name}",
            font=("Microsoft YaHei UI", 9),
            bg=self.config.color,
            fg="white",
            relief=tk.FLAT,
            activebackground=self._darken_color(self.config.color),
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._on_click,
        )
        btn.pack(side=tk.RIGHT, padx=(8, 0))
        self._button = btn
        return btn
    
    def create_small_button(self, toolbar_frame) -> tk.Widget:
        """创建小型图标按钮（仅图标）"""
        if not HAS_TKINTER:
            return None
            
        btn = tk.Label(
            toolbar_frame,
            text=self.config.icon,
            font=("Segoe UI Symbol", 14),
            bg=toolbar_frame.cget("bg"),
            fg=self.config.color,
            cursor="hand2",
        )
        btn.pack(side=tk.RIGHT, padx=(6, 0))
        btn.bind("<Button-1>", lambda e: self._on_click())
        
        # 添加悬停效果
        btn.bind("<Enter>", lambda e: btn.configure(fg=self._darken_color(self.config.color)))
        btn.bind("<Leave>", lambda e: btn.configure(fg=self.config.color))
        
        self._button = btn
        return btn
    
    def create_nav_button(self, parent_frame, style: str = "Accent.TButton") -> tk.Widget:
        """
        创建导航栏风格的大按钮（类似 assistant_btn）
        
        Args:
            parent_frame: 父框架
            style: ttk 样式名称，如 "Accent.TButton"
        
        Returns:
            创建的按钮部件
        """
        if not HAS_TKINTER:
            return None
        
        btn = ttk.Button(
            parent_frame,
            text=self.config.icon,
            command=self._on_click,
            style=style,
            width=3
        )
        btn.pack(side=tk.LEFT, padx=1)
        self._button = btn
        return btn
    
    def create_text_button(self, parent_frame, style: str = "Accent.TButton") -> tk.Widget:
        """
        创建带文字的醒目按钮
        
        Args:
            parent_frame: 父框架
            style: ttk 样式名称
        
        Returns:
            创建的按钮部件
        """
        if not HAS_TKINTER:
            return None
        
        btn = ttk.Button(
            parent_frame,
            text=f"{self.config.icon} {self.config.name}",
            command=self._on_click,
            style=style,
        )
        btn.pack(side=tk.LEFT, padx=4)
        self._button = btn
        return btn
    
    def _on_click(self):
        """按钮点击事件"""
        if self._command:
            self._command()
        else:
            self.show_popup()
    
    def show_popup(self, parent=None):
        """显示专家Agent弹窗"""
        if not HAS_TKINTER:
            logger.warning("tkinter 不可用，无法显示弹窗")
            return
        
        # 如果已有弹窗，提升到前台
        if self._popup is not None:
            try:
                window = getattr(self._popup, '_window', None)
                if window is not None:
                    window.lift()
                    window.focus_force()
                    return
            except tk.TclError:
                self._popup = None
        
        # 导入并创建弹窗
        try:
            from .popup_manager import LearningAssistantPopup
            
            popup_id = f"specialist_{self.config.role}"
            popup_config = {
                "title": f"{self.config.icon} {self.config.name}",
                "input_hint": f"向{self.config.name}提问...（{self.config.description}）",
            }
            
            self._popup = LearningAssistantPopup(
                popup_id=popup_id,
                config=popup_config,
                agent=self._agent,
                llm=self._llm,
                ws2_system=self._ws2_system,
            )
            self._popup.show(parent=parent or self.parent)
            
            # 注册学习状态注入器
            self._register_learning_state_injector()
            
            # 添加欢迎消息 - 展示职能和能力
            welcome_lines = [
                f"你好！我是{self.config.name} {self.config.icon}",
                "",
                f"📌 {self.config.description}",
                "",
            ]
            
            # 从 system_prompt 提取职责
            if self.config.system_prompt:
                lines = self.config.system_prompt.strip().split("\n")
                in_duties = False
                duties = []
                role_desc = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        if in_duties and duties:
                            break
                        continue
                    if "角色" in stripped or "Role" in stripped:
                        role_desc.append(stripped)
                        continue
                    if "你的职责" in stripped or "你的职责：" in stripped or "职责" == stripped:
                        in_duties = True
                        continue
                    if in_duties:
                        if stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                            duties.append(stripped)
                        elif stripped.startswith("- ") or stripped.startswith("• "):
                            duties.append(stripped[2:].strip())
                        elif duties and not stripped.startswith(("-", "1.", "2.", "3.", "4.", "5.")):
                            break
                
                if duties:
                    welcome_lines.append("🔧 核心职能：")
                    for d in duties[:6]:
                        welcome_lines.append(f"  • {d}")
                    welcome_lines.append("")
                elif role_desc:
                    welcome_lines.append(f"📋 {role_desc[0]}")
                    welcome_lines.append("")
            
            # 显示可用工具数量
            if self._agent and hasattr(self._agent, 'tools'):
                tool_count = len(self._agent.tools)
                welcome_lines.append(f"🛠️ 已加载 {tool_count} 个专业工具")
                welcome_lines.append("")
            
            # 提示使用方式
            welcome_lines.append("💡 你可以直接向我提问，或让我帮你完成任务。")
            welcome_lines.append("")
            welcome_lines.append("有什么我可以帮你的吗？")
            
            welcome_msg = "\n".join(welcome_lines)
            self._popup._append_to_area("system", welcome_msg)
            
        except Exception as e:
            logger.error(f"显示专家弹窗失败: {e}", exc_info=True)
    
    def _register_learning_state_injector(self):
        """注册学习状态注入器到 agent，首次对话时注入到 system prompt"""
        if not self._course_tracker or not self._popup or not self._popup._agent:
            return

        agent = self._popup._agent

        # 避免重复注册
        if getattr(agent, '_learning_state_injector_registered', False):
            return
        agent._learning_state_injector_registered = True

        tracker = self._course_tracker

        def _injector(agent_ref, user_input: str) -> str:
            """一次性注入学习状态和 UI 状态到 system prompt"""
            ctx_lines = []

            # 学习状态
            try:
                state = tracker.get_learning_state()
                if state.get("exec_mode_active"):
                    ctx_lines.append("【当前学习状态】")
                    ctx_lines.append(f"- 正在学习: {state.get('course_title', state.get('course_id', '未知'))}")
                    if state.get('domain'):
                        ctx_lines.append(f"- 课程领域: {state['domain']}")
                    if state.get('current_lesson_number'):
                        ctx_lines.append(f"- 当前课时: 第 {state['current_lesson_number']} 节")
                    if state.get('timer_running'):
                        ctx_lines.append("- 计时器: 运行中")
                    if state.get('completed_count') is not None:
                        ctx_lines.append(f"- 进度: {state['completed_count']}/{state.get('total_lessons', '?')} 节 ({state.get('completion_pct', 0)}%)")
            except Exception:
                pass

            # UI 状态：当前活跃标签页
            try:
                tab_key = getattr(tracker, '_active_tab_key', None)
                if tab_key:
                    tab_names = {
                        "overview": "总览", "exec": "执行模式", "taskboard": "任务看板",
                        "coursesim": "课程系统", "search": "网络研探", "projects": "项目管理",
                        "analyze": "科研文本分析", "crawler": "网络搜索", "synergy": "数据枢纽",
                        "domain": "域分布", "resource": "课程资源", "manage": "导入与管理",
                        "notes": "笔记", "wflog": "工作日志",
                    }
                    tab_name = tab_names.get(tab_key, tab_key)
                    ctx_lines.append(f"【当前界面】用户正在查看「{tab_name}」标签页")

                    # 根据标签页注入更具体的上下文
                    if tab_key == "projects":
                        # 项目管理页：列出项目
                        try:
                            ws = getattr(tracker, 'ws2_system', None)
                            if ws and hasattr(ws, 'projects'):
                                projs = ws.projects
                                if projs:
                                    names = [p.get('name', p.get('id', '?')) for p in projs[:10]]
                                    ctx_lines.append(f"- 项目列表: {', '.join(names)}")
                                else:
                                    ctx_lines.append("- 项目列表: 暂无项目")
                        except Exception:
                            pass
                    elif tab_key == "analyze":
                        ctx_lines.append("- 用户正在使用科研文本分析工具")
                        paper_file = getattr(tracker, '_current_paper_file', None)
                        if paper_file:
                            ctx_lines.append(f"- 当前加载的论文: {Path(paper_file).name}")
                    elif tab_key == "search":
                        ctx_lines.append("- 用户正在使用网络研探/书签工具")
                    elif tab_key == "notes":
                        ctx_lines.append("- 用户正在查看笔记")
                    elif tab_key == "coursesim":
                        ctx_lines.append("- 用户正在查看课程系统")
                    elif tab_key == "resource":
                        ctx_lines.append("- 用户正在查看课程资源")
            except Exception:
                pass

            if not ctx_lines:
                return ""
            return "\n".join(ctx_lines)

        agent.register_context_injector(_injector)
    
    def _darken_color(self, hex_color: str, factor: float = 0.8) -> str:
        """加深颜色"""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        return f"#{r:02x}{g:02x}{b:02x}"


def add_specialist_button_to_panel(
    panel_frame,
    specialist_config,
    agent=None,
    llm=None,
    ws2_system=None,
    toolbar_frame=None,
    small=False,
) -> Optional[SpecialistPopupButton]:
    """
    为面板添加专家Agent按钮的便捷函数
    
    Args:
        panel_frame: 面板主框架
        specialist_config: 专家配置
        agent: 专家Agent实例（可选，会自动创建）
        llm: LLM实例
        ws2_system: WS2系统实例
        toolbar_frame: 工具栏框架（可选，会自动创建）
        small: 是否使用小图标按钮
    
    Returns:
        SpecialistPopupButton 实例
    """
    if not HAS_TKINTER:
        return None
    
    # 如果没有提供工具栏，在面板顶部创建一个
    if toolbar_frame is None:
        toolbar_frame = tk.Frame(panel_frame, bg=panel_frame.cget("bg"))
        toolbar_frame.pack(fill=tk.X, pady=(0, 8), before=panel_frame.winfo_children()[0] if panel_frame.winfo_children() else None)
    
    # 创建按钮
    btn = SpecialistPopupButton(
        parent=panel_frame,
        specialist_config=specialist_config,
        agent=agent,
        llm=llm,
        ws2_system=ws2_system,
    )
    
    if small:
        btn.create_small_button(toolbar_frame)
    else:
        btn.create_button(toolbar_frame)
    
    return btn
