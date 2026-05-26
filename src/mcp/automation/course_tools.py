#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课程系统专用工具集
让教师模型可以直接调用课程系统的所有功能
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class CourseSystemBaseTool(Tool):
    """课程系统工具基类"""
    
    def __init__(self, course_sim_engine=None, ws2_system=None, course_tracker=None):
        self.course_sim_engine = course_sim_engine
        self.ws2_system = ws2_system
        self.course_tracker = course_tracker
    
    def set_engine(self, course_sim_engine=None, ws2_system=None, course_tracker=None):
        """设置课程引擎和WS2系统"""
        if course_sim_engine is not None:
            self.course_sim_engine = course_sim_engine
        if ws2_system is not None:
            self.ws2_system = ws2_system
        if course_tracker is not None:
            self.course_tracker = course_tracker
    
    def _check_engine(self) -> Optional[str]:
        """检查课程引擎是否初始化"""
        if not self.course_sim_engine:
            return "课程系统未初始化"
        return None
    
    def _make_result(self, success: bool, data: dict, message: str = "",
                     error: str = "", **kwargs) -> str:
        """快速构造 ToolResult JSON 字符串"""
        tr = ToolResult(success=success, data=data, message=message,
                        error=error, **kwargs)
        return tr.to_json()


class GetCurrentSlotTool(CourseSystemBaseTool):
    """获取当前课程插槽信息"""
    
    def name(self) -> str:
        return "get_current_course_slot"
    
    def description(self) -> str:
        return "获取当前正在进行的课程信息"
    
    def execute(self, **kwargs) -> str:
        err = self._check_engine()
        if err:
            return self._make_result(False, {}, error=err)
        
        try:
            slot = self.course_sim_engine.get_current_slot()
            if not slot:
                return self._make_result(False, {}, message="当前没有课程")
            
            slot_dict = {
                "course_id": slot.course_id,
                "course_name": slot.course_name,
                "teacher": slot.teacher,
                "location": slot.location,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "day_of_week": slot.day_of_week
            }
            
            return self._make_result(
                True, 
                slot_dict,
                message=f"当前课程: {slot.course_name}"
            )
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetWeekTimetableTool(CourseSystemBaseTool):
    """获取本周课程表"""
    
    def name(self) -> str:
        return "get_week_timetable"
    
    def description(self) -> str:
        return "获取本周完整的课程表信息"
    
    def execute(self, **kwargs) -> str:
        err = self._check_engine()
        if err:
            return self._make_result(False, {}, error=err)
        
        try:
            week_slots = self.course_sim_engine.get_week_slots()
            current_week = self.course_sim_engine.get_week_number()
            
            slots_list = []
            for key, slot in week_slots.items():
                slots_list.append({
                    "key": key,
                    "course_id": slot.course_id,
                    "course_name": slot.course_name,
                    "teacher": slot.teacher,
                    "location": slot.location,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "day_of_week": slot.day_of_week
                })
            
            return self._make_result(
                True,
                {"week_number": current_week, "slots": slots_list},
                message=f"第 {current_week} 周课程表"
            )
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetNextCourseTool(CourseSystemBaseTool):
    """获取下一节课信息"""
    
    def name(self) -> str:
        return "get_next_course"
    
    def description(self) -> str:
        return "获取即将开始的下一节课信息"
    
    def execute(self, **kwargs) -> str:
        err = self._check_engine()
        if err:
            return self._make_result(False, {}, error=err)
        
        try:
            now = datetime.now()
            week_slots = self.course_sim_engine.get_week_slots()
            
            current_min = now.hour * 60 + now.minute
            next_slot = None
            min_diff = float('inf')
            
            current_dow = now.isoweekday()
            
            for key, slot in week_slots.items():
                if slot.day_of_week != current_dow:
                    continue
                
                start_h, start_m = map(int, slot.start_time.split(':'))
                start_min = start_h * 60 + start_m
                
                if start_min > current_min and (start_min - current_min) < min_diff:
                    min_diff = start_min - current_min
                    next_slot = slot
            
            if next_slot:
                return self._make_result(
                    True,
                    {
                        "course_name": next_slot.course_name,
                        "start_time": next_slot.start_time,
                        "end_time": next_slot.end_time,
                        "location": next_slot.location,
                        "minutes_left": min_diff
                    },
                    message=f"下一节课: {next_slot.course_name} ({min_diff}分钟后)"
                )
            else:
                return self._make_result(False, {}, message="今天没有下一节课了")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCurrentWeekInfoTool(CourseSystemBaseTool):
    """获取当前周详细信息"""
    
    def name(self) -> str:
        return "get_current_week_info"
    
    def description(self) -> str:
        return "获取当前周信息，包括周数、日期范围等"
    
    def execute(self, **kwargs) -> str:
        err = self._check_engine()
        if err:
            return self._make_result(False, {}, error=err)
        
        try:
            week_num = self.course_sim_engine.get_week_number()
            date_range = self.course_sim_engine.get_date_range_for_week()
            now = datetime.now()
            current_dow = now.isoweekday()
            
            from .course_simulation import DAY_NAMES
            
            return self._make_result(
                True,
                {
                    "week_number": week_num,
                    "date_start": date_range.get("start"),
                    "date_end": date_range.get("end"),
                    "date_start_short": date_range.get("start_md"),
                    "date_end_short": date_range.get("end_md"),
                    "today_weekday": current_dow,
                    "today_weekday_name": DAY_NAMES.get(current_dow, "")
                },
                message=f"当前第 {week_num} 周"
            )
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCourseDetailTool(CourseSystemBaseTool):
    """获取课程详细信息"""
    
    def name(self) -> str:
        return "get_course_detail"
    
    def description(self) -> str:
        return "获取指定课程的详细信息"
    
    def execute(self, course_id: str = None, **kwargs) -> str:
        err = self._check_engine()
        if err:
            return self._make_result(False, {}, error=err)
        
        if not course_id:
            return self._make_result(False, {}, error="请提供课程ID")
        
        try:
            if self.course_tracker and hasattr(self.course_tracker, 'get_course_info'):
                course_info = self.course_tracker.get_course_info(course_id)
                if course_info:
                    return self._make_result(True, course_info, message=f"课程: {course_id}")
            
            return self._make_result(False, {}, message="课程信息未找到")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetLessonNotesTool(CourseSystemBaseTool):
    """获取课程笔记"""
    
    def name(self) -> str:
        return "get_lesson_notes"
    
    def description(self) -> str:
        return "获取当前课程的笔记内容"
    
    def execute(self, **kwargs) -> str:
        try:
            if self.ws2_system and hasattr(self.ws2_system, 'get_or_create_note'):
                slot = self.course_sim_engine.get_current_slot() if self.course_sim_engine else None
                if slot:
                    note_path, created = self.ws2_system.get_or_create_note(
                        slot.course_id, 
                        slot.lesson_number if hasattr(slot, 'lesson_number') else None
                    )
                    if note_path and Path(note_path).exists():
                        with open(note_path, 'r', encoding='utf-8') as f:
                            note_content = f.read()
                        return self._make_result(
                            True,
                            {
                                "course_id": slot.course_id,
                                "note_content": note_content
                            },
                            message="笔记加载成功"
                        )
            
            return self._make_result(False, {}, message="没有找到笔记")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


def register_course_tools(agent, course_sim_engine=None, ws2_system=None, course_tracker=None):
    """注册课程系统工具到 Agent"""
    tools = [
        GetCurrentSlotTool(course_sim_engine, ws2_system, course_tracker),
        GetWeekTimetableTool(course_sim_engine, ws2_system, course_tracker),
        GetNextCourseTool(course_sim_engine, ws2_system, course_tracker),
        GetCurrentWeekInfoTool(course_sim_engine, ws2_system, course_tracker),
        GetCourseDetailTool(course_sim_engine, ws2_system, course_tracker),
        GetLessonNotesTool(course_sim_engine, ws2_system, course_tracker)
    ]
    
    if agent and hasattr(agent, 'tools'):
        for tool in tools:
            agent.tools.append(tool)
        logger.info(f"已注册 {len(tools)} 个课程系统工具")
    
    return tools
