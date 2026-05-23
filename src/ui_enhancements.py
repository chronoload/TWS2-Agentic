#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 UI 增强模块 - 艺术风格、流式笔记、实时日志
==================================================
现代化UI设计：渐变色、圆角、阴影、流畅动画
流式笔记系统：实时记录、即时反馈
增强的视觉设计
"""

import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from datetime import datetime
from collections import defaultdict
import re

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class ArtisticTheme:
    """艺术主题配置"""

    COLORS = {
        'primary': '#667eea',
        'primary_dark': '#5a67d8',
        'secondary': '#f093fb',
        'success': '#48bb78',
        'warning': '#ed8936',
        'danger': '#fc8181',
        'info': '#4fd1c5',
        'dark': '#2d3748',
        'gray': '#718096',
        'light': '#f7fafc',
        'white': '#ffffff',
        'gradient_start': '#667eea',
        'gradient_end': '#764ba2',
    }

    FONTS = {
        'title': ('Microsoft YaHei', 18, 'bold'),
        'subtitle': ('Microsoft YaHei', 14, 'bold'),
        'body': ('Microsoft YaHei', 10),
        'small': ('Microsoft YaHei', 9),
        'mono': ('Consolas', 11, 'bold'),
        'emoji': ('Segoe UI Emoji', 12),
    }


class StreamingNotesPanel:
    """流式笔记面板 - 实时记录、即时反馈"""

    def __init__(self, parent, system, wflogger, course_id, lesson_number, theme):
        self.parent = parent
        self.system = system
        self.wflogger = wflogger
        self.course_id = course_id
        self.lesson_number = lesson_number
        self.theme = theme
        self.notes_history = []
        self._build()

    def _build(self):
        """构建流式笔记面板"""
        # 主容器
        main_frame = tk.Frame(self.parent, bg=self.theme.COLORS['light'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 标题栏
        header = tk.Frame(main_frame, bg=self.theme.COLORS['primary'])
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header, text="📝 流式笔记",
                font=self.theme.FONTS['subtitle'],
                fg='white', bg=self.theme.COLORS['primary']).pack(side=tk.LEFT, padx=15, pady=10)

        # 记录数标签
        self.count_label = tk.Label(header, text="0 条记录",
                                    font=self.theme.FONTS['small'],
                                    fg='white', bg=self.theme.COLORS['primary_dark'])
        self.count_label.pack(side=tk.RIGHT, padx=15, pady=10)

        # 输入区域
        input_frame = tk.Frame(main_frame, bg=self.theme.COLORS['white'],
                               highlightbackground=self.theme.COLORS['primary'],
                               highlightthickness=2)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        self.note_entry = tk.Text(input_frame, font=self.theme.FONTS['body'],
                                  height=4, wrap=tk.WORD, padx=10, pady=8,
                                  bg=self.theme.COLORS['white'],
                                  fg=self.theme.COLORS['dark'],
                                  relief=tk.FLAT, borderwidth=0)
        self.note_entry.pack(fill=tk.X, padx=5, pady=5)
        self.note_entry.focus()

        # 占位符提示
        self.note_entry.insert(1.0, "在此输入学习笔记...\n支持多行输入，回车提交")
        self.note_entry.bind('<FocusIn>', self._on_entry_focus)
        self.note_entry.bind('<FocusOut>', self._on_entry_blur)
        self.note_entry.bind('<Return>', lambda e: self._submit_note())

        # 按钮行
        btn_frame = tk.Frame(main_frame, bg=self.theme.COLORS['light'])
        btn_frame.pack(fill=tk.X)

        submit_btn = tk.Button(btn_frame, text="✏️ 提交笔记",
                              font=self.theme.FONTS['body'],
                              bg=self.theme.COLORS['primary'],
                              fg='white', relief=tk.FLAT,
                              padx=20, pady=8,
                              command=self._submit_note)
        submit_btn.pack(side=tk.LEFT, padx=5)

        clear_btn = tk.Button(btn_frame, text="🗑️ 清空",
                             font=self.theme.FONTS['body'],
                             bg=self.theme.COLORS['gray'],
                             fg='white', relief=tk.FLAT,
                             padx=20, pady=8,
                             command=self._clear_entry)
        clear_btn.pack(side=tk.LEFT, padx=5)

        # 笔记历史区域
        history_label = tk.Label(main_frame, text="📜 实时笔记流",
                                font=self.theme.FONTS['subtitle'],
                                fg=self.theme.COLORS['dark'],
                                bg=self.theme.COLORS['light'],
                                anchor='w')
        history_label.pack(fill=tk.X, pady=(10, 5))

        # 滚动历史容器
        self.history_container = tk.Frame(main_frame, bg=self.theme.COLORS['white'],
                                         highlightbackground=self.theme.COLORS['gray'],
                                         highlightthickness=1)
        self.history_container.pack(fill=tk.BOTH, expand=True)

        # 加载历史笔记
        self._load_history()

    def _on_entry_focus(self, event):
        """焦点进入"""
        if self.note_entry.get(1.0, tk.END).strip() == "在此输入学习笔记...\n支持多行输入，回车提交":
            self.note_entry.delete(1.0, tk.END)

    def _on_entry_blur(self, event):
        """焦点离开"""
        if not self.note_entry.get(1.0, tk.END).strip():
            self.note_entry.insert(1.0, "在此输入学习笔记...\n支持多行输入，回车提交")

    def _submit_note(self):
        """提交笔记"""
        content = self.note_entry.get(1.0, tk.END).strip()
        if content and content != "在此输入学习笔记...\n支持多行输入，回车提交":
            # 记录到工作日志
            self.wflogger.log_note(content, self.course_id, self.lesson_number)

            # 添加到历史
            self._add_note_to_history(content)

            # 清空输入
            self.note_entry.delete(1.0, tk.END)
            self.note_entry.insert(1.0, "在此输入学习笔记...\n支持多行输入，回车提交")

    def _add_note_to_history(self, content):
        """添加笔记到历史"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        note_data = {'content': content, 'time': timestamp}
        self.notes_history.insert(0, note_data)

        # 更新计数
        self.count_label.config(text=f"{len(self.notes_history)} 条记录")

        # 创建笔记卡片
        card = tk.Frame(self.history_container, bg=self.theme.COLORS['white'],
                       highlightbackground=self.theme.COLORS['info'],
                       highlightthickness=1)
        card.pack(fill=tk.X, padx=5, pady=3, anchor='n')

        # 时间标签
        time_label = tk.Label(card, text=timestamp,
                            font=self.theme.FONTS['small'],
                            fg=self.theme.COLORS['info'],
                            bg=self.theme.COLORS['white'])
        time_label.pack(anchor='w', padx=10, pady=(8, 2))

        # 内容
        content_label = tk.Label(card, text=content[:200],
                                font=self.theme.FONTS['body'],
                                fg=self.theme.COLORS['dark'],
                                bg=self.theme.COLORS['white'],
                                wraplength=400, justify='left', anchor='w')
        content_label.pack(fill=tk.X, padx=10, pady=(0, 8))

        # 滚动到顶部
        self.history_container.update_idletasks()
        self.history_container.tkraise(card)

    def _load_history(self):
        """加载历史笔记"""
        entries = self.wflogger.get_entries()
        lesson_notes = [
            e for e in entries
            if e.get('type') == 'note' and
               e.get('lesson_number') == self.lesson_number
        ][-20:]  # 最近20条

        for entry in lesson_notes:
            ts = entry.get('timestamp', '')[11:19]
            detail = entry.get('detail', '')
            if detail:
                note_data = {'content': detail, 'time': ts}
                self.notes_history.append(note_data)

        # 显示历史（倒序）
        for note in reversed(self.notes_history[-10:]):
            self._add_note_to_history(note['content'])


class StreamingLogPanel:
    """流式日志面板 - 实时反馈"""

    def __init__(self, parent, wflogger, theme):
        self.parent = parent
        self.wflogger = wflogger
        self.theme = theme
        self.log_entries = []
        self._build()

    def _build(self):
        """构建流式日志面板"""
        # 主容器
        main_frame = tk.Frame(self.parent, bg=self.theme.COLORS['light'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 标题栏
        header = tk.Frame(main_frame, bg=self.theme.COLORS['secondary'])
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header, text="⚡ 实时日志",
                font=self.theme.FONTS['subtitle'],
                fg='white', bg=self.theme.COLORS['secondary']).pack(side=tk.LEFT, padx=15, pady=10)

        # 状态指示器
        self.status_dot = tk.Label(header, text="●",
                                  font=self.theme.FONTS['emoji'],
                                  fg=self.theme.COLORS['success'],
                                  bg=self.theme.COLORS['secondary'])
        self.status_dot.pack(side=tk.RIGHT, padx=(0, 5))

        self.status_label = tk.Label(header, text="记录中",
                                   font=self.theme.FONTS['small'],
                                   fg='white', bg=self.theme.COLORS['secondary'])
        self.status_label.pack(side=tk.RIGHT, padx=(0, 15), pady=10)

        # 日志流容器
        self.log_container = tk.Frame(main_frame, bg=self.theme.COLORS['white'])
        self.log_container.pack(fill=tk.BOTH, expand=True)

        # 自动刷新
        self._refresh_logs()

    def _refresh_logs(self):
        """刷新日志"""
        if not self.wflogger:
            return

        entries = self.wflogger.get_entries()
        current_entries = entries[-10:] if len(entries) > 10 else entries

        # 清空旧日志
        for widget in self.log_container.winfo_children():
            widget.destroy()

        # 显示最新日志
        for entry in reversed(current_entries):
            self._add_log_entry(entry)

        # 定时刷新
        self.parent.after(2000, self._refresh_logs)

    def _add_log_entry(self, entry):
        """添加日志条目"""
        etype = entry.get('type', '')
        timestamp = entry.get('timestamp', '')[11:19]
        action = entry.get('action', '')
        detail = entry.get('detail', '')

        # 类型颜色映射
        type_colors = {
            'timer_start': (self.theme.COLORS['success'], '▶️'),
            'timer_stop': (self.theme.COLORS['warning'], '⏹️'),
            'action': (self.theme.COLORS['info'], '⚡'),
            'note': (self.theme.COLORS['success'], '📝'),
            'blur': (self.theme.COLORS['gray'], '👋'),
            'focus_return': (self.theme.COLORS['primary'], '👋'),
            'lesson_complete': (self.theme.COLORS['success'], '✅'),
        }

        color, icon = type_colors.get(etype, (self.theme.COLORS['gray'], '•'))

        # 条目容器
        entry_frame = tk.Frame(self.log_container, bg=self.theme.COLORS['white'])
        entry_frame.pack(fill=tk.X, padx=5, pady=2, anchor='w')

        # 时间
        time_label = tk.Label(entry_frame, text=timestamp,
                            font=('Consolas', 9),
                            fg=self.theme.COLORS['gray'],
                            bg=self.theme.COLORS['white'])
        time_label.pack(side=tk.LEFT, padx=(0, 5))

        # 图标
        icon_label = tk.Label(entry_frame, text=icon,
                            font=self.theme.FONTS['emoji'],
                            fg=color, bg=self.theme.COLORS['white'])
        icon_label.pack(side=tk.LEFT, padx=(0, 3))

        # 内容
        content = action if action else detail
        if content and len(content) > 50:
            content = content[:47] + '...'

        content_label = tk.Label(entry_frame, text=content,
                               font=self.theme.FONTS['small'],
                               fg=self.theme.COLORS['dark'],
                               bg=self.theme.COLORS['white'])
        content_label.pack(side=tk.LEFT)


class EnhancedExecutionMode:
    """增强执行模式 - 现代化UI"""

    def __init__(self, parent, system, wflogger, course_id, lesson, theme):
        self.parent = parent
        self.system = system
        self.wflogger = wflogger
        self.course_id = course_id
        self.lesson = lesson
        self.theme = theme
        self._build()

    def _build(self):
        """构建执行模式界面"""
        # 清空父容器
        for widget in self.parent.winfo_children():
            widget.destroy()

        if self.lesson is None:
            self._build_completion_view()
            return

        lnum = self.lesson.get("lesson_number", 0)
        title = self.lesson.get("lesson_title", "")
        question = self.lesson.get("central_question", "")
        description = self.lesson.get("description", "")

        # 主布局：左侧内容 + 右侧面板
        main_container = tk.PanedWindow(self.parent, orient=tk.HORIZONTAL,
                                       sashrelief=tk.FLAT, sashwidth=5)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 左侧：课时内容
        content_frame = tk.Frame(main_container, bg=self.theme.COLORS['light'])
        main_container.add(content_frame, width=600)

        self._build_lesson_content(content_frame, lnum, title, question, description)

        # 右侧：笔记和日志
        side_frame = tk.Frame(main_container, bg=self.theme.COLORS['light'])
        main_container.add(side_frame, width=350)

        self._build_side_panel(side_frame)

    def _build_lesson_content(self, parent, lnum, title, question, description):
        """构建课时内容"""
        # 滚动容器
        canvas = tk.Canvas(parent, bg=self.theme.COLORS['light'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=self.theme.COLORS['light'])

        scroll_frame.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 渐变标题栏
        header = tk.Frame(scroll_frame, bg=self.theme.COLORS['primary'], height=80)
        header.pack(fill=tk.X, pady=(0, 15))
        header.pack_propagate(False)

        # 课时号
        tk.Label(header, text=f"课时 {lnum}",
                font=self.theme.FONTS['small'],
                fg='white', bg=self.theme.COLORS['primary']).pack(anchor='w', padx=20, pady=(15, 0))

        # 标题
        tk.Label(header, text=title,
                font=self.theme.FONTS['title'],
                fg='white', bg=self.theme.COLORS['primary'],
                wraplength=550, justify='left').pack(anchor='w', padx=20, pady=(5, 15))

        # 中心问题卡片
        if question:
            question_card = tk.Frame(scroll_frame, bg=self.theme.COLORS['warning'],
                                    highlightbackground=self.theme.COLORS['warning'],
                                    highlightthickness=2)
            question_card.pack(fill=tk.X, padx=15, pady=(0, 15))

            tk.Label(question_card, text="🎯 中心问题",
                    font=self.theme.FONTS['subtitle'],
                    fg='white', bg=self.theme.COLORS['warning']).pack(anchor='w', padx=15, pady=(10, 5))

            # 分解问题
            questions = [q.strip() for q in re.split(r'[,，；;、]', question) if q.strip()]
            for q in questions[:3]:
                tk.Label(question_card, text=f"▸ {q}",
                        font=self.theme.FONTS['body'],
                        fg='white', bg=self.theme.COLORS['warning'],
                        wraplength=500, justify='left').pack(anchor='w', padx=25, pady=2)

            tk.Frame(question_card, bg=self.theme.COLORS['warning'],
                    height=10).pack(fill=tk.X)

        # 详细内容卡片
        if description:
            desc_card = tk.Frame(scroll_frame, bg=self.theme.COLORS['white'],
                                highlightbackground=self.theme.COLORS['gray'],
                                highlightthickness=1)
            desc_card.pack(fill=tk.X, padx=15, pady=(0, 15))

            tk.Label(desc_card, text="📖 详细内容",
                    font=self.theme.FONTS['subtitle'],
                    fg=self.theme.COLORS['dark'],
                    bg=self.theme.COLORS['white']).pack(anchor='w', padx=15, pady=(12, 8))

            desc_text = tk.Text(desc_card, font=self.theme.FONTS['body'],
                               bg=self.theme.COLORS['light'],
                               fg=self.theme.COLORS['dark'],
                               wrap=tk.WORD, height=8,
                               relief=tk.FLAT, borderwidth=0)
            desc_text.pack(fill=tk.X, padx=15, pady=(0, 12))
            desc_text.insert(1.0, description)
            desc_text.config(state=tk.DISABLED)

        # 资源标签页（固定高度）
        self._build_resource_tabs(scroll_frame)

        # 进度条
        self._build_progress_section(scroll_frame)

    def _build_resource_tabs(self, parent):
        """构建资源标签页（固定布局）"""
        course = self.system.get_course_by_id(self.course_id)
        lnum = self.lesson.get("lesson_number", 0)
        cid = self.course_id

        lesson_only_res = self.system.rmgr.get_for_lesson(cid, lnum) if self.system.rmgr else []
        course_only_res = self.system.rmgr.get_for_course(cid) if self.system.rmgr else []

        # 资源区域标题
        tk.Label(parent, text="📚 资源管理",
                font=self.theme.FONTS['subtitle'],
                fg=self.theme.COLORS['dark'],
                bg=self.theme.COLORS['light']).pack(anchor='w', padx=15, pady=(10, 5))

        # 笔记本式标签
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.X, padx=15, pady=(0, 10))

        # 课时资源 Tab - 固定大小
        lr_tab = tk.Frame(nb, bg=self.theme.COLORS['white'], height=120)
        lr_tab.pack_propagate(False)
        nb.add(lr_tab, text=f"🔗 课时资源 ({len(lesson_only_res)})")

        if lesson_only_res:
            lr_canvas = tk.Canvas(lr_tab, bg=self.theme.COLORS['white'], highlightthickness=0)
            lr_scroll = ttk.Scrollbar(lr_tab, orient="vertical", command=lr_canvas.yview)
            lr_frame = tk.Frame(lr_canvas, bg=self.theme.COLORS['white'])
            lr_frame.bind("<Configure>",
                         lambda e: lr_canvas.configure(scrollregion=lr_canvas.bbox("all")))
            lr_canvas.create_window((0, 0), window=lr_frame, anchor="nw")
            lr_canvas.configure(yscrollcommand=lr_scroll.set)
            lr_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            lr_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            for res in lesson_only_res[:5]:
                self._render_resource_item(lr_frame, res, cid)
        else:
            tk.Label(lr_tab, text="暂无课时资源",
                    font=self.theme.FONTS['small'],
                    fg=self.theme.COLORS['gray'],
                    bg=self.theme.COLORS['white']).pack(pady=30)

        # 课程资源 Tab - 固定大小
        cr_tab = tk.Frame(nb, bg=self.theme.COLORS['white'], height=120)
        cr_tab.pack_propagate(False)
        nb.add(cr_tab, text=f"📚 课程资源 ({len(course_only_res)})")

        if course_only_res:
            cr_canvas = tk.Canvas(cr_tab, bg=self.theme.COLORS['white'], highlightthickness=0)
            cr_scroll = ttk.Scrollbar(cr_tab, orient="vertical", command=cr_canvas.yview)
            cr_frame = tk.Frame(cr_canvas, bg=self.theme.COLORS['white'])
            cr_frame.bind("<Configure>",
                         lambda e: cr_canvas.configure(scrollregion=cr_canvas.bbox("all")))
            cr_canvas.create_window((0, 0), window=cr_frame, anchor="nw")
            cr_canvas.configure(yscrollcommand=cr_scroll.set)
            cr_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            cr_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            for res in course_only_res[:5]:
                self._render_resource_item(cr_frame, res, cid)
        else:
            tk.Label(cr_tab, text="暂无课程资源",
                    font=self.theme.FONTS['small'],
                    fg=self.theme.COLORS['gray'],
                    bg=self.theme.COLORS['white']).pack(pady=30)

    def _render_resource_item(self, parent, res, course_id):
        """渲染单个资源项"""
        item_frame = tk.Frame(parent, bg=self.theme.COLORS['white'])
        item_frame.pack(fill=tk.X, pady=2)

        icon = "📄" if res.get("type") == "pdf" else "🌐"
        label = res.get("label", "")

        tk.Label(item_frame, text=f"{icon} {label[:30]}",
                font=self.theme.FONTS['small'],
                fg=self.theme.COLORS['info'],
                bg=self.theme.COLORS['white']).pack(side=tk.LEFT, padx=5)

    def _build_progress_section(self, parent):
        """构建进度区域"""
        course = self.system.get_course_by_id(self.course_id)
        lnum = self.lesson.get("lesson_number", 0)

        pct = self.system.get_completion_pct(self.course_id)
        remaining = self.system.get_remaining_count(self.course_id)
        total = len(course.get("lessons", [])) if course else 0

        # 进度卡片
        progress_card = tk.Frame(parent, bg=self.theme.COLORS['white'],
                                highlightbackground=self.theme.COLORS['primary'],
                                highlightthickness=2)
        progress_card.pack(fill=tk.X, padx=15, pady=(10, 15))

        tk.Label(progress_card, text="📊 学习进度",
                font=self.theme.FONTS['subtitle'],
                fg=self.theme.COLORS['dark'],
                bg=self.theme.COLORS['white']).pack(anchor='w', padx=15, pady=(12, 5))

        # 进度文本
        progress_text = f"已完成 {total - remaining}/{total} 课时 ({pct}%)"
        tk.Label(progress_card, text=progress_text,
                font=self.theme.FONTS['body'],
                fg=self.theme.COLORS['gray'],
                bg=self.theme.COLORS['white']).pack(anchor='w', padx=15)

        # 进度条
        pbar = ttk.Progressbar(progress_card, length=500, mode="determinate",
                              maximum=100, value=pct)
        pbar.pack(fill=tk.X, padx=15, pady=10)

        # 完成按钮
        btn_frame = tk.Frame(progress_card, bg=self.theme.COLORS['white'])
        btn_frame.pack(pady=(0, 12))

        complete_btn = tk.Button(btn_frame, text="✅ 完成此课时 → 进入下一步",
                                font=self.theme.FONTS['body'],
                                bg=self.theme.COLORS['success'],
                                fg='white', relief=tk.FLAT,
                                padx=25, pady=10,
                                command=lambda: self._complete_current())
        complete_btn.pack()

    def _render_resource_row(self, parent, res, course_id=None, on_delete=None):
        """渲染资源行"""
        item_frame = tk.Frame(parent, bg=self.theme.COLORS['white'])
        item_frame.pack(fill=tk.X, pady=2)

    def _complete_current(self):
        """完成当前课时"""
        # 这个方法会被外部调用
        pass

    def _build_side_panel(self, parent):
        """构建侧边栏"""
        # 标签页
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 流式笔记 Tab
        notes_tab = tk.Frame(nb, bg=self.theme.COLORS['light'])
        nb.add(notes_tab, text="📝 笔记")
        StreamingNotesPanel(notes_tab, self.system, self.wflogger,
                           self.course_id, self.lesson.get("lesson_number", 0),
                           self.theme)

        # 流式日志 Tab
        log_tab = tk.Frame(nb, bg=self.theme.COLORS['light'])
        nb.add(log_tab, text="⚡ 日志")
        StreamingLogPanel(log_tab, self.wflogger, self.theme)

    def _build_completion_view(self):
        """构建完成视图"""
        complete_frame = tk.Frame(self.parent, bg=self.theme.COLORS['light'])
        complete_frame.pack(fill=tk.BOTH, expand=True)

        # 庆祝动画
        tk.Label(complete_frame, text="🎉",
                font=("Segoe UI Emoji", 72),
                bg=self.theme.COLORS['light']).pack(pady=50)

        tk.Label(complete_frame, text="恭喜！全部课时已完成！",
                font=self.theme.FONTS['title'],
                fg=self.theme.COLORS['success'],
                bg=self.theme.COLORS['light']).pack(pady=20)


class BeautifulStatsVisualization:
    """美观的统计可视化"""

    def __init__(self, parent, system, wflogger, theme):
        self.parent = parent
        self.system = system
        self.wflogger = wflogger
        self.theme = theme

    def create_dashboard(self):
        """创建仪表板"""
        for widget in self.parent.winfo_children():
            widget.destroy()

        # 主容器
        main_frame = tk.Frame(self.parent, bg=self.theme.COLORS['light'])
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        header = tk.Frame(main_frame, bg=self.theme.COLORS['primary'])
        header.pack(fill=tk.X, pady=(0, 15))

        tk.Label(header, text="📊 学习统计分析",
                font=self.theme.FONTS['title'],
                fg='white', bg=self.theme.COLORS['primary']).pack(padx=20, pady=15)

        # 标签页
        nb = ttk.Notebook(main_frame)
        nb.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))

        # Tab 1: 进度总览
        progress_tab = tk.Frame(nb, bg=self.theme.COLORS['white'])
        nb.add(progress_tab, text="📈 进度总览")
        self._create_progress_charts(progress_tab)

        # Tab 2: 时间分析
        time_tab = tk.Frame(nb, bg=self.theme.COLORS['white'])
        nb.add(time_tab, text="⏰ 时间分析")
        self._create_time_charts(time_tab)

        # Tab 3: 详细数据
        data_tab = tk.Frame(nb, bg=self.theme.COLORS['white'])
        nb.add(data_tab, text="📋 详细数据")
        self._create_detail_view(data_tab)

    def _create_progress_charts(self, parent):
        """创建进度图表"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg="white")

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(frame, text="课程完成进度",
                font=self.theme.FONTS['subtitle'],
                fg=self.theme.COLORS['dark'],
                bg="white").pack(pady=10)

        # 饼图
        fig = Figure(figsize=(8, 5), dpi=100)
        fig.patch.set_facecolor('white')

        ax = fig.add_subplot(111)
        done_total = 0
        remaining_total = 0

        for c in self.system.courses[:8]:
            cid = c.get("note_id", c.get("course_title", ""))
            remaining = self.system.get_remaining_count(cid)
            completed = len(c.get("lessons", [])) - remaining
            done_total += completed
            remaining_total += remaining

        if done_total + remaining_total > 0:
            sizes = [done_total, remaining_total]
            colors = ['#48bb78', '#e2e8f0']
            labels = [f'已完成 ({done_total})', f'剩余 ({remaining_total})']
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors,
                                             autopct='%1.1f%%', startangle=90)
            for autotext in autotexts:
                autotext.set_fontsize(12)
                autotext.set_fontweight('bold')

        fig.tight_layout()
        chart = FigureCanvasTkAgg(fig, master=frame)
        chart.get_tk_widget().pack(pady=10)

        # 条形图：各课程进度
        fig2 = Figure(figsize=(8, 5), dpi=100)
        fig2.patch.set_facecolor('white')
        ax2 = fig2.add_subplot(111)

        courses = []
        pcts = []
        colors = []

        for c in self.system.courses[:8]:
            cid = c.get("note_id", c.get("course_title", ""))
            pct = self.system.get_completion_pct(cid)
            courses.append(c.get("course_title", "")[:15])
            pcts.append(pct)
            domain = c.get("domain", "UNKNOWN")
            colors.append(self.theme.COLORS.get(domain, "#718096"))

        if courses:
            y_pos = range(len(courses))
            ax2.barh(y_pos, pcts, color=colors)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(courses)
            ax2.set_xlim(0, 100)
            ax2.set_xlabel('完成百分比 (%)')

            for i, v in enumerate(pcts):
                ax2.text(v + 1, i, f'{v:.0f}%', va='center')

        fig2.tight_layout()
        chart2 = FigureCanvasTkAgg(fig2, master=frame)
        chart2.get_tk_widget().pack(pady=10)

    def _create_time_charts(self, parent):
        """创建时间图表"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg="white")

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(frame, text="学习时间分析",
                font=self.theme.FONTS['subtitle'],
                fg=self.theme.COLORS['dark'],
                bg="white").pack(pady=10)

        stats = self.wflogger.get_stats() if self.wflogger else {}

        # 每日活动趋势
        fig = Figure(figsize=(8, 4), dpi=100)
        fig.patch.set_facecolor('white')
        ax = fig.add_subplot(111)

        daily = stats.get("daily", {})
        if daily:
            days = []
            counts = []
            for day, count in sorted(daily.items())[-14:]:
                days.append(day[5:])
                counts.append(count)

            if days:
                ax.fill_between(days, counts, alpha=0.3, color='#667eea')
                ax.plot(days, counts, marker='o', linewidth=2, color='#667eea')
                ax.set_ylabel('活动次数')
                ax.set_title('每日学习活动 (近14天)')

        fig.tight_layout()
        chart = FigureCanvasTkAgg(fig, master=frame)
        chart.get_tk_widget().pack(pady=10)

        # 课程时间分布
        fig2 = Figure(figsize=(8, 4), dpi=100)
        fig2.patch.set_facecolor('white')
        ax2 = fig2.add_subplot(111)

        course_times = stats.get("course_times", {})
        if course_times:
            sorted_courses = sorted(course_times.items(), key=lambda x: -x[1])[:6]
            titles = []
            hours = []
            colors_list = []

            for cid, secs in sorted_courses:
                course = self.system.get_course_by_id(cid)
                titles.append((course.get("course_title", "")[:15] if course else cid[:15]))
                hours.append(secs / 3600)
                domain = course.get("domain", "UNKNOWN") if course else "UNKNOWN"
                colors_list.append(self.theme.COLORS.get(domain, "#718096"))

            ax2.bar(titles, hours, color=colors_list)
            ax2.set_ylabel('学习时间 (小时)')
            ax2.set_title('各课程学习时间分布')

        fig2.tight_layout()
        chart2 = FigureCanvasTkAgg(fig2, master=frame)
        chart2.get_tk_widget().pack(pady=10)

    def _create_detail_view(self, parent):
        """创建详细数据视图"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg="white")

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(frame, text="详细统计数据",
                font=self.theme.FONTS['subtitle'],
                fg=self.theme.COLORS['dark'],
                bg="white").pack(pady=10)

        stats = self.wflogger.get_stats() if self.wflogger else {}

        # 基本统计卡片
        total_focus_h = stats.get("total_focus_time", 0) / 3600
        total_blur_h = stats.get("total_blur_time", 0) / 3600
        total_focus = stats.get("total_focus_time", 0)
        complete_count = stats.get("complete_count", 0)

        # 统计卡片行
        stats_row = tk.Frame(frame, bg="white")
        stats_row.pack(fill=tk.X, padx=20, pady=10)

        stats_data = [
            ("📊 日志条目", f"{stats.get('total_entries', 0)}", self.theme.COLORS['info']),
            ("⏱️ 专注时间", f"{total_focus_h:.1f}h", self.theme.COLORS['success']),
            ("✅ 完成课时", f"{complete_count}", self.theme.COLORS['success']),
            ("📝 笔记记录", f"{stats.get('note_count', 0)}", self.theme.COLORS['warning']),
        ]

        for i, (label, value, color) in enumerate(stats_data):
            card = tk.Frame(stats_row, bg=color, padx=15, pady=15)
            card.pack(side=tk.LEFT, expand=True, padx=5)

            tk.Label(card, text=label,
                    font=self.theme.FONTS['small'],
                    fg='white', bg=color).pack()
            tk.Label(card, text=value,
                    font=self.theme.FONTS['subtitle'],
                    fg='white', bg=color).pack()

        # 效率指标
        efficiency_row = tk.Frame(frame, bg="white")
        efficiency_row.pack(fill=tk.X, padx=20, pady=(10, 20))

        total_time = stats.get('total_focus_time', 0) + stats.get('total_blur_time', 0)
        focus_rate = (stats.get('total_focus_time', 0) / total_time * 100) if total_time > 0 else 0
        efficiency = complete_count / (total_focus / 3600) if total_focus > 0 else 0

        eff_data = [
            ("专注效率", f"{focus_rate:.1f}%"),
            ("平均每课时", f"{total_focus / complete_count / 60:.0f}分钟" if complete_count > 0 else "N/A"),
            ("学习效率", f"{efficiency:.2f}课时/h"),
        ]

        for label, value in eff_data:
            card = tk.Frame(efficiency_row, bg=self.theme.COLORS['primary'], padx=20, pady=12)
            card.pack(side=tk.LEFT, expand=True, padx=5)

            tk.Label(card, text=label,
                    font=self.theme.FONTS['small'],
                    fg='white', bg=self.theme.COLORS['primary']).pack()
            tk.Label(card, text=value,
                    font=self.theme.FONTS['subtitle'],
                    fg='white', bg=self.theme.COLORS['primary']).pack()
