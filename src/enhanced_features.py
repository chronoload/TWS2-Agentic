#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TS2 增强模块 - 高级详情显示、执行模式集成、事件日志与统计可视化
=====================================================================
增强课程详情、课时详情、执行模式信息集成、事件日志、统计可视化功能

依赖: course_tracker.py 中的 CourseSystem, WorkflowLogger, DOMAIN_COLORS, DOMAIN_NAMES
"""

import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from collections import defaultdict
import re

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class EnhancedLessonDetail:
    """增强版课时详情组件"""

    def __init__(self, parent, system, wflogger, course_id, lesson, base):
        self.parent = parent
        self.system = system
        self.wflogger = wflogger
        self.course_id = course_id
        self.lesson = lesson
        self.base = base
        self._build()

    def _build(self):
        """构建增强版课时详情"""
        for w in self.parent.winfo_children():
            w.destroy()

        if self.lesson is None:
            ttk.Label(self.parent, text="🎉", font=("", 48)).pack(pady=20)
            ttk.Label(self.parent, text="恭喜！本课程全部课时已完成！",
                      font=("", 16, "bold"), foreground="#27ae60").pack(pady=10)
            return

        lnum = self.lesson.get("lesson_number", 0)
        title = self.lesson.get("lesson_title", "")
        question = self.lesson.get("central_question", "")
        description = self.lesson.get("description", "")
        course = self.system.get_course_by_id(self.course_id)

        # 可滚动容器
        r_canvas = tk.Canvas(self.parent, highlightthickness=0, bg="#F8F9FA")
        r_scroll = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=r_canvas.yview)
        scroll_inner = ttk.Frame(r_canvas)
        scroll_inner.bind("<Configure>", lambda e: r_canvas.configure(scrollregion=r_canvas.bbox("all")))
        r_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
        r_canvas.configure(yscrollcommand=r_scroll.set)
        r_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        r_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        inner = scroll_inner

        # ==================== 1. 课时基本信息 ====================
        info_frame = ttk.LabelFrame(inner, text="📖 课时信息", padding=12)
        info_frame.pack(fill=tk.X, padx=15, pady=10)

        # 课时号和标题
        header = ttk.Frame(info_frame)
        header.pack(fill=tk.X)
        ttk.Label(header, text=f"课时 {lnum}", font=("", 12), foreground="#2980b9").pack(side=tk.LEFT)
        ttk.Label(header, text=title, font=("", 16, "bold")).pack(side=tk.LEFT, padx=15)

        # Section归属
        sec = self.system.get_lesson_section(self.course_id, lnum)
        if sec:
            sec_info = f"📂 {sec.get('section_title', f'Section {sec.get(\"section_number\", \"?\")}')}"
            ttk.Label(info_frame, text=sec_info, font=("", 10), foreground="#8e44ad").pack(anchor="w", pady=(5, 0))

        # ==================== 2. 中心问题（重点突出） ====================
        if question:
            question_frame = ttk.LabelFrame(inner, text="🎯 中心问题", padding=12)
            question_frame.pack(fill=tk.X, padx=15, pady=10)

            # 分解中心问题为要点
            q_lines = [q.strip() for q in re.split(r'[,，；;、]', question) if q.strip()]
            for q in q_lines:
                q_row = ttk.Frame(question_frame)
                q_row.pack(fill=tk.X, pady=2)
                ttk.Label(q_row, text="▸", foreground="#e74c3c", font=("", 11)).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Label(q_row, text=q, font=("", 11), foreground="#c0392b").pack(side=tk.LEFT)

        # ==================== 3. 详细描述 ====================
        if description:
            desc_frame = ttk.LabelFrame(inner, text="📝 详细内容", padding=12)
            desc_frame.pack(fill=tk.X, padx=15, pady=10)

            # 文本框显示描述
            desc_text = tk.Text(desc_frame, wrap=tk.WORD, font=("", 10), height=6,
                                 bg="#FAFAFA", relief=tk.FLAT)
            desc_text.pack(fill=tk.X)
            desc_text.insert(1.0, description)
            desc_text.config(state=tk.DISABLED)

            # 高亮关键词
            self._highlight_keywords(desc_text, question)

        # ==================== 4. 学习目标（从描述中提取） ====================
        learning_frame = ttk.LabelFrame(inner, text="📋 学习目标", padding=12)
        learning_frame.pack(fill=tk.X, padx=15, pady=10)

        # 从描述中提取学习目标（格式：掌握/理解/学会/了解/应用等）
        goals = self._extract_learning_goals(description, question)
        if goals:
            for i, goal in enumerate(goals, 1):
                goal_row = ttk.Frame(learning_frame)
                goal_row.pack(fill=tk.X, pady=2)
                ttk.Label(goal_row, text=f"{i}.", font=("", 10, "bold"), foreground="#3498db").pack(side=tk.LEFT, padx=(0, 5))
                ttk.Label(goal_row, text=goal, font=("", 10), wraplength=500).pack(side=tk.LEFT)
        else:
            ttk.Label(learning_frame, text="从课时描述中提取学习要点...", style="Sub.TLabel", foreground="#95a5a6").pack(anchor="w")

        # ==================== 5. 参考资料 ====================
        course_refs = course.get("references", []) if course else []
        lesson_refs = self.lesson.get("references", []) if self.lesson else []

        if course_refs or lesson_refs:
            ref_frame = ttk.LabelFrame(inner, text="📚 参考资料", padding=12)
            ref_frame.pack(fill=tk.X, padx=15, pady=10)

            # 课时级参考资料
            if lesson_refs:
                ttk.Label(ref_frame, text="【课时参考资料】", font=("", 10, "bold"), foreground="#2c3e50").pack(anchor="w")
                for ref in lesson_refs[:10]:
                    ref_text = ref if isinstance(ref, str) else ref.get("title", str(ref))
                    ref_row = ttk.Frame(ref_frame)
                    ref_row.pack(fill=tk.X, pady=1)
                    ttk.Label(ref_row, text="  📖", font=("", 9)).pack(side=tk.LEFT)
                    ttk.Label(ref_row, text=ref_text, font=("", 9), foreground="#2980b9",
                             cursor="hand2").pack(side=tk.LEFT)

            # 课程级参考资料
            if course_refs:
                ttk.Label(ref_frame, text="【课程参考资料】", font=("", 10, "bold"), foreground="#2c3e50").pack(anchor="w", pady=(10, 0))
                for ref in course_refs[:10]:
                    ref_text = ref if isinstance(ref, str) else ref.get("title", str(ref))
                    ref_row = ttk.Frame(ref_frame)
                    ref_row.pack(fill=tk.X, pady=1)
                    ttk.Label(ref_row, text="  📚", font=("", 9)).pack(side=tk.LEFT)
                    ttk.Label(ref_row, text=ref_text, font=("", 9), foreground="#7f8c8d",
                             cursor="hand2").pack(side=tk.LEFT)

        # ==================== 6. 关联资源 ====================
        lesson_only_res = self.system.rmgr.get_for_lesson(self.course_id, lnum) if self.system.rmgr else []
        course_only_res = self.system.rmgr.get_for_course(self.course_id) if self.system.rmgr else []

        res_frame = ttk.LabelFrame(inner, text="🔗 关联资源", padding=12)
        res_frame.pack(fill=tk.X, padx=15, pady=10)

        if lesson_only_res or course_only_res:
            # 课时资源
            if lesson_only_res:
                ttk.Label(res_frame, text="课时资源:", font=("", 10, "bold"), foreground="#27ae60").pack(anchor="w")
                for res in lesson_only_res:
                    res_row = ttk.Frame(res_frame)
                    res_row.pack(fill=tk.X, pady=2)
                    icon = "📄" if res.get("type") == "pdf" else "🌐"
                    ttk.Label(res_row, text=f"  {icon}", font=("", 9)).pack(side=tk.LEFT)
                    ttk.Label(res_row, text=res.get("label", ""), font=("", 9), foreground="#2980b9").pack(side=tk.LEFT)

            # 课程资源
            if course_only_res:
                ttk.Label(res_frame, text="课程资源:", font=("", 10, "bold"), foreground="#27ae60").pack(anchor="w", pady=(8, 0))
                for res in course_only_res[:5]:
                    res_row = ttk.Frame(res_frame)
                    res_row.pack(fill=tk.X, pady=2)
                    icon = "📄" if res.get("type") == "pdf" else "🌐"
                    ttk.Label(res_row, text=f"  {icon}", font=("", 9)).pack(side=tk.LEFT)
                    ttk.Label(res_row, text=res.get("label", ""), font=("", 9), foreground="#7f8c8d").pack(side=tk.LEFT)
        else:
            ttk.Label(res_frame, text="暂无关联资源", style="Sub.TLabel", foreground="#95a5a6").pack(anchor="w")

        # ==================== 7. 笔记入口 ====================
        note_frame = ttk.LabelFrame(inner, text="📓 学习笔记", padding=12)
        note_frame.pack(fill=tk.X, padx=15, pady=10)

        note_path, _ = self.system.get_or_create_note(self.course_id, lnum)
        ttk.Label(note_frame, text=f"笔记文件: {note_path.name if note_path else '未创建'}",
                 font=("", 9), foreground="#7f8c8d").pack(anchor="w")

        # 最近笔记预览
        recent_notes = self._get_recent_notes(lnum)
        if recent_notes:
            ttk.Label(note_frame, text="最近的笔记记录:", font=("", 9, "bold")).pack(anchor="w", pady=(5, 2))
            for note in recent_notes[:3]:
                ttk.Label(note_frame, text=f"  • {note}", font=("", 9), foreground="#34495e",
                        wraplength=450).pack(anchor="w")

    def _extract_learning_goals(self, description, question):
        """从描述和中心问题中提取学习目标"""
        goals = []
        keywords = ['掌握', '理解', '学会', '了解', '应用', '分析', '证明', '推导', '计算', '设计']

        # 从中心问题提取
        if question:
            goals.append(f"核心问题: {question}")

        # 从描述提取动词短语
        if description:
            for kw in keywords:
                pattern = rf'{kw}[\w\s，,、的于]{{0,30}}'
                matches = re.findall(pattern, description)
                for m in matches[:2]:
                    m = m.strip().rstrip('，。,.')
                    if len(m) > 5 and m not in goals:
                        goals.append(m)
                        if len(goals) >= 5:
                            break

        return goals[:5]

    def _highlight_keywords(self, text_widget, keywords):
        """在文本中高亮关键词"""
        if not keywords:
            return

        # 简单的关键词列表
        kws = [k.strip() for k in re.split(r'[,，；;、]', keywords) if k.strip()]
        content = text_widget.get(1.0, tk.END)

        # 使用tag标记高亮（这里简化处理）
        text_widget.tag_config("highlight", background="#FFF9C4")

    def _get_recent_notes(self, lesson_number):
        """获取最近的笔记记录"""
        entries = self.wflogger.get_entries() if self.wflogger else []
        notes = []
        for entry in reversed(entries[-50:]):
            if entry.get("type") == "note" and entry.get("lesson_number") == lesson_number:
                detail = entry.get("detail", "")
                if detail and len(detail) > 3:
                    ts = entry.get("timestamp", "")[:16]
                    notes.append(f"[{ts}] {detail[:50]}")
        return notes


class StatisticsVisualization:
    """统计可视化组件"""

    def __init__(self, parent, system, wflogger):
        self.parent = parent
        self.system = system
        self.wflogger = wflogger

    def create_dashboard(self):
        """创建统计仪表板"""
        for w in self.parent.winfo_children():
            w.destroy()

        # 创建标签页
        notebook = ttk.Notebook(self.parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: 学习进度总览
        progress_tab = ttk.Frame(notebook)
        notebook.add(progress_tab, text="📈 学习进度")
        self._create_progress_tab(progress_tab)

        # Tab 2: 时间分布
        time_tab = ttk.Frame(notebook)
        notebook.add(time_tab, text="⏰ 时间分布")
        self._create_time_distribution_tab(time_tab)

        # Tab 3: 知识点掌握度
        mastery_tab = ttk.Frame(notebook)
        notebook.add(mastery_tab, text="🎯 知识点掌握")
        self._create_mastery_tab(mastery_tab)

        # Tab 4: 详细统计
        detail_tab = ttk.Frame(notebook)
        notebook.add(detail_tab, text="📊 详细统计")
        self._create_detail_tab(detail_tab)

    def _create_progress_tab(self, parent):
        """学习进度Tab"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 标题
        ttk.Label(frame, text="各课程学习进度", font=("", 14, "bold")).pack(pady=10)

        # 饼图
        fig = Figure(figsize=(8, 4), dpi=100)
        ax = fig.add_subplot(111)

        courses_data = []
        labels = []
        colors = []

        for c in self.system.courses[:10]:
            cid = c.get("note_id", c.get("course_title", ""))
            pct = self.system.get_completion_pct(cid)
            done, total = self.system.get_course_progress(cid).get("completed_lessons", []), len(c.get("lessons", []))
            if total > 0:
                courses_data.append(pct)
                labels.append(c.get("course_title", "")[:15])
                domain = c.get("domain", "UNKNOWN")
                colors.append(DOMAIN_COLORS.get(domain, "#7f8c8d"))

        if courses_data:
            ax.barh(labels, courses_data, color=colors[:len(labels)])
            ax.set_xlim(0, 100)
            ax.set_xlabel("完成百分比 (%)")
            ax.set_title("课程完成进度", fontsize=12)
            for i, v in enumerate(courses_data):
                ax.text(v + 1, i, f"{v:.1f}%", va='center', fontsize=8)

        fig.tight_layout()
        canvas2 = FigureCanvasTkAgg(fig, master=frame)
        canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _create_time_distribution_tab(self, parent):
        """时间分布Tab"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(frame, text="学习时间分布", font=("", 14, "bold")).pack(pady=10)

        # 统计时间数据
        stats = self.wflogger.get_stats() if self.wflogger else {}
        lesson_times = stats.get("lesson_times", {})
        course_times = stats.get("course_times", {})

        # 图1: 各课程学习时间
        fig = Figure(figsize=(8, 4), dpi=100)
        ax = fig.add_subplot(111)

        if course_times:
            courses = []
            hours = []
            colors = []

            for cid, secs in sorted(course_times.items(), key=lambda x: -x[1])[:8]:
                course = self.system.get_course_by_id(cid)
                title = course.get("course_title", "")[:20] if course else cid[:20]
                courses.append(title)
                hours.append(secs / 3600)
                domain = course.get("domain", "UNKNOWN") if course else "UNKNOWN"
                colors.append(DOMAIN_COLORS.get(domain, "#7f8c8d"))

            if courses:
                ax.bar(courses, hours, color=colors)
                ax.set_ylabel("学习时间 (小时)")
                ax.set_title("各课程学习时间", fontsize=12)
                ax.tick_params(axis='x', rotation=45)
                for i, v in enumerate(hours):
                    ax.text(i, v + 0.1, f"{v:.1f}h", ha='center', fontsize=8)

        fig.tight_layout()
        canvas2 = FigureCanvasTkAgg(fig, master=frame)
        canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 图2: 每日学习时间趋势
        fig2 = Figure(figsize=(8, 3), dpi=100)
        ax2 = fig2.add_subplot(111)

        daily = stats.get("daily", {})
        if daily:
            days = []
            counts = []
            for day, count in sorted(daily.items())[-14:]:
                days.append(day[5:])
                counts.append(count)

            if days:
                ax2.plot(days, counts, marker='o', linewidth=2, color='#3498db')
                ax2.fill_between(days, counts, alpha=0.3)
                ax2.set_ylabel("活动次数")
                ax2.set_title("每日学习活动趋势 (近14天)", fontsize=12)
                ax2.tick_params(axis='x', rotation=45)

        fig2.tight_layout()
        canvas3 = FigureCanvasTkAgg(fig2, master=frame)
        canvas3.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _create_mastery_tab(self, parent):
        """知识点掌握度Tab"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(frame, text="知识点掌握度分析", font=("", 14, "bold")).pack(pady=10)

        # 按Section统计掌握度
        fig = Figure(figsize=(8, 5), dpi=100)
        ax = fig.add_subplot(111)

        sections_mastery = defaultdict(lambda: {"done": 0, "total": 0})

        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            completed = set(self.system.get_course_progress(cid).get("completed_lessons", []))
            sections = c.get("sections", [])
            lessons = c.get("lessons", [])

            for sec in sections:
                snum = sec.get("section_number", 0)
                stitle = sec.get("section_title", f"Section {snum}")
                lr = sec.get("lesson_range", "")

                sec_lessons = [l for l in lessons if l.get("section") == snum]
                if not sec_lessons and lr and "-" in str(lr):
                    try:
                        lo, hi = str(lr).split("-")
                        sec_lessons = [l for l in lessons if int(lo) <= l.get("lesson_number", 0) <= int(hi)]
                    except:
                        pass

                for l in sec_lessons:
                    sections_mastery[f"{stitle[:20]}"]["total"] += 1
                    if l.get("lesson_number", 0) in completed:
                        sections_mastery[f"{stitle[:20]}"]["done"] += 1

        if sections_mastery:
            titles = list(sections_mastery.keys())[:10]
            mastery_pcts = []
            colors = []

            for t in titles:
                d = sections_mastery[t]
                pct = (d["done"] / d["total"] * 100) if d["total"] > 0 else 0
                mastery_pcts.append(pct)
                if pct >= 80:
                    colors.append("#27ae60")
                elif pct >= 50:
                    colors.append("#f39c12")
                else:
                    colors.append("#e74c3c")

            y_pos = range(len(titles))
            bars = ax.barh(y_pos, mastery_pcts, color=colors)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(titles)
            ax.set_xlim(0, 100)
            ax.set_xlabel("掌握度 (%)")

            for i, (bar, pct) in enumerate(zip(bars, mastery_pcts)):
                ax.text(pct + 1, i, f"{pct:.0f}%", va='center', fontsize=9)

        fig.tight_layout()
        canvas2 = FigureCanvasTkAgg(fig, master=frame)
        canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _create_detail_tab(self, parent):
        """详细统计Tab"""
        canvas = tk.Canvas(parent, bg="white")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(frame, text="详细统计数据", font=("", 14, "bold")).pack(pady=10)

        stats = self.wflogger.get_stats() if self.wflogger else {}

        # 基本统计
        basic_frame = ttk.LabelFrame(frame, text="📊 基本统计", padding=10)
        basic_frame.pack(fill=tk.X, padx=15, pady=5)

        basic_stats = [
            ("日志条目总数", f"{stats.get('total_entries', 0)} 条"),
            ("专注学习时间", f"{stats.get('total_focus_time', 0) / 3600:.1f} 小时"),
            ("离开时间", f"{stats.get('total_blur_time', 0) / 3600:.1f} 小时"),
            ("完成课时数", f"{stats.get('complete_count', 0)} 个"),
            ("笔记记录数", f"{stats.get('note_count', 0)} 条"),
            ("离开次数", f"{stats.get('blur_count', 0)} 次"),
        ]

        for i, (label, value) in enumerate(basic_stats):
            row = ttk.Frame(basic_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}:", font=("", 10), width=20).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 10, "bold")).pack(side=tk.LEFT)

        # 动作统计
        action_frame = ttk.LabelFrame(frame, text="🎯 动作统计", padding=10)
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        action_counts = stats.get("action_counts", {})
        if action_counts:
            for action, count in sorted(action_counts.items(), key=lambda x: -x[1])[:15]:
                row = ttk.Frame(action_frame)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=f"  • {action}", font=("", 9), width=25).pack(side=tk.LEFT)
                ttk.Label(row, text=f"{count} 次", font=("", 9)).pack(side=tk.LEFT)
        else:
            ttk.Label(action_frame, text="暂无动作数据", foreground="#95a5a6").pack()

        # 学习效率
        efficiency_frame = ttk.LabelFrame(frame, text="📈 学习效率", padding=10)
        efficiency_frame.pack(fill=tk.X, padx=15, pady=5)

        total_focus = stats.get('total_focus_time', 0)
        complete_count = stats.get('complete_count', 0)
        efficiency = complete_count / (total_focus / 3600) if total_focus > 0 else 0

        efficiency_data = [
            ("总学习时长", f"{total_focus / 3600:.1f} 小时"),
            ("完成课时", f"{complete_count} 个"),
            ("平均每课时时长", f"{total_focus / complete_count / 60:.0f} 分钟" if complete_count > 0 else "N/A"),
            ("学习效率", f"{efficiency:.2f} 课时/小时"),
        ]

        for label, value in efficiency_data:
            row = ttk.Frame(efficiency_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}:", font=("", 10), width=20).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 10, "bold"), foreground="#27ae60").pack(side=tk.LEFT)


class EnhancedWorkflowLogger:
    """增强版工作流日志器"""

    # 增强的事件类型
    ENHANCED_EVENT_TYPES = {
        # 学习行为
        'start_lesson': '开始学习课时',
        'pause_lesson': '暂停学习',
        'resume_lesson': '继续学习',
        'complete_lesson': '完成课时',
        'skip_lesson': '跳过课时',

        # 笔记行为
        'open_note': '打开笔记',
        'create_note': '创建笔记',
        'edit_note': '编辑笔记',
        'quick_note': '快速笔记',

        # 资源行为
        'open_resource': '打开资源',
        'open_pdf': '打开PDF',
        'open_url': '打开链接',
        'add_resource': '添加资源',

        # 学习状态
        'focus': '专注学习',
        'blur': '窗口失焦',
        'focus_return': '回到学习',

        # 导航行为
        'view_course': '查看课程',
        'view_section': '查看章节',
        'view_lesson': '查看课时',
        'enter_exec_mode': '进入执行模式',
        'exit_exec_mode': '退出执行模式',

        # 评估行为
        'mark_done': '标记完成',
        'undo_done': '撤销完成',
        'reset_progress': '重置进度',

        # 笔记
        'note': '笔记记录',
    }

    # 学习状态分类
    LEARNING_STATES = {
        'focus': ['start_lesson', 'resume_lesson', 'focus'],
        'blur': ['pause_lesson', 'blur'],
        'complete': ['complete_lesson', 'mark_done'],
        'browse': ['open_note', 'open_resource', 'open_pdf', 'open_url', 'view_course', 'view_section', 'view_lesson'],
    }

    def __init__(self, base_logger):
        self.base = base_logger

        # 增强的数据收集
        self.state_durations = defaultdict(float)  # 各状态时长
        self.lesson_sessions = defaultdict(list)    # 每课时的学习会话
        self.resource_access = defaultdict(int)     # 资源访问次数
        self.note_words = 0                        # 笔记字数统计
        self.focus_streaks = []                    # 专注连续记录
        self._current_focus_start = None
        self._current_blur_start = None

    def log_enhanced(self, event_type, course_id=None, lesson_number=None, detail="", metadata=None):
        """增强版日志记录"""
        # 记录基础日志
        self.base.log_action(event_type, course_id, lesson_number, detail)

        # 收集增强数据
        if event_type == 'focus' and self._current_blur_start:
            # 从失焦恢复
            blur_duration = (datetime.now() - self._current_blur_start).total_seconds()
            self.state_durations['blur'] += blur_duration
            self._current_blur_start = None

        elif event_type == 'blur':
            self._current_blur_start = datetime.now()
            self.state_durations['blur'] += 0

        elif event_type in ['start_lesson', 'view_lesson', 'resume_lesson']:
            self._current_focus_start = datetime.now()

        elif event_type in ['complete_lesson', 'pause_lesson', 'blur']:
            if self._current_focus_start:
                focus_duration = (datetime.now() - self._current_focus_start).total_seconds()
                if focus_duration > 5:  # 只记录超过5秒的专注
                    self.state_durations['focus'] += focus_duration
                    self._current_focus_start = None

        # 资源访问统计
        if event_type in ['open_pdf', 'open_url', 'open_resource']:
            resource_key = f"{course_id}:{lesson_number}"
            self.resource_access[resource_key] += 1

        # 笔记字数统计
        if event_type in ['quick_note', 'edit_note', 'note']:
            if detail:
                self.note_words += len(detail)

        # 课时会话记录
        if event_type == 'start_lesson' and course_id and lesson_number:
            self.lesson_sessions[lesson_number].append({
                'start': datetime.now().isoformat(),
                'end': None,
                'duration': 0
            })

        elif event_type == 'complete_lesson' and lesson_number:
            sessions = self.lesson_sessions.get(lesson_number, [])
            if sessions and sessions[-1]['end'] is None:
                try:
                    start = datetime.fromisoformat(sessions[-1]['start'])
                    sessions[-1]['end'] = datetime.now().isoformat()
                    sessions[-1]['duration'] = (datetime.now() - start).total_seconds()
                except:
                    pass

    def get_enhanced_stats(self):
        """获取增强统计"""
        base_stats = self.base.get_stats()

        # 计算专注效率
        total_focus = self.state_durations.get('focus', 0)
        total_blur = self.state_durations.get('blur', 0)
        total_time = total_focus + total_blur
        focus_rate = (total_focus / total_time * 100) if total_time > 0 else 0

        # 计算平均课时时长
        lesson_durations = []
        for sessions in self.lesson_sessions.values():
            for s in sessions:
                if s.get('duration', 0) > 0:
                    lesson_durations.append(s['duration'])

        avg_lesson_duration = sum(lesson_durations) / len(lesson_durations) if lesson_durations else 0

        # 计算完成率
        total_focus_hours = total_focus / 3600
        complete_count = base_stats.get('complete_count', 0)
        efficiency = complete_count / total_focus_hours if total_focus_hours > 0 else 0

        return {
            **base_stats,
            'focus_rate': focus_rate,
            'avg_lesson_duration': avg_lesson_duration,
            'efficiency': efficiency,
            'total_lesson_sessions': sum(len(s) for s in self.lesson_sessions.values()),
            'resource_access_count': sum(self.resource_access.values()),
            'note_words': self.note_words,
            'state_durations': dict(self.state_durations),
            'top_resources': sorted(self.resource_access.items(), key=lambda x: -x[1])[:10],
        }

    def get_daily_report(self, date=None):
        """生成日报"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        entries = self.base.get_entries()
        day_entries = [e for e in entries if e.get('timestamp', '').startswith(date)]

        if not day_entries:
            return None

        # 统计当日数据
        day_stats = {
            'date': date,
            'total_entries': len(day_entries),
            'focus_time': 0,
            'blur_count': 0,
            'lessons_completed': 0,
            'notes_count': 0,
            'actions': defaultdict(int),
        }

        for entry in day_entries:
            etype = entry.get('type', '')
            if etype == 'blur':
                day_stats['blur_count'] += 1
            elif etype == 'lesson_complete':
                day_stats['lessons_completed'] += 1
            elif etype == 'note':
                day_stats['notes_count'] += 1
            elif etype == 'action':
                action = entry.get('action', '')
                day_stats['actions'][action] += 1

        return day_stats
