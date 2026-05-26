#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import threading
import uuid
import time
import json
import os
import logging

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

logger = logging.getLogger(__name__)

DAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}

# 时段分类
PERIOD_CATEGORIES = {
    "morning": (0, 4),      # 上午: 索引 0-3
    "lunch": (4, 5),        # 午休: 索引 4
    "afternoon": (5, 9),    # 下午: 索引 5-8
    "evening": (9, 10),     # 傍晚: 索引 9
    "night": (10, 12),      # 晚上: 索引 10-11
}

PERIODS = [
    # 早晨时段 (morning starts at index 0)
    ("早读", "06:00", "07:00"),
    ("早读", "07:00", "08:00"),
    ("第1节", "08:00", "08:45"),
    ("第2节", "08:55", "09:40"),
    ("第3节", "10:00", "10:45"),
    ("第4节", "10:55", "11:40"),
    # 午休时段 (lunch at index 5)
    ("午休", "11:40", "14:00"),
    ("第5节", "14:00", "14:45"),
    ("第6节", "14:55", "15:40"),
    ("第7节", "16:00", "16:45"),
    ("第8节", "16:55", "17:40"),
    # 傍晚时段 (evening at index 10)
    ("傍晚", "17:40", "19:00"),
    ("第9节", "19:00", "19:45"),
    ("第10节", "19:55", "20:40"),
    # 晚上时段 (night at index 13)
    ("晚自习", "20:50", "22:00"),
    ("夜间", "22:00", "23:00"),
]

COURSE_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]




@dataclass
class TimetableSlot:
    slot_id: str
    course_id: str
    course_name: str
    day_of_week: int
    start_time: str
    end_time: str
    location: str = ""
    teacher: str = ""
    period_idx: int = 0
    color: str = ""
    teacher_model_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "day_of_week": self.day_of_week,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "location": self.location,
            "teacher": self.teacher,
            "period_idx": self.period_idx,
            "color": self.color,
            "teacher_model_prompt": self.teacher_model_prompt,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimetableSlot":
        return cls(
            slot_id=d.get("slot_id", ""),
            course_id=d.get("course_id", ""),
            course_name=d.get("course_name", ""),
            day_of_week=d.get("day_of_week", 1),
            start_time=d.get("start_time", "08:00"),
            end_time=d.get("end_time", "08:45"),
            location=d.get("location", ""),
            teacher=d.get("teacher", ""),
            period_idx=d.get("period_idx", 0),
            color=d.get("color", ""),
            teacher_model_prompt=d.get("teacher_model_prompt"),
        )


@dataclass
class Timetable:
    timetable_id: str
    name: str
    semester_start: str
    semester_end: str
    slots: List[TimetableSlot]
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timetable_id": self.timetable_id,
            "name": self.name,
            "semester_start": self.semester_start,
            "semester_end": self.semester_end,
            "slots": [s.to_dict() for s in self.slots],
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Timetable":
        return cls(
            timetable_id=d.get("timetable_id", ""),
            name=d.get("name", ""),
            semester_start=d.get("semester_start", ""),
            semester_end=d.get("semester_end", ""),
            slots=[TimetableSlot.from_dict(s) for s in d.get("slots", [])],
            enabled=d.get("enabled", True),
        )


@dataclass
class CourseSession:
    session_id: str
    slot: TimetableSlot
    started_at: str
    status: str
    teacher_messages: List[Dict]
    student_questions: List[Dict]
    resources_opened: List[str]
    notes_taken: str


class TimetablePersistence:
    def __init__(self, db_dir: str = None):
        if db_dir is None:
            db_dir = os.path.join(os.path.expanduser("~"), ".ts2")
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, "timetables.json")
        self._lock = threading.RLock()

    def save(self, timetables: Dict[str, Timetable]):
        with self._lock:
            data = {}
            for tid, tt in timetables.items():
                data[tid] = tt.to_dict()
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> Dict[str, Timetable]:
        with self._lock:
            if not os.path.exists(self.db_path):
                return {}
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {tid: Timetable.from_dict(d) for tid, d in data.items()}
            except Exception:
                logger.debug("Failed to load timetables", exc_info=True)
                return {}


class CourseSimulationEngine:
    def __init__(self, root: Optional[tk.Tk] = None, agent=None, llm=None, ws2_system=None):
        self._lock = threading.RLock()
        self._root = root
        self._timetables: Dict[str, Timetable] = {}
        self._current_session: Optional[CourseSession] = None
        self._locked_windows: List[tk.Toplevel] = []
        self._teacher_window: Optional[tk.Toplevel] = None
        self._course_prompt_window: Optional[tk.Toplevel] = None
        self._check_timer: Optional[str] = None
        self._running = False
        self._popup_manager = None
        self._course_tracker = None
        self._teacher_chat_widget = None
        self._teacher_input_widget = None
        self._teacher_messages_var: Optional[tk.StringVar] = None
        self._elapsed_var: Optional[tk.StringVar] = None
        self._elapsed_start: Optional[float] = None
        self._elapsed_timer_id: Optional[str] = None
        self._persistence = TimetablePersistence()
        self._load_timetables()
        self._agent = agent
        self._llm = llm
        self._ws2_system = ws2_system  # WS2系统引用

    def _load_timetables(self):
        loaded = self._persistence.load()
        if loaded:
            self._timetables = loaded
        else:
            self._create_empty_timetable()

    def _create_empty_timetable(self):
        tt = Timetable(
            timetable_id=f"tt_default",
            name="课程系统",
            semester_start="",
            semester_end="",
            slots=[],
            enabled=True,
        )
        self._timetables[tt.timetable_id] = tt
        self._persistence.save(self._timetables)

    def _save_timetables(self):
        self._persistence.save(self._timetables)

    def set_root(self, root: tk.Tk):
        with self._lock:
            self._root = root

    def set_popup_manager(self, popup_manager):
        with self._lock:
            self._popup_manager = popup_manager

    def set_course_tracker(self, course_tracker):
        with self._lock:
            self._course_tracker = course_tracker

    def set_ws2_system(self, ws2_system):
        """设置WS2系统引用"""
        with self._lock:
            self._ws2_system = ws2_system

    def set_agent(self, agent):
        with self._lock:
            self._agent = agent

    def set_llm(self, llm):
        with self._lock:
            self._llm = llm

    def add_timetable(self, timetable: Timetable) -> str:
        with self._lock:
            if not timetable.timetable_id:
                timetable.timetable_id = str(uuid.uuid4())
            self._timetables[timetable.timetable_id] = timetable
            self._save_timetables()
            logger.info("Added timetable: %s (%s)", timetable.name, timetable.timetable_id)
            return timetable.timetable_id

    def add_slot(self, timetable_id: str, slot: TimetableSlot) -> bool:
        with self._lock:
            tt = self._timetables.get(timetable_id)
            if not tt:
                return False
            if not slot.slot_id:
                slot.slot_id = str(uuid.uuid4())
            if not slot.color:
                existing_colors = {s.color for s in tt.slots if s.color}
                for c in COURSE_COLORS:
                    if c not in existing_colors:
                        slot.color = c
                        break
                if not slot.color:
                    slot.color = COURSE_COLORS[len(tt.slots) % len(COURSE_COLORS)]
            tt.slots.append(slot)
            self._save_timetables()
            return True

    def remove_slot(self, timetable_id: str, slot_id: str) -> bool:
        with self._lock:
            tt = self._timetables.get(timetable_id)
            if not tt:
                return False
            tt.slots = [s for s in tt.slots if s.slot_id != slot_id]
            self._save_timetables()
            return True

    def remove_timetable(self, timetable_id: str) -> bool:
        with self._lock:
            if timetable_id in self._timetables:
                del self._timetables[timetable_id]
                self._save_timetables()
                return True
            return False

    def get_active_timetable(self) -> Optional[Timetable]:
        with self._lock:
            for tt in self._timetables.values():
                if tt.enabled:
                    return tt
            if self._timetables:
                return next(iter(self._timetables.values()))
            return None

    def get_slot_at(self, day: int, period_idx: int) -> Optional[TimetableSlot]:
        with self._lock:
            tt = self.get_active_timetable()
            if not tt:
                return None
            for slot in tt.slots:
                if slot.day_of_week == day and slot.period_idx == period_idx:
                    return slot
            return None

    def get_week_slots(self) -> Dict[str, TimetableSlot]:
        with self._lock:
            result = {}
            tt = self.get_active_timetable()
            if not tt:
                return result
            for slot in tt.slots:
                key = f"{slot.day_of_week}_{slot.period_idx}"
                result[key] = slot
            return result

    def get_current_slot(self) -> Optional[TimetableSlot]:
        with self._lock:
            now = datetime.now()
            current_dow = now.isoweekday()
            current_minutes = self._time_to_minutes(now.strftime("%H:%M"))

            for tt in self._timetables.values():
                if not tt.enabled:
                    continue
                try:
                    sem_start = datetime.strptime(tt.semester_start, "%Y-%m-%d")
                    sem_end = datetime.strptime(tt.semester_end, "%Y-%m-%d")
                    if now.date() < sem_start.date() or now.date() > sem_end.date():
                        continue
                except ValueError:
                    continue

                for slot in tt.slots:
                    if slot.day_of_week != current_dow:
                        continue
                    start_min = self._time_to_minutes(slot.start_time)
                    end_min = self._time_to_minutes(slot.end_time)
                    if start_min <= current_minutes < end_min:
                        return slot
            return None

    def get_next_slot(self) -> Optional[TimetableSlot]:
        with self._lock:
            now = datetime.now()
            current_dow = now.isoweekday()
            current_minutes = self._time_to_minutes(now.strftime("%H:%M"))

            best_slot = None
            best_diff = float("inf")

            for tt in self._timetables.values():
                if not tt.enabled:
                    continue
                for slot in tt.slots:
                    if slot.day_of_week < current_dow:
                        continue
                    start_min = self._time_to_minutes(slot.start_time)
                    if slot.day_of_week == current_dow and start_min <= current_minutes:
                        continue
                    diff = (slot.day_of_week - current_dow) * 1440 + (start_min - current_minutes)
                    if diff < best_diff:
                        best_diff = diff
                        best_slot = slot
            return best_slot

    def get_remaining_time(self) -> Optional[int]:
        slot = self.get_current_slot()
        if not slot:
            return None
        now = datetime.now()
        end_min = self._time_to_minutes(slot.end_time)
        current_min = self._time_to_minutes(now.strftime("%H:%M"))
        remaining = end_min - current_min
        return max(0, remaining)

    def get_week_number(self) -> int:
        """计算当前是第几周"""
        tt = self.get_active_timetable()
        if not tt or not tt.semester_start:
            return 1
        
        try:
            sem_start = datetime.strptime(tt.semester_start, "%Y-%m-%d")
            now = datetime.now()
            
            # 如果当前日期在学期开始之前，返回第1周
            if now < sem_start:
                return 1
            
            # 计算周数差异
            days_diff = (now - sem_start).days
            week_num = (days_diff // 7) + 1
            
            # 确保不返回负数
            return max(1, week_num)
        except (ValueError, Exception):
            return 1
    
    def get_date_for_weekday(self, day_of_week: int) -> str:
        """获取指定星期几的日期 (格式: mm-dd)"""
        now = datetime.now()
        current_dow = now.isoweekday()
        # 计算与今天的天数差异
        days_diff = day_of_week - current_dow
        target_date = now + timedelta(days=days_diff)
        return target_date.strftime("%m-%d")
    
    def get_date_range_for_week(self) -> Dict[str, str]:
        """获取本周的日期范围"""
        now = datetime.now()
        current_dow = now.isoweekday()
        start_date = now - timedelta(days=current_dow - 1)
        end_date = start_date + timedelta(days=6)
        return {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "start_md": start_date.strftime("%m-%d"),
            "end_md": end_date.strftime("%m-%d"),
        }
    
    def get_current_period_index(self) -> Optional[int]:
        """获取当前时段的索引"""
        now = datetime.now()
        current_minutes = self._time_to_minutes(now.strftime("%H:%M"))
        
        for idx, (_, p_start, p_end) in enumerate(PERIODS):
            start_min = self._time_to_minutes(p_start)
            end_min = self._time_to_minutes(p_end)
            if start_min <= current_minutes < end_min:
                return idx
        return None

    def enter_course_mode(self, slot: TimetableSlot) -> None:
        with self._lock:
            if self._current_session is not None:
                logger.warning("Already in course mode, exiting previous first")
                self._exit_course_mode_unlocked()
            
            # 先关闭前一节的课程提示窗口（如果存在）
            self._close_popup_windows()

            self._play_notification_sound()
            self._show_course_alert(slot)
            self._lock_other_windows()
            self._open_teacher_window(slot)
            self._open_course_prompt_window(slot)
            # 不复用工具面板，让 course_tracker 自行管理辅助工具

            session = CourseSession(
                session_id=str(uuid.uuid4()),
                slot=slot,
                started_at=datetime.now().isoformat(),
                status="active",
                teacher_messages=[],
                student_questions=[],
                resources_opened=[],
                notes_taken="",
            )
            self._current_session = session
            self._elapsed_start = time.time()
            self._update_elapsed_time()
            logger.info("Entered course mode: %s (%s)", slot.course_name, slot.slot_id)

    def exit_course_mode(self) -> None:
        with self._lock:
            self._exit_course_mode_unlocked()

    def _exit_course_mode_unlocked(self) -> None:
        if self._current_session is None:
            return

        self._current_session.status = "ended"

        if self._course_tracker is not None:
            try:
                self._course_tracker.save_session_record(self._current_session)
            except Exception as e:
                logger.error("Failed to save session record: %s", e)

        # 只关闭教师窗口，不关闭课程提示窗口
        # 课程提示窗口在新课程开始时会自动关闭
        self._close_teacher_window()
        self._unlock_windows()

        if self._check_timer is not None and self._root is not None:
            try:
                self._root.after_cancel(self._check_timer)
            except Exception:
                pass
            self._check_timer = None

        if self._elapsed_timer_id is not None and self._root is not None:
            try:
                self._root.after_cancel(self._elapsed_timer_id)
            except Exception:
                pass
            self._elapsed_timer_id = None

        logger.info("Exited course mode: %s", self._current_session.slot.course_name)
        self._current_session = None
        self._elapsed_start = None

    def check_and_trigger(self) -> None:
        with self._lock:
            if self._current_session is not None:
                slot = self._current_session.slot
                now = datetime.now()
                current_minutes = self._time_to_minutes(now.strftime("%H:%M"))
                end_min = self._time_to_minutes(slot.end_time)
                if current_minutes >= end_min:
                    self._exit_course_mode_unlocked()
                return

            current_slot = self.get_current_slot()
            if current_slot is not None:
                self._exit_course_mode_unlocked()
                self.enter_course_mode(current_slot)

    def start_periodic_check(self, interval_ms: int = 60000) -> None:
        with self._lock:
            self._running = True
            self._schedule_check(interval_ms)

    def stop_periodic_check(self) -> None:
        with self._lock:
            self._running = False
            if self._check_timer is not None and self._root is not None:
                try:
                    self._root.after_cancel(self._check_timer)
                except Exception:
                    pass
                self._check_timer = None

    def _schedule_check(self, interval_ms: int) -> None:
        if not self._running or self._root is None:
            return
        self.check_and_trigger()
        self._check_timer = self._root.after(interval_ms, self._schedule_check, interval_ms)

    def _play_notification_sound(self) -> None:
        try:
            if HAS_WINSOUND:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                if self._root is not None:
                    self._root.bell()
        except Exception:
            pass

    def _show_course_alert(self, slot: TimetableSlot) -> None:
        if self._root is None:
            return
        day_name = DAY_NAMES.get(slot.day_of_week, "未知")
        msg = (
            f"课程即将开始！\n\n"
            f"课程：{slot.course_name}\n"
            f"时间：{day_name} {slot.start_time}-{slot.end_time}\n"
            f"地点：{slot.location or '未指定'}\n"
            f"教师：{slot.teacher or '未指定'}\n\n"
            f"点击确定后将进入课程模式..."
        )
        # 使用自定义对话框，不影响教师窗口
        def show_alert():
            result = messagebox.showinfo("课程提醒", msg, parent=self._root)
            # 不在这里做任何操作，由enter_course_mode继续执行
        
        self._root.after(0, show_alert)

    def _lock_other_windows(self) -> None:
        if self._root is None:
            return
        try:
            for child in self._root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    if child not in [self._teacher_window, self._course_prompt_window, self._tool_panel]:
                        try:
                            child.attributes("-disabled", True)
                            self._locked_windows.append(child)
                        except Exception:
                            pass
        except Exception:
            pass

    def _unlock_windows(self) -> None:
        for win in self._locked_windows:
            try:
                if win.winfo_exists():
                    win.attributes("-disabled", False)
            except Exception:
                pass
        self._locked_windows.clear()

    def _open_teacher_window(self, slot: TimetableSlot) -> None:
        if self._root is None:
            return

        # 注册课程系统工具到Agent
        if self._agent:
            try:
                from .course_tools import register_course_tools
                register_course_tools(
                    self._agent, 
                    course_sim_engine=self,
                    ws2_system=self._ws2_system,
                    course_tracker=self._course_tracker
                )
            except Exception as e:
                logger.warning(f"注册课程系统工具失败: {e}")

        self._teacher_window = tk.Toplevel(self._root)
        self._teacher_window.title(f"教师模型 - {slot.course_name}")
        
        screen_w = self._teacher_window.winfo_screenwidth()
        screen_h = self._teacher_window.winfo_screenheight()
        x = (screen_w - 750) // 2
        y = (screen_h - 650) // 2
        self._teacher_window.geometry(f"750x650+{x}+{y}")
        
        self._teacher_window.attributes("-topmost", True)
        self._teacher_window.protocol("WM_DELETE_WINDOW", self._on_teacher_close)

        main_frame = ttk.Frame(self._teacher_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 课程信息面板
        course_info_frame = ttk.LabelFrame(main_frame, text="📚 课程信息", padding=8)
        course_info_frame.pack(fill=tk.X, pady=(0, 5))
        
        info_left = ttk.Frame(course_info_frame)
        info_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tt = self.get_active_timetable()
        week_num = self.get_week_number()
        
        ttk.Label(info_left, text=f"课程名称: {slot.course_name}", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        ttk.Label(info_left, text=f"时间: {slot.start_time} - {slot.end_time}", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        if slot.location:
            ttk.Label(info_left, text=f"地点: {slot.location}", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        if slot.teacher:
            ttk.Label(info_left, text=f"教师: {slot.teacher}", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W)
        
        info_right = ttk.Frame(course_info_frame)
        info_right.pack(side=tk.RIGHT)
        ttk.Label(info_right, text=f"第 {week_num} 周", font=("Microsoft YaHei UI", 10, "bold")).pack()

        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))

        title_label = ttk.Label(
            header_frame,
            text=f"👨‍🏫 教师模型 - {slot.course_name}",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        title_label.pack(side=tk.LEFT)

        self._teacher_topmost_var = tk.BooleanVar(value=True)
        self._teacher_topmost_btn = tk.Checkbutton(
            header_frame, text="📌", variable=self._teacher_topmost_var,
            background="#f0f0f0", selectcolor="#d0d0d0",
            indicatoron=False, relief=tk.FLAT,
            command=self._toggle_teacher_topmost
        )
        self._teacher_topmost_btn.pack(side=tk.LEFT, padx=(5, 0))

        self._elapsed_var = tk.StringVar(value="已学习: 00:00:00")
        ttk.Label(
            header_frame,
            textvariable=self._elapsed_var,
            font=("Microsoft YaHei UI", 10),
            foreground="#0066cc",
        ).pack(side=tk.RIGHT)

        chat_frame = ttk.Frame(main_frame)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self._teacher_chat_widget = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            state=tk.DISABLED,
            background="#f9f9f9",
        )
        chat_scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self._teacher_chat_widget.yview)
        self._teacher_chat_widget.configure(yscrollcommand=chat_scrollbar.set)
        self._teacher_chat_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(5, 0))

        self._teacher_input_widget = ttk.Entry(input_frame, font=("Microsoft YaHei UI", 10))
        self._teacher_input_widget.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._teacher_input_widget.bind("<Return>", self._on_teacher_send)

        ttk.Button(input_frame, text="发送", command=self._on_teacher_send_btn).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(btn_frame, text="⏸ 暂停", command=self._on_pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📝 笔记", command=self._on_notes).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⏹ 结束课程", command=self._on_end_course).pack(side=tk.RIGHT, padx=2)

        system_prompt = slot.teacher_model_prompt or f"你是一位{slot.course_name}课程教师，请耐心解答学生的问题，提供专业、清晰的讲解。"
        self._append_teacher_message("系统", f"教师模型已启动，课程：{slot.course_name}")
        self._append_teacher_message("系统", f"System Prompt: {system_prompt}")
        self._append_teacher_message("系统", "你现在可以使用课程系统工具来查询课程信息、获取笔记、查看课程表等。可用工具包括：get_current_course_slot、get_week_timetable、get_next_course、get_current_week_info、get_course_detail、get_lesson_notes。")

    def _open_course_prompt_window(self, slot: TimetableSlot) -> None:
        if self._root is None:
            return

        self._course_prompt_window = tk.Toplevel(self._root)
        self._course_prompt_window.title(f"课程提示 - {slot.course_name}")
        
        screen_w = self._course_prompt_window.winfo_screenwidth()
        screen_h = self._course_prompt_window.winfo_screenheight()
        x = (screen_w - 400) // 2
        y = (screen_h - 500) // 2
        self._course_prompt_window.geometry(f"400x500+{x}+{y}")
        
        self._course_prompt_window.attributes("-topmost", True)
        self._course_prompt_window.protocol("WM_DELETE_WINDOW", lambda: None)
        
        if self._teacher_window is not None and self._teacher_window.winfo_exists():
            self._teacher_window.lift()

        main_frame = ttk.Frame(self._course_prompt_window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = ttk.Label(
            header_frame,
            text=slot.course_name,
            font=("Microsoft YaHei UI", 14, "bold"),
            foreground="#0066cc",
        )
        title_label.pack(side=tk.LEFT)

        self._course_topmost_var = tk.BooleanVar(value=True)
        self._course_topmost_btn = tk.Checkbutton(
            header_frame, text="📌", variable=self._course_topmost_var,
            background="#f0f0f0", selectcolor="#d0d0d0",
            indicatoron=False, relief=tk.FLAT,
            command=self._toggle_course_topmost
        )
        self._course_topmost_btn.pack(side=tk.LEFT, padx=(5, 0))

        info_frame = ttk.LabelFrame(main_frame, text="课程信息", padding=8)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        day_name = DAY_NAMES.get(slot.day_of_week, "未知")
        ttk.Label(info_frame, text=f"⏰ 时间：{day_name} {slot.start_time} - {slot.end_time}", font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=1)
        ttk.Label(info_frame, text=f"📍 地点：{slot.location or '未指定'}", font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=1)
        if slot.teacher:
            ttk.Label(info_frame, text=f"👨‍🏫 教师：{slot.teacher}", font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W, pady=1)

        content_frame = ttk.LabelFrame(main_frame, text="本节内容", padding=8)
        content_frame.pack(fill=tk.X, pady=(0, 10))

        content_text = self._get_current_course_content(slot)
        content_label = ttk.Label(content_frame, text=content_text, font=("Microsoft YaHei UI", 10), wraplength=350, justify=tk.LEFT)
        content_label.pack(anchor=tk.W)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        ttk.Button(btn_frame, text="✅ 进入课程模式", command=self._on_enter_course).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="⏭ 跳过", command=self._on_skip_course).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)



    def _append_teacher_message(self, role: str, content: str) -> None:
        if self._teacher_chat_widget is None:
            return
        try:
            self._teacher_chat_widget.configure(state=tk.NORMAL)
            self._teacher_chat_widget.insert(tk.END, f"[{role}] {content}\n\n")
            self._teacher_chat_widget.configure(state=tk.DISABLED)
            self._teacher_chat_widget.see(tk.END)
        except Exception:
            pass

    def _update_elapsed_time(self) -> None:
        if self._elapsed_start is None or self._root is None:
            return
        elapsed = int(time.time() - self._elapsed_start)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        if self._elapsed_var is not None:
            self._elapsed_var.set(f"已学习: {hours:02d}:{minutes:02d}:{seconds:02d}")
        self._elapsed_timer_id = self._root.after(1000, self._update_elapsed_time)

    def _on_teacher_send(self, event=None) -> None:
        self._on_teacher_send_btn()

    def _on_teacher_send_btn(self) -> None:
        if self._teacher_input_widget is None:
            return
        text = self._teacher_input_widget.get().strip()
        if not text:
            return
        self._teacher_input_widget.delete(0, tk.END)

        with self._lock:
            if self._current_session is not None:
                self._current_session.student_questions.append({
                    "role": "student",
                    "content": text,
                    "timestamp": datetime.now().isoformat(),
                })

        self._append_teacher_message("学生", text)
        self._simulate_teacher_response(text)

    def _simulate_teacher_response(self, question: str) -> None:
        if self._current_session is None:
            return
        course_name = self._current_session.slot.course_name
        
        # 尝试使用真实的 Agent/LLM 响应
        if self._agent is not None or self._llm is not None:
            try:
                system_prompt = self._current_session.slot.teacher_model_prompt or f"你是一位{course_name}课程教师，请耐心解答学生的问题，提供专业、清晰的讲解。"
                
                if self._llm is not None:
                    # 使用 LLM 调用
                    response = self._llm.generate(f"{system_prompt}\n\n学生问题：{question}")
                elif self._agent is not None and hasattr(self._agent, 'process'):
                    # 使用 Agent 处理
                    response = self._agent.process(f"{system_prompt}\n\n学生问题：{question}")
                else:
                    # 默认模拟响应
                    response = f'关于\u201c{question}\u201d，这是{course_name}课程的一个重要问题。让我为您详细解答...'
            except Exception as e:
                logger.error(f"Failed to get real teacher response: {e}")
                response = f'关于\u201c{question}\u201d，这是{course_name}课程的一个重要问题。让我为您详细解答...'
        else:
            # 模拟响应（兼容旧代码）
            response = f'关于\u201c{question}\u201d，这是{course_name}课程的一个重要问题。让我为您详细解答...'

        with self._lock:
            if self._current_session is not None:
                self._current_session.teacher_messages.append({
                    "role": "teacher",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                })

        self._append_teacher_message("教师", response)

    def _toggle_teacher_topmost(self) -> None:
        if self._teacher_window is not None and self._teacher_window.winfo_exists():
            self._teacher_window.attributes("-topmost", self._teacher_topmost_var.get())

    def _toggle_course_topmost(self) -> None:
        if self._course_prompt_window is not None and self._course_prompt_window.winfo_exists():
            self._course_prompt_window.attributes("-topmost", self._course_topmost_var.get())

    def _on_teacher_close(self) -> None:
        if self._teacher_window is not None:
            try:
                if self._teacher_window.winfo_exists():
                    self._teacher_window.destroy()
            except Exception:
                pass
            self._teacher_window = None
            self._teacher_chat_widget = None
            self._teacher_input_widget = None

    def _on_pause(self) -> None:
        with self._lock:
            if self._current_session is not None:
                if self._current_session.status == "active":
                    self._current_session.status = "paused"
                    self._append_teacher_message("系统", "课程已暂停")
                    if self._elapsed_timer_id is not None and self._root is not None:
                        try:
                            self._root.after_cancel(self._elapsed_timer_id)
                        except Exception:
                            pass
                        self._elapsed_timer_id = None
                elif self._current_session.status == "paused":
                    self._current_session.status = "active"
                    self._append_teacher_message("系统", "课程已恢复")
                    self._update_elapsed_time()

    def _on_notes(self) -> None:
        self._open_notepad()

    def _on_end_course(self) -> None:
        if messagebox.askyesno("确认", "确定要结束当前课程吗？"):
            self.exit_course_mode()

    def _on_enter_course(self) -> None:
        if self._course_prompt_window is not None:
            try:
                self._course_prompt_window.destroy()
            except Exception:
                pass
            self._course_prompt_window = None

    def _on_skip_course(self) -> None:
        self.exit_course_mode()

    def _close_popup_windows(self) -> None:
        # 只关闭课程提示窗口，不关闭教师窗口
        # 教师窗口由 _exit_course_mode 时单独关闭
        win_attr = "_course_prompt_window"
        win = getattr(self, win_attr, None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            setattr(self, win_attr, None)

    def _close_teacher_window(self) -> None:
        # 专门关闭教师窗口的方法
        win_attr = "_teacher_window"
        win = getattr(self, win_attr, None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            setattr(self, win_attr, None)
        
        self._teacher_chat_widget = None
        self._teacher_input_widget = None

    def _get_current_course_content(self, slot: TimetableSlot) -> str:
        if self._course_tracker is not None:
            try:
                info = self._course_tracker.get_current_section(slot.course_id)
                if info:
                    return info
            except Exception:
                pass
        return f"{slot.course_name} - 本节课内容待更新"

    def _get_recommended_resources(self, slot: TimetableSlot) -> List[str]:
        resources = [f"{slot.course_name} 教材相关章节"]
        if slot.teacher_model_prompt:
            resources.append("教师推荐补充材料")
        if self._course_tracker is not None:
            try:
                extra = self._course_tracker.get_recommended_resources(slot.course_id)
                if extra:
                    resources.extend(extra)
            except Exception:
                pass
        return resources



    def _open_notepad(self) -> None:
        if self._root is None:
            return
        note_win = tk.Toplevel(self._root)
        note_win.title("笔记本")
        note_win.geometry("500x400")

        frame = ttk.Frame(note_win, padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(frame, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(note_win)
        btn_frame.pack(fill=tk.X, padx=5, pady=3)

        def _save_note():
            content = text_widget.get("1.0", tk.END).strip()
            with self._lock:
                if self._current_session is not None:
                    self._current_session.notes_taken = content

        ttk.Button(btn_frame, text="💾 保存到课程笔记", command=_save_note).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 清空", command=lambda: text_widget.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2)



    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        try:
            parts = time_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return -1

    @property
    def current_session(self) -> Optional[CourseSession]:
        with self._lock:
            return self._current_session

    @property
    def active_session(self) -> Optional[CourseSession]:
        with self._lock:
            return self._current_session

    @property
    def timetables(self) -> Dict[str, Timetable]:
        with self._lock:
            return dict(self._timetables)

    @property
    def is_in_course_mode(self) -> bool:
        with self._lock:
            return self._current_session is not None
