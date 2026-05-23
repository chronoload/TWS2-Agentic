#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 专用工具集
让 Agent 可以直接调用 WS2 系统的所有功能
完全集成 Tool 基类和使用 ToolResult 结构化输出

优化内容:
- ToolResult 结构化输出 (JSON 可解析)
- 共享 BookmarkManager 实例 (避免每工具独立创建)
- 均匀的结果截断
- 一致的错误/成功格式
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class WS2BaseTool(Tool):
    """WS2 工具基类 - 正确继承 Tool"""

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager: Optional["BookmarkManager"] = None):
        self.ws2_system = ws2_system
        self.project_manager = project_manager
        self.task_board_manager = task_board_manager
        self.base_dir = Path(base_dir) if base_dir else None
        self._bookmark_manager = bookmark_manager

    def set_system(self, ws2_system=None, project_manager=None, task_manager=None):
        """设置系统对象"""
        if ws2_system is not None:
            self.ws2_system = ws2_system
        if project_manager is not None:
            self.project_manager = project_manager
        if task_manager is not None:
            self.task_board_manager = task_manager

    def _check_ws2(self) -> Optional[str]:
        """检查 WS2 是否初始化，未初始化则返回错误消息"""
        if not self.ws2_system:
            return "WS2 系统未初始化"
        return None

    def _make_result(self, success: bool, data: dict, message: str = "",
                     error: str = "", **kwargs) -> str:
        """快速构造 ToolResult JSON 字符串"""
        tr = ToolResult(success=success, data=data, message=message,
                        error=error, **kwargs)
        return tr.to_json()


class BookmarkManager:
    """书签管理器（共享实例）"""

    def __init__(self, bookmarks_path=None):
        self.bookmarks_path = Path(bookmarks_path) if bookmarks_path else None
        self.bookmarks = []
        self._loaded = False

    def _lazy_load(self):
        """延迟加载，直到首次访问才读取文件"""
        if self._loaded:
            return
        self._loaded = True
        if not self.bookmarks_path or not self.bookmarks_path.exists():
            self.bookmarks = []
            return
        try:
            with open(self.bookmarks_path, 'r', encoding='utf-8') as f:
                self.bookmarks = json.load(f)
        except Exception as e:
            logger.warning(f"加载书签失败: {e}")
            self.bookmarks = []

    def save(self):
        self._lazy_load()
        if self.bookmarks_path:
            self.bookmarks_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.bookmarks_path, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, ensure_ascii=False, indent=2)

    def get_all(self):
        self._lazy_load()
        return self.bookmarks

    def search(self, query):
        self._lazy_load()
        query_lower = query.lower()
        return [b for b in self.bookmarks if query_lower in b.get('name', '').lower()
                or query_lower in b.get('url', '').lower()]

    def get_by_category(self, category):
        self._lazy_load()
        return [b for b in self.bookmarks if b.get('category') == category]

    def get_categories(self):
        self._lazy_load()
        return sorted(set(b.get('category') for b in self.bookmarks if b.get('category')))

    def add(self, bookmark: dict):
        self._lazy_load()
        self.bookmarks.append(bookmark)
        self.save()


# ============================================================
# 1. 总览与统计工具
# ============================================================

class GetOverviewTool(WS2BaseTool):
    name = "ws2_get_overview"
    description = "获取 WS2 总览信息，包括课程总数、总课时、已完成课时、完成率、总学时等"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            total_courses = len(self.ws2_system.courses)
            done, total = self.ws2_system.get_overall_progress()
            total_hours = sum(
                sum(l.get("estimated_hours", 0) for l in c.get("lessons", []))
                for c in self.ws2_system.courses
            )
            completion_rate = (done / total * 100) if total > 0 else 0

            data = {
                "total_courses": total_courses,
                "total_lessons": total,
                "completed_lessons": done,
                "completion_rate": round(completion_rate, 1),
                "total_hours": round(total_hours, 1),
            }
            msg = (
                f"📊 WS2 系统总览\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📚 课程总数：{total_courses}\n"
                f"📖 总课时：{total}\n"
                f"✅ 已完成：{done}\n"
                f"📈 完成率：{completion_rate:.1f}%\n"
                f"⏱️ 总学时：{total_hours:.1f}小时"
            )
            return self._make_result(True, data, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetDomainStatsTool(WS2BaseTool):
    name = "ws2_get_domain_stats"
    description = "获取领域分布统计，按领域统计课程数量"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            stats = self.ws2_system.get_domain_stats()
            lines = ["📚 课程领域分布", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for domain, count in sorted(stats.items(), key=lambda x: -x[1]):
                lines.append(f"• {domain}：{count} 个课程")
            return self._make_result(True, {"domains": stats}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ListDomainsTool(WS2BaseTool):
    name = "ws2_list_domains"
    description = "列出所有存在的课程领域"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            domains = sorted(set(c.get("domain", "未知") for c in self.ws2_system.courses))
            domain_list = {}
            for d in domains:
                domain_list[d] = len([c for c in self.ws2_system.courses if c.get("domain") == d])

            lines = ["🎯 所有领域", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for i, domain in enumerate(domains, 1):
                lines.append(f"{i}. {domain} ({domain_list[domain]} 个课程)")
            return self._make_result(True, {"domains": domain_list}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetProgressByDomainTool(WS2BaseTool):
    name = "ws2_get_progress_by_domain"
    description = "按领域获取进度统计，包括课程数、课时数、完成数、完成率"
    parameters = {
        "type": "object",
        "properties": {"domain": {"type": "string", "description": "领域名称，可选，不提供则显示所有"}},
    }

    def execute(self, domain: Optional[str] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            target_domains = []
            if domain:
                target_domains = [domain]
            else:
                target_domains = sorted(set(c.get("domain", "未知") for c in self.ws2_system.courses))

            domain_data = {}
            lines = ["📈 按领域进度统计", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for d in target_domains:
                courses = [c for c in self.ws2_system.courses if c.get("domain") == d]
                if not courses:
                    continue
                total_lessons = 0
                done_lessons = 0
                for c in courses:
                    cid = c.get("note_id", c.get("course_title", ""))
                    lessons = c.get("lessons", [])
                    total_lessons += len(lessons)
                    progress = self.ws2_system.get_course_progress(cid)
                    done_lessons += len(progress.get("completed_lessons", []))
                completion_rate = (done_lessons / total_lessons * 100) if total_lessons > 0 else 0
                domain_data[d] = {
                    "course_count": len(courses),
                    "total_lessons": total_lessons,
                    "completed_lessons": done_lessons,
                    "completion_rate": round(completion_rate, 1),
                }
                lines.append(f"\n【{d}】\n  课程数：{len(courses)}\n  总课时：{total_lessons}"
                             f"\n  已完成：{done_lessons}\n  进度：{completion_rate:.1f}%")
            return self._make_result(True, {"domains": domain_data}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 2. 课程管理工具
# ============================================================

class ListCoursesTool(WS2BaseTool):
    name = "ws2_list_courses"
    description = "列出所有课程，可按领域过滤，可限制显示数量"
    parameters = {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "按领域过滤，可选"},
            "limit": {"type": "integer", "description": "显示数量限制，默认 30"},
            "only_in_progress": {"type": "boolean", "description": "只显示进行中的课程，默认 false"},
        },
    }

    def execute(self, domain: Optional[str] = None, limit: int = 30, only_in_progress: bool = False) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            courses = self.ws2_system.courses
            if domain:
                courses = [c for c in courses if c.get("domain") == domain]

            lines = ["📚 课程列表", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            course_list = []
            count = 0
            for c in courses:
                cid = c.get("note_id", c.get("course_title", ""))
                title = c.get("course_title", "")
                course_domain = c.get("domain", "未知")
                completion_pct = self.ws2_system.get_completion_pct(cid)
                lesson_count = len(c.get("lessons", []))
                progress = self.ws2_system.get_course_progress(cid)
                done_count = len(progress.get("completed_lessons", []))
                if only_in_progress and done_count == 0:
                    continue
                course_list.append({
                    "id": cid, "title": title, "domain": course_domain,
                    "progress_pct": round(completion_pct, 1),
                    "done": done_count, "total": lesson_count,
                })
                status_icon = "✅" if completion_pct == 100 else "📖" if done_count > 0 else "⭕"
                lines.append(f"\n{count + 1}. {status_icon} {title}\n"
                             f"  领域：{course_domain}\n"
                             f"  进度：{completion_pct:.1f}% ({done_count}/{lesson_count})")
                count += 1
                if count >= limit:
                    break

            if len(courses) > limit:
                lines.append(f"\n\n... 还有 {len(courses) - limit} 个课程")

            return self._make_result(True, {
                "courses": course_list,
                "total": len(courses),
                "showing": min(count, limit),
                "filtered_by_domain": bool(domain),
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class SearchCoursesTool(WS2BaseTool):
    name = "ws2_search_courses"
    description = "搜索课程，支持按标题、描述、作者、领域匹配"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
        "required": ["query"],
    }

    def execute(self, query: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            query_lower = query.lower()
            results = []
            for c in self.ws2_system.courses:
                title = c.get("course_title", "").lower()
                desc = c.get("course_description", "").lower()
                author = c.get("author", "").lower()
                domain = c.get("domain", "").lower()
                if query_lower in title or query_lower in desc or query_lower in author or query_lower in domain:
                    results.append(c)

            if not results:
                return self._make_result(True, {"query": query, "results": [], "count": 0},
                                          f"⚠️ 未找到包含「{query}」的课程")

            search_results = []
            lines = [f"🔍 搜索结果（{len(results)} 个）", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for i, c in enumerate(results[:20], 1):
                cid = c.get("note_id", "")
                title = c.get("course_title", "")
                course_domain = c.get("domain", "")
                completion_pct = self.ws2_system.get_completion_pct(cid)
                search_results.append({
                    "id": cid, "title": title, "domain": course_domain,
                    "progress_pct": round(completion_pct, 0),
                })
                lines.append(f"\n{i}. {title} ({course_domain})\n  进度：{completion_pct:.0f}%")
            if len(results) > 20:
                lines.append(f"\n\n... 还有 {len(results) - 20} 个结果")

            return self._make_result(True, {
                "query": query, "results": search_results, "count": len(results),
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCourseDetailTool(WS2BaseTool):
    name = "ws2_get_course_detail"
    description = "获取课程详情，包括基本信息、课时列表、进度等"
    parameters = {
        "type": "object",
        "properties": {"course_id": {"type": "string", "description": "课程 ID（note_id）或标题"}},
        "required": ["course_id"],
    }

    def execute(self, course_id: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                for c in self.ws2_system.courses:
                    if course_id.lower() in c.get("course_title", "").lower():
                        course = c
                        break
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            cid = course.get("note_id", "")
            title = course.get("course_title", "")
            domain = course.get("domain", "未知")
            author = course.get("author", "")
            desc = course.get("course_description", "")
            lessons = course.get("lessons", [])
            completion_pct = self.ws2_system.get_completion_pct(cid)
            progress = self.ws2_system.get_course_progress(cid)
            completed_lessons = set(progress.get("completed_lessons", []))

            lesson_list = []
            lines = [f"📚 课程详情：{title}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                     f"ID：{cid}", f"领域：{domain}"]
            if author:
                lines.append(f"作者：{author}")
            lines.append(f"进度：{completion_pct:.1f}%")
            lines.append(f"课时：{len(lessons)}")
            if desc:
                lines.append(f"\n简介：{desc}")
            lines.append("\n课时列表：")
            for i, lesson in enumerate(lessons, 1):
                lesson_title = lesson.get("lesson_title", lesson.get("title", ""))
                is_done = i in completed_lessons
                status = "✅" if is_done else "⭕"
                hours = lesson.get("estimated_hours", 0)
                lesson_list.append({
                    "number": i, "title": lesson_title,
                    "completed": is_done, "hours": hours,
                })
                line = f"  {status} 第{i}课：{lesson_title}"
                if hours > 0:
                    line += f" ({hours}小时)"
                lines.append(line)

            return self._make_result(True, {
                "id": cid, "title": title, "domain": domain, "author": author,
                "completion_pct": round(completion_pct, 1),
                "lesson_count": len(lessons),
                "completed_lessons": list(completed_lessons),
                "lessons": lesson_list,
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class CreateCourseTool(WS2BaseTool):
    name = "ws2_create_course"
    description = "创建新课程模板"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "课程标题"},
            "domain": {"type": "string", "description": "领域，默认「其他」"},
        },
        "required": ["title"],
    }

    def execute(self, title: str, domain: str = "其他") -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            new_course = self.ws2_system.create_course(title, domain)
            self.ws2_system.courses.append(new_course)
            msg = f"✅ 课程创建成功\n标题：{title}\n领域：{domain}\nID：{new_course.get('note_id', '')}"
            return self._make_result(True, {
                "title": title, "domain": domain,
                "id": new_course.get("note_id", ""),
            }, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RemoveCourseTool(WS2BaseTool):
    name = "ws2_remove_course"
    description = "删除课程（从内存、进度、JSON 文件中移除）"
    parameters = {
        "type": "object",
        "properties": {"course_id": {"type": "string", "description": "课程 ID（note_id）或标题"}},
        "required": ["course_id"],
    }

    def execute(self, course_id: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            success = self.ws2_system.remove_course(course_id)
            if success:
                return self._make_result(True, {"course_id": course_id},
                                          f"✅ 课程已删除：{course_id}")
            return self._make_result(False, {}, error=f"未找到课程：{course_id}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class FindDuplicatesTool(WS2BaseTool):
    name = "ws2_find_duplicates"
    description = "检测重复课程（按标题相似度）"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            duplicates = self.ws2_system.find_duplicates()
            if not duplicates:
                return self._make_result(True, {"duplicates": {}}, "✅ 没有发现重复课程")

            lines = ["⚠️ 发现重复课程", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            dup_data = {}
            for base, courses in duplicates.items():
                dup_data[base] = [c.get("course_title", "") for c in courses]
                lines.append(f"\n组：{base}")
                for c in courses:
                    lines.append(f"  • {c.get('course_title', '')}")
            return self._make_result(True, {"duplicates": dup_data}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 3. 课时学习工具
# ============================================================

class MarkLessonCompleteTool(WS2BaseTool):
    name = "ws2_mark_lesson_complete"
    description = "标记课时完成，自动更新复习调度"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID（note_id）或标题"},
            "lesson_number": {"type": "integer", "description": "课时编号（从 1 开始）"},
            "workload": {"type": "integer", "description": "工作量（难度），用于复习间隔计算，默认 5"},
        },
        "required": ["course_id", "lesson_number"],
    }

    def execute(self, course_id: str, lesson_number: int, workload: int = 5) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                for c in self.ws2_system.courses:
                    if course_id.lower() in c.get("course_title", "").lower():
                        course = c
                        course_id = c.get("note_id", c.get("course_title", ""))
                        break
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            self.ws2_system.mark_lesson_complete(course_id, lesson_number)
            self.ws2_system.update_review_schedule(course_id, lesson_number, workload)

            title = course.get("course_title", "")
            lessons = course.get("lessons", [])
            lesson_title = ""
            if 1 <= lesson_number <= len(lessons):
                lesson_title = lessons[lesson_number - 1].get("lesson_title", "")

            msg = f"✅ 已标记完成\n课程：{title}\n第{lesson_number}课：{lesson_title}"
            return self._make_result(True, {
                "course_id": course_id, "course_title": title,
                "lesson_number": lesson_number, "lesson_title": lesson_title,
                "workload": workload,
            }, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetNextLessonTool(WS2BaseTool):
    name = "ws2_get_next_lesson"
    description = "获取课程的下一个待学习课时"
    parameters = {
        "type": "object",
        "properties": {"course_id": {"type": "string", "description": "课程 ID（note_id）或标题"}},
        "required": ["course_id"],
    }

    def execute(self, course_id: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                for c in self.ws2_system.courses:
                    if course_id.lower() in c.get("course_title", "").lower():
                        course = c
                        course_id = c.get("note_id", c.get("course_title", ""))
                        break
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            next_lesson_num = self.ws2_system.get_next_lesson(course_id)
            lessons = course.get("lessons", [])
            title = course.get("course_title", "")

            if next_lesson_num is None:
                return self._make_result(True, {
                    "course_id": course_id, "course_title": title,
                    "next_lesson": None, "all_completed": True,
                }, f"✅ 「{title}」所有课时已完成！")

            if 1 <= next_lesson_num <= len(lessons):
                lesson = lessons[next_lesson_num - 1]
                lesson_title = lesson.get("lesson_title", lesson.get("title", ""))
                hours = lesson.get("estimated_hours", 0)
                msg = (f"📖 下一课\n课程：{title}\n第{next_lesson_num}课：{lesson_title}"
                       + (f"\n预计：{hours}小时" if hours > 0 else ""))
                return self._make_result(True, {
                    "course_id": course_id, "course_title": title,
                    "next_lesson_number": next_lesson_num,
                    "next_lesson_title": lesson_title,
                    "estimated_hours": hours,
                    "all_completed": False,
                }, msg)

            return self._make_result(True, {
                "course_id": course_id, "course_title": title,
                "next_lesson": None, "all_completed": False,
            }, f"「{title}」没有待学习的课时")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCourseProgressTool(WS2BaseTool):
    name = "ws2_get_course_progress"
    description = "获取课程的详细进度信息"
    parameters = {
        "type": "object",
        "properties": {"course_id": {"type": "string", "description": "课程 ID（note_id）或标题"}},
        "required": ["course_id"],
    }

    def execute(self, course_id: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                for c in self.ws2_system.courses:
                    if course_id.lower() in c.get("course_title", "").lower():
                        course = c
                        course_id = c.get("note_id", c.get("course_title", ""))
                        break
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            progress = self.ws2_system.get_course_progress(course_id)
            completion_pct = self.ws2_system.get_completion_pct(course_id)
            completed = len(progress.get("completed_lessons", []))
            total = len(course.get("lessons", []))

            lines = [
                f"📊 课程进度：{course.get('course_title', '')}",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"完成率：{completion_pct:.1f}%",
                f"已完成：{completed} / {total} 课时",
            ]
            if progress.get('started_at'):
                lines.append(f"开始于：{progress.get('started_at')}")
            if progress.get('last_updated'):
                lines.append(f"更新于：{progress.get('last_updated')}")

            return self._make_result(True, {
                "course_id": course_id,
                "course_title": course.get("course_title", ""),
                "completion_pct": round(completion_pct, 1),
                "completed_lessons": completed,
                "total_lessons": total,
                "started_at": progress.get("started_at", ""),
                "last_updated": progress.get("last_updated", ""),
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 4. 复习调度工具
# ============================================================

class GetReviewScheduleTool(WS2BaseTool):
    name = "ws2_get_review_schedule"
    description = "获取所有待复习课程列表"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            review_items = []
            lines = ["📅 待复习课程", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]

            for c in self.ws2_system.courses:
                cid = c.get("note_id", c.get("course_title", ""))
                due = self.ws2_system.get_due_reviews(cid)
                if due:
                    title = c.get("course_title", "")
                    lines.append(f"\n【{title}】")
                    for item in due:
                        lesson_num = item['lesson_number']
                        overdue_days = item.get('overdue_days', 0)
                        workload = item.get('workload', 5)
                        lines.append(f"  第{lesson_num}课：逾期 {overdue_days}天（工作量：{workload}）")
                        review_items.append({
                            "course_id": cid,
                            "course_title": title,
                            "lesson_number": lesson_num,
                            "overdue_days": overdue_days,
                            "workload": workload,
                        })

            if not review_items:
                return self._make_result(True, {"reviews": []},
                                          "✅ 没有待复习的课程，继续保持！")

            return self._make_result(True, {"reviews": review_items, "count": len(review_items)},
                                      "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class MarkReviewDoneTool(WS2BaseTool):
    name = "ws2_mark_review_done"
    description = "标记复习完成，计算下次复习时间"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID（note_id）或标题"},
            "lesson_number": {"type": "integer", "description": "课时编号（从 1 开始）"},
        },
        "required": ["course_id", "lesson_number"],
    }

    def execute(self, course_id: str, lesson_number: int) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                for c in self.ws2_system.courses:
                    if course_id.lower() in c.get("course_title", "").lower():
                        course = c
                        course_id = c.get("note_id", c.get("course_title", ""))
                        break
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            self.ws2_system.mark_review_done(course_id, lesson_number)
            title = course.get("course_title", "")
            msg = f"✅ 复习已标记完成\n课程：{title}\n第{lesson_number}课"
            return self._make_result(True, {
                "course_id": course_id, "course_title": title,
                "lesson_number": lesson_number,
            }, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 5. 资源管理工具
# ============================================================

class GetResourcesTool(WS2BaseTool):
    name = "ws2_get_resources"
    description = "获取课程的所有资源列表"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID（note_id）或标题，可选"},
            "lesson_number": {"type": "integer", "description": "课时编号，可选，不提供则获取课程级资源"},
        },
    }

    def execute(self, course_id: Optional[str] = None, lesson_number: Optional[int] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        if not self.ws2_system.rmgr:
            return self._make_result(False, {}, error="WS2 资源管理器未初始化")
        try:
            resource_data = {"resources": []}
            lines = []

            if course_id:
                course = self.ws2_system.get_course_by_id(course_id)
                if not course:
                    for c in self.ws2_system.courses:
                        if course_id.lower() in c.get("course_title", "").lower():
                            course = c
                            course_id = c.get("note_id", c.get("course_title", ""))
                            break
                if not course:
                    return self._make_result(False, {}, error=f"未找到课程：{course_id}")

                course_title = course.get("course_title", "")
                all_resources = self.ws2_system.rmgr.get(course_id)
                if lesson_number:
                    resources = [r for r in all_resources if r.get("lesson_number") == lesson_number]
                    lines.append(f"📚 第{lesson_number}课资源：{course_title}")
                else:
                    resources = [r for r in all_resources if r.get("lesson_number") is None]
                    lines.append(f"📚 课程资源：{course_title}")

                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                if not resources:
                    lines.append("没有找到资源")
                else:
                    for r in resources:
                        icon = r.get("icon", "📄")
                        label = r.get("label", "")
                        path = r.get("path", "")
                        url = r.get("url", "")
                        res_item = {"icon": icon, "label": label, "path": path, "url": url,
                                     "type": r.get("type", "unknown")}
                        resource_data["resources"].append(res_item)
                        lines.append(f"\n{icon} {label}")
                        if path:
                            lines.append(f"  路径：{path}")
                        if url:
                            lines.append(f"  链接：{url}")
            else:
                lines.extend(["📚 所有资源（按课程）", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"])
                has_resources = False
                for c in self.ws2_system.courses:
                    cid = c.get("note_id", c.get("course_title", ""))
                    resources = self.ws2_system.rmgr.get(cid)
                    if resources:
                        has_resources = True
                        title = c.get("course_title", "")
                        lines.append(f"\n【{title}】")
                        for r in resources:
                            icon = r.get("icon", "📄")
                            label = r.get("label", "")
                            lines.append(f"  {icon} {label}")
                if not has_resources:
                    lines.append("没有找到任何资源")

            return self._make_result(True, resource_data, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 6. 书签管理工具
# ============================================================

class AddBookmarkTool(WS2BaseTool):
    name = "ws2_add_bookmark"
    description = "添加新书签"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "书签名称"},
            "url": {"type": "string", "description": "书签 URL"},
            "category": {"type": "string", "description": "分类，可选"},
            "icon": {"type": "string", "description": "图标，默认🌐"},
        },
        "required": ["name", "url"],
    }

    def execute(self, name: str, url: str, category: Optional[str] = None, icon: str = "🌐") -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            bookmark = {"name": name, "url": url, "icon": icon, "category": category}
            self._bookmark_manager.add(bookmark)
            msg = f"✅ 书签添加成功\n名称：{name}\n链接：{url}"
            return self._make_result(True, {
                "name": name, "url": url, "category": category, "icon": icon,
            }, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ListBookmarksTool(WS2BaseTool):
    name = "ws2_list_bookmarks"
    description = "列出所有书签或按分类列出"
    parameters = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "分类名称，可选，不提供则列出所有"},
            "limit": {"type": "integer", "description": "显示数量限制，默认 50"},
        },
    }

    def execute(self, category: Optional[str] = None, limit: int = 50) -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            if category:
                bookmarks = self._bookmark_manager.get_by_category(category)
                title = f"🔖 书签列表 - {category}"
            else:
                bookmarks = self._bookmark_manager.get_all()
                title = "🔖 所有书签"

            lines = [title, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            bm_list = []
            for i, b in enumerate(bookmarks[:limit], 1):
                icon = b.get('icon', '🌐')
                name = b.get('name', '')
                url = b.get('url', '')
                cat = b.get('category', '')
                bm_list.append({"name": name, "url": url, "category": cat, "icon": icon})
                lines.append(f"\n{i}. {icon} {name}\n  链接：{url}")
                if cat:
                    lines.append(f"  分类：{cat}")

            if len(bookmarks) > limit:
                lines.append(f"\n... 还有 {len(bookmarks) - limit} 个书签")

            return self._make_result(True, {"bookmarks": bm_list, "total": len(bookmarks),
                                              "showing": min(len(bookmarks), limit)},
                                      "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class SearchBookmarksTool(WS2BaseTool):
    name = "ws2_search_bookmarks"
    description = "搜索书签"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
        "required": ["query"],
    }

    def execute(self, query: str) -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            bookmarks = self._bookmark_manager.search(query)
            if not bookmarks:
                return self._make_result(True, {"query": query, "bookmarks": []},
                                          f"⚠️ 未找到包含「{query}」的书签")

            lines = [f"🔖 搜索结果（{len(bookmarks)} 个）", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            bm_list = []
            for i, b in enumerate(bookmarks[:20], 1):
                icon = b.get('icon', '🌐')
                name = b.get('name', '')
                url = b.get('url', '')
                bm_list.append({"name": name, "url": url, "icon": icon})
                lines.append(f"\n{i}. {icon} {name}\n  链接：{url}")
            if len(bookmarks) > 20:
                lines.append(f"\n... 还有 {len(bookmarks) - 20} 个结果")

            return self._make_result(True, {"query": query, "bookmarks": bm_list,
                                              "count": len(bookmarks)}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ListBookmarkCategoriesTool(WS2BaseTool):
    name = "ws2_list_bookmark_categories"
    description = "列出所有书签分类"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            categories = self._bookmark_manager.get_categories()
            lines = ["📂 书签分类", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            cat_data = {}
            for i, cat in enumerate(categories, 1):
                count = len(self._bookmark_manager.get_by_category(cat))
                cat_data[cat] = count
                lines.append(f"{i}. {cat} ({count} 个)")
            return self._make_result(True, {"categories": cat_data}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 7. 笔记管理工具
# ============================================================

class NotesManager:
    """笔记管理器（共享实例）- 延迟初始化"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.notes_dir = Path(base_dir) / "Notes" if base_dir else None

    @property
    def ready(self) -> bool:
        return self.notes_dir is not None and self.notes_dir.exists()

    def list_courses(self) -> List[str]:
        if not self.ready:
            return []
        return sorted([d.name for d in self.notes_dir.iterdir() if d.is_dir()])

    def list_files(self, course: str) -> List[str]:
        if not self.ready:
            return []
        course_dir = self.notes_dir / course
        if not course_dir.exists():
            return []
        return sorted([f.name for f in course_dir.iterdir() if f.is_file()])

    def read(self, course: str, filename: str) -> Optional[str]:
        if not self.ready:
            return None
        note_path = self.notes_dir / course / filename
        if not note_path.exists():
            return None
        content = note_path.read_text(encoding='utf-8')
        return content

    def write(self, course: str, filename: str, content: str) -> bool:
        if not self.notes_dir:
            return False
        course_dir = self.notes_dir / course
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / filename).write_text(content, encoding='utf-8')
        return True


class ListNotesTool(WS2BaseTool):
    name = "ws2_list_notes"
    description = "列出所有笔记文件"
    parameters = {
        "type": "object",
        "properties": {"course": {"type": "string", "description": "课程名称，可选，不提供则列出所有"}},
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: Optional[str] = None) -> str:
        if not self._notes_manager or not self._notes_manager.ready:
            return self._make_result(False, {}, error="笔记目录不存在")
        try:
            if course:
                files = self._notes_manager.list_files(course)
                if not files:
                    return self._make_result(True, {"course": course, "files": []},
                                              f"⚠️ 未找到课程目录：{course}")
                lines = [f"📝 笔记列表 - {course}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                for f in files:
                    lines.append(f"\n• {f}")
                return self._make_result(True, {"course": course, "files": files},
                                          "\n".join(lines))
            else:
                courses = self._notes_manager.list_courses()
                lines = ["📝 笔记列表", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                notes_data = {}
                for cn in courses:
                    files = self._notes_manager.list_files(cn)
                    notes_data[cn] = files
                    lines.append(f"\n【{cn}】")
                    for f in files:
                        lines.append(f"  • {f}")
                return self._make_result(True, {"courses": notes_data}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ReadNoteTool(WS2BaseTool):
    name = "ws2_read_note"
    description = "读取笔记文件内容"
    parameters = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "description": "课程名称"},
            "filename": {"type": "string", "description": "笔记文件名"},
        },
        "required": ["course", "filename"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: str, filename: str) -> str:
        if not self._notes_manager or not self._notes_manager.ready:
            return self._make_result(False, {}, error="笔记目录不存在")
        try:
            content = self._notes_manager.read(course, filename)
            if content is None:
                return self._make_result(False, {}, error=f"未找到笔记：{filename}")
            msg = f"📝 笔记：{filename}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{content}"
            return self._make_result(True, {"course": course, "filename": filename,
                                              "content": content, "length": len(content)}, msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class WriteNoteTool(WS2BaseTool):
    name = "ws2_write_note"
    description = "创建或更新笔记文件"
    parameters = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "description": "课程名称"},
            "filename": {"type": "string", "description": "笔记文件名"},
            "content": {"type": "string", "description": "笔记内容"},
        },
        "required": ["course", "filename", "content"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: str, filename: str, content: str) -> str:
        if not self._notes_manager:
            return self._make_result(False, {}, error="笔记目录未设置")
        try:
            success = self._notes_manager.write(course, filename, content)
            if success:
                msg = f"✅ 笔记保存成功\n课程：{course}\n文件名：{filename}"
                return self._make_result(True, {
                    "course": course, "filename": filename, "length": len(content),
                }, msg)
            return self._make_result(False, {}, error="笔记保存失败")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 8. 项目/任务/RAG 工具（占位，传递给 ws2_system）
# ============================================================

# 这些工具代理到 ws2_system.project_manager / task_board_manager

class ListProjectsTool(WS2BaseTool):
    name = "ws2_list_projects"
    description = "列出所有项目"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        if not self.project_manager:
            return self._make_result(False, {}, error="项目管理器未初始化")
        try:
            projects = self.project_manager.list_projects() if hasattr(self.project_manager, 'list_projects') else []
            lines = ["📁 项目列表", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for i, p in enumerate(projects[:50], 1):
                name = getattr(p, 'name', p) if not isinstance(p, str) else p
                lines.append(f"{i}. {name}")
            return self._make_result(True, {"projects": projects[:50],
                                              "total": len(projects)}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class CreateProjectTool(WS2BaseTool):
    name = "ws2_create_project"
    description = "创建新项目"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "项目名称"},
        },
        "required": ["name"],
    }

    def execute(self, name: str) -> str:
        if not self.project_manager:
            return self._make_result(False, {}, error="项目管理器未初始化")
        try:
            if hasattr(self.project_manager, 'create_project'):
                self.project_manager.create_project(name)
                return self._make_result(True, {"name": name}, f"✅ 项目创建成功：{name}")
            return self._make_result(False, {}, error="create_project 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ListTasksTool(WS2BaseTool):
    name = "ws2_list_tasks"
    description = "列出所有任务，可按状态/日期筛选"
    parameters = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "状态筛选（todo/done/in_progress）"},
        },
    }

    def execute(self, status: Optional[str] = None) -> str:
        if not self.task_board_manager:
            return self._make_result(False, {}, error="任务管理器未初始化")
        try:
            tasks = []
            if hasattr(self.task_board_manager, 'get_all_tasks'):
                tasks = self.task_board_manager.get_all_tasks()
            elif hasattr(self.task_board_manager, 'list_tasks'):
                tasks = self.task_board_manager.list_tasks()
            elif hasattr(self.task_board_manager, 'tasks'):
                tasks = self.task_board_manager.tasks

            if status:
                tasks = [t for t in tasks if getattr(t, 'status', '') == status
                         or (isinstance(t, dict) and t.get('status') == status)]

            lines = ["📋 任务列表", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            task_list = []
            for i, t in enumerate(tasks[:50], 1):
                title = getattr(t, 'title', '') if not isinstance(t, dict) else t.get('title', '')
                st = getattr(t, 'status', '') if not isinstance(t, dict) else t.get('status', '')
                task_list.append({"title": title, "status": st})
                icon = "✅" if st == "done" else "🔄" if st == "in_progress" else "⭕"
                lines.append(f"{i}. {icon} {title} ({st})")

            return self._make_result(True, {"tasks": task_list, "total": len(tasks),
                                              "filtered_by_status": bool(status)}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class AddTaskTool(WS2BaseTool):
    name = "ws2_add_task"
    description = "添加新任务"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "任务标题"},
            "description": {"type": "string", "description": "任务描述，可选"},
        },
        "required": ["title"],
    }

    def execute(self, title: str, description: Optional[str] = None) -> str:
        if not self.task_board_manager:
            return self._make_result(False, {}, error="任务管理器未初始化")
        try:
            method = None
            if hasattr(self.task_board_manager, 'add_task'):
                method = self.task_board_manager.add_task
            elif hasattr(self.task_board_manager, 'create_task'):
                method = self.task_board_manager.create_task
            if method:
                method(title, description or "")
                return self._make_result(True, {"title": title}, f"✅ 任务已添加：{title}")
            return self._make_result(False, {}, error="add_task 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class UpdateTaskTool(WS2BaseTool):
    name = "ws2_update_task"
    description = "更新任务"
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID 或标题"},
            "status": {"type": "string", "description": "新状态"},
        },
        "required": ["task_id", "status"],
    }

    def execute(self, task_id: str, status: str) -> str:
        if not self.task_board_manager:
            return self._make_result(False, {}, error="任务管理器未初始化")
        try:
            method = None
            if hasattr(self.task_board_manager, 'update_task'):
                method = self.task_board_manager.update_task
            elif hasattr(self.task_board_manager, 'set_status'):
                method = self.task_board_manager.set_status
            if method:
                method(task_id, status=status)
                return self._make_result(True, {"task_id": task_id, "status": status},
                                          f"✅ 任务已更新：{task_id} -> {status}")
            return self._make_result(False, {}, error="update_task 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 9. 数据库管理工具
# ============================================================

class ReloadAllSourcesTool(WS2BaseTool):
    name = "ws2_reload_all_sources"
    description = "重新加载所有数据库源（去重合并）"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            if hasattr(self.ws2_system, 'reload_all_sources'):
                result = self.ws2_system.reload_all_sources()
                count = len(result) if isinstance(result, (list, dict)) else 0
                return self._make_result(True, {"loaded": count},
                                          f"✅ 已重新加载 {count} 个源")
            return self._make_result(False, {}, error="reload_all_sources 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class AddDbPathTool(WS2BaseTool):
    name = "ws2_add_db_path"
    description = "添加数据库源"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "数据库路径"},
        },
        "required": ["path"],
    }

    def execute(self, path: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            if hasattr(self.ws2_system, 'add_db_path'):
                self.ws2_system.add_db_path(path)
                return self._make_result(True, {"path": path}, f"✅ 已添加数据库源：{path}")
            return self._make_result(False, {}, error="add_db_path 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetDbPathsTool(WS2BaseTool):
    name = "ws2_get_db_paths"
    description = "获取当前所有数据库源路径"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        try:
            if hasattr(self.ws2_system, 'get_db_paths'):
                paths = self.ws2_system.get_db_paths()
                lines = ["🗄️ 数据库源", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
                for i, p in enumerate(paths, 1):
                    lines.append(f"{i}. {p}")
                return self._make_result(True, {"paths": paths}, "\n".join(lines))
            return self._make_result(False, {}, error="get_db_paths 方法不可用")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 10. RAG 知识管理工具
# ============================================================

class RAGAddFileTool(WS2BaseTool):
    name = "ws2_rag_add_file"
    description = "向 RAG 知识库添加文件（支持 .txt, .md, .json）"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "文件路径"}},
        "required": ["path"],
    }

    def execute(self, path: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        rag = getattr(self.ws2_system, 'rag', None)
        if not rag or not rag.rag_engine:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            result = rag.rag_engine.add_file(path)
            rag.rag_engine.persist()
            return self._make_result(True, {"path": path, "ids": result},
                                      f"✅ 文件已添加到 RAG：{path}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGAddDirectoryTool(WS2BaseTool):
    name = "ws2_rag_add_directory"
    description = "向 RAG 知识库添加整个目录的文件"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "目录路径"}},
        "required": ["path"],
    }

    def execute(self, path: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        rag = getattr(self.ws2_system, 'rag', None)
        if not rag or not rag.rag_engine:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            result = rag.rag_engine.add_directory(path)
            count = len(result) if isinstance(result, dict) else 0
            rag.rag_engine.persist()
            return self._make_result(True, {"path": path, "files_added": count},
                                      f"✅ 已添加 {count} 个文件到 RAG")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGAddTextTool(WS2BaseTool):
    name = "ws2_rag_add_text"
    description = "向 RAG 知识库添加文本内容"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "文本内容"},
            "source": {"type": "string", "description": "来源描述，可选"},
        },
        "required": ["text"],
    }

    def execute(self, text: str, source: Optional[str] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        rag = getattr(self.ws2_system, 'rag', None)
        if not rag or not rag.rag_engine:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            metadata = {"source": source} if source else None
            doc_id = rag.rag_engine.add_text(text, metadata=metadata)
            rag.rag_engine.persist()
            return self._make_result(True, {"id": doc_id, "length": len(text), "source": source},
                                      f"✅ 已添加文本 ({len(text)} 字符) 到 RAG")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGSearchTool(WS2BaseTool):
    name = "ws2_rag_search"
    description = "在 RAG 知识库中搜索相关内容"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "top_k": {"type": "integer", "description": "返回结果数量，默认 5"},
        },
        "required": ["query"],
    }

    def execute(self, query: str, top_k: int = 5) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        if not hasattr(self.ws2_system, 'rag') or not self.ws2_system.rag:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            results = self.ws2_system.rag.search(query, top_k)
            lines = [f"🔍 RAG 搜索：{query}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            rag_results = []
            for i, r in enumerate(results[:top_k], 1):
                content = r.get("content", r.get("text", ""))
                score = r.get("score", r.get("similarity", 0))
                source = r.get("source", "")
                rag_results.append({"content": content, "score": score, "source": source})
                lines.append(f"\n{i}. [score={score:.3f}]")
                if source:
                    lines.append(f"   来源：{source}")
                lines.append(f"   {content}")
            return self._make_result(True, {"query": query, "results": rag_results,
                                              "count": len(results)}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGGetContextTool(WS2BaseTool):
    name = "ws2_rag_get_context"
    description = "获取 RAG 知识库中的上下文，用于增强回答"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "查询内容"}},
        "required": ["query"],
    }

    def execute(self, query: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        if not hasattr(self.ws2_system, 'rag') or not self.ws2_system.rag:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            context = self.ws2_system.rag.get_context(query)
            return self._make_result(True, {"query": query, "context": context},
                                      f"📚 RAG 上下文：\n{context}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGGetStatsTool(WS2BaseTool):
    name = "ws2_rag_get_stats"
    description = "获取 RAG 知识库的统计信息"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        if not hasattr(self.ws2_system, 'rag') or not self.ws2_system.rag:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            stats = self.ws2_system.rag.get_stats()
            lines = ["📊 RAG 知识库统计", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for k, v in stats.items():
                lines.append(f"  {k}: {v}")
            return self._make_result(True, {"stats": stats}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RAGClearTool(WS2BaseTool):
    name = "ws2_rag_clear"
    description = "清空 RAG 知识库（谨慎使用）"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)
        rag = getattr(self.ws2_system, 'rag', None)
        if not rag or not rag.rag_engine:
            return self._make_result(False, {}, error="RAG 系统未初始化")
        try:
            rag.rag_engine.clear()
            rag.rag_engine.persist()
            return self._make_result(True, {}, "✅ RAG 知识库已清空")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 工具工厂
# ============================================================

# 全局共享实例（延迟初始化）
_shared_bookmark_manager: Optional[BookmarkManager] = None
_shared_notes_manager: Optional[NotesManager] = None


def _get_bookmark_manager(base_dir: Optional[Path] = None) -> Optional[BookmarkManager]:
    """获取或创建共享的书签管理器实例"""
    global _shared_bookmark_manager
    if _shared_bookmark_manager is not None:
        return _shared_bookmark_manager
    if base_dir:
        bookmarks_path = Path(base_dir) / "bookmarks.json"
        _shared_bookmark_manager = BookmarkManager(bookmarks_path)
    return _shared_bookmark_manager


def _get_notes_manager(base_dir: Optional[Path] = None) -> Optional[NotesManager]:
    """获取或创建共享的笔记管理器实例"""
    global _shared_notes_manager
    if _shared_notes_manager is not None:
        return _shared_notes_manager
    if base_dir:
        _shared_notes_manager = NotesManager(base_dir)
    return _shared_notes_manager


def get_ws2_tools(
    ws2_system=None,
    project_manager=None,
    task_board_manager=None,
    base_dir: Optional[Path] = None,
) -> List[Tool]:
    """获取所有 WS2 工具（共享管理器实例）"""
    bm = _get_bookmark_manager(base_dir)
    nm = _get_notes_manager(base_dir)

    common_kwargs = {
        "ws2_system": ws2_system,
        "project_manager": project_manager,
        "task_board_manager": task_board_manager,
        "base_dir": base_dir,
        "bookmark_manager": bm,
    }

    # 需要 notes_manager 的单独传
    note_kwargs = {**common_kwargs, "notes_manager": nm}

    return [
        # 总计与统计
        GetOverviewTool(**common_kwargs),
        GetDomainStatsTool(**common_kwargs),
        ListDomainsTool(**common_kwargs),
        GetProgressByDomainTool(**common_kwargs),
        # 课程管理
        ListCoursesTool(**common_kwargs),
        SearchCoursesTool(**common_kwargs),
        GetCourseDetailTool(**common_kwargs),
        CreateCourseTool(**common_kwargs),
        RemoveCourseTool(**common_kwargs),
        FindDuplicatesTool(**common_kwargs),
        # 课时学习
        MarkLessonCompleteTool(**common_kwargs),
        GetNextLessonTool(**common_kwargs),
        GetCourseProgressTool(**common_kwargs),
        # 复习调度
        GetReviewScheduleTool(**common_kwargs),
        MarkReviewDoneTool(**common_kwargs),
        # 资源管理
        GetResourcesTool(**common_kwargs),
        # 书签管理（使用共享 BookmarkManager）
        ListBookmarksTool(**common_kwargs),
        SearchBookmarksTool(**common_kwargs),
        ListBookmarkCategoriesTool(**common_kwargs),
        AddBookmarkTool(**common_kwargs),
        # 笔记管理（使用共享 NotesManager）
        ListNotesTool(**note_kwargs),
        ReadNoteTool(**note_kwargs),
        WriteNoteTool(**note_kwargs),
        # 项目管理
        ListProjectsTool(**common_kwargs),
        CreateProjectTool(**common_kwargs),
        # 任务看板
        ListTasksTool(**common_kwargs),
        AddTaskTool(**common_kwargs),
        UpdateTaskTool(**common_kwargs),
        # 数据库管理
        ReloadAllSourcesTool(**common_kwargs),
        AddDbPathTool(**common_kwargs),
        GetDbPathsTool(**common_kwargs),
        # RAG 知识管理
        RAGAddFileTool(**common_kwargs),
        RAGAddDirectoryTool(**common_kwargs),
        RAGAddTextTool(**common_kwargs),
        RAGSearchTool(**common_kwargs),
        RAGGetContextTool(**common_kwargs),
        RAGGetStatsTool(**common_kwargs),
        RAGClearTool(**common_kwargs),
    ]