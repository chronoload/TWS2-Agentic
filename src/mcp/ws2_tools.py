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

    def delete(self, bookmark_id: str):
        self._lazy_load()
        original_len = len(self.bookmarks)
        self.bookmarks = [b for b in self.bookmarks if b.get('id') != bookmark_id]
        if len(self.bookmarks) < original_len:
            self.save()
            return True
        return False

    def update(self, bookmark_id: str, updates: dict):
        self._lazy_load()
        for b in self.bookmarks:
            if b.get('id') == bookmark_id:
                b.update(updates)
                self.save()
                return True
        return False


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


class DeleteBookmarkTool(WS2BaseTool):
    name = "ws2_delete_bookmark"
    description = "删除指定书签"
    parameters = {
        "type": "object",
        "properties": {
            "bookmark_id": {"type": "string", "description": "要删除的书签 ID"},
        },
        "required": ["bookmark_id"],
    }

    def execute(self, bookmark_id: str) -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            success = self._bookmark_manager.delete(bookmark_id)
            if success:
                return self._make_result(True, {"deleted": bookmark_id}, f"✅ 已删除书签: {bookmark_id}")
            else:
                return self._make_result(False, {}, error=f"未找到书签: {bookmark_id}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class UpdateBookmarkTool(WS2BaseTool):
    name = "ws2_update_bookmark"
    description = "更新书签信息"
    parameters = {
        "type": "object",
        "properties": {
            "bookmark_id": {"type": "string", "description": "要更新的书签 ID"},
            "name": {"type": "string", "description": "新书签名称"},
            "url": {"type": "string", "description": "新 URL"},
            "category": {"type": "string", "description": "新分类"},
            "description": {"type": "string", "description": "新描述"},
        },
        "required": ["bookmark_id"],
    }

    def execute(self, bookmark_id: str, name: str = None, url: str = None,
                category: str = None, description: str = None) -> str:
        if not self._bookmark_manager:
            return self._make_result(False, {}, error="书签管理器未初始化")
        try:
            updates = {}
            if name is not None:
                updates["name"] = name
            if url is not None:
                updates["url"] = url
            if category is not None:
                updates["category"] = category
            if description is not None:
                updates["description"] = description

            if not updates:
                return self._make_result(False, {}, error="没有提供更新内容")

            success = self._bookmark_manager.update(bookmark_id, updates)
            if success:
                return self._make_result(True, {"updated": bookmark_id, "fields": list(updates.keys())},
                                         f"✅ 已更新书签: {bookmark_id} ({', '.join(updates.keys())})")
            else:
                return self._make_result(False, {}, error=f"未找到书签: {bookmark_id}")
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

    def knit_rmd(self, course: str, filename: str, output_format: str = "html_document") -> Dict[str, Any]:
        """
        使用 knitr 编译 Rmd 文件
        
        Args:
            course: 课程名称
            filename: Rmd 文件名
            output_format: 输出格式 (html_document, pdf_document, word_document 等)
        
        Returns:
            包含成功状态和输出信息的字典
        """
        if not self.ready:
            return {"success": False, "error": "笔记目录不存在"}

        course_dir = self.notes_dir / course
        rmd_path = course_dir / filename

        if not rmd_path.exists():
            return {"success": False, "error": f"Rmd 文件不存在: {filename}"}

        import subprocess
        import sys
        from pathlib import Path

        # 确定输出文件路径
        output_ext = {
            "html_document": ".html",
            "pdf_document": ".pdf",
            "word_document": ".docx",
            "ioslides_presentation": ".html",
            "slidy_presentation": ".html",
            "beamer_presentation": ".pdf",
            "tufte_html": ".html",
            "tufte_handout": ".pdf",
            "tufte_book": ".pdf",
        }.get(output_format, ".html")

        output_filename = rmd_path.stem + output_ext
        output_path = course_dir / output_filename

        # 构建 R 脚本
        r_script = f'''
        library(rmarkdown)
        rmd_file <- "{rmd_path.as_posix()}"
        output_format <- "{output_format}"
        tryCatch({{
            render(rmd_file, output_format = output_format, quiet = FALSE)
            cat("SUCCESS\\n")
        }}, error = function(e) {{
            cat(paste("ERROR:", e$message, "\\n"))
        }})
        '''

        # 创建临时 R 脚本文件
        temp_r_script = course_dir / f"_temp_knit_{rmd_path.stem}.R"
        temp_r_script.write_text(r_script, encoding='utf-8')

        try:
            # 使用 Rscript 执行
            result = subprocess.run(
                ["Rscript", str(temp_r_script)],
                capture_output=True,
                text=True,
                cwd=str(course_dir),
                timeout=300  # 5 分钟超时
            )

            # 检查结果
            if result.returncode == 0 and "SUCCESS" in result.stdout:
                return {
                    "success": True,
                    "output_file": str(output_path),
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                return {
                    "success": False,
                    "error": error_msg,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "编译超时 (超过 5 分钟)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # 清理临时文件
            if temp_r_script.exists():
                temp_r_script.unlink()

    def list_rmd_files(self, course: str) -> List[str]:
        """列出课程目录中的所有 Rmd 文件"""
        if not self.ready:
            return []
        course_dir = self.notes_dir / course
        if not course_dir.exists():
            return []
        return sorted([f.name for f in course_dir.glob("*.Rmd") if f.is_file()])

    def delete(self, course: str, filename: str) -> bool:
        if not self.ready:
            return False
        note_path = self.notes_dir / course / filename
        if note_path.exists():
            note_path.unlink()
            return True
        return False

    def search(self, query: str, course: str = None) -> List[Dict[str, Any]]:
        if not self.ready:
            return []
        query_lower = query.lower()
        results = []
        courses = [course] if course else self.list_courses()
        for c in courses:
            for fname in self.list_files(c):
                content = self.read(c, fname)
                if content and query_lower in content.lower():
                    match_line = 0
                    for i, line in enumerate(content.splitlines(), 1):
                        if query_lower in line.lower():
                            match_line = i
                            break
                    results.append({
                        "course": c,
                        "filename": fname,
                        "match_line": match_line,
                        "preview": content[:200]
                    })
        return results


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


class DeleteNoteTool(WS2BaseTool):
    name = "ws2_delete_note"
    description = "删除笔记文件"
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
        if not self._notes_manager:
            return self._make_result(False, {}, error="笔记目录未设置")
        try:
            success = self._notes_manager.delete(course, filename)
            if success:
                return self._make_result(True, {"course": course, "deleted": filename},
                                         f"✅ 已删除笔记: {course}/{filename}")
            return self._make_result(False, {}, error=f"笔记不存在: {course}/{filename}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class SearchNotesTool(WS2BaseTool):
    name = "ws2_search_notes"
    description = "全文搜索笔记内容"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "course": {"type": "string", "description": "限定课程（可选）"},
        },
        "required": ["query"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, query: str, course: str = None) -> str:
        if not self._notes_manager:
            return self._make_result(False, {}, error="笔记目录未设置")
        try:
            results = self._notes_manager.search(query, course)
            if not results:
                return self._make_result(True, {"count": 0}, f"未找到包含「{query}」的笔记")
            lines = [f"🔍 搜索「{query}」结果 ({len(results)} 个)"]
            for r in results:
                lines.append(f"  📄 {r['course']}/{r['filename']} (第{r['match_line']}行)")
            return self._make_result(True, {"count": len(results), "results": results}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 7a. Rmd 管理工具
# ============================================================

class ListRmdFilesTool(WS2BaseTool):
    name = "ws2_list_rmd"
    description = "列出课程的所有 Rmd 笔记文件"
    parameters = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "description": "课程名称"},
        },
        "required": ["course"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: str) -> str:
        if not self._notes_manager or not self._notes_manager.ready:
            return self._make_result(False, {}, error="笔记目录不存在")
        try:
            files = self._notes_manager.list_rmd_files(course)
            if not files:
                return self._make_result(True, {"course": course, "files": []},
                                          f"ℹ️ 课程「{course}」没有 Rmd 文件")
            lines = [f"📓 Rmd 笔记列表 - {course}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for f in files:
                lines.append(f"\n• {f}")
            return self._make_result(True, {"course": course, "files": files}, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class KnitRmdTool(WS2BaseTool):
    name = "ws2_knit_rmd"
    description = "使用 knitr 编译 R Markdown 文件"
    parameters = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "description": "课程名称"},
            "filename": {"type": "string", "description": "Rmd 文件名"},
            "output_format": {"type": "string", "description": "输出格式 (html_document, pdf_document, word_document 等, 默认 html_document)", "default": "html_document"},
        },
        "required": ["course", "filename"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: str, filename: str, output_format: str = "html_document") -> str:
        if not self._notes_manager or not self._notes_manager.ready:
            return self._make_result(False, {}, error="笔记目录不存在")
        try:
            result = self._notes_manager.knit_rmd(course, filename, output_format)
            if result["success"]:
                output_file = result["output_file"]
                msg = f"✅ Rmd 编译成功\n课程：{course}\n源文件：{filename}\n输出格式：{output_format}\n输出文件：{output_file}"
                return self._make_result(True, {
                    "course": course, "filename": filename, "output_format": output_format,
                    "output_file": output_file
                }, msg)
            else:
                error_msg = result.get("error", "未知错误")
                stderr = result.get("stderr", "")
                msg = f"❌ Rmd 编译失败\n课程：{course}\n源文件：{filename}\n错误：{error_msg}"
                if stderr:
                    msg += f"\n\n标准错误：\n{stderr}"
                return self._make_result(False, {}, error=msg)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class KnitAndOpenRmdTool(WS2BaseTool):
    name = "ws2_knit_and_open_rmd"
    description = "编译 Rmd 文件并使用默认程序打开输出"
    parameters = {
        "type": "object",
        "properties": {
            "course": {"type": "string", "description": "课程名称"},
            "filename": {"type": "string", "description": "Rmd 文件名"},
            "output_format": {"type": "string", "description": "输出格式 (html_document, pdf_document, word_document 等, 默认 html_document)", "default": "html_document"},
        },
        "required": ["course", "filename"],
    }

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, notes_manager: Optional[NotesManager] = None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._notes_manager = notes_manager or (NotesManager(base_dir) if base_dir else None)

    def execute(self, course: str, filename: str, output_format: str = "html_document") -> str:
        if not self._notes_manager or not self._notes_manager.ready:
            return self._make_result(False, {}, error="笔记目录不存在")
        try:
            result = self._notes_manager.knit_rmd(course, filename, output_format)
            if not result["success"]:
                error_msg = result.get("error", "未知错误")
                return self._make_result(False, {}, error=f"编译失败：{error_msg}")

            output_file = result["output_file"]

            # 打开输出文件
            import sys
            import os
            import subprocess
            from pathlib import Path

            target_path = Path(output_file)
            if not target_path.exists():
                return self._make_result(False, {}, error=f"输出文件不存在：{output_file}")

            if sys.platform == "win32":
                os.startfile(str(target_path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target_path)])
            else:
                subprocess.run(["xdg-open", str(target_path)])

            msg = f"✅ Rmd 编译并打开成功\n课程：{course}\n源文件：{filename}\n输出格式：{output_format}\n已打开：{output_file}"
            return self._make_result(True, {
                "course": course, "filename": filename, "output_format": output_format,
                "output_file": output_file
            }, msg)
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
# 11. 课程信息修改工具
# ============================================================

class UpdateCourseInfoTool(WS2BaseTool):
    name = "ws2_update_course_info"
    description = "更新课程信息（标题、领域、作者、描述、总学时等）"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "course_title": {"type": "string", "description": "课程标题（可选）"},
            "domain": {"type": "string", "description": "领域分类（可选）"},
            "total_hours": {"type": "number", "description": "总学时（可选）"},
            "positioning": {"type": "string", "description": "课程定位（可选）"},
            "target_audience": {"type": "string", "description": "目标受众（可选）"},
            "assessment": {"type": "string", "description": "评估方式（可选）"},
        },
        "required": ["course_id"],
    }

    def execute(self, course_id: str, **kwargs) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            # 更新课程信息
            updated_fields = []
            for key, value in kwargs.items():
                if value is not None:
                    course[key] = value
                    updated_fields.append(key)

            # 保存更新
            if updated_fields:
                self.ws2_system._save_data()

            lines = [
                f"✅ 课程信息已更新",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"课程：{course.get('course_title', '')}"
            ]
            for field in updated_fields:
                lines.append(f"  • {field} = {kwargs[field]}")

            return self._make_result(True, {
                "course_id": course_id,
                "updated_fields": updated_fields,
                "course": course
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 12. 课时管理工具
# ============================================================

class AddLessonTool(WS2BaseTool):
    name = "ws2_add_lesson"
    description = "添加课时到课程"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "lesson_title": {"type": "string", "description": "课时标题"},
            "lesson_number": {"type": "integer", "description": "课时编号（可选，不指定则追加）"},
            "duration": {"type": "number", "description": "课时时长（小时，可选）"},
            "content": {"type": "string", "description": "内容概要（可选）"},
            "references": {"type": "array", "items": {"type": "string"}, "description": "参考资料（可选）"},
        },
        "required": ["course_id", "lesson_title"],
    }

    def execute(self, course_id: str, lesson_title: str, lesson_number: Optional[int] = None,
                duration: Optional[float] = None, content: Optional[str] = None,
                references: Optional[List[str]] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            if "lessons" not in course:
                course["lessons"] = []

            # 确定课时编号
            if lesson_number is None:
                existing_numbers = [l.get("lesson_number", i+1) for i, l in enumerate(course["lessons"])]
                lesson_number = max(existing_numbers + [0]) + 1

            # 创建新课时
            new_lesson = {
                "lesson_number": lesson_number,
                "lesson_title": lesson_title,
            }
            if duration is not None:
                new_lesson["duration"] = duration
            if content:
                new_lesson["content"] = content
            if references:
                new_lesson["references"] = references

            # 插入或替换
            inserted = False
            for i, lesson in enumerate(course["lessons"]):
                if lesson.get("lesson_number") == lesson_number:
                    course["lessons"][i] = new_lesson
                    inserted = True
                    break
            if not inserted:
                course["lessons"].append(new_lesson)
                # 按课时编号排序
                course["lessons"].sort(key=lambda x: x.get("lesson_number", 0))

            self.ws2_system._save_data()

            lines = [
                f"✅ 课时已添加",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"课程：{course.get('course_title', '')}",
                f"课时 #{lesson_number}：{lesson_title}"
            ]

            return self._make_result(True, {
                "course_id": course_id,
                "lesson_number": lesson_number,
                "lesson": new_lesson
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class UpdateLessonTool(WS2BaseTool):
    name = "ws2_update_lesson"
    description = "更新课时信息"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "lesson_number": {"type": "integer", "description": "课时编号"},
            "lesson_title": {"type": "string", "description": "课时标题（可选）"},
            "duration": {"type": "number", "description": "课时时长（可选）"},
            "content": {"type": "string", "description": "内容概要（可选）"},
        },
        "required": ["course_id", "lesson_number"],
    }

    def execute(self, course_id: str, lesson_number: int, **kwargs) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            # 查找课时
            lesson = None
            lesson_idx = -1
            for i, l in enumerate(course.get("lessons", [])):
                if l.get("lesson_number") == lesson_number:
                    lesson = l
                    lesson_idx = i
                    break

            if not lesson:
                return self._make_result(False, {}, error=f"未找到课时 #{lesson_number}")

            # 更新字段
            updated_fields = []
            for key, value in kwargs.items():
                if value is not None:
                    lesson[key] = value
                    updated_fields.append(key)

            self.ws2_system._save_data()

            lines = [
                f"✅ 课时已更新",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"课程：{course.get('course_title', '')}",
                f"课时 #{lesson_number}"
            ]
            for field in updated_fields:
                lines.append(f"  • {field} = {kwargs[field]}")

            return self._make_result(True, {
                "course_id": course_id,
                "lesson_number": lesson_number,
                "updated_fields": updated_fields
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RemoveLessonTool(WS2BaseTool):
    name = "ws2_remove_lesson"
    description = "删除课程中的指定课时"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "lesson_number": {"type": "integer", "description": "课时编号"},
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
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            # 查找并删除课时
            lessons = course.get("lessons", [])
            removed = False
            removed_title = ""
            for i, l in enumerate(lessons):
                if l.get("lesson_number") == lesson_number:
                    removed_title = l.get("lesson_title", "")
                    del lessons[i]
                    removed = True
                    break

            if not removed:
                return self._make_result(False, {}, error=f"未找到课时 #{lesson_number}")

            # 更新进度数据（删除已完成记录）
            course_key = course.get("note_id", course.get("course_title", ""))
            if course_key in self.ws2_system.progress:
                completed = self.ws2_system.progress[course_key].get("completed_lessons", [])
                if lesson_number in completed:
                    completed.remove(lesson_number)
                    self.ws2_system._save_progress()

            self.ws2_system._save_data()

            lines = [
                f"✅ 课时已删除",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"课程：{course.get('course_title', '')}",
                f"已删除课时 #{lesson_number}：{removed_title}"
            ]

            return self._make_result(True, {
                "course_id": course_id,
                "lesson_number": lesson_number,
                "lesson_title": removed_title
            }, "\n".join(lines))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 13. 资源管理工具
# ============================================================

class AddResourceTool(WS2BaseTool):
    name = "ws2_add_resource"
    description = "添加资源到课程"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "resource_type": {"type": "string", "description": "资源类型 (pdf/url/video/image/note/code)"},
            "label": {"type": "string", "description": "资源标签"},
            "path": {"type": "string", "description": "文件路径（本地文件，可选）"},
            "url": {"type": "string", "description": "URL（网络资源，可选）"},
            "lesson_number": {"type": "integer", "description": "关联的课时编号（可选）"},
        },
        "required": ["course_id", "resource_type", "label"],
    }

    def execute(self, course_id: str, resource_type: str, label: str,
                path: Optional[str] = None, url: Optional[str] = None,
                lesson_number: Optional[int] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        if not self.ws2_system.rmgr:
            return self._make_result(False, {}, error="资源管理器未初始化")

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            course_key = course.get("note_id", course.get("course_title", ""))

            # 创建资源条目
            entry = {"type": resource_type, "label": label}
            if path:
                entry["path"] = path
            if url:
                entry["url"] = url
            if lesson_number:
                entry["lesson_number"] = lesson_number

            added = self.ws2_system.rmgr.add_entry(course_key, entry)

            if added:
                return self._make_result(True, {
                    "course_id": course_id,
                    "resource": entry
                }, f"✅ 资源已添加：{label}")
            else:
                return self._make_result(False, {}, error="资源已存在或添加失败")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RemoveResourceTool(WS2BaseTool):
    name = "ws2_remove_resource"
    description = "删除课程中的资源"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "label": {"type": "string", "description": "资源标签（可选，不指定则列出可选资源）"},
        },
        "required": ["course_id"],
    }

    def execute(self, course_id: str, label: Optional[str] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        if not self.ws2_system.rmgr:
            return self._make_result(False, {}, error="资源管理器未初始化")

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            course_key = course.get("note_id", course.get("course_title", ""))
            resources = self.ws2_system.rmgr.get(course_key)

            if not resources:
                return self._make_result(True, {}, f"ℹ️ 课程无资源：{course.get('course_title', '')}")

            if not label:
                lines = [
                    f"📁 课程资源列表",
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    f"课程：{course.get('course_title', '')}",
                    f"\n请提供 label 参数删除资源，可选资源："
                ]
                for r in resources:
                    lines.append(f"  • {r.get('label', '')} ({r.get('type', '')})")
                return self._make_result(True, {"resources": resources}, "\n".join(lines))

            # 查找并删除
            removed = False
            for r in resources:
                if r.get("label") == label:
                    self.ws2_system.rmgr.remove(course_key, r)
                    removed = True
                    break

            if removed:
                return self._make_result(True, {}, f"✅ 资源已删除：{label}")
            else:
                return self._make_result(False, {}, error=f"未找到资源：{label}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 14. 快速访问工具
# ============================================================

class OpenCourseNoteTool(WS2BaseTool):
    name = "ws2_open_course_note"
    description = "使用默认程序打开课程的笔记文件或目录"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "filename": {"type": "string", "description": "笔记文件名（可选，不指定则打开课程目录）"},
        },
        "required": ["course_id"],
    }

    def execute(self, course_id: str, filename: Optional[str] = None) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        try:
            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            # 尝试使用 course_tracker 中的 open_file 函数
            import sys
            import os
            from pathlib import Path
            import subprocess

            # 查找 Notes 目录
            base_dir = self._base_dir if self._base_dir else Path(__file__).parent.parent
            notes_dir = base_dir / "Notes"

            if not notes_dir.exists():
                notes_dir = base_dir.parent / "Notes"

            if not notes_dir.exists():
                return self._make_result(False, {}, error="Notes 目录不存在")

            course_title = course.get("course_title", "").replace("/", "_").replace("\\", "_")
            course_dir = notes_dir / course_title

            if filename:
                target = course_dir / filename
            else:
                target = course_dir

            if not target.exists():
                return self._make_result(False, {}, error=f"目标不存在：{target}")

            # 使用系统默认程序打开
            if sys.platform == "win32":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target)])
            else:
                subprocess.run(["xdg-open", str(target)])

            return self._make_result(True, {
                "course_id": course_id,
                "target": str(target)
            }, f"✅ 已打开：{target}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class OpenResourceTool(WS2BaseTool):
    name = "ws2_open_resource"
    description = "打开课程资源（PDF、URL 等）"
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "string", "description": "课程 ID 或标题"},
            "label": {"type": "string", "description": "资源标签"},
        },
        "required": ["course_id", "label"],
    }

    def execute(self, course_id: str, label: str) -> str:
        err = self._check_ws2()
        if err:
            return self._make_result(False, {}, error=err)

        if not self.ws2_system.rmgr:
            return self._make_result(False, {}, error="资源管理器未初始化")

        try:
            import sys
            import os
            import webbrowser
            from pathlib import Path
            import subprocess

            course = self.ws2_system.get_course_by_id(course_id)
            if not course:
                return self._make_result(False, {}, error=f"未找到课程：{course_id}")

            course_key = course.get("note_id", course.get("course_title", ""))
            resources = self.ws2_system.rmgr.get(course_key)

            resource = None
            for r in resources:
                if r.get("label") == label:
                    resource = r
                    break

            if not resource:
                return self._make_result(False, {}, error=f"未找到资源：{label}")

            # 尝试打开
            url = resource.get("url", "")
            path = resource.get("path", "")

            if url:
                webbrowser.open(url)
                return self._make_result(True, {
                    "course_id": course_id,
                    "label": label,
                    "url": url
                }, f"✅ 已打开 URL：{url}")

            if path:
                base_dir = self._base_dir if self._base_dir else Path(__file__).parent.parent
                full_path = Path(path) if Path(path).is_absolute() else base_dir / path

                if full_path.exists():
                    if sys.platform == "win32":
                        os.startfile(str(full_path))
                    elif sys.platform == "darwin":
                        subprocess.run(["open", str(full_path)])
                    else:
                        subprocess.run(["xdg-open", str(full_path)])

                    return self._make_result(True, {
                        "course_id": course_id,
                        "label": label,
                        "path": str(full_path)
                    }, f"✅ 已打开文件：{full_path}")
                else:
                    return self._make_result(False, {}, error=f"文件不存在：{full_path}")

            return self._make_result(False, {}, error="资源没有 URL 或路径")
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
        # 课程信息修改
        UpdateCourseInfoTool(**common_kwargs),
        # 课时学习
        MarkLessonCompleteTool(**common_kwargs),
        GetNextLessonTool(**common_kwargs),
        GetCourseProgressTool(**common_kwargs),
        # 课时管理
        AddLessonTool(**common_kwargs),
        UpdateLessonTool(**common_kwargs),
        RemoveLessonTool(**common_kwargs),
        # 复习调度
        GetReviewScheduleTool(**common_kwargs),
        MarkReviewDoneTool(**common_kwargs),
        # 资源管理
        GetResourcesTool(**common_kwargs),
        AddResourceTool(**common_kwargs),
        RemoveResourceTool(**common_kwargs),
        # 书签管理（使用共享 BookmarkManager）
        ListBookmarksTool(**common_kwargs),
        SearchBookmarksTool(**common_kwargs),
        ListBookmarkCategoriesTool(**common_kwargs),
        AddBookmarkTool(**common_kwargs),
        DeleteBookmarkTool(**common_kwargs),
        UpdateBookmarkTool(**common_kwargs),
        # 笔记管理（使用共享 NotesManager）
        ListNotesTool(**note_kwargs),
        ReadNoteTool(**note_kwargs),
        WriteNoteTool(**note_kwargs),
        DeleteNoteTool(**note_kwargs),
        SearchNotesTool(**note_kwargs),
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
        # 快速访问
        OpenCourseNoteTool(**common_kwargs),
        OpenResourceTool(**common_kwargs),
        # Rmd 管理（使用共享 NotesManager）
        ListRmdFilesTool(**note_kwargs),
        KnitRmdTool(**note_kwargs),
        KnitAndOpenRmdTool(**note_kwargs),
        # 自动化工具
        ListAutomationTasksTool(**common_kwargs),
        CreateAutomationTaskTool(**common_kwargs),
        ToggleAutomationTaskTool(**common_kwargs),
        RunAutomationTaskTool(**common_kwargs),
        # 课程系统工具
        GetCourseTimetableTool(**common_kwargs),
        AddCourseToTimetableTool(**common_kwargs),
        GetCurrentCourseTool(**common_kwargs),
        # 学术搜索聚合工具
        ScholarSearchTool(),
        ScholarGetByDoiTool(),
        ScholarSearchGeneTool(),
        ScholarSearchProteinTool(),
        # 文本链接解析工具
        ParseTextLinksTool(**common_kwargs),
        ImportLinksToHubTool(**common_kwargs),
    ]


# ============================================================
# 17. 自动化与课程系统工具
# ============================================================

class AutomationBaseTool(WS2BaseTool):
    """自动化工具基类"""

    def __init__(self, ws2_system=None, project_manager=None, task_board_manager=None, base_dir=None,
                 bookmark_manager=None, automation_engine=None, event_bus=None):
        super().__init__(ws2_system, project_manager, task_board_manager, base_dir, bookmark_manager)
        self._automation_engine = automation_engine
        self._event_bus = event_bus

    def _get_engine(self):
        """获取自动化引擎"""
        if self._automation_engine:
            return self._automation_engine
        try:
            from ..automation.engine import get_automation_engine
            return get_automation_engine()
        except Exception:
            return None


class ListAutomationTasksTool(AutomationBaseTool):
    name = "ws2_list_automation_tasks"
    description = "列出所有自动化任务及其状态"
    parameters = {
        "type": "object",
        "properties": {
            "enabled_only": {"type": "boolean", "description": "仅显示已启用的任务"},
        },
    }

    def execute(self, enabled_only: bool = False) -> str:
        engine = self._get_engine()
        if not engine:
            return self._make_result(False, {}, "自动化引擎未初始化")

        try:
            tasks = engine.list_tasks(enabled_only=enabled_only)
            data = [{
                "name": t.name,
                "task_type": t.task_type,
                "trigger_type": t.trigger_type,
                "enabled": t.enabled,
                "interval_minutes": t.interval_minutes if hasattr(t, 'interval_minutes') else None,
            } for t in tasks]
            return self._make_result(True, {"count": len(data), "tasks": data}, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class CreateAutomationTaskTool(AutomationBaseTool):
    name = "ws2_create_automation_task"
    description = "创建新的自动化任务"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "任务名称"},
            "task_type": {"type": "string", "description": "任务类型 (scheduled/event/manual)"},
            "trigger_type": {"type": "string", "description": "触发类型 (interval/cron/event)"},
            "interval_minutes": {"type": "integer", "description": "间隔时间（分钟）"},
            "action_config": {"type": "object", "description": "动作配置"},
        },
        "required": ["name", "task_type", "trigger_type"],
    }

    def execute(self, name: str, task_type: str, trigger_type: str,
                interval_minutes: Optional[int] = None, action_config: Optional[Dict] = None) -> str:
        engine = self._get_engine()
        if not engine:
            return self._make_result(False, {}, "自动化引擎未初始化")

        try:
            task_id = engine.create_task(
                name=name,
                task_type=task_type,
                trigger_type=trigger_type,
                interval_minutes=interval_minutes,
                action_config=action_config or {},
            )
            return self._make_result(True, {"task_id": task_id, "name": name}, f"任务已创建: {name} (ID: {task_id})")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ToggleAutomationTaskTool(AutomationBaseTool):
    name = "ws2_toggle_automation_task"
    description = "启用或禁用自动化任务"
    parameters = {
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "任务名称"},
            "enabled": {"type": "boolean", "description": "启用或禁用"},
        },
        "required": ["task_name", "enabled"],
    }

    def execute(self, task_name: str, enabled: bool) -> str:
        engine = self._get_engine()
        if not engine:
            return self._make_result(False, {}, "自动化引擎未初始化")

        try:
            engine.toggle_task(task_name, enabled)
            return self._make_result(True, {"task_name": task_name, "enabled": enabled},
                                      f"任务 {'启用' if enabled else '禁用'}成功: {task_name}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class RunAutomationTaskTool(AutomationBaseTool):
    name = "ws2_run_automation_task"
    description = "手动执行自动化任务"
    parameters = {
        "type": "object",
        "properties": {
            "task_name": {"type": "string", "description": "任务名称"},
        },
        "required": ["task_name"],
    }

    def execute(self, task_name: str) -> str:
        engine = self._get_engine()
        if not engine:
            return self._make_result(False, {}, "自动化引擎未初始化")

        try:
            result = engine.run_task(task_name)
            return self._make_result(True, {"task_name": task_name, "result": result}, f"任务执行完成: {task_name}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCourseTimetableTool(WS2BaseTool):
    name = "ws2_get_course_timetable"
    description = "获取课程系统课表信息"
    parameters = {
        "type": "object",
        "properties": {
            "day_of_week": {"type": "integer", "description": "星期几 (1-7)"},
        },
    }

    def execute(self, day_of_week: Optional[int] = None) -> str:
        if not self.ws2_system or not hasattr(self.ws2_system, '_course_sim_engine'):
            return self._make_result(False, {}, "课程系统未初始化")

        try:
            engine = self.ws2_system._course_sim_engine
            tt = engine.get_active_timetable()
            if not tt:
                return self._make_result(False, {}, "课表不存在")

            slots = tt.slots
            if day_of_week:
                slots = [s for s in slots if s.day_of_week == day_of_week]

            data = [{
                "course_name": s.course_name,
                "day": s.day_of_week,
                "time": f"{s.start_time}-{s.end_time}",
                "location": s.location,
                "teacher": s.teacher,
            } for s in slots]

            return self._make_result(True, {"count": len(data), "timetable": data},
                                      f"课表共有 {len(data)} 个课时\n" + json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class AddCourseToTimetableTool(WS2BaseTool):
    name = "ws2_add_course_to_timetable"
    description = "添加课程到课表"
    parameters = {
        "type": "object",
        "properties": {
            "course_name": {"type": "string", "description": "课程名称"},
            "day_of_week": {"type": "integer", "description": "星期几 (1-7)"},
            "start_time": {"type": "string", "description": "开始时间 (如 08:00)"},
            "end_time": {"type": "string", "description": "结束时间 (如 08:45)"},
            "location": {"type": "string", "description": "上课地点"},
        },
        "required": ["course_name", "day_of_week", "start_time", "end_time"],
    }

    def execute(self, course_name: str, day_of_week: int, start_time: str,
                end_time: str, location: Optional[str] = None) -> str:
        if not self.ws2_system or not hasattr(self.ws2_system, '_course_sim_engine'):
            return self._make_result(False, {}, "课程系统未初始化")

        try:
            from ..automation.course_simulation import TimetableSlot, PERIODS

            period_idx = 0
            for idx, p in enumerate(PERIODS):
                if p[1] == start_time:
                    period_idx = idx
                    break

            slot = TimetableSlot(
                slot_id="",
                course_id=course_name,
                course_name=course_name,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                period_idx=period_idx,
                location=location or "",
            )

            engine = self.ws2_system._course_sim_engine
            tt = engine.get_active_timetable()
            engine.add_slot(tt.timetable_id, slot)

            return self._make_result(True, {"course": course_name, "day": day_of_week, "time": f"{start_time}-{end_time}"},
                                      f"已添加 {course_name} 到课表")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class GetCurrentCourseTool(WS2BaseTool):
    name = "ws2_get_current_course"
    description = "获取当前正在进行的课程（如果有）"
    parameters = {"type": "object", "properties": {}}

    def execute(self) -> str:
        if not self.ws2_system or not hasattr(self.ws2_system, '_course_sim_engine'):
            return self._make_result(False, {}, "课程系统未初始化")

        try:
            engine = self.ws2_system._course_sim_engine
            slot = engine.get_current_slot()
            if slot:
                data = {
                    "course_name": slot.course_name,
                    "day": slot.day_of_week,
                    "time": f"{slot.start_time}-{slot.end_time}",
                    "location": slot.location,
                }
                return self._make_result(True, data, f"当前课程: {slot.course_name} ({slot.start_time}-{slot.end_time})")
            else:
                return self._make_result(True, {}, "当前没有正在进行的课程")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 18. 学术搜索聚合工具
# ============================================================

class ScholarSearchTool(Tool):
    name = "ws2_scholar_search"
    description = "聚合搜索学术论文，支持 OpenAlex、Crossref、Semantic Scholar、arXiv 等数据库"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "每个来源最多返回结果数"},
            "domains": {"type": "array", "items": {"type": "string"},
                       "description": "限定搜索领域 (physics/chemistry/biology/cs 等)"},
        },
        "required": ["query"],
    }

    def __init__(self):
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from mcp.scholar.adapters.openalex import OpenAlexAdapter
            from mcp.scholar.adapters.crossref import CrossrefAdapter
            from mcp.scholar.adapters.semantic_scholar import SemanticScholarAdapter
            from mcp.scholar.adapters.arxiv import ArxivAdapter
            from mcp.scholar.adapters.core_ac import CoreAcAdapter
            self._openalex = OpenAlexAdapter()
            self._crossref = CrossrefAdapter()
            self._semantic = SemanticScholarAdapter()
            self._arxiv = ArxivAdapter()
            self._core = CoreAcAdapter()
            self._available = True
        except ImportError as e:
            self._available = False
            if 'logger' in dir():
                logger.warning(f"学术搜索模块导入失败: {e}")
            else:
                import logging
                logging.getLogger(__name__).warning(f"学术搜索模块导入失败: {e}")

    def execute(self, query: str, max_results: int = 5,
                domains: Optional[List[str]] = None) -> str:
        if not self._available:
            return self._make_result(False, {}, "学术搜索模块未安装")

        results = []
        try:
            r1 = self._openalex.search(query, per_page=max_results)
            if r1.success:
                results.append({"source": "OpenAlex", "data": r1.data})

            r2 = self._crossref.search(query, rows=max_results)
            if r2.success:
                results.append({"source": "Crossref", "data": r2.data})

            r3 = self._semantic.search(query, limit=max_results)
            if r3.success:
                results.append({"source": "SemanticScholar", "data": r3.data})

            r4 = self._arxiv.search(query, max_results=max_results)
            if r4.success:
                results.append({"source": "arXiv", "data": r4.data})

            r5 = self._core.search(query, limit=max_results)
            if r5.success:
                results.append({"source": "CORE", "data": r5.data})

            summary = f"从 {len(results)} 个来源获取到结果\n\n"
            for r in results:
                count = len(r["data"]) if r["data"] else 0
                summary += f"[{r['source']}] {count} 条结果\n"

            return self._make_result(True, {"sources": len(results), "results": results}, summary)
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ScholarGetByDoiTool(Tool):
    name = "ws2_scholar_get_by_doi"
    description = "通过 DOI 获取论文元数据"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI 标识符"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from mcp.scholar.adapters.crossref import CrossrefAdapter
            from mcp.scholar.adapters.semantic_scholar import SemanticScholarAdapter
            from mcp.scholar.adapters.openalex import OpenAlexAdapter
            self._crossref = CrossrefAdapter()
            self._semantic = SemanticScholarAdapter()
            self._openalex = OpenAlexAdapter()
            self._available = True
        except ImportError:
            self._available = False

    def execute(self, doi: str) -> str:
        if not self._available:
            return self._make_result(False, {}, "学术搜索模块未安装")

        try:
            results = []
            for adapter, name in [(self._crossref, "Crossref"),
                                   (self._semantic, "SemanticScholar"),
                                   (self._openalex, "OpenAlex")]:
                try:
                    r = adapter.get_by_doi(doi)
                    if r.success:
                        results.append({"source": name, "data": r.data})
                except Exception:
                    pass

            if results:
                return self._make_result(True, {"doi": doi, "sources": len(results), "results": results},
                                          f"从 {len(results)} 个来源获取到 DOI 文献信息")
            return self._make_result(False, {}, "未找到该 DOI 对应的文献")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ScholarSearchGeneTool(Tool):
    name = "ws2_scholar_search_gene"
    description = "搜索基因相关信息（MyGene）"
    parameters = {
        "type": "object",
        "properties": {
            "gene": {"type": "string", "description": "基因名称或符号"},
        },
        "required": ["gene"],
    }

    def __init__(self):
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from mcp.scholar.adapters.mygene import MyGeneAdapter
            self._adapter = MyGeneAdapter()
            self._available = True
        except ImportError:
            self._available = False

    def execute(self, gene: str) -> str:
        if not self._available:
            return self._make_result(False, {}, "MyGene 模块未安装")

        try:
            r = self._adapter.search(gene)
            if r.success:
                return self._make_result(True, {"gene": gene, "data": r.data},
                                          f"找到基因 {gene} 的信息")
            return self._make_result(False, {}, f"未找到基因 {gene}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


class ScholarSearchProteinTool(Tool):
    name = "ws2_scholar_search_protein"
    description = "搜索蛋白质结构信息（RCSB PDB）"
    parameters = {
        "type": "object",
        "properties": {
            "protein": {"type": "string", "description": "蛋白质名称或 PDB ID"},
        },
        "required": ["protein"],
    }

    def __init__(self):
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from mcp.scholar.adapters.rcsb_pdb import RcsbPdbAdapter
            self._adapter = RcsbPdbAdapter()
            self._available = True
        except ImportError:
            self._available = False

    def execute(self, protein: str) -> str:
        if not self._available:
            return self._make_result(False, {}, "RCSB PDB 模块未安装")

        try:
            r = self._adapter.search(protein)
            if r.success:
                return self._make_result(True, {"protein": protein, "data": r.data},
                                          f"找到蛋白质 {protein} 的结构信息")
            return self._make_result(False, {}, f"未找到蛋白质 {protein}")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))


# ============================================================
# 19. 文本链接解析工具
# ============================================================

class ParseTextLinksTool(WS2BaseTool):
    name = "ws2_parse_text_links"
    description = "解析文本中的URL、DOI、arXiv、邮箱等链接"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要解析的文本内容"},
        },
        "required": ["text"],
    }

    def execute(self, text: str) -> str:
        import re
        from urllib.parse import urlparse
        
        url_pattern = r'https?://[^\s<>"\')\]]+'
        doi_pattern = r'(?:doi[:\s]*)?(?:https?://(?:dx\.)?doi\.org/)?10\.\d{4,}[^\s<>"\')\]]*'
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        arxiv_pattern = r'arxiv:(?:org/)?(\d+\.\d+)'
        
        found_links = []
        
        for match in re.finditer(url_pattern, text):
            url = match.group()
            parsed = urlparse(url)
            domain = parsed.netloc
            
            link_type = "URL"
            if 'arxiv.org' in domain:
                link_type = "arXiv"
            elif 'github.com' in domain:
                link_type = "GitHub"
            elif 'doi.org' in domain or 'dx.doi.org' in domain:
                link_type = "DOI"
            elif 'pubmed' in domain or 'ncbi.nlm.nih.gov' in domain:
                link_type = "PubMed"
            elif 'nature.com' in domain:
                link_type = "Nature"
            elif 'science.org' in domain:
                link_type = "Science"
            elif 'ieee.org' in domain:
                link_type = "IEEE"
            elif 'acm.org' in domain:
                link_type = "ACM"
            elif 'scholar.google' in domain:
                link_type = "GoogleScholar"
            
            found_links.append({
                "type": link_type,
                "url": url,
            })
        
        for match in re.finditer(doi_pattern, text, re.IGNORECASE):
            doi = match.group()
            if not doi.startswith('http'):
                doi = f"https://doi.org/{doi.replace('doi:', '').strip()}"
            found_links.append({"type": "DOI", "url": doi})
        
        for match in re.finditer(email_pattern, text):
            email = match.group()
            found_links.append({"type": "Email", "url": f"mailto:{email}"})
        
        for match in re.finditer(arxiv_pattern, text, re.IGNORECASE):
            arxiv_id = match.group(1)
            url = f"https://arxiv.org/abs/{arxiv_id}"
            found_links.append({"type": "arXiv", "url": url})
        
        seen = set()
        unique_links = []
        for link in found_links:
            key = link["url"].lower()[:100]
            if key not in seen:
                seen.add(key)
                unique_links.append(link)
        
        if unique_links:
            lines = [f"🔗 解析到 {len(unique_links)} 个链接", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            for i, link in enumerate(unique_links, 1):
                lines.append(f"{i}. [{link['type']}] {link['url']}")
            return self._make_result(True, {"links": unique_links, "count": len(unique_links)}, "\n".join(lines))
        else:
            return self._make_result(False, {}, "未解析到任何链接")


class ImportLinksToHubTool(WS2BaseTool):
    name = "ws2_import_links_to_hub"
    description = "将链接列表导入到数据中心"
    parameters = {
        "type": "object",
        "properties": {
            "links": {"type": "array", "description": "链接列表，每项包含type和url"},
            "source": {"type": "string", "description": "来源说明（可选）"},
        },
        "required": ["links"],
    }

    def execute(self, links: List[Dict], source: Optional[str] = None) -> str:
        try:
            from ws2_data_hub import get_data_hub, HubItem, SourceType, ItemType
            hub = get_data_hub()
            if not hub:
                return self._make_result(False, {}, "数据中心未初始化")
            
            imported = 0
            for link in links:
                url = link.get("url", "")
                link_type = link.get("type", "URL")
                
                if not url:
                    continue
                
                is_paper = any(x in url.lower() for x in ["arxiv", "pubmed", "doi", "nature", "science", "ieee", "acm"])
                item_type = ItemType.PAPER.value if is_paper else ItemType.BOOKMARK.value
                tags = ["scholar", "paper", "auto_import"] if is_paper else ["bookmark", "url", "auto_import"]
                
                hub_item = HubItem(
                    title=f"[{link_type}] {url[:50]}",
                    content=f"从文本解析提取的链接\n\n来源: {source or 'unknown'}",
                    summary=link_type,
                    url=url,
                    source_type=SourceType.ANALYSIS.value,
                    item_type=item_type,
                    tags=tags,
                    metadata={
                        "link_type": link_type,
                        "imported_at": datetime.now().isoformat() if 'datetime' in dir() else "",
                        "source": source,
                    }
                )
                hub.add_item(hub_item)
                imported += 1
            
            return self._make_result(True, {"imported": imported}, f"✅ 已导入 {imported} 个链接到数据中心")
        except ImportError:
            return self._make_result(False, {}, "数据中心模块未安装")
        except Exception as e:
            return self._make_result(False, {}, error=str(e))