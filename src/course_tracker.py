#!/usr/bin/env python3
"""
课程教学管理系统 TS2 — Course Tracking & Progress System
=========================================================
读取 courses_structured.json，GUI 可视化，顺序记录进度，完成消除+弹出下一步
支持三种导入（JSON / 单MD / 批量MD）、课程管理（新建/编辑）、资源管理（PDF/URL）

依赖: tkinter (内置), matplotlib
"""

import json
import os
import re
import sys
import hashlib
import webbrowser
import platform
import subprocess
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import Counter
import numpy as np

# ─── TS2 基础路径 ──────────────────────────────────────────────────────
BASE = Path(__file__).parent

# ─── 跨平台工具函数 ──────────────────────────────────────────────────────
PLATFORM = platform.system().lower()
IS_MAC = PLATFORM == "darwin"

def _on_mousewheel(event, canvas):
    """跨平台鼠标滚轮事件处理"""
    if IS_MAC:
        canvas.yview_scroll(int(-1 * event.delta), "units")
    else:
        canvas.yview_scroll(int(-1 * (event.delta // 120)), "units")

def _on_mousewheel_h(event, canvas):
    """跨平台水平鼠标滚轮事件处理"""
    if IS_MAC:
        canvas.xview_scroll(int(-1 * event.delta), "units")
    else:
        canvas.xview_scroll(int(-1 * (event.delta // 120)), "units")

def open_file(filepath):
    """跨平台打开文件或文件夹（支持 Windows/macOS/Linux）"""
    fp = Path(filepath)
    if not fp.exists():
        return False
    # 确保使用绝对路径
    abs_fp = fp.resolve()
    try:
        if PLATFORM == "windows":
            os.startfile(str(abs_fp))
        elif PLATFORM == "darwin":
            # macOS: 优先尝试用默认应用打开，而不是强制Positron
            try:
                subprocess.run(["open", str(abs_fp)], check=False)
            except Exception:
                # 如果失败，尝试用Positron
                try:
                    subprocess.run(["open", "-a", "Positron", str(abs_fp)], check=False)
                except Exception:
                    # 最后尝试通用方式
                    import shutil
                    try:
                        shutil.open(str(abs_fp))
                    except Exception:
                        pass
        else:
            # Linux
            subprocess.run(["xdg-open", str(abs_fp)], check=False)
    except Exception:
        return False
    return True

def open_url(url):
    """跨平台打开 URL"""
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False

# ============================================================
# JSON 校验层 (TS2 适配)
# ============================================================

def load_json_safe(path):
    """安全加载 JSON，出错返回 None"""
    try:
        p = Path(path) if isinstance(path, str) else path
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def validate_course_json(data):
    """校验 JSON 是否符合 TS2 格式规范，返回 (ok, msg)"""
    if not isinstance(data, dict):
        return False, "根必须是 JSON 对象"
    if "courses" not in data:
        return False, "缺少 'courses' 数组"
    if not isinstance(data["courses"], list):
        return False, "'courses' 必须是数组"
    if len(data["courses"]) == 0:
        return False, "courses 数组为空，至少要有1门课程"
    for idx, c in enumerate(data["courses"]):
        if not isinstance(c, dict):
            return False, f"courses[{idx}] 不是对象"
        if not c.get("course_title", "").strip():
            return False, f"courses[{idx}] 缺少 'course_title' 或为空"
        if "total_hours" not in c:
            return False, f"courses[{idx}] 缺少 'total_hours'"
        if c.get("total_hours") is not None and not isinstance(c["total_hours"], (int, float)):
            return False, f"courses[{idx}] 'total_hours' 必须是数字或 null"
        if "domain" not in c:
            return False, f"courses[{idx}] 缺少 'domain'"
        if "lessons" not in c or not isinstance(c["lessons"], list):
            return False, f"courses[{idx}] 缺少 'lessons' 数组"
        for li, l in enumerate(c["lessons"]):
            if not isinstance(l, dict):
                return False, f"courses[{idx}].lessons[{li}] 不是对象"
            if "lesson_title" not in l:
                return False, f"courses[{idx}].lessons[{li}] 缺少 'lesson_title'"
        if "sections" in c and not isinstance(c["sections"], list):
            return False, f"courses[{idx}] 'sections' 必须是数组"
    return True, f"校验通过: {len(data['courses'])} 门课程，格式正确"


# ============================================================
# 资源管理层
# ============================================================

class ResourceMgr:
    """PDF/URL/Video/Image 资源索引管理"""

    RESOURCE_ICONS = {"pdf": "📄", "url": "🌐", "video": "🎬", "image": "🖼️", "note": "📝", "code": "💻"}

    def __init__(self, filepath):
        self.path = Path(filepath) if isinstance(filepath, str) else filepath
        self.data = self._load()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def reload(self):
        """重新从磁盘加载资源索引"""
        self.data = self._load()

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, course_key):
        """获取课程资源列表，key 可以是 note_id 或 course_title"""
        return self.data.get(course_key, [])

    def _dedup_key(self, entry):
        t = entry.get("type", "")
        if t == "pdf":
            return f"pdf:{entry.get('path','')}:{entry.get('lesson_number','')}"
        if t == "url":
            return f"url:{entry.get('url','')}:{entry.get('lesson_number','')}"
        if t == "video":
            return f"video:{entry.get('url', entry.get('path',''))}:{entry.get('lesson_number','')}"
        if t == "image":
            return f"image:{entry.get('path','')}:{entry.get('lesson_number','')}"
        return f"{t}:{entry.get('url', entry.get('path',''))}:{entry.get('lesson_number','')}"

    def add_entry(self, course_key, entry):
        self.data.setdefault(course_key, [])
        dk = self._dedup_key(entry)
        for r in self.data[course_key]:
            if self._dedup_key(r) == dk:
                return False
        self.data[course_key].append(entry)
        self.save()
        return True

    def add_pdf(self, course_key, filepath, base_dir, lesson_number=None):
        fp = Path(filepath)
        try:
            rel = fp.relative_to(base_dir)
        except ValueError:
            rel = fp
        name = fp.stem[:30]
        path_str = str(rel.as_posix())
        self.data.setdefault(course_key, [])
        for r in self.data[course_key]:
            if r.get("type") == "pdf" and r.get("path") == path_str and r.get("lesson_number") == lesson_number:
                return False
        entry = {"type": "pdf", "label": f"📄 {name}", "path": path_str}
        if lesson_number is not None:
            entry["lesson_number"] = lesson_number
        self.data[course_key].append(entry)
        self.save()
        return True

    def add_url(self, course_key, label, url, lesson_number=None):
        entry = {"type": "url", "label": f"🌐 {label}", "url": url}
        if lesson_number is not None:
            entry["lesson_number"] = lesson_number
        return self.add_entry(course_key, entry)

    def add_video(self, course_key, label, url=None, filepath=None, base_dir=None, lesson_number=None):
        if filepath and base_dir:
            fp = Path(filepath)
            try:
                rel = fp.relative_to(base_dir)
            except ValueError:
                rel = fp
            path_str = str(rel.as_posix())
            name = fp.stem[:30]
            entry = {"type": "video", "label": f"🎬 {label or name}", "path": path_str}
        else:
            entry = {"type": "video", "label": f"🎬 {label}", "url": url or ""}
        if lesson_number is not None:
            entry["lesson_number"] = lesson_number
        return self.add_entry(course_key, entry)

    def add_image(self, course_key, filepath, base_dir, lesson_number=None, caption=""):
        fp = Path(filepath)
        try:
            rel = fp.relative_to(base_dir)
        except ValueError:
            rel = fp
        name = fp.stem[:30]
        path_str = str(rel.as_posix())
        entry = {"type": "image", "label": f"🖼️ {caption or name}", "path": path_str}
        if lesson_number is not None:
            entry["lesson_number"] = lesson_number
        return self.add_entry(course_key, entry)

    def get_for_lesson(self, course_key, lesson_number):
        """获取课时级资源"""
        result = []
        for r in self.data.get(course_key, []):
            if r.get("lesson_number") == lesson_number:
                result.append(r)
        return result

    def get_for_course(self, course_key):
        """获取课程级资源（无 lesson_number 字段的）"""
        result = []
        for r in self.data.get(course_key, []):
            if "lesson_number" not in r:
                result.append(r)
        return result

    def remove(self, course_key, resource):
        """删除指定资源条目（按 dedup_key 匹配）"""
        entries = self.data.get(course_key, [])
        dk = self._dedup_key(resource)
        for i, r in enumerate(entries):
            if self._dedup_key(r) == dk:
                entries.pop(i)
                self.save()
                return True
        return False


# ============================================================
# 数据层
# ============================================================

class ProjectManager:
    """项目管理数据管理 - 类似IDE的项目空间"""
    
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else BASE
        self.data_file = self.data_dir / "projects.json"
        self.projects = self._load_projects()
    
    def _load_projects(self):
        """加载项目数据"""
        if self.data_file.exists():
            try:
                projects = json.loads(self.data_file.read_text(encoding="utf-8"))
                return projects
            except Exception:
                pass
        return []
    
    def _save_projects(self):
        """保存项目数据"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(self.projects, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def create_project(self, name, description, folder_path, tags=None):
        """创建新项目"""
        project = {
            "id": f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "name": name,
            "description": description,
            "folder_path": str(Path(folder_path).resolve()),
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "last_opened": None,
            "status": "active",  # active, archived, completed
            "metadata": {
                "files": [],
                "notes": [],
                "tasks": []
            }
        }
        
        # 创建项目配置文件
        proj_folder = Path(folder_path)
        proj_folder.mkdir(parents=True, exist_ok=True)
        proj_config = proj_folder / ".ts2_project.json"
        proj_config.write_text(json.dumps({
            "project_id": project["id"],
            "name": name,
            "created_at": project["created_at"]
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        
        self.projects.append(project)
        self._save_projects()
        return project
    
    def open_project(self, project_id):
        """打开项目"""
        for proj in self.projects:
            if proj["id"] == project_id:
                proj["last_opened"] = datetime.now().isoformat()
                self._save_projects()
                return proj
        return None
    
    def update_project(self, project_id, **kwargs):
        """更新项目"""
        for proj in self.projects:
            if proj["id"] == project_id:
                proj.update(kwargs)
                proj["last_updated"] = datetime.now().isoformat()
                self._save_projects()
                return proj
        return None
    
    def delete_project(self, project_id, delete_folder=False):
        """删除项目"""
        proj_to_delete = None
        for i, proj in enumerate(self.projects):
            if proj["id"] == project_id:
                proj_to_delete = proj
                del self.projects[i]
                break
        
        if proj_to_delete and delete_folder:
            try:
                folder = Path(proj_to_delete["folder_path"])
                if folder.exists():
                    import shutil
                    shutil.rmtree(folder)
            except Exception:
                pass
        
        self._save_projects()
    
    def get_all_projects(self):
        """获取所有项目"""
        return self.projects
    
    def get_project_by_id(self, project_id):
        """根据ID获取项目"""
        for proj in self.projects:
            if proj["id"] == project_id:
                return proj
        return None


class TaskBoardManager:
    """任务看板数据管理"""
    
    TASK_STATUS = ["待办", "进行中", "已完成", "已归档"]
    TASK_PRIORITIES = ["高", "中", "低"]
    RECURRENCE_TYPES = ["不循环", "每天", "每周", "每月", "每年"]
    
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else BASE
        self.data_file = self.data_dir / "task_board.json"
        self.tasks = self._load_tasks()
    
    def _load_tasks(self):
        """加载任务数据"""
        if self.data_file.exists():
            try:
                tasks = json.loads(self.data_file.read_text(encoding="utf-8"))
                # 为旧任务添加时间字段
                for task in tasks:
                    if "start_time" not in task:
                        task["start_time"] = "09:00"  # 默认上午9点开始
                    if "duration" not in task:
                        task["duration"] = 60  # 默认60分钟
                    if "recurrence" not in task:
                        task["recurrence"] = "不循环"
                    if "recurrence_end" not in task:
                        task["recurrence_end"] = None
                return tasks
            except Exception:
                pass
        return []
    
    def _save_tasks(self):
        """保存任务数据"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(self.tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def add_task(self, title, description="", due_date=None, priority="中", status="待办", start_time="09:00", duration=60, recurrence="不循环", recurrence_end=None):
        """添加新任务"""
        task = {
            "id": f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "title": title,
            "description": description,
            "due_date": due_date,
            "priority": priority,
            "status": status,
            "start_time": start_time,
            "duration": duration,
            "recurrence": recurrence,
            "recurrence_end": recurrence_end,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.tasks.append(task)
        self._save_tasks()
        return task
    
    def update_task(self, task_id, **kwargs):
        """更新任务"""
        for task in self.tasks:
            if task["id"] == task_id:
                task.update(kwargs)
                task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_tasks()
                return task
        return None
    
    def delete_task(self, task_id):
        """删除任务"""
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self._save_tasks()
    
    def get_tasks_by_date(self, date_str):
        """获取指定日期的任务"""
        return [t for t in self.tasks if t.get("due_date") == date_str]
    
    def get_tasks_by_status(self, status):
        """获取指定状态的任务"""
        return [t for t in self.tasks if t.get("status") == status]
    
    def get_all_tasks(self):
        """获取所有任务"""
        return self.tasks
    
    def get_dates_with_tasks(self):
        """获取有任务的日期集合"""
        dates = set()
        for task in self.tasks:
            due_date = task.get("due_date")
            if due_date:
                dates.add(due_date)
        return dates


class CourseSystem:
    """课程系统数据模型、进度管理与多源数据库"""

    def __init__(self, json_path: str = None, progress_path: str = None, resource_path: str = None):
        self.json_path = json_path
        self.progress_path = progress_path
        self.resource_path = resource_path
        self.data = {}
        self.progress = {}
        self.courses = []
        self.metadata = {}
        self.db_paths = []          # 多源数据库路径
        self.rmgr = None           # 资源管理器
        self._init_paths()
        self._load_data()
        self._load_progress()
        self._init_resource_mgr()

    # 排除的 JSON 文件名（进度/资源等非课程数据）
    _EXCLUDED_JSON = {"courses_structured_progress.json", "resource_index.json",
                      "courses_structured_progress.bak.json"}

    def _init_paths(self):
        """初始化默认路径，并自动扫描目录下所有课程 JSON 文件"""
        if self.json_path is None:
            self.json_path = str(BASE / "courses_structured.json")
        if self.progress_path is None:
            self.progress_path = self.json_path.replace(".json", "_progress.json")
        if self.resource_path is None:
            self.resource_path = str(BASE / "resource_index.json")
        # 默认数据库源
        self.db_paths = [Path(self.json_path)]
        # 自动扫描目录下其他包含 courses 的 JSON 文件
        self._auto_discover_json_sources()

    def _auto_discover_json_sources(self):
        """扫描 BASE 目录下所有有效的课程 JSON 文件，自动加入 db_paths"""
        for f in BASE.glob("*.json"):
            if f.name in self._EXCLUDED_JSON:
                continue
            if f in self.db_paths:
                continue
            # 跳过进度文件（文件名含 _progress）
            if "_progress" in f.name:
                continue
            # 尝试读取，检查是否包含 courses 数组
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(d, dict) and isinstance(d.get("courses"), list) and len(d["courses"]) > 0:
                    self.db_paths.append(f)
            except Exception:
                pass

    def _load_data(self):
        """加载主数据文件，然后合并所有数据库源"""
        if os.path.exists(self.json_path):
            with open(self.json_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {"metadata": {}, "courses": []}
        self.metadata = self.data.get("metadata", {})
        self.courses = self.data.get("courses", [])
        # 合并所有已发现的数据库源
        self._merge_all_sources()

    def _merge_all_sources(self):
        """合并 db_paths 中所有源的课程数据（去重）"""
        seen_keys = set()
        # 先记录主文件中已有的课程
        for c in self.courses:
            cid = c.get("note_id", "")
            title = c.get("course_title", "").strip()
            key = cid or title
            if key:
                seen_keys.add(key)
        # 合并其他源
        for p in self.db_paths:
            if p == Path(self.json_path):
                continue  # 主文件已加载
            if not p.exists():
                continue
            d = load_json_safe(p)
            if not d or "courses" not in d:
                continue
            for c in d["courses"]:
                cid = c.get("note_id", "")
                title = c.get("course_title", "").strip()
                key = cid or title
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    self.courses.append(c)

    def _load_progress(self):
        if os.path.exists(self.progress_path):
            with open(self.progress_path, "r", encoding="utf-8") as f:
                self.progress = json.load(f)
        # 确保所有已加载课程都有进度条目（新增源的课程不会被遗漏）
        self._init_progress()
        self._save_progress()

    def _init_progress(self):
        """初始化所有课程的进度"""
        for c in self.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            if cid not in self.progress:
                self.progress[cid] = {
                    "completed_lessons": [],
                    "current_lesson": None,
                    "started_at": None,
                    "last_updated": None,
                    "review_schedule": {},
                }
            elif "review_schedule" not in self.progress[cid]:
                self.progress[cid]["review_schedule"] = {}

    def _init_resource_mgr(self):
        self.rmgr = ResourceMgr(self.resource_path)
        self.rmgr.reload()

    def _save_progress(self):
        with open(self.progress_path, "w", encoding="utf-8") as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)

    # ─── 多源数据库操作 ─────────────────────────────────────────────────

    def add_db_path(self, path):
        """添加数据库源"""
        p = Path(path) if isinstance(path, str) else path
        if p not in self.db_paths:
            self.db_paths.append(p)

    def reload_all_sources(self):
        """重新加载所有数据库源（去重合并）"""
        seen_titles, merged_courses = set(), []
        for p in self.db_paths:
            if p and p.exists():
                d = load_json_safe(p)
                if d and "courses" in d:
                    for c in d["courses"]:
                        cid = c.get("note_id", "")
                        title = c.get("course_title", "").strip()
                        # 用 note_id 去重，其次用 title
                        key = cid or title
                        if key and key not in seen_titles:
                            seen_titles.add(key)
                            merged_courses.append(c)
        self.courses = merged_courses
        self._init_progress()
        self._save_progress()

    def save_courses_to(self, path, courses_list):
        """保存课程列表到指定 JSON 文件"""
        data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "framework": "课程处理方程：符号化建模、最佳实践与全日程时刻表",
            },
            "courses": courses_list,
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def remove_course(self, course_id):
        """删除课程（从内存、进度、JSON文件中移除）"""
        course = self.get_course_by_id(course_id)
        if not course:
            return False
        self.courses = [c for c in self.courses
                        if c.get("note_id") != course_id and c.get("course_title") != course_id]
        self.progress.pop(course_id, None)
        self._save_progress()
        for p in self.db_paths:
            if not p.exists():
                continue
            d = load_json_safe(p)
            if not d or "courses" not in d:
                continue
            before = len(d["courses"])
            d["courses"] = [c for c in d["courses"]
                            if c.get("note_id") != course_id and c.get("course_title") != course_id]
            if len(d["courses"]) < before:
                self.save_courses_to(str(p), d["courses"])
        if self.rmgr:
            all_res = self.rmgr.get(course_id)
            for res in all_res:
                self.rmgr.remove(course_id, res)
        return True

    def find_duplicates(self):
        """检测重复课程（按标题相似度）"""
        groups = {}
        for c in self.courses:
            title = c.get("course_title", "").strip()
            base = re.sub(r'[《》\s（）\(\)课程大纲Syllabus]', '', title)[:20]
            if base not in groups:
                groups[base] = []
            groups[base].append(c)
        return {k: v for k, v in groups.items() if len(v) > 1}

    def update_review_schedule(self, course_id, lesson_number, workload):
        """根据工作量更新复习调度"""
        if course_id not in self.progress:
            return
        rs = self.progress[course_id].setdefault("review_schedule", {})
        ln_str = str(lesson_number)
        now = datetime.now()
        if workload <= 0:
            interval_days = 14
        elif workload <= 5:
            interval_days = 7
        elif workload <= 15:
            interval_days = 4
        elif workload <= 30:
            interval_days = 2
        else:
            interval_days = 1
        review_count = rs.get(ln_str, {}).get("review_count", 0)
        interval_days = max(1, int(interval_days * (1.5 ** min(review_count, 5))))
        next_review = now + timedelta(days=interval_days)
        rs[ln_str] = {
            "workload": workload,
            "interval_days": interval_days,
            "next_review": next_review.isoformat(),
            "last_reviewed": now.isoformat(),
            "review_count": review_count,
        }
        self._save_progress()

    def get_due_reviews(self, course_id):
        """获取当前需要复习的课时列表"""
        if course_id not in self.progress:
            return []
        rs = self.progress[course_id].get("review_schedule", {})
        now = datetime.now()
        due = []
        for ln_str, info in rs.items():
            try:
                next_r = datetime.fromisoformat(info.get("next_review", ""))
                if next_r <= now:
                    due.append({
                        "lesson_number": int(ln_str),
                        "workload": info.get("workload", 0),
                        "interval_days": info.get("interval_days", 7),
                        "review_count": info.get("review_count", 0),
                        "overdue_days": (now - next_r).days,
                    })
            except:
                pass
        due.sort(key=lambda x: -x["workload"])
        return due

    def mark_review_done(self, course_id, lesson_number):
        """标记复习完成，计算下次复习时间"""
        if course_id not in self.progress:
            return
        rs = self.progress[course_id].get("review_schedule", {})
        ln_str = str(lesson_number)
        if ln_str not in rs:
            return
        info = rs[ln_str]
        workload = info.get("workload", 5)
        review_count = info.get("review_count", 0) + 1
        info["review_count"] = review_count
        info["last_reviewed"] = datetime.now().isoformat()
        if workload <= 5:
            base_days = 7
        elif workload <= 15:
            base_days = 4
        elif workload <= 30:
            base_days = 2
        else:
            base_days = 1
        interval_days = max(1, int(base_days * (1.5 ** min(review_count, 5))))
        info["interval_days"] = interval_days
        info["next_review"] = (datetime.now() + timedelta(days=interval_days)).isoformat()
        self._save_progress()

    def create_course(self, title, domain="UNKNOWN"):
        """创建新课程模板"""
        h = hashlib.md5(title.encode("utf-8")).hexdigest()[:16]
        return {
            "note_id": f"new_{h}",
            "course_title": title,
            "total_hours": None,
            "domain": domain,
            "prerequisites": [],
            "positioning": "",
            "target_audience": "",
            "assessment": "",
            "sections": [],
            "lessons": [],
            "references": [],
        }

    def import_courses(self, courses_list, target_path=None):
        """导入课程列表到系统，可选择保存到指定文件"""
        added = 0
        for c in courses_list:
            cid = c.get("note_id", "")
            title = c.get("course_title", "").strip()
            # 检查重复
            existing = self.get_course_by_id(cid or title)
            if existing:
                continue
            self.courses.append(c)
            # 初始化进度
            key = cid or title
            if key not in self.progress:
                self.progress[key] = {
                    "completed_lessons": [],
                    "current_lesson": None,
                    "started_at": None,
                    "last_updated": None,
                }
            added += 1
        self._save_progress()
        if target_path and added > 0:
            tp = Path(target_path)
            existing_data = load_json_safe(tp) or {"metadata": {}, "courses": []}
            if "courses" not in existing_data:
                existing_data["courses"] = []
            existing_data["courses"].extend(courses_list)
            tp.write_text(json.dumps(existing_data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_db_path(tp)
        return added

    # ─── 统计属性 ───────────────────────────────────────────────────────

    @property
    def total_hours(self):
        return sum(c.get("total_hours", 0) or 0 for c in self.courses)

    @property
    def total_lessons(self):
        return sum(len(c.get("lessons", [])) for c in self.courses)

    @property
    def domain_distribution(self):
        return Counter(c.get("domain", "UNKNOWN") for c in self.courses)

    def courses_with_hours_count(self):
        return sum(1 for c in self.courses if c.get("total_hours"))

    # ─── 课程查询与进度 ─────────────────────────────────────────────────

    def get_course_by_id(self, course_id: str):
        for c in self.courses:
            if c.get("note_id") == course_id or c.get("course_title") == course_id:
                return c
        return None

    def find_course(self, name):
        """模糊查找课程"""
        c = self.get_course_by_id(name)
        if c:
            return c
        s = name[:20]
        for c in self.courses:
            title = c.get("course_title", "")
            if s in title or title[:20] in s:
                return c
            if name[:10] in title or title[:10] in name:
                return c
        return None

    def get_course_progress(self, course_id: str):
        return self.progress.get(course_id, {
            "completed_lessons": [],
            "current_lesson": None,
            "started_at": None,
            "last_updated": None,
        })

    def get_next_lesson(self, course_id: str):
        """获取下一个未完成的课时"""
        course = self.get_course_by_id(course_id)
        if not course or not course.get("lessons"):
            return None
        prog = self.get_course_progress(course_id)
        completed = set(prog.get("completed_lessons", []))
        for lesson in course["lessons"]:
            lnum = lesson.get("lesson_number")
            if lnum not in completed:
                return lesson
        return None  # All completed

    def get_lesson(self, course_id: str, lesson_number: int):
        """根据课程ID和课时编号获取课时信息"""
        course = self.get_course_by_id(course_id)
        if not course:
            return None
        for lesson in course.get("lessons", []):
            if lesson.get("lesson_number") == lesson_number:
                return lesson
        return None

    def complete_lesson(self, course_id: str, lesson_number: int):
        """标记课时完成，返回下一个课时"""
        if course_id not in self.progress:
            self.progress[course_id] = {
                "completed_lessons": [],
                "current_lesson": None,
                "started_at": None,
                "last_updated": None,
            }
        prog = self.progress[course_id]
        if lesson_number not in prog["completed_lessons"]:
            prog["completed_lessons"].append(lesson_number)
        prog["last_updated"] = datetime.now().isoformat()
        if prog["started_at"] is None:
            prog["started_at"] = datetime.now().isoformat()
        self._save_progress()
        return self.get_next_lesson(course_id)

    def undo_lesson(self, course_id: str, lesson_number: int):
        """撤销课时完成"""
        if course_id in self.progress:
            prog = self.progress[course_id]
            if lesson_number in prog["completed_lessons"]:
                prog["completed_lessons"].remove(lesson_number)
                prog["last_updated"] = datetime.now().isoformat()
                self._save_progress()

    def get_completion_pct(self, course_id: str):
        """获取课程完成百分比"""
        course = self.get_course_by_id(course_id)
        if not course or not course.get("lessons"):
            return 0
        total = len(course["lessons"])
        prog = self.get_course_progress(course_id)
        done = len(prog.get("completed_lessons", []))
        return round(done / total * 100, 1) if total > 0 else 0

    def get_remaining_count(self, course_id: str):
        course = self.get_course_by_id(course_id)
        if not course or not course.get("lessons"):
            return 0
        prog = self.get_course_progress(course_id)
        done = len(prog.get("completed_lessons", []))
        return len(course["lessons"]) - done

    def reset_course(self, course_id: str):
        """重置课程进度"""
        self.progress[course_id] = {
            "completed_lessons": [],
            "current_lesson": None,
            "started_at": None,
            "last_updated": None,
        }
        self._save_progress()

    def get_domain_stats(self):
        """域分布统计"""
        stats = {}
        for c in self.courses:
            d = c.get("domain", "UNKNOWN")
            if d not in stats:
                stats[d] = {"count": 0, "hours": 0, "courses": []}
            stats[d]["count"] += 1
            stats[d]["hours"] += c.get("total_hours") or 0
            stats[d]["courses"].append(c.get("course_title", ""))
        return stats

    def get_overall_progress(self):
        """总进度统计"""
        total_lessons = 0
        completed_lessons = 0
        for c in self.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            lessons = c.get("lessons", [])
            total_lessons += len(lessons)
            prog = self.get_course_progress(cid)
            completed_lessons += len(prog.get("completed_lessons", []))
        return completed_lessons, total_lessons

    # ─── 笔记生成 ──────────────────────────────────────────────────────

    @staticmethod
    def generate_note_yaml(course, lesson=None):
        """生成 Rmd YAML front-matter，适配 note_template.Rmd 格式

        Args:
            course: 课程 dict
            lesson: 课时 dict（可选，为 None 则生成课程级笔记）

        Returns:
            (yaml_str, body_str) — yaml 首部 + 正文模板
        """
        domain = course.get("domain", "UNKNOWN")
        domain_name = DOMAIN_NAMES.get(domain, domain) if 'DOMAIN_NAMES' in globals() else domain
        course_title = course.get("course_title", "Lecture Notes")
        subtitle = f"{domain_name}/{course_title}"
        if lesson:
            subtitle = f"{domain_name}/{course_title} — 课时{lesson.get('lesson_number', '')} {lesson.get('lesson_title', '')}"

        # 选择输出格式
        yaml_lines = [
            "---",
            f'title: "Lecture Notes"',
            f'subtitle: "{subtitle}"',
            'author: "P.C."',
            'date: "`r Sys.Date()`"',
            'always_allow_html: true',
            '# 多语言切换（默认中文，取消注释切换定理名为英文）',
            '# header-includes: \\newcommand{\\envlang}{en}',
            'output:',
            '  pdf_document:',
            '    template: null',
            '    includes:',
            '      in_header: ../template/preamble-book.tex',
            '    pandoc_args:',
            '      - --lua-filter=../template/env_mapping.lua',
            '    latex_engine: xelatex',
            '    fig_caption: true',
            '    number_sections: true',
            '    toc: true',
            '    toc_depth: 3',
            '    md_extensions: +fenced_divs+bracketed_spans',
            '    keep_tex: false',
            '    keep_md: false',
            '    extra_dependencies:',
            '      ctex: []',
            '      geometry: [top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm]',
            '      fancyhdr: []',
            '      lastpage: []',
            '      booktabs: []',
            '      multirow: []',
            '      graphicx: []',
            '      amsmath: []',
            '      amssymb: []',
            '      amsthm: []',
            '      bm: []',
            '      listings: []',
            '      xcolor: [table]',
            '      hyperref: []',
            '      longtable: []',
            '      float: []',
            '      caption: []',
            '  html_document:',
            '    toc: true',
            '    toc_float: true',
            '    code_folding: show',
            '    theme: flatly',
            '    highlight: tango',
            '    number_sections: true',
            "---",
        ]

        yaml_str = "\n".join(yaml_lines)

        # 正文模板
        if lesson:
            lnum = lesson.get("lesson_number", 0)
            ltitle = lesson.get("lesson_title", "")
            central_q = lesson.get("central_question", "")
            body_lines = [
                "",
                "```{r setup, include=FALSE}",
                "# Windows中文路径支持",
                "if (.Platform$OS.type == \"windows\") {",
                "  # 设置正确的编码选项",
                "  options(encoding = \"UTF-8\")",
                "  Sys.setlocale(\"LC_ALL\", \"Chinese (Simplified)_China.UTF-8\")",
                "  # 或者尝试更通用的：",
                "  # Sys.setlocale(\"LC_ALL\", \"\")",
                "}",
                "knitr::opts_chunk$set(",
                "  echo       = TRUE,",
                "  message    = FALSE,",
                "  warning    = FALSE,",
                "  fig.width  = 8,",
                "  fig.height = 6,",
                "  fig.dpi    = 300,",
                '  fig.align  = "center",',
                "  cache      = TRUE,",
                "  autodep    = TRUE",
                ")",
                'options(knitr.table.format = "latex")',
                "set.seed(42)",
                "```",
                "",
                "```{r packages, include=FALSE}",
                "library(tidyverse)",
                "library(knitr)",
                "library(kableExtra)",
                "library(ggplot2)",
                "library(gridExtra)",
                "",
                "theme_set(theme_bw(base_size = 12) +",
                '  theme(plot.title = element_text(hjust = 0.5, face = "bold"),',
                '        legend.position = "bottom"))',
                "```",
                "",
                f"\\newpage",
                "",
                f"# 课时 {lnum}：{ltitle}",
                "",
            ]
            if central_q:
                body_lines += [
                    f"## 中心问题",
                    "",
                    f"> {central_q}",
                    "",
                ]
            body_lines += [
                "## 笔记",
                "",
                "",
                "",
            ]
        else:
            # 课程级笔记模板
            sections = course.get("sections", [])
            body_lines = [
                "",
                "```{r setup, include=FALSE}",
                "# Windows中文路径支持",
                "if (.Platform$OS.type == \"windows\") {",
                "  # 设置正确的编码选项",
                "  options(encoding = \"UTF-8\")",
                "  Sys.setlocale(\"LC_ALL\", \"Chinese (Simplified)_China.UTF-8\")",
                "  # 或者尝试更通用的：",
                "  # Sys.setlocale(\"LC_ALL\", \"\")",
                "}",
                "knitr::opts_chunk$set(",
                "  echo       = TRUE,",
                "  message    = FALSE,",
                "  warning    = FALSE,",
                "  fig.width  = 8,",
                "  fig.height = 6,",
                "  fig.dpi    = 300,",
                '  fig.align  = "center",',
                "  cache      = TRUE,",
                "  autodep    = TRUE",
                ")",
                'options(knitr.table.format = "latex")',
                "set.seed(42)",
                "```",
                "",
                "```{r packages, include=FALSE}",
                "library(tidyverse)",
                "library(knitr)",
                "library(kableExtra)",
                "library(ggplot2)",
                "library(gridExtra)",
                "",
                "theme_set(theme_bw(base_size = 12) +",
                '  theme(plot.title = element_text(hjust = 0.5, face = "bold"),',
                '        legend.position = "bottom"))',
                "```",
                "",
                "\\newpage",
                "",
                f"# {course_title}",
                "",
            ]
            if sections:
                for sec in sections:
                    snum = sec.get("section_number", 0)
                    stitle = sec.get("section_title", f"Section {snum}")
                    body_lines += [
                        f"## Section {snum}：{stitle}",
                        "",
                        "",
                    ]

        return yaml_str, "\n".join(body_lines)

    def get_lesson_section(self, course_id, lesson_number):
        """获取课时所属的 Section 信息，返回 dict 或 None"""
        course = self.get_course_by_id(course_id)
        if not course:
            return None
        sections = course.get("sections", [])
        for sec in sections:
            lr = sec.get("lesson_range", "")
            if lr:
                try:
                    parts = lr.split("-")
                    start, end = int(parts[0]), int(parts[-1])
                    if start <= lesson_number <= end:
                        return sec
                except (ValueError, IndexError):
                    pass
        # 如果 sections 没有 lesson_range，按课时编号推算
        if not sections:
            return None
        lessons = course.get("lessons", [])
        total = len(lessons)
        if total == 0:
            return None
        per_section = max(1, total // len(sections))
        idx = 0
        for i, sec in enumerate(sections):
            count = per_section if i < len(sections) - 1 else (total - idx)
            if idx <= lesson_number - 1 < idx + count:
                return sec
            idx += count
        return sections[-1] if sections else None

    def get_lesson_resources(self, course_id, lesson_number):
        """获取课时可用的全部资源：课时级 + 课程级"""
        lesson_res = self.rmgr.get_for_lesson(course_id, lesson_number) if self.rmgr else []
        course_res = self.rmgr.get_for_course(course_id) if self.rmgr else []
        return lesson_res + course_res

    def get_or_create_note(self, course_id, lesson_number=None):
        """获取或创建笔记文件，返回 (path, created)

        Args:
            course_id: 课程标识
            lesson_number: 课时编号，None 则为课程级笔记

        Returns:
            (Path, bool) — 文件路径, 是否新建
        """
        course = self.get_course_by_id(course_id)
        if not course:
            return None, False

        # 笔记目录
        notes_dir = BASE / "Notes"
        notes_dir.mkdir(exist_ok=True)

        # 确定文件名
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', course.get("course_title", "unknown"))[:40]
        if lesson_number is not None:
            lesson = None
            for l in course.get("lessons", []):
                if l.get("lesson_number") == lesson_number:
                    lesson = l
                    break
            safe_ltitle = re.sub(r'[\\/:*?"<>|]', '_', lesson.get("lesson_title", ""))[:30] if lesson else ""
            fn = f"L{lesson_number:02d}_{safe_ltitle}.Rmd" if lesson else f"L{lesson_number:02d}.Rmd"
            note_path = notes_dir / safe_title / fn
        else:
            note_path = notes_dir / safe_title / f"course_notes.Rmd"

        note_path.parent.mkdir(parents=True, exist_ok=True)

        if note_path.exists():
            return note_path, False

        # 生成内容
        lesson_obj = None
        if lesson_number is not None:
            for l in course.get("lessons", []):
                if l.get("lesson_number") == lesson_number:
                    lesson_obj = l
                    break

        yaml_str, body_str = self.generate_note_yaml(course, lesson_obj)
        note_path.write_text(yaml_str + body_str, encoding="utf-8")
        return note_path, True


# ============================================================
# GUI 层
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# MD 解析器
from md_builder import parse_md_file, parse_md_directory

_URL_PATTERN = re.compile(
    r'https?://[^\s<>"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+',
    re.IGNORECASE
)

_VIDEO_HOSTS = {
    'youtube.com', 'youtu.be', 'www.youtube.com',
    'bilibili.com', 'www.bilibili.com', 'b23.tv',
    'vimeo.com', 'v.qq.com', 'ixigua.com',
    'douyin.com', 'www.douyin.com',
}

def _detect_urls(text):
    return _URL_PATTERN.findall(text)

def _classify_url(url):
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    for vh in _VIDEO_HOSTS:
        if vh in host:
            return "video"
    return "url"

def _extract_title_from_url(url):
    from urllib.parse import urlparse, unquote
    try:
        path = unquote(urlparse(url).path)
        parts = [p for p in path.split('/') if p and not p.startswith('.') and len(p) > 2]
        if parts:
            title = parts[-1].replace('-', ' ').replace('_', ' ').replace('.html', '').replace('.htm', '')
            if len(title) > 3:
                return title[:50]
    except Exception:
        pass
    return ""

# 中文字体支持
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 工作流日志层
# ============================================================

class WorkflowLogger:
    """执行模式工作流日志：计时、动作捕捉、笔记"""

    LOG_FILE = BASE / "workflow_log.json"

    def __init__(self):
        self.entries = self._load()
        # 计时状态
        self._timer_start = None       # datetime
        self._timer_course = None      # course_id
        self._timer_lesson = None      # lesson_number
        # 失焦状态
        self._blur_time = None
        self._blur_course = None
        self._blur_lesson = None

    def _load(self):
        try:
            if self.LOG_FILE.exists():
                entries = json.loads(self.LOG_FILE.read_text(encoding="utf-8"))
                # 按时间戳排序（确保日志按时间顺序排列）
                entries.sort(key=lambda x: x.get("timestamp", ""))
                return entries
        except Exception:
            pass
        return []

    def save(self):
        # 保存前确保按时间排序
        self.entries.sort(key=lambda x: x.get("timestamp", ""))
        self.LOG_FILE.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def start_timer(self, course_id, lesson_number):
        """开始计时（进入/切换课时）"""
        now = datetime.now()
        # 如果之前有计时，先结束
        if self._timer_start and self._timer_course:
            elapsed = (now - self._timer_start).total_seconds()
            if elapsed > 1:
                self._add_entry("timer_stop", self._timer_course, self._timer_lesson,
                                detail=f"耗时 {self._fmt_duration(elapsed)}")
        self._timer_start = now
        self._timer_course = course_id
        self._timer_lesson = lesson_number
        self._add_entry("timer_start", course_id, lesson_number)

    def stop_timer(self, course_id=None, lesson_number=None):
        """停止当前计时"""
        if not self._timer_start:
            return
        elapsed = (datetime.now() - self._timer_start).total_seconds()
        cid = course_id or self._timer_course
        ln = lesson_number or self._timer_lesson
        self._add_entry("timer_stop", cid, ln, detail=f"耗时 {self._fmt_duration(elapsed)}")
        self._timer_start = None
        self._timer_course = None
        self._timer_lesson = None

    def log_action(self, action, course_id=None, lesson_number=None, detail=""):
        """记录动作"""
        self._add_entry("action", course_id, lesson_number, action=action, detail=detail)

    def log_note(self, text, course_id=None, lesson_number=None):
        """记录笔记"""
        self._add_entry("note", course_id, lesson_number, detail=text)

    def log_blur(self, course_id=None, lesson_number=None):
        """窗口失焦"""
        self._blur_time = datetime.now()
        self._blur_course = course_id
        self._blur_lesson = lesson_number
        self._add_entry("blur", course_id, lesson_number)

    def log_focus_return(self, course_id=None, lesson_number=None, reason=""):
        """窗口回焦"""
        duration = ""
        if self._blur_time:
            elapsed = (datetime.now() - self._blur_time).total_seconds()
            duration = f"离开 {self._fmt_duration(elapsed)}"
        self._add_entry("focus_return", course_id or self._blur_course,
                        lesson_number or self._blur_lesson,
                        detail=f"{duration}{' — ' + reason if reason else ''}")
        self._blur_time = None

    def log_lesson_complete(self, course_id, lesson_number, detail=""):
        """完成课时"""
        self.stop_timer(course_id, lesson_number)
        self._add_entry("lesson_complete", course_id, lesson_number, detail=detail)

    def log_open_note(self, course_id=None, lesson_number=None, detail=""):
        self._add_entry("open_note", course_id, lesson_number, detail=detail)

    def log_open_resource(self, course_id=None, lesson_number=None, detail=""):
        self._add_entry("open_resource", course_id, lesson_number, detail=detail)

    def get_stats(self, start_date=None, end_date=None):
        """汇总统计 - 支持日期范围筛选"""
        total_entries = len(self.entries)
        action_counts = {}
        total_focus_time = 0.0
        total_blur_time = 0.0
        lesson_times = {}  # (course_id, lesson) -> seconds
        course_times = {}  # course_id -> seconds
        note_count = 0
        complete_count = 0
        blur_count = 0
        daily = {}  # date_str -> count
        weekly = {}  # week_str -> count
        monthly = {}  # month_str -> count
        hourly = {}  # hour -> count
        weekday = {}  # 0-6 -> count

        prev_timer_start = None
        prev_blur_time = None
        prev_focus_time = None

        for e in self.entries:
            ts = e.get("timestamp", "")
            action = e.get("action", "")
            etype = e.get("type", "")
            cid = e.get("course_id", "")
            ln = e.get("lesson_number")

            # 日期范围筛选
            if start_date or end_date:
                if not ts:
                    continue
                entry_date = ts[:10]
                if start_date and entry_date < start_date:
                    continue
                if end_date and entry_date > end_date:
                    continue

            # 日计数
            day = ts[:10] if ts else ""
            daily[day] = daily.get(day, 0) + 1

            # 周计数 (ISO周)
            if ts:
                try:
                    dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                    week_num = dt.isocalendar()[1]
                    week_str = f"{dt.year}-W{week_num:02d}"
                    weekly[week_str] = weekly.get(week_str, 0) + 1
                    
                    # 月计数
                    month_str = ts[:7]
                    monthly[month_str] = monthly.get(month_str, 0) + 1
                    
                    # 小时计数
                    hour = int(ts[11:13])
                    hourly[hour] = hourly.get(hour, 0) + 1
                    
                    # 星期计数 (0=周一, 6=周日)
                    wd = dt.weekday()
                    weekday[wd] = weekday.get(wd, 0) + 1
                except:
                    pass

            if etype == "action":
                action_counts[action] = action_counts.get(action, 0) + 1
            elif etype == "note":
                note_count += 1
            elif etype == "lesson_complete":
                complete_count += 1
            elif etype == "timer_stop":
                # 从detail中提取耗时
                detail = e.get("detail", "")
                try:
                    parts = detail.replace("耗时 ", "").split()
                    t = self._parse_duration(parts[0]) if parts else 0
                    key = (cid, ln)
                    lesson_times[key] = lesson_times.get(key, 0) + t
                    course_times[cid] = course_times.get(cid, 0) + t
                    total_focus_time += t
                except Exception:
                    pass
            elif etype == "blur":
                blur_count += 1
            elif etype == "focus_return":
                detail = e.get("detail", "")
                try:
                    if "离开 " in detail:
                        dur_str = detail.split("离开 ")[1].split(" ")[0].split("—")[0].strip()
                        total_blur_time += self._parse_duration(dur_str)
                except Exception:
                    pass

        return {
            "total_entries": total_entries,
            "action_counts": action_counts,
            "action_categories": self._categorize_actions(action_counts),
            "total_focus_time": total_focus_time,
            "total_blur_time": total_blur_time,
            "lesson_times": lesson_times,
            "course_times": course_times,
            "note_count": note_count,
            "complete_count": complete_count,
            "blur_count": blur_count,
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "hourly": hourly,
            "weekday": weekday,
            "evaluation": self._evaluate_learning(action_counts, total_focus_time, complete_count, note_count, blur_count),
        }

    def get_stats_by_period(self, period="all"):
        """按时间段获取统计数据"""
        today = datetime.now().date()
        
        if period == "today":
            start_date = end_date = today.strftime("%Y-%m-%d")
        elif period == "yesterday":
            yesterday = today - timedelta(days=1)
            start_date = end_date = yesterday.strftime("%Y-%m-%d")
        elif period == "week":
            # 本周一到今天
            monday = today - timedelta(days=today.weekday())
            start_date = monday.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif period == "last_week":
            # 上周
            last_monday = today - timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + timedelta(days=6)
            start_date = last_monday.strftime("%Y-%m-%d")
            end_date = last_sunday.strftime("%Y-%m-%d")
        elif period == "month":
            # 本月
            first_day = today.replace(day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif period == "last_month":
            # 上月
            last_month = today.replace(day=1) - timedelta(days=1)
            first_day = last_month.replace(day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = last_month.strftime("%Y-%m-%d")
        elif period == "year":
            # 本年
            first_day = today.replace(month=1, day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        else:
            start_date = end_date = None
        
        return self.get_stats(start_date, end_date)

    def _categorize_actions(self, action_counts):
        """将动作分类统计"""
        categories = {
            "学习": ["open_note", "save_note", "preview_pdf", "open_pdf", "preview_pdf_page"],
            "资源管理": ["add_resource", "open_url", "delete_resource"],
            "编辑操作": ["create_file", "open_file", "delete_file", "open_in_positron"],
            "系统操作": ["view_lesson", "timer_start", "timer_stop"],
            "笔记记录": ["log_note"],
            "完成标记": ["lesson_complete"],
            "其他": [],
        }
        
        cat_counts = {cat: 0 for cat in categories}
        uncategorized = {}
        
        for action, count in action_counts.items():
            matched = False
            for cat, actions in categories.items():
                if action in actions:
                    cat_counts[cat] += count
                    matched = True
                    break
            if not matched:
                uncategorized[action] = count
                cat_counts["其他"] += count
        
        return {"counts": cat_counts, "uncategorized": uncategorized}

    def _evaluate_learning(self, action_counts, focus_time, complete_count, note_count, blur_count):
        """评价学习表现"""
        total_actions = sum(action_counts.values()) if action_counts else 0
        
        # 活跃度评分
        activity_score = min(total_actions / 50 * 100, 100) if total_actions > 0 else 0
        
        # 专注度评分
        total_time = focus_time + (blur_count * 60)  # 假设每次失焦平均1分钟
        focus_rate = (focus_time / total_time * 100) if total_time > 0 else 0
        
        # 学习效率（每小时完成课时数）
        efficiency = complete_count / (focus_time / 3600) if focus_time > 0 else 0
        
        # 笔记密度（每小时笔记数）
        note_density = note_count / (focus_time / 3600) if focus_time > 0 else 0
        
        # 资源利用程度
        resource_actions = action_counts.get("add_resource", 0) + action_counts.get("open_url", 0) + \
                          action_counts.get("open_pdf", 0) + action_counts.get("preview_pdf", 0)
        resource_score = min(resource_actions / total_actions * 100, 100) if total_actions > 0 else 0
        
        # 综合评分
        weights = [0.2, 0.25, 0.2, 0.15, 0.2]
        scores = [activity_score, focus_rate, min(efficiency * 10, 100), 
                  min(note_density * 20, 100), resource_score]
        overall = sum(w * s for w, s in zip(weights, scores))
        
        def get_grade(score):
            if score >= 80:
                return "优秀", "#27ae60"
            elif score >= 60:
                return "良好", "#f39c12"
            elif score >= 40:
                return "一般", "#e67e22"
            else:
                return "需改进", "#e74c3c"
        
        overall_grade, overall_color = get_grade(overall)
        
        return {
            "activity_score": round(activity_score, 1),
            "focus_rate": round(focus_rate, 1),
            "efficiency": round(efficiency, 2),
            "note_density": round(note_density, 2),
            "resource_score": round(resource_score, 1),
            "overall": round(overall, 1),
            "overall_grade": overall_grade,
            "overall_color": overall_color,
            "grade_details": {
                "活跃度": {"score": round(activity_score, 1), "grade": get_grade(activity_score)},
                "专注度": {"score": round(focus_rate, 1), "grade": get_grade(focus_rate)},
                "完成效率": {"score": round(min(efficiency * 10, 100), 1), "grade": get_grade(min(efficiency * 10, 100))},
                "笔记密度": {"score": round(min(note_density * 20, 100), 1), "grade": get_grade(min(note_density * 20, 100))},
                "资源利用": {"score": round(resource_score, 1), "grade": get_grade(resource_score)},
            }
        }

    def get_entries(self):
        """返回所有日志条目（按时间排序）"""
        # 确保返回时也是排序的
        self.entries.sort(key=lambda x: x.get("timestamp", ""))
        return self.entries

    def get_session_analysis(self, course_id, lesson_number):
        """分析某课时的所有计时环节，量子化判定贡献/耗散"""
        lesson_entries = [e for e in self.entries
                         if e.get("course_id") == course_id
                         and e.get("lesson_number") == lesson_number]
        sessions = []
        current = None
        for e in lesson_entries:
            etype = e.get("type", "")
            ts = e.get("timestamp", "")
            if etype == "timer_start":
                current = {
                    "start_ts": ts,
                    "start_dt": datetime.fromisoformat(ts) if ts else None,
                    "stop_ts": None,
                    "stop_dt": None,
                    "duration_sec": 0,
                    "actions": [],
                }
            elif etype == "timer_stop" and current:
                current["stop_ts"] = ts
                try:
                    current["stop_dt"] = datetime.fromisoformat(ts)
                    current["duration_sec"] = (current["stop_dt"] - current["start_dt"]).total_seconds()
                except:
                    pass
                sessions.append(current)
                current = None
            elif current and etype in ("action", "note", "open_note", "open_resource"):
                current["actions"].append({
                    "type": etype,
                    "timestamp": ts,
                    "detail": e.get("detail", ""),
                    "action": e.get("action", ""),
                })
        if current:
            now = datetime.now()
            current["stop_ts"] = now.isoformat()
            current["stop_dt"] = now
            current["duration_sec"] = (now - current["start_dt"]).total_seconds()
            sessions.append(current)

        MIN_CONTRIBUTION_SEC = 15 * 60
        for s in sessions:
            has_action = len(s["actions"]) > 0
            long_enough = s["duration_sec"] >= MIN_CONTRIBUTION_SEC
            s["is_contribution"] = has_action and long_enough
            s["is_dissipation"] = not s["is_contribution"]

        return sessions

    def get_lesson_workload(self, course_id, lesson_number):
        """计算课时工作量 = f(有效时间, 动作次数)"""
        sessions = self.get_session_analysis(course_id, lesson_number)
        effective_sec = 0
        action_count = 0
        note_count = 0
        resource_count = 0
        dissipation_sec = 0
        for s in sessions:
            if s["is_contribution"]:
                effective_sec += s["duration_sec"]
                for a in s["actions"]:
                    if a["type"] == "action":
                        action_count += 1
                    elif a["type"] == "note":
                        note_count += 1
                    elif a["type"] in ("open_note", "open_resource"):
                        resource_count += 1
            else:
                dissipation_sec += s["duration_sec"]

        total_actions = action_count + note_count + resource_count
        effective_min = effective_sec / 60
        workload = (effective_min * 0.4) + (total_actions * 2.0) + (note_count * 3.0) + (resource_count * 1.5)
        return {
            "workload": round(workload, 1),
            "effective_sec": effective_sec,
            "dissipation_sec": dissipation_sec,
            "action_count": action_count,
            "note_count": note_count,
            "resource_count": resource_count,
            "total_actions": total_actions,
            "session_count": len(sessions),
            "contribution_count": sum(1 for s in sessions if s["is_contribution"]),
            "dissipation_count": sum(1 for s in sessions if s["is_dissipation"]),
        }

    def get_course_workload_summary(self, course_id, lessons):
        """获取课程所有课时的工作量概览"""
        result = {}
        for l in lessons:
            lnum = l.get("lesson_number")
            w = self.get_lesson_workload(course_id, lnum)
            if w["session_count"] > 0:
                result[lnum] = w
        return result

    def clear(self):
        """清空所有日志"""
        self.entries = []
        self.save()

    def _add_entry(self, entry_type, course_id=None, lesson_number=None,
                   action="", detail=""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
        }
        if course_id:
            entry["course_id"] = course_id
        if lesson_number is not None:
            entry["lesson_number"] = lesson_number
        if action:
            entry["action"] = action
        if detail:
            entry["detail"] = detail
        self.entries.append(entry)
        self.save()

    def get_lesson_elapsed(self, entry, lesson_entries):
        base = None
        for e in lesson_entries:
            if e.get("type") == "timer_start":
                try:
                    base = datetime.fromisoformat(e.get("timestamp", ""))
                except:
                    pass
                break
        if base is None:
            return ""
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", ""))
            delta = (ts - base).total_seconds()
            if delta < 0:
                return ""
            m, s = divmod(int(delta), 60)
            h, m = divmod(m, 60)
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"
        except:
            return ""

    @staticmethod
    def _fmt_duration(seconds):
        """秒 → 可读格式"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}分{s}秒"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}时{m}分"

    @staticmethod
    def _parse_duration(s):
        """可读格式 → 秒"""
        total = 0
        # 匹配 数字+单位
        for m in re.finditer(r'(\d+)(时|分|秒)', s):
            val = int(m.group(1))
            unit = m.group(2)
            if unit == "时":
                total += val * 3600
            elif unit == "分":
                total += val * 60
            elif unit == "秒":
                total += val
        return total


# 颜色方案
DOMAIN_COLORS = {
    "P": "#3498db",   # 蓝 - 物理
    "A": "#e74c3c",   # 红 - 代数
    "CS": "#2ecc71",  # 绿 - 计算机系统
    "DS": "#f39c12",  # 橙 - 数据结构
    "DE": "#9b59b6",  # 紫 - 数字电路
    "SE": "#1abc9c",  # 青 - 软件工程
    "D": "#e67e22",   # 深橙 - 离散
    "N": "#95a5a6",   # 灰 - 分析
    "M": "#2980b9",   # 深蓝 - 建模
    "S": "#d35400",   # 深红 - 生信
    "C": "#c0392b",   # 深红 - 范畴
    "BIO": "#27ae60", # 绿 - 生物
    "LM": "#8e44ad",  # 紫 - 逻辑
    "UNKNOWN": "#7f8c8d",
}

DOMAIN_NAMES = {
    "A": "代数学域", "D": "离散结构域", "P": "系统物理域",
    "C": "范畴论域", "M": "建模与计算域", "S": "合成生信域",
    "N": "分析学域", "CS": "计算机系统域", "SE": "软件工程域",
    "DS": "数据结构与算法域", "DE": "数字电路与嵌入式域",
    "LM": "逻辑与数学基础域", "BIO": "生物信息域", "UNKNOWN": "未分类",
}


class CourseTrackerApp:
    """主应用 — TS2 增强版（含导入、管理、资源）"""

    def __init__(self, root: tk.Tk, system: CourseSystem):
        self.root = root
        self.system = system
        self.root.title("学术教研系统 TS2")
        self.root.geometry("1380x850")
        self.root.minsize(1100, 700)

        # 当前选中的课程 ID
        self._sel_course_id = None
        # UI 状态追踪
        self.exec_mode_active = False
        self.current_execution_course = None
        self._current_detail_course = None

        # 工作流日志
        self.wflogger = WorkflowLogger()
        self._exec_timer_running = False  # 当前是否在执行模式计时中
        self._exec_current_lnum = None    # 当前计时的课时号
        
        # 任务看板管理器
        self.task_board_mgr = TaskBoardManager()
        # 项目管理器
        self.project_mgr = ProjectManager()
        
        # 可视化分析器
        self._visualizer = None
        try:
            from ws2_visualization import create_visualizer
            self._visualizer = create_visualizer(BASE)
            self._visualizer.initialize(course_system=self.system, 
                                      workflow_logger=self.wflogger)
        except ImportError:
            pass
        
        # 网络爬虫管理器
        self._web_crawler = None
        self._web_crawler_ui = None

        # 窗口焦点追踪（失焦/回焦捕捉）
        self._window_blurred = False
        self.root.bind("<FocusOut>", self._on_window_blur)
        self.root.bind("<FocusIn>", self._on_window_focus)

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("", 16, "bold"))
        style.configure("Heading.TLabel", font=("", 13, "bold"))
        style.configure("Sub.TLabel", font=("", 10))
        style.configure("Complete.TButton", foreground="green")
        style.configure("Active.TButton", foreground="blue")
        style.configure("Nav.TButton", font=("", 10))
        style.configure("NavActive.TButton", font=("", 10, "bold"), foreground="#2980b9")
        style.configure("Log.Treeview", rowheight=26)

        self._build_ui()
        self._refresh_overview()

    # ============ UI 构建 ============

    def _build_ui(self):
        """构建主界面"""
        # 顶部导航栏
        self.nav_frame = ttk.Frame(self.root)
        self.nav_frame.pack(fill=tk.X, padx=10, pady=5)

        # 助手按钮（最左侧）
        def open_assistant_window():
            try:
                sys.path.insert(0, str(BASE))
                from mcp.agent_assistant import AgentAssistantWindow
                assistant_window = AgentAssistantWindow(
                    self.root,
                    BASE,
                    self.system,
                    self.project_mgr,
                    self.task_board_mgr
                )
                assistant_window.show()
            except Exception as e:
                messagebox.showerror("错误", f"启动独立助手失败: {e}")
                import traceback
                traceback.print_exc()
        

        self.nav_buttons = {}
        for key, text, cmd in [
            ("overview", "总览", self._show_overview),
            ("exec", "执行模式", self._show_execution_mode),
            ("taskboard", "任务看板", self._show_task_board),
            ("search", "网络研探", self._show_search_page),
            ("projects", "项目管理", self._show_projects_page),
            ("analyze", "科研文本分析", self._show_research_analysis),
            ("crawler", "网络爬虫", self._show_web_crawler),
            ("synergy", "研究交流中心", self._show_synergy_hub),
            ("domain", "域分布", self._show_domain_chart),
            ("resource", "课程资源", self._show_resource_page),
            ("manage", "导入与管理", self._show_management_page),
            ("notes", "笔记", self._show_notes_page),
            ("wflog", "工作日志", self._show_workflow_log),
        ]:
            btn = ttk.Button(self.nav_frame, text=text, command=cmd, style="Nav.TButton")
            btn.pack(side=tk.LEFT, padx=3)
            self.nav_buttons[key] = btn

        self.assistant_btn = ttk.Button(
            self.nav_frame, 
            text="🤖",
            command=open_assistant_window,
            style="Accent.TButton",
            width=3
        )
        self.assistant_btn.pack(side=tk.LEFT, padx=1)
        
        self.nav_title = ttk.Label(self.nav_frame, text="", style="Title.TLabel")
        self.nav_title.pack(side=tk.LEFT, padx=20)
        
        # Overall progress label
        self.overall_label = ttk.Label(self.nav_frame, text="", style="Sub.TLabel")
        self.overall_label.pack(side=tk.RIGHT, padx=10)

        # 主内容区
        self.content_frame = ttk.Frame(self.root)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def _clear_content(self):
        self._stop_log_refresh()
        self.root.unbind_all("<MouseWheel>")
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.exec_mode_active = False
        self._current_detail_course = None

    def _adaptive_wraplength(self, ratio=0.6):
        w = self.content_frame.winfo_width() or 800
        return max(120, int(w * ratio))

    def _update_overall_label(self):
        done, total = self.system.get_overall_progress()
        pct = round(done / total * 100, 1) if total > 0 else 0
        self.overall_label.config(text=f"总进度: {done}/{total} 课时 ({pct}%)")

    def _highlight_nav(self, active_key):
        """高亮当前导航按钮"""
        for key, btn in self.nav_buttons.items():
            btn.config(style="NavActive.TButton" if key == active_key else "Nav.TButton")

    # ─── 窗口焦点追踪 ───

    def _on_window_blur(self, event):
        """窗口失焦 — 记录离开时间"""
        # 只在执行模式活跃时捕捉
        if not (hasattr(self, 'exec_mode_active') and self.exec_mode_active):
            return
        # 忽略子窗口（Toplevel）触发的焦点事件
        if event.widget != self.root:
            return
        self._window_blurred = True
        self.wflogger.log_blur(
            getattr(self, 'current_execution_course', None),
            self._exec_current_lnum
        )

    def _on_window_focus(self, event):
        """窗口回焦 — 直接记录，不弹窗询问"""
        if not self._window_blurred:
            return
        if event.widget != self.root:
            return
        # 立即置 False 防止重入
        self._window_blurred = False

        cid = getattr(self, 'current_execution_course', None)
        ln = self._exec_current_lnum

        # 直接记录回焦事件，不弹窗
        self.wflogger.log_focus_return(cid, ln)

    # ─── 日志辅助方法 ───

    def _wf_log_action(self, action, detail=""):
        """记录动作到工作流日志"""
        self.wflogger.log_action(
            action,
            getattr(self, 'current_execution_course', None),
            self._exec_current_lnum,
            detail
        )

    # ============ 总览页 ============

    def _show_overview(self):
        self._clear_content()
        self._highlight_nav("overview")
        self.nav_title.config(text="课程总览")
        self._update_overall_label()

        # 顶部统计卡片
        stats_frame = ttk.Frame(self.content_frame)
        stats_frame.pack(fill=tk.X, pady=5)

        total_courses = len(self.system.courses)
        total_hours = self.system.total_hours
        done, total_l = self.system.get_overall_progress()

        for i, (label, value) in enumerate([
            ("课程总数", f"{total_courses}"),
            ("总课时", f"{total_hours}τ"),
            ("已完成课时", f"{done}/{total_l}"),
            ("完成率", f"{round(done/total_l*100,1)}%" if total_l else "0%"),
        ]):
            f = ttk.LabelFrame(stats_frame, text=label)
            f.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
            ttk.Label(f, text=value, font=("", 18, "bold")).pack(padx=10, pady=8)

        # ── 域过滤栏 ──
        filter_bar = ttk.Frame(self.content_frame)
        filter_bar.pack(fill=tk.X, padx=10, pady=(4, 2))

        ttk.Label(filter_bar, text="按域过滤：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        existing_domains = sorted(set(c.get("domain", "UNKNOWN") for c in self.system.courses))
        self._overview_filter_vars = {}
        all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_bar, text="全部", variable=all_var,
                        command=lambda: self._toggle_overview_filter_all(all_var)).pack(side=tk.LEFT, padx=3)

        for domain in existing_domains:
            dn = DOMAIN_NAMES.get(domain, domain)
            var = tk.BooleanVar(value=True)
            self._overview_filter_vars[domain] = var
            ttk.Checkbutton(filter_bar, text=f"{dn}", variable=var,
                            command=lambda: self._refresh_overview_cards()).pack(side=tk.LEFT, padx=3)

        # ── 搜索栏 ──
        search_frame = ttk.Frame(self.content_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=(2, 4))
        ttk.Label(search_frame, text="🔍 搜索：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._overview_search_var = tk.StringVar()
        self._overview_search_var.trace_add("write", lambda *args: self._refresh_overview_cards())
        search_entry = ttk.Entry(search_frame, textvariable=self._overview_search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(search_frame, text="清除", width=8,
                   command=lambda: (self._overview_search_var.set(""), search_entry.focus())).pack(side=tk.RIGHT)

        # 主区域：PanedWindow 左卡片 + 右统计
        main_paned = tk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL,
                                     sashrelief=tk.RAISED, sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左侧：课程卡片
        self._overview_cards_container = ttk.Frame(main_paned, padding=2)
        main_paned.add(self._overview_cards_container, width=700)
        self._build_course_cards(self._overview_cards_container)

        # 右侧：统计+日志
        stats_panel = ttk.Frame(main_paned, padding=2)
        main_paned.add(stats_panel, width=280)
        self._build_overview_stats(stats_panel)

    def _toggle_overview_filter_all(self, all_var):
        """全选/取消全选域过滤"""
        val = all_var.get()
        for var in self._overview_filter_vars.values():
            var.set(val)
        self._refresh_overview_cards()

    def _refresh_overview_cards(self):
        """根据域过滤条件刷新总览页卡片"""
        for w in self._overview_cards_container.winfo_children():
            w.destroy()
        self._build_course_cards(self._overview_cards_container)

    def _refresh_exec_cards(self):
        """刷新执行模式选择课程页面卡片（支持搜索过滤）"""
        if not hasattr(self, '_exec_cards_container'):
            return
        for w in self._exec_cards_container.winfo_children():
            w.destroy()
        search_query = ""
        if hasattr(self, '_exec_search_var'):
            search_query = self._exec_search_var.get().strip().lower()
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            domain = c.get("domain", "UNKNOWN")
            color = DOMAIN_COLORS.get(domain, "#7f8c8d")
            pct = self.system.get_completion_pct(cid)
            lessons = c.get("lessons", [])
            total_lessons = len(lessons)
            completed_set = set(self.system.get_course_progress(cid).get("completed_lessons", []))
            completed_count = len(completed_set)
            remaining = total_lessons - completed_count
            total_hours = sum(l.get("estimated_hours", 0) for l in lessons)
            next_l = self.system.get_next_lesson(cid)
            if search_query:
                match_text = f"{title} {domain} {c.get('author', '')}".lower()
                lesson_matched = any(search_query in l.get("lesson_title", "").lower() or search_query in l.get("title", "").lower() for l in lessons)
                if search_query not in match_text and not lesson_matched:
                    continue
            if remaining == 0:
                status_text = "✅ 已完成"
            else:
                status_text = f"⏳ 剩余 {remaining} 课时"
                if next_l:
                    status_text += f" | 下一节: 课时{next_l['lesson_number']}"
            card = ttk.Frame(self._exec_cards_container, relief="groove", borderwidth=1)
            card.pack(fill=tk.X, padx=8, pady=6)
            tk.Canvas(card, width=8, bg=color, highlightthickness=0).pack(side=tk.LEFT, fill=tk.Y)
            info = ttk.Frame(card)
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)
            ttk.Label(info, text=title, font=("", 12, "bold")).pack(anchor="w")
            meta_line = []
            if domain:
                meta_line.append(f"🌐 {domain}")
            meta_line.append(f"📖 {total_lessons} 节")
            if total_hours > 0:
                meta_line.append(f"⏱️ {total_hours:.1f}h")
            ttk.Label(info, text="  |  ".join(meta_line), style="Sub.TLabel").pack(anchor="w")
            ttk.Label(info, text=status_text, style="Sub.TLabel").pack(anchor="w")
            pbar = ttk.Progressbar(info, length=400, mode="determinate", maximum=100)
            pbar["value"] = pct
            pbar.pack(fill=tk.X, pady=2)
            ttk.Label(info, text=f"完成 {pct}%", style="Sub.TLabel").pack(anchor="w")
            btn_frame = ttk.Frame(card)
            btn_frame.pack(side=tk.RIGHT, padx=12)
            ttk.Button(btn_frame, text="▶ 进入", command=lambda cid=cid: self._show_execution_mode(cid)).pack(pady=5)
            if completed_count > 0 and remaining > 0:
                ttk.Label(btn_frame, text="进行中").pack(pady=2)
            elif remaining == 0:
                ttk.Label(btn_frame, text="已完成").pack(pady=2)

    def _build_course_cards(self, parent):
        """构建可滚动的课程卡片列表"""
        cards_frame = ttk.Frame(parent)
        cards_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self._overview_canvas = tk.Canvas(cards_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(cards_frame, orient="vertical", command=self._overview_canvas.yview)
        self._overview_canvas.configure(yscrollcommand=scrollbar.set)

        self._overview_scroll_frame = ttk.Frame(self._overview_canvas)
        self._overview_canvas.create_window((0, 0), window=self._overview_scroll_frame,
                                             anchor="nw", tags=("scroll_win",))

        self._overview_scroll_frame.bind("<Configure>",
            lambda e: self._overview_canvas.configure(scrollregion=self._overview_canvas.bbox("all")))
        # 宽度自适应
        self._overview_canvas.bind("<Configure>", self._on_overview_canvas_configure)

        self._overview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮：进入/离开时绑定/解绑
        self._overview_canvas.bind("<Enter>", lambda e: self._overview_canvas.bind_all(
            "<MouseWheel>", lambda ev: _on_mousewheel(ev, self._overview_canvas)))
        self._overview_canvas.bind("<Leave>", lambda e: self._overview_canvas.unbind_all("<MouseWheel>"))

        # 获取过滤条件
        active_filters = getattr(self, '_overview_filter_vars', {})
        search_query = getattr(self, '_overview_search_var', tk.StringVar(value="")).get().strip().lower()
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            domain = c.get("domain", "UNKNOWN")
            if active_filters and not active_filters.get(domain, tk.BooleanVar(value=True)).get():
                continue
            title = c.get("course_title", "未知课程")
            # 搜索匹配检查
            if search_query:
                match_text = f"{title} {domain} {DOMAIN_NAMES.get(domain, domain)} {c.get('author', '')}".lower()
                if search_query not in match_text:
                    # 再检查课时内容
                    lesson_matched = False
                    for l in c.get("lessons", []):
                        ltitle = l.get("title", "")
                        if search_query in str(ltitle).lower():
                            lesson_matched = True
                            break
                    if not lesson_matched:
                        continue
            hours = c.get("total_hours", "?")
            n_lessons = len(c.get("lessons", []))
            pct = self.system.get_completion_pct(cid)
            remaining = self.system.get_remaining_count(cid)
            color = DOMAIN_COLORS.get(domain, "#7f8c8d")
            domain_name = DOMAIN_NAMES.get(domain, domain)

            card = ttk.Frame(self._overview_scroll_frame, relief="groove", borderwidth=1)
            card.pack(fill=tk.X, padx=5, pady=3)

            color_bar = tk.Canvas(card, width=6, bg=color, highlightthickness=0)
            color_bar.pack(side=tk.LEFT, fill=tk.Y)

            info = ttk.Frame(card)
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=5)

            row1 = ttk.Frame(info)
            row1.pack(fill=tk.X)
            ttk.Label(row1, text=f"[{domain_name}]", foreground=color, font=("", 9)).pack(side=tk.LEFT)
            ttk.Label(row1, text=f"  {title}", font=("", 11, "bold")).pack(side=tk.LEFT)

            row2 = ttk.Frame(info)
            row2.pack(fill=tk.X, pady=2)
            ttk.Label(row2, text=f"{hours}τ | {n_lessons}课时 | 剩余{remaining}", style="Sub.TLabel").pack(side=tk.LEFT)

            progress_bar = ttk.Progressbar(info, length=300, mode="determinate", maximum=100)
            progress_bar["value"] = pct
            progress_bar.pack(fill=tk.X, pady=2)

            row3 = ttk.Frame(info)
            row3.pack(fill=tk.X)
            ttk.Label(row3, text=f"完成 {pct}%", style="Sub.TLabel").pack(side=tk.LEFT)

            btn_frame = ttk.Frame(card)
            btn_frame.pack(side=tk.RIGHT, padx=10, pady=5)

            ttk.Button(btn_frame, text="📖 详情",
                       command=lambda cid=cid: self._show_course_detail(cid)).pack(pady=1)
            ttk.Button(btn_frame, text="▶ 执行",
                       command=lambda cid=cid: self._show_execution_mode(cid)).pack(pady=1)
            ttk.Button(btn_frame, text="🔄 重置",
                       command=lambda cid=cid: self._confirm_reset(cid)).pack(pady=1)
            ttk.Button(btn_frame, text="🗑️ 删除",
                       command=lambda cid=cid: self._confirm_delete_course(cid)).pack(pady=1)

    def _on_overview_canvas_configure(self, event):
        """总览Canvas宽度变化时，内部Frame自适应"""
        self._overview_canvas.itemconfig("scroll_win", width=event.width)

    def _build_overview_stats(self, parent):
        """总览右侧：统计图 + 日志流"""
        # 上部：统计图（紧凑）
        chart_frame = ttk.LabelFrame(parent, text="学习统计", padding=3)
        chart_frame.pack(fill=tk.X, pady=(0, 5))

        wf_stats = self.wflogger.get_stats()

        # 创建一个包含两个图表的figure
        fig = Figure(figsize=(2.6, 4.0), dpi=85)
        fig.subplots_adjust(left=0.38, right=0.95, top=0.95, bottom=0.08, hspace=0.25)

        # ========== 图1: 课程完成进度百分比条形图 ==========
        ax1 = fig.add_subplot(211)
        courses_data = []
        for c in self.system.courses[:6]:
            cid = c.get("note_id", c.get("course_title", ""))
            pct = self.system.get_completion_pct(cid)
            title = c.get("course_title", "")[:6] if c else ""
            domain = c.get("domain", "") if c else ""
            if pct > 0 or len(c.get("lessons", [])) > 0:
                courses_data.append((title, pct, domain))
        
        if courses_data:
            courses_data.sort(key=lambda x: -x[1])
            names = [c[0] for c in courses_data]
            pcts = [c[1] for c in courses_data]
            clrs = [DOMAIN_COLORS.get(c[2], "#7f8c8d") for c in courses_data]
            
            y_pos = range(len(names))
            ax1.barh(y_pos, [100] * len(y_pos), color='#f0f0f0', zorder=0)
            ax1.barh(y_pos, pcts, color=clrs, height=0.55, zorder=1)
            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(names, fontsize=6)
            ax1.set_xlim(0, 100)
            ax1.set_xlabel("%", fontsize=6)
            ax1.set_title("完成进度", fontsize=8, fontweight='bold')
            ax1.tick_params(axis="x", labelsize=6)
            for i, v in enumerate(pcts):
                ax1.text(v + 1, i, f'{v:.0f}%', va='center', fontsize=5, fontweight='bold')
        else:
            ax1.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=8)
            ax1.set_title("完成进度", fontsize=8, fontweight='bold')

        # ========== 图2: 月进度折线图 ==========
        ax2 = fig.add_subplot(212)
        daily = wf_stats.get("daily", {})
        if daily:
            monthly_data = {}
            for day_str, count in daily.items():
                try:
                    year_month = day_str[:7]
                    monthly_data[year_month] = monthly_data.get(year_month, 0) + count
                except:
                    pass
            
            if monthly_data:
                sorted_months = sorted(monthly_data.keys())[-6:]
                months = [m[5:] for m in sorted_months]
                counts = [monthly_data[m] for m in sorted_months]
                
                ax2.plot(months, counts, marker='o', linewidth=2, color='#27ae60', 
                        markersize=4, markeredgecolor='white', markeredgewidth=1)
                ax2.fill_between(months, counts, alpha=0.3, color='#27ae60')
                ax2.set_xlabel("月份", fontsize=6)
                ax2.set_ylabel("活动次数", fontsize=6)
                ax2.set_title("月进度趋势", fontsize=8, fontweight='bold')
                ax2.tick_params(axis="x", labelsize=5, rotation=45)
                ax2.tick_params(axis="y", labelsize=5)
                ax2.grid(axis='y', alpha=0.3, linestyle='--')
            else:
                ax2.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=8)
                ax2.set_title("月进度趋势", fontsize=8, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=8)
            ax2.set_title("月进度趋势", fontsize=8, fontweight='bold')

        canvas_w = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas_w.draw()
        canvas_w.get_tk_widget().pack(fill=tk.X)

        # 统计数字
        num_frame = ttk.Frame(chart_frame)
        num_frame.pack(fill=tk.X, pady=3)

        focus_min = round(wf_stats.get("total_focus_time", 0) / 60, 1)
        note_count = wf_stats.get("note_count", 0)
        complete_count = wf_stats.get("complete_count", 0)
        blur_count = wf_stats.get("blur_count", 0)

        for label, val in [("专注", f"{focus_min}m"), ("笔记", f"{note_count}"),
                           ("完成", f"{complete_count}"), ("离开", f"{blur_count}")]:
            f = ttk.Frame(num_frame)
            f.pack(side=tk.LEFT, expand=True, fill=tk.X)
            ttk.Label(f, text=val, font=("", 9, "bold")).pack()
            ttk.Label(f, text=label, font=("", 7), foreground="#666").pack()

        # 下部：日志流
        log_frame = ttk.LabelFrame(parent, text="日志流", padding=3)
        log_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("time", "event")
        self._overview_log_tree = ttk.Treeview(log_frame, columns=columns, show="headings",
                                                height=12, selectmode="browse", style="Log.Treeview")
        self._overview_log_tree.heading("time", text="时间")
        self._overview_log_tree.heading("event", text="事件")
        self._overview_log_tree.column("time", width=70, anchor="center", stretch=False)
        self._overview_log_tree.column("event", width=180, stretch=True)

        self._overview_log_tree.tag_configure("timer_start", foreground="#2e7d32", font=("", 11, "bold"))
        self._overview_log_tree.tag_configure("timer_stop", foreground="#1565c0", font=("", 11, "bold"))
        self._overview_log_tree.tag_configure("action", foreground="#6a1b9a", font=("", 12))
        self._overview_log_tree.tag_configure("note", foreground="#e65100", font=("", 14))
        self._overview_log_tree.tag_configure("blur", foreground="#9e9e9e",font=("", 11, "bold"))
        self._overview_log_tree.tag_configure("focus_return", foreground="#00838f",font=("", 11, "bold"))
        self._overview_log_tree.tag_configure("lesson_complete", foreground="#c62828", font=("", 16, "bold"))
        self._overview_log_tree.tag_configure("open_note", foreground="#00695c", font=("", 16))
        self._overview_log_tree.tag_configure("open_resource", foreground="#4e342e", font=("", 16))

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self._overview_log_tree.yview)
        self._overview_log_tree.configure(yscrollcommand=log_scroll.set)
        self._overview_log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._load_overview_log()

    def _load_overview_log(self):
        """加载日志流到总览"""
        if not hasattr(self, '_overview_log_tree') or self._overview_log_tree is None:
            return
        for item in self._overview_log_tree.get_children():
            self._overview_log_tree.delete(item)

        entries = self.wflogger.get_entries()[-50:]
        type_labels = {
            "timer_start": "▶ 开始计时",
            "timer_stop": "⏹ 停止计时",
            "action": "⚡ 动作",
            "note": "📝 笔记",
            "blur": "👋 离开",
            "focus_return": "✅ 返回",
            "lesson_complete": "🎯 完成课时",
            "open_note": "📓 打开笔记",
            "open_resource": "📂 打开资源",
        }
        for entry in reversed(entries):
            ts = entry.get("timestamp", "")[11:19]
            etype = entry.get("type", "")
            detail = entry.get("detail", "")
            action = entry.get("action", "")
            label = type_labels.get(etype, etype)
            if detail:
                label += f" {detail[:30]}"
            elif action:
                label += f" {action[:30]}"
            self._overview_log_tree.insert("", 0, values=(ts, label), tags=(etype,))

    # ============ 域分布图 ============

    def _show_domain_chart(self):
        self._clear_content()
        self._highlight_nav("domain")
        self.nav_title.config(text="域分布")

        fig = Figure(figsize=(10, 6), dpi=100)

        # 左: 课时分布饼图
        ax1 = fig.add_subplot(121)
        stats = self.system.get_domain_stats()
        labels = []
        sizes = []
        colors = []
        for domain, info in sorted(stats.items()):
            dn = DOMAIN_NAMES.get(domain, domain)
            labels.append(f"{dn}\n{info['hours']}τ")
            sizes.append(info["hours"])
            colors.append(DOMAIN_COLORS.get(domain, "#7f8c8d"))
        if sizes:
            ax1.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90, textprops={"fontsize": 8})
        ax1.set_title("课时分布", fontsize=12, fontweight="bold")

        # 右: 各课程完成进度条
        ax2 = fig.add_subplot(122)
        course_names = []
        pcts = []
        bar_colors = []
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            short = title[:20] + "..." if len(title) > 20 else title
            course_names.append(short)
            pcts.append(self.system.get_completion_pct(cid))
            bar_colors.append(DOMAIN_COLORS.get(c.get("domain", "UNKNOWN"), "#7f8c8d"))

        if course_names:
            y_pos = range(len(course_names))
            ax2.barh(y_pos, pcts, color=bar_colors, height=0.6)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(course_names, fontsize=7)
            ax2.set_xlabel("完成 %")
            ax2.set_xlim(0, 100)
            for i, v in enumerate(pcts):
                ax2.text(v + 1, i, f"{v}%", va="center", fontsize=7)
        ax2.set_title("课程进度", fontsize=12, fontweight="bold")

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.content_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ============ 课程详情页 ============

    def _show_course_detail(self, course_id: str):
        self._clear_content()
        self._highlight_nav("overview")
        self._current_detail_course = course_id
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        self._sel_course_id = course_id
        self.nav_title.config(text=course.get("course_title", ""))
        cid = course_id
        domain = course.get("domain", "UNKNOWN")
        color = DOMAIN_COLORS.get(domain, "#7f8c8d")
        domain_name = DOMAIN_NAMES.get(domain, domain)
        pct = self.system.get_completion_pct(cid)
        prog = self.system.get_course_progress(cid)

        # 顶部信息
        top = ttk.Frame(self.content_frame)
        top.pack(fill=tk.X, pady=5)

        ttk.Button(top, text="← 返回总览", command=self._show_overview).pack(side=tk.LEFT, padx=5)

        info_frame = ttk.Frame(top)
        info_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(info_frame, text=course.get("course_title", ""), style="Title.TLabel").pack(anchor="w")
        sub = f"[{domain_name}]  |  {course.get('total_hours', '?')}τ  |  {len(course.get('lessons', []))}课时  |  完成 {pct}%"
        ttk.Label(info_frame, text=sub, style="Sub.TLabel").pack(anchor="w")

        # 进度条
        pbar = ttk.Progressbar(top, length=300, mode="determinate", maximum=100)
        pbar["value"] = pct
        pbar.pack(side=tk.RIGHT, padx=20)

        # 标签页
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # Tab 1: 课时列表
        lessons_frame = ttk.Frame(notebook)
        notebook.add(lessons_frame, text="📋 课时列表")
        self._build_lessons_list(lessons_frame, course, cid)

        # Tab 2: Section结构
        sections_frame = ttk.Frame(notebook)
        notebook.add(sections_frame, text="📚 Section结构")
        self._build_sections_view(sections_frame, course, cid)

        # Tab 3: 课程信息
        info_tab = ttk.Frame(notebook)
        notebook.add(info_tab, text="ℹ️ 课程信息")
        self._build_course_info(info_tab, course)

        # Tab 4: 课程资源
        res_tab = ttk.Frame(notebook)
        notebook.add(res_tab, text="🔗 课程资源")
        self._build_course_resources(res_tab, cid)

        # Tab 5: 课程笔记
        notes_tab = ttk.Frame(notebook)
        notebook.add(notes_tab, text="📝 课程笔记")
        self._build_course_notes_tab(notes_tab, cid)

    def _build_lessons_list(self, parent, course, cid):
        completed = set(self.system.get_course_progress(cid).get("completed_lessons", []))
        lessons = course.get("lessons", [])

        # Treeview
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("status", "num", "section", "title", "question", "description")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=25)
        tree.heading("status", text="状态")
        tree.heading("num", text="课时#")
        tree.heading("section", text="Section")
        tree.heading("title", text="标题")
        tree.heading("question", text="中心问题")
        tree.heading("description", text="描述")

        tree.column("status", width=50, anchor="center")
        tree.column("num", width=50, anchor="center")
        tree.column("section", width=120)
        tree.column("title", width=300)
        tree.column("question", width=250)
        tree.column("description", width=250)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for lesson in lessons:
            lnum = lesson.get("lesson_number", 0)
            is_done = lnum in completed
            status = "✅" if is_done else "⬜"
            title = lesson.get("lesson_title", "")
            question = lesson.get("central_question", "")
            desc = lesson.get("description", "")
            # 描述列只显示前80字符，避免过长
            desc_short = desc[:80] + "…" if len(desc) > 80 else desc
            sec = self.system.get_lesson_section(cid, lnum)
            sec_text = f"S{sec.get('section_number', '?')}" if sec else ""
            tag = "done" if is_done else "pending"
            tree.insert("", "end", values=(status, lnum, sec_text, title, question, desc_short), tags=(tag,))

        tree.tag_configure("done", foreground="#888888")
        tree.tag_configure("pending", foreground="#000000")

        # 底部按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="▶ 开始顺序执行",
                   command=lambda: self._show_execution_mode(cid)).pack(side=tk.LEFT, padx=5)

        # 打开选中课时笔记
        def open_selected_note():
            sel = tree.selection()
            if not sel:
                return
            item = tree.item(sel[0])
            lnum = int(item["values"][1])
            self._open_note(cid, lnum)

        ttk.Button(btn_frame, text="📝 打开笔记", command=open_selected_note).pack(side=tk.LEFT, padx=5)

        # 标记选中为完成
        def mark_selected_done():
            sel = tree.selection()
            if not sel:
                return
            item = tree.item(sel[0])
            lnum = int(item["values"][1])
            if item["values"][0] != "✅":
                self.system.complete_lesson(cid, lnum)
                self._show_course_detail(cid)  # refresh

        ttk.Button(btn_frame, text="✅ 标记选中完成", command=mark_selected_done).pack(side=tk.LEFT, padx=5)

        # 撤销选中
        def undo_selected():
            sel = tree.selection()
            if not sel:
                return
            item = tree.item(sel[0])
            lnum = int(item["values"][1])
            if item["values"][0] == "✅":
                self.system.undo_lesson(cid, lnum)
                self._show_course_detail(cid)

        ttk.Button(btn_frame, text="↩ 撤销选中", command=undo_selected).pack(side=tk.LEFT, padx=5)

    def _build_sections_view(self, parent, course, cid):
        completed = set(self.system.get_course_progress(cid).get("completed_lessons", []))
        sections = course.get("sections", [])
        lessons = course.get("lessons", [])

        tree = ttk.Treeview(parent, columns=("sec", "title", "hours", "progress"), show="headings", height=20)
        tree.heading("sec", text="Section#")
        tree.heading("title", text="标题")
        tree.heading("hours", text="课时")
        tree.heading("progress", text="进度")

        tree.column("sec", width=80, anchor="center")
        tree.column("title", width=400)
        tree.column("hours", width=80, anchor="center")
        tree.column("progress", width=300)

        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for sec in sections:
            snum = sec.get("section_number", 0)
            stitle = sec.get("section_title", "")
            shours = sec.get("section_hours") or sec.get("hours") or ""
            # 计算 section 内课时完成情况
            sec_lessons = [l for l in lessons if l.get("section") == snum]
            if not sec_lessons:
                lr = sec.get("lesson_range", "")
                if lr and "-" in str(lr):
                    try:
                        lo, hi = str(lr).split("-")
                        sec_lessons = [l for l in lessons
                                      if int(lo) <= l.get("lesson_number", 0) <= int(hi)]
                    except (ValueError, TypeError):
                        pass
            if sec_lessons:
                done_count = sum(1 for l in sec_lessons if l.get("lesson_number", 0) in completed)
                total_count = len(sec_lessons)
                pct_str = f"{done_count}/{total_count} ({round(done_count/total_count*100,1) if total_count else 0}%)"
            else:
                pct_str = ""
            tree.insert("", "end", values=(f"Section {snum}", stitle, f"{shours}τ" if shours else "", pct_str))

    def _build_course_info(self, parent, course):
        # Scrollable text
        text = tk.Text(parent, wrap=tk.WORD, font=("", 10))
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def add_line(label, value):
            text.insert(tk.END, f"【{label}】\n", "label")
            text.insert(tk.END, f"{value}\n\n", "value")

        add_line("课程标题", course.get("course_title", ""))
        add_line("note_id", course.get("note_id", "无"))
        add_line("总课时", f"{course.get('total_hours', '?')}τ")
        add_line("学科域", f"{course.get('domain', '')} - {DOMAIN_NAMES.get(course.get('domain',''), '')}")
        add_line("先修要求", "\n".join(course.get("prerequisites", [])) or "无")
        add_line("授课对象", course.get("target_audience", "未指定"))
        add_line("考核方式", course.get("assessment", "未指定"))
        add_line("课程定位", course.get("positioning", "未指定"))
        refs = course.get("references", [])
        if refs and isinstance(refs[0], dict):
            add_line("参考书目", "\n".join(f"• {r.get('title', r)}" for r in refs) or "无")
        else:
            add_line("参考书目", "\n".join(f"• {r}" for r in refs) or "无")
        add_line("Section数", str(len(course.get("sections", []))))
        add_line("课时数", str(len(course.get("lessons", []))))
        add_line("数据来源", course.get("source_type", "未知"))
        if course.get("source_file"):
            add_line("源文件", course["source_file"])

        text.tag_configure("label", font=("", 10, "bold"), foreground="#2c3e50")
        text.tag_configure("value", font=("", 10))
        text.config(state=tk.DISABLED)

    # ============ 课程资源 Tab ============

    def _build_course_resources(self, parent, course_id):
        """在课程详情中展示资源 — 按课时分组"""
        rmgr = self.system.rmgr
        course = self.system.get_course_by_id(course_id)
        all_resources = rmgr.get(course_id)

        # 顶部操作栏
        tb = ttk.Frame(parent)
        tb.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(tb, text="🔗 课程资源", font=("", 12, "bold"), foreground="#2C3E50").pack(side=tk.LEFT)
        bf = ttk.Frame(tb)
        bf.pack(side=tk.RIGHT)
        ttk.Button(bf, text="📂 添加课程文件", command=lambda: self._add_file_resource(course_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="📁 批量导入文件", command=lambda: self._batch_import_files(course_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="📋 手动分配导入", command=lambda: self._manual_batch_import(course_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🔖 添加课程URL", command=lambda: self._add_url_resource(course_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🗑️ 多选删除", command=lambda: self._batch_delete_resources(course_id)).pack(side=tk.LEFT, padx=2)

        # 资源列表
        lf = ttk.LabelFrame(parent, text="资源清单", padding=6)
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        r_canvas = tk.Canvas(lf, highlightthickness=0, bg="#FAFAFA")
        r_scroll = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=r_canvas.yview)
        r_inner = ttk.Frame(r_canvas)
        r_inner.bind("<Configure>", lambda e: r_canvas.configure(scrollregion=r_canvas.bbox("all")))
        r_canvas.create_window((0, 0), window=r_inner, anchor="nw")
        r_canvas.configure(yscrollcommand=r_scroll.set)
        r_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        r_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        if not all_resources:
            ttk.Label(r_inner, text="暂无资源\n\n点击上方按钮添加\n或在执行模式中按课时添加", font=("", 11), foreground="#95a5a6").pack(pady=40)
            return

        # 按课时分组
        course_level = []
        lesson_map = {}  # lesson_number -> [resources]
        if course:
            for l in course.get("lessons", []):
                lesson_map[l.get("lesson_number", 0)] = []

        for res in all_resources:
            ln = res.get("lesson_number")
            if ln is not None and ln in lesson_map:
                lesson_map[ln].append(res)
            elif ln is not None:
                lesson_map.setdefault(ln, []).append(res)
            else:
                course_level.append(res)

        def _render_resource_row(res, container):
            rt = res.get("type", "")
            label = res.get("label", "")
            row = ttk.Frame(container)
            row.pack(fill=tk.X, pady=3, padx=4)
            icon = ResourceMgr.RESOURCE_ICONS.get(rt, "📎")
            ttk.Label(row, text=f"  {icon}", font=("", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=label, wraplength=320, font=("", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(row, text="✕", width=3,
                       command=lambda r=res: self._delete_resource(course_id, r,
                                                                   lambda: self._show_course_detail(course_id))).pack(side=tk.RIGHT, padx=1)
            if rt == "pdf":
                ttk.Button(row, text="📂", width=3,
                           command=lambda p=res.get("path", ""): self._open_resource_pdf(p)).pack(side=tk.RIGHT, padx=2)
            elif rt == "url":
                ttk.Button(row, text="🌐", width=3,
                           command=lambda u=res.get("url", ""): self._open_url(u)).pack(side=tk.RIGHT, padx=2)

        # 课程级资源
        if course_level:
            sec_label = ttk.Label(r_inner, text="📁 课程级资源", font=("", 10, "bold"), foreground="#2C3E50")
            sec_label.pack(anchor="w", padx=4, pady=(6, 2))
            for res in course_level:
                _render_resource_row(res, r_inner)
            ttk.Separator(r_inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        # 课时级资源
        if course:
            lessons = course.get("lessons", [])
            for lesson in lessons:
                lnum = lesson.get("lesson_number", 0)
                lresources = lesson_map.get(lnum, [])
                # 显示有资源的课时，或也显示无资源的课时（给添加按钮）
                if lresources:
                    ltitle = lesson.get("lesson_title", "")
                    sec_label = ttk.Label(r_inner, text=f"📖 课时 {lnum}: {ltitle}",
                                          font=("", 9, "bold"), foreground="#2980b9")
                    sec_label.pack(anchor="w", padx=8, pady=(4, 1))
                    for res in lresources:
                        _render_resource_row(res, r_inner)
                    ttk.Button(r_inner, text="  + 添加更多资源",
                               command=lambda ln=lnum: self._add_lesson_resource(course_id, ln)).pack(anchor="w", padx=20, pady=1)

    def _add_file_resource(self, course_id):
        fp = filedialog.askopenfilename(title="选择文件", filetypes=[("PDF", "*.pdf"), ("所有文件", "*.*")])
        if fp and self.system.rmgr.add_pdf(course_id, fp, BASE):
            messagebox.showinfo("成功", "文件已添加")
            self._show_course_detail(course_id)
        elif fp:
            messagebox.showinfo("提示", "文件已存在")

    # ─── 手动分配多选导入 ──────────────────────────────────────────────────

    def _manual_batch_import(self, preselect_course_id=None):
        """非模式匹配：选择多个文件 → 弹窗逐一/批量手动分配课程"""
        files = filedialog.askopenfilenames(
            title="选择要导入的文件（手动分配课程）",
            filetypes=[("PDF", "*.pdf"), ("文档", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                       ("所有文件", "*.*")],
            initialdir=str(BASE.parent / "Courses")
        )
        if not files:
            return

        courses = self.system.courses
        course_items = []
        for c in courses:
            cid_i = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            domain = c.get("domain", "")
            dn = DOMAIN_NAMES.get(domain, domain)
            course_items.append((cid_i, f"[{dn}] {title}"))

        dlg = tk.Toplevel(self.root)
        dlg.title("📋 手动分配导入")
        dlg.geometry("900x600")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"📋 为 {len(files)} 个文件手动分配课程",
                  font=("", 14, "bold"), foreground="#2C3E50").pack(pady=(10, 5))

        # 底部确认（先pack，确保可见）
        bottom = ttk.Frame(dlg)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # 中间内容区
        mid = ttk.Frame(dlg)
        mid.pack(fill=tk.BOTH, expand=True)

        # 文件-课程映射表
        cols = ("file", "course", "section", "lesson")
        tree = ttk.Treeview(mid, columns=cols, show="headings", height=18)
        tree.heading("file", text="文件名")
        tree.heading("course", text="分配课程")
        tree.heading("section", text="节(可选)")
        tree.heading("lesson", text="课时号(可选)")
        tree.column("file", width=280)
        tree.column("course", width=200)
        tree.column("section", width=80, anchor="center")
        tree.column("lesson", width=80, anchor="center")

        ts = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ts.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        ts.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        # 右侧操作面板
        right = ttk.Frame(mid, padding=8)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=5)

        row_map = {}  # iid -> (filepath, course_id, section_number_or_None, lesson_number_or_None)

        def _course_label(cid):
            c = self.system.get_course_by_id(cid)
            return c.get("course_title", cid) if c else cid

        # 初始填入，如果 preselect_course_id 则预选
        for fp in files:
            fname = Path(fp).name[:55]
            cid = preselect_course_id
            sn = None
            ln = None
            clabel = _course_label(cid) if cid else "⚠ 未分配"
            sn_str = ""
            ln_str = ""
            iid = tree.insert("", "end", values=(fname, clabel, sn_str, ln_str))
            row_map[iid] = (fp, cid, sn, ln)
            if not cid:
                tree.item(iid, tags=("unassigned",))
        tree.tag_configure("unassigned", foreground="#e74c3c")

        # 选中行高亮
        def _on_select(event):
            sel = tree.selection()
            if sel:
                iid = sel[0]
                fp, cid, sn, ln = row_map[iid]
                # 更新右侧信息
                for w in right.winfo_children():
                    w.destroy()
                _build_right_panel(iid, fp, cid, sn, ln)

        tree.bind("<<TreeviewSelect>>", _on_select)

        def _build_right_panel(iid, fp, cur_cid, cur_sn, cur_ln):
            for w in right.winfo_children():
                w.destroy()

            ttk.Label(right, text=Path(fp).name, font=("", 10, "bold"), wraplength=180).pack(pady=(5, 10))

            ttk.Label(right, text="分配课程：", font=("", 9, "bold")).pack(anchor="w")
            search_var = tk.StringVar()
            se = ttk.Entry(right, textvariable=search_var, width=22)
            se.pack(pady=2)
            se.focus()

            cl = tk.Listbox(right, height=10, font=("", 9), selectmode=tk.SINGLE, exportselection=False)
            cl.pack(fill=tk.BOTH, expand=True, pady=2)
            cl._cid_map = {}

            def _populate(ft=""):
                cl.delete(0, tk.END)
                idx = 0
                for cid_i, label in course_items:
                    if not ft or ft.lower() in label.lower():
                        cl.insert(tk.END, label)
                        cl._cid_map[idx] = cid_i
                        if cid_i == cur_cid:
                            cl.selection_set(idx)
                        idx += 1

            _populate()
            search_var.trace_add("write", lambda *_: _populate(search_var.get()))

            # 节号
            ttk.Label(right, text="节号(留空=课程级)：", font=("", 9, "bold")).pack(anchor="w", pady=(8, 0))
            sn_var = tk.StringVar(value=str(cur_sn) if cur_sn is not None else "")
            sn_entry = ttk.Entry(right, textvariable=sn_var, width=10)
            sn_entry.pack(anchor="w", pady=2)

            # 课时号
            ttk.Label(right, text="课时号(留空=课程级)：", font=("", 9, "bold")).pack(anchor="w", pady=(4, 0))
            ln_var = tk.StringVar(value=str(cur_ln) if cur_ln is not None else "")
            ln_entry = ttk.Entry(right, textvariable=ln_var, width=10)
            ln_entry.pack(anchor="w", pady=2)

            def _apply():
                s = cl.curselection()
                new_cid = cl._cid_map.get(s[0]) if s else cur_cid
                new_sn = None
                new_ln = None
                sn_text = sn_var.get().strip()
                ln_text = ln_var.get().strip()
                if sn_text:
                    try:
                        new_sn = int(sn_text)
                    except ValueError:
                        messagebox.showwarning("提示", "节号必须是整数", parent=dlg)
                        return
                if ln_text:
                    try:
                        new_ln = int(ln_text)
                    except ValueError:
                        messagebox.showwarning("提示", "课时号必须是整数", parent=dlg)
                        return
                if not new_cid:
                    messagebox.showwarning("提示", "请选择课程", parent=dlg)
                    return
                row_map[iid] = (fp, new_cid, new_sn, new_ln)
                clabel = _course_label(new_cid)
                sn_str = str(new_sn) if new_sn is not None else ""
                ln_str = str(new_ln) if new_ln is not None else ""
                tree.item(iid, values=(Path(fp).name[:55], clabel, sn_str, ln_str), tags=())
                tree.tag_configure("unassigned", foreground="#e74c3c")

            def _apply_to_all():
                """将选中课程的分配应用到所有未分配的文件"""
                s = cl.curselection()
                new_cid = cl._cid_map.get(s[0]) if s else None
                if not new_cid:
                    messagebox.showwarning("提示", "请先选择课程", parent=dlg)
                    return
                new_sn = None
                new_ln = None
                sn_text = sn_var.get().strip()
                ln_text = ln_var.get().strip()
                if sn_text:
                    try:
                        new_sn = int(sn_text)
                    except ValueError:
                        pass
                if ln_text:
                    try:
                        new_ln = int(ln_text)
                    except ValueError:
                        pass
                clabel = _course_label(new_cid)
                sn_str = str(new_sn) if new_sn is not None else ""
                ln_str = str(new_ln) if new_ln is not None else ""
                count = 0
                for i, (fp_i, cid_i, sn_i, ln_i) in row_map.items():
                    if not cid_i:  # 仅覆盖未分配的
                        row_map[i] = (fp_i, new_cid, new_sn, new_ln)
                        tree.item(i, values=(Path(fp_i).name[:55], clabel, sn_str, ln_str), tags=())
                        count += 1
                if count == 0:
                    # 所有文件都已有分配，询问是否覆盖全部
                    if messagebox.askyesno("提示", "所有文件已分配课程，是否覆盖全部？", parent=dlg):
                        for i, (fp_i, cid_i, sn_i, ln_i) in row_map.items():
                            row_map[i] = (fp_i, new_cid, new_sn, new_ln)
                            tree.item(i, values=(Path(fp_i).name[:55], clabel, sn_str, ln_str), tags=())

            ttk.Button(right, text="✅ 应用到选中行", command=_apply).pack(fill=tk.X, pady=(10, 2))
            ttk.Button(right, text="📋 应用到全部未分配", command=_apply_to_all).pack(fill=tk.X, pady=2)

        # 默认选中第一行
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.event_generate("<<TreeviewSelect>>")

        def _confirm():
            unassigned_count = sum(1 for fp, cid, sn, ln in row_map.values() if not cid)
            if unassigned_count > 0:
                if not messagebox.askyesno("确认", f"仍有 {unassigned_count} 个文件未分配课程，继续？", parent=dlg):
                    return
            added, skipped = 0, 0
            for iid in tree.get_children():
                fp, cid, sn, ln = row_map[iid]
                if not cid:
                    continue
                if sn is not None and ln is None:
                    # 按节分配：查找该节下的所有课时，为每个课时添加资源
                    course = self.system.get_course_by_id(cid)
                    if course:
                        sections = course.get("sections", [])
                        target_sec = None
                        for sec in sections:
                            if sec.get("section_number") == sn:
                                target_sec = sec
                                break
                        if target_sec:
                            lr = target_sec.get("lesson_range", "")
                            if lr:
                                try:
                                    parts = lr.split("-")
                                    start_ln, end_ln = int(parts[0]), int(parts[-1])
                                    for lnum in range(start_ln, end_ln + 1):
                                        if self.system.rmgr.add_pdf(cid, fp, BASE, lesson_number=lnum):
                                            added += 1
                                        else:
                                            skipped += 1
                                except (ValueError, IndexError):
                                    # lesson_range 解析失败，按课程级添加
                                    if self.system.rmgr.add_pdf(cid, fp, BASE):
                                        added += 1
                                    else:
                                        skipped += 1
                            else:
                                # section 无 lesson_range，按课程级添加
                                if self.system.rmgr.add_pdf(cid, fp, BASE):
                                    added += 1
                                else:
                                    skipped += 1
                        else:
                            # 未找到指定 section，按课程级添加
                            if self.system.rmgr.add_pdf(cid, fp, BASE):
                                added += 1
                            else:
                                skipped += 1
                    else:
                        if self.system.rmgr.add_pdf(cid, fp, BASE):
                            added += 1
                        else:
                            skipped += 1
                else:
                    # 正常按课时号或课程级添加
                    if self.system.rmgr.add_pdf(cid, fp, BASE, lesson_number=ln):
                        added += 1
                    else:
                        skipped += 1
            msg = f"已添加 {added} 个文件"
            if skipped:
                msg += f"，跳过 {skipped} 个（已存在）"
            messagebox.showinfo("导入完成", msg, parent=self.root)
            self._log(f"manual batch import: {added} added, {skipped} skipped")
            dlg.destroy()
            if preselect_course_id:
                self._show_course_detail(preselect_course_id)
            else:
                self._refresh_all()

        ttk.Button(bottom, text="✅ 确认导入", command=_confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(bottom, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    # ─── 多选删除资源 ──────────────────────────────────────────────────

    def _batch_delete_resources(self, course_id):
        """弹窗多选删除该课程的资源 - TreeView 实现"""
        rmgr = self.system.rmgr
        all_res = rmgr.get(course_id)
        if not all_res:
            messagebox.showinfo("提示", "该课程暂无资源")
            return

        course = self.system.get_course_by_id(course_id)
        course_title = course.get("course_title", course_id) if course else course_id

        dlg = tk.Toplevel(self.root)
        dlg.title(f"🗑️ 多选删除资源 — {course_title}")
        dlg.geometry("750x550")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"🗑️ 选择要删除的资源（支持 Ctrl/Shift 多选）",
                  font=("", 12, "bold"), foreground="#c0392b").pack(pady=(10, 5))

        # TreeView 区域
        list_frame = ttk.Frame(dlg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(list_frame, selectmode='extended', columns=('icon', 'label', 'level'), show='headings')
        tree.heading('icon', text='')
        tree.heading('label', text='资源名称')
        tree.heading('level', text='级别')
        tree.column('icon', width=40, anchor='center')
        tree.column('label', width=500)
        tree.column('level', width=80, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        res_list = []
        for idx, res in enumerate(all_res):
            rt = res.get("type", "")
            label = res.get("label", "")
            ln = res.get("lesson_number")
            level = f"课时{ln}" if ln is not None else "课程级"
            icon = ResourceMgr.RESOURCE_ICONS.get(rt, "📎")
            tree.insert('', 'end', values=(icon, label, level))
            res_list.append(res)

        # 底部
        bottom = ttk.Frame(dlg)
        bottom.pack(fill=tk.X, padx=10, pady=10)

        selected_label = ttk.Label(bottom, text="已选 0 项")
        selected_label.pack(side=tk.LEFT, padx=10)

        def _update_count(*_):
            count = len(tree.selection())
            selected_label.config(text=f"已选 {count} 项")

        tree.bind('<<TreeviewSelect>>', _update_count)

        def _confirm_delete():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("提示", "未选择任何资源", parent=dlg)
                return
            if not messagebox.askyesno("确认删除", f"确定要删除 {len(selection)} 个资源吗？\n此操作不可撤销。", parent=dlg):
                return
            deleted = 0
            for item in selection:
                idx = tree.index(item)
                res = res_list[idx]
                if rmgr.remove(course_id, res):
                    deleted += 1
            messagebox.showinfo("删除完成", f"已删除 {deleted} 个资源", parent=self.root)
            dlg.destroy()
            self._show_course_detail(course_id)

        ttk.Button(bottom, text="🗑️ 确认删除", command=_confirm_delete).pack(side=tk.RIGHT, padx=10)
        ttk.Button(bottom, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=5)

    # ─── 批量导入文件资源 ──────────────────────────────────────────────────

    @staticmethod
    def _match_course_for_file(filename, courses):
        """根据文件名自动匹配课程，返回 (course_id, confidence) 或 (None, 0)
        
        增强匹配策略：
        1. 过滤连接词和停用词
        2. 领域词汇关联绑定（同调->代数几何，几何->代数等）
        3. 中英文双向翻译匹配
        4. 只要有领域词汇匹配就算成功
        """
        clean = Path(filename).stem.lower()
        clean = re.sub(r'[\s_\-—]+', ' ', clean).strip()
        
        if not clean:
            return None, 0
        
        # 停用词列表（连接词、介词、代词等）
        stopwords = {
            # 英文停用词
            'the', 'and', 'for', 'with', 'from', 'into', 'about', 'against', 'between',
            'through', 'during', 'before', 'after', 'above', 'below', 'to', 'of', 'in',
            'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here',
            'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
            'most', 'other', 'some', 'such', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'can', 'will', 'just', 'should', 'now', 'also', 'but',
            'not', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do',
            'does', 'did', 'doing', 'would', 'could', 'may', 'might', 'must',
            # 通用中文停用词
            '课程', '课时', '系统', '理论', '基础', '原理', '导论', '应用', '实践',
            '实验', '设计', '方法', '概论', '入门', '教材', '习题', '解答', '答案',
            '详解', '教程', '指南', '译丛', '精品', '第一', '第二', '第三', '第四',
            '第五', '第六', '第七', '第八', '第九', '第十', '上册', '下册', '上卷',
            '下卷', '第1版', '第2版', '第3版', '章节', '内容', '课程', '版本',
            '资料', '讲义', '总复习', '测试', '考试', '复习', '提纲', '大纲',
            '笔记', '总结', '要点', '重点', '难点', '考点', '知识点', '知识',
            '概述', '简介', '总论', '绪论', '引言', '前言', '序言', '后记',
            '目录', '索引', '参考文献', '附录', '图表', '插图', '公式',
            '问题', '思考', '讨论', '研究', '分析', '说明', '讲解', '论述',
            '第', '章', '节', '篇', '卷', '册', '部', '集', '期', '号',
            # 学术文献常见词
            '基于', '关于', '对于', '由于', '通过', '利用', '采用', '使用',
            '实现', '完成', '提出', '给出', '建立', '构建', '形成', '得到',
            '进行', '开展', '实施', '提供', '达到', '获得', '表明', '证明',
            '探讨', '讨论', '研究', '分析', '总结', '归纳', '概括', '论述',
            '阐述', '说明', '介绍', '描述', '阐述', '论证', '论证', '推理',
            '推导', '演算', '计算', '求解', '求解', '优化', '改进', '完善',
            '提高', '增强', '改进', '改进', '扩展', '推广', '发展', '突破',
            # 常见干扰词（书籍标记、版本信息）
            'pdf', 'doc', 'docx', 'zip', 'rar', 'epub', 'introduction', 'basic',
            'advanced', 'problems', 'solutions', 'manual', 'guide', 'edition',
            'version', 'vol', 'master', 'main', 'chapter', 'part', 'section',
            'zlibrary', 'library', 'ebook', 'book', 'textbook', 'notes',
            '简体中文', '繁体中文', '中文版', '英文版', '原版', '影印版',
            '修订版', '增补版', '新版', '旧版', '全套', '合集', '全集',
            # 时间相关
            '2020', '2021', '2022', '2023', '2024', '2025',
            '第1版', '第2版', '第3版', '第4版', '第5版',
        }
        
        # 领域词汇映射和关联（中文英文双向映射）
        domain_keywords = {
            # 代数领域
            'algebra': ['代数', '线性代数', '抽象代数', '高等代数'],
            'linear': ['线性', '线性代数'],
            'group': ['群', '群论'],
            'ring': ['环', '环论'],
            'field': ['域', '域论'],
            'module': ['模', '模论'],
            'galois': ['伽罗瓦', '伽罗瓦理论'],
            'representation': ['表示', '表示论'],
            'lie': ['李', '李代数', '李群'],
            'abelian': ['阿贝尔', '阿贝尔群'],
            'commutative': ['交换', '交换代数'],
            'homomorphism': ['同态'],
            'isomorphism': ['同构'],
            'morphism': ['态射'],
            'functor': ['函子'],
            'category': ['范畴', '范畴论'],
            'tensor': ['张量', '张量代数'],
            'matrix': ['矩阵'],
            'vector': ['向量'],
            'characteristic': ['特征', '特征值'],
            'eigenvalue': ['特征值'],
            'eigenvector': ['特征向量'],
            'determinant': ['行列式'],
            'polynomial': ['多项式'],
            'ideal': ['理想'],
            'lattice': ['格'],
            'boolean': ['布尔', '布尔代数'],
            
            # 几何领域
            'geometry': ['几何', '几何学', '解析几何'],
            'differential': ['微分', '微分几何'],
            'riemann': ['黎曼', '黎曼几何'],
            'manifold': ['流形'],
            'curvature': ['曲率'],
            'metric': ['度量'],
            'topology': ['拓扑', '拓扑学'],
            'homotopy': ['同伦', '同伦论'],
            'homology': ['同调', '同调论'],
            'cohomology': ['上同调', '上同调论'],
            'sheaf': ['层', '层论'],
            'scheme': ['概形'],
            'algebraic': ['代数几何'],
            'projective': ['射影', '射影几何'],
            'affine': ['仿射', '仿射几何'],
            'complex': ['复几何', '复分析'],
            'riemannian': ['黎曼几何'],
            'symplectic': ['辛几何'],
            'contact': ['接触几何'],
            'fibration': ['纤维丛'],
            'bundle': ['丛', '纤维丛'],
            'chern': ['陈类'],
            'pontryagin': ['庞特里亚金类'],
            'stiefel': ['斯蒂弗尔'],
            'characteristic': ['示性类'],
            'gauss': ['高斯'],
            'euler': ['欧拉'],
            
            # 分析领域
            'analysis': ['分析', '数学分析'],
            'calculus': ['微积分'],
            'functional': ['泛函', '泛函分析'],
            'complex': ['复分析', '复变函数'],
            'real': ['实分析', '实变函数'],
            'measure': ['测度', '测度论'],
            'fourier': ['傅里叶'],
            'operator': ['算子', '算子理论'],
            'spectral': ['谱', '谱理论'],
            'pde': ['偏微分方程'],
            'ode': ['常微分方程'],
            'integral': ['积分', '积分方程'],
            'differential': ['微分方程'],
            'asymptotic': ['渐近'],
            'perturbation': ['摄动'],
            'variational': ['变分', '变分法'],
            'harmony': ['调和分析'],
            'wavelet': ['小波', '小波分析'],
            'distribution': ['分布', '广义函数'],
            'sobolev': ['索伯列夫'],
            
            # 物理领域
            'physics': ['物理', '物理学'],
            'mechanics': ['力学'],
            'quantum': ['量子', '量子力学'],
            'electrodynamics': ['电动力学'],
            'thermodynamics': ['热力学'],
            'relativity': ['相对论'],
            'statistical': ['统计物理'],
            'particle': ['粒子物理'],
            'field': ['场论', '场'],
            'classical': ['经典力学'],
            'newtonian': ['牛顿力学'],
            'lagrangian': ['拉格朗日'],
            'hamiltonian': ['哈密顿'],
            'statistical': ['统计力学'],
            'quantum': ['量子场论'],
            'string': ['弦论'],
            'cosmology': ['宇宙学'],
            'astrophysics': ['天体物理'],
            'condensed': ['凝聚态'],
            'solid': ['固体物理'],
            'plasma': ['等离子体'],
            'nuclear': ['核物理'],
            'optics': ['光学'],
            'acoustics': ['声学'],
            'electromagnetism': ['电磁学'],
            
            # 计算机领域
            'computer': ['计算机', '计算机科学'],
            'programming': ['编程', '程序设计'],
            'algorithm': ['算法'],
            'data': ['数据'],
            'structure': ['结构'],
            'machine': ['机器学习'],
            'learning': ['学习'],
            'neural': ['神经网络'],
            'deep': ['深度学习'],
            'artificial': ['人工智能', '人工智能'],
            'intelligence': ['智能'],
            'database': ['数据库'],
            'network': ['网络'],
            'security': ['安全', '网络安全'],
            'cryptography': ['密码学'],
            'graphics': ['图形学', '计算机图形学'],
            'vision': ['视觉', '计算机视觉'],
            'nlp': ['自然语言处理'],
            'robotics': ['机器人'],
            'distributed': ['分布式'],
            'parallel': ['并行计算'],
            'cloud': ['云计算'],
            'operating': ['操作系统'],
            'compiler': ['编译原理'],
            'software': ['软件工程'],
            
            # 化学领域
            'chemistry': ['化学'],
            'organic': ['有机', '有机化学'],
            'inorganic': ['无机', '无机化学'],
            'physical': ['物理化学'],
            'analytical': ['分析化学'],
            'biochemistry': ['生物化学'],
            'spectroscopy': ['光谱学'],
            'chromatography': ['色谱法'],
            'thermodynamics': ['热化学'],
            'kinetics': ['动力学', '化学动力学'],
            'electrochemistry': ['电化学'],
            'polymer': ['高分子', '高分子化学'],
            'medicinal': ['药物化学'],
            'environmental': ['环境化学'],
            'materials': ['材料化学'],
            'nanochemistry': ['纳米化学'],
            
            # 生物领域
            'biology': ['生物', '生物学'],
            'cell': ['细胞', '细胞学'],
            'molecular': ['分子', '分子生物学'],
            'genetics': ['遗传', '遗传学'],
            'ecology': ['生态', '生态学'],
            'biochemistry': ['生物化学'],
            'microbiology': ['微生物'],
            'virology': ['病毒学'],
            'immunology': ['免疫学'],
            'neuroscience': ['神经科学'],
            'evolution': ['进化', '进化论'],
            'botany': ['植物学'],
            'zoology': ['动物学'],
            'physiology': ['生理学'],
            'anatomy': ['解剖学'],
            'pathology': ['病理学'],
            'pharmacology': ['药理学'],
            'biophysics': ['生物物理'],
            'bioinformatics': ['生物信息学'],
            'genomics': ['基因组学'],
            'proteomics': ['蛋白质组学'],
            'metabolomics': ['代谢组学'],
            
            # 音乐领域
            'music': ['音乐'],
            'symphony': ['交响', '交响乐'],
            'piano': ['钢琴'],
            'composer': ['作曲', '作曲理论'],
            'orchestra': ['管弦乐'],
            'harmony': ['和声', '和声学'],
            'counterpoint': ['对位法'],
            'theory': ['乐理', '音乐理论'],
            'opera': ['歌剧'],
            'chamber': ['室内乐'],
            'vocal': ['声乐'],
            'instrument': ['器乐'],
            
            # 数学通用
            'number': ['数论'],
            'analytic': ['解析数论'],
            'algebraic': ['代数数论'],
            'combinatorics': ['组合数学', '组合学'],
            'graph': ['图论'],
            'optimization': ['最优化', '优化'],
            'operations': ['运筹学'],
            'probability': ['概率', '概率论'],
            'statistics': ['统计', '统计学'],
            'stochastic': ['随机', '随机过程'],
            'numerical': ['数值分析', '数值计算'],
            'approximation': ['逼近'],
            'transform': ['变换'],
            'laplace': ['拉普拉斯'],
            'integral': ['积分'],
            'differential': ['微分'],
            'equation': ['方程'],
            'formula': ['公式'],
            'theorem': ['定理'],
            'lemma': ['引理'],
            'corollary': ['推论'],
            'proof': ['证明'],
            'axiom': ['公理'],
            'conjecture': ['猜想'],
            'hypothesis': ['假设'],
            'invariant': ['不变量'],
            'symmetry': ['对称', '对称性'],
            'duality': ['对偶', '对偶性'],
            'compact': ['紧', '紧致'],
            'connected': ['连通', '连通性'],
            'continuous': ['连续', '连续性'],
            'differentiable': ['可微', '可微性'],
            'integrable': ['可积', '可积性'],
            'bounded': ['有界'],
            'infinite': ['无穷', '无限'],
            'finite': ['有限'],
            'discrete': ['离散'],
            'cardinality': ['基数', '势'],
            'ordinal': ['序数'],
            'cardinal': ['基数'],
            'sequence': ['数列'],
            'series': ['级数'],
            'convergence': ['收敛', '收敛性'],
            'divergence': ['发散'],
            'limit': ['极限'],
            'continuity': ['连续'],
            'derivative': ['导数'],
            'integral': ['积分'],
            'differential': ['微分'],
            'gradient': ['梯度'],
            'divergence': ['散度'],
            'curl': ['旋度'],
            'laplacian': ['拉普拉斯算子'],
        }
        
        # 中文到英文的反向映射（扩展版）
        chinese_to_english = {}
        for eng, chns in domain_keywords.items():
            for ch in chns:
                if ch not in chinese_to_english:
                    chinese_to_english[ch] = []
                if eng not in chinese_to_english[ch]:
                    chinese_to_english[ch].append(eng)
        
        # 额外的中文专业词汇到领域的直接映射
        chinese_domain_direct = {
            # 代数与数论
            '数论': ['number', 'analytic', 'algebraic'],
            '抽象代数': ['algebra'],
            '线性代数': ['linear', 'algebra'],
            '高等代数': ['algebra', 'linear'],
            '矩阵论': ['matrix'],
            '模论': ['module'],
            '群论': ['group'],
            '环论': ['ring'],
            '域论': ['field'],
            '伽罗瓦理论': ['galois'],
            '表示论': ['representation'],
            '李代数': ['lie'],
            '李群': ['lie'],
            '交换代数': ['commutative', 'algebra'],
            '同调代数': ['homology', 'cohomology', 'algebra'],
            '范畴论': ['category', 'functor'],
            '张量': ['tensor'],
            '多重线性代数': ['tensor'],
            '特征值': ['characteristic', 'eigenvalue'],
            '特征向量': ['eigenvector'],
            '行列式': ['determinant'],
            '多项式': ['polynomial'],
            '理想': ['ideal'],
            '格': ['lattice'],
            '布尔代数': ['boolean'],
            
            # 几何与拓扑
            '微分几何': ['differential', 'geometry'],
            '黎曼几何': ['riemann', 'riemannian'],
            '拓扑学': ['topology'],
            '代数拓扑': ['topology', 'homotopy', 'homology', 'cohomology'],
            '同伦论': ['homotopy'],
            '同调论': ['homology'],
            '上同调论': ['cohomology'],
            '层论': ['sheaf'],
            '纤维丛': ['bundle', 'fibration'],
            '示性类': ['characteristic', 'chern', 'pontryagin'],
            '陈类': ['chern'],
            '射影几何': ['projective'],
            '仿射几何': ['affine'],
            '复几何': ['complex'],
            '辛几何': ['symplectic'],
            '接触几何': ['contact'],
            '代数几何': ['algebraic', 'geometry', 'scheme'],
            '解析几何': ['geometry', 'analytic'],
            
            # 分析与方程
            '数学分析': ['analysis', 'calculus'],
            '实变函数': ['real', 'analysis'],
            '复变函数': ['complex', 'analysis'],
            '泛函分析': ['functional', 'analysis'],
            '测度论': ['measure'],
            '积分方程': ['integral'],
            '常微分方程': ['ode', 'differential'],
            '偏微分方程': ['pde', 'differential'],
            '积分': ['integral', 'calculus'],
            '微分': ['differential', 'calculus'],
            '导数': ['derivative'],
            '极限': ['limit'],
            '级数': ['series'],
            '收敛': ['convergence'],
            '发散': ['divergence'],
            '傅里叶分析': ['fourier'],
            '调和分析': ['harmony', 'fourier'],
            '小波分析': ['wavelet'],
            '算子理论': ['operator'],
            '谱理论': ['spectral'],
            '广义函数': ['distribution'],
            '变分法': ['variational'],
            '最优化': ['optimization'],
            
            # 物理
            '经典力学': ['classical', 'mechanics', 'newtonian'],
            '牛顿力学': ['newtonian', 'mechanics'],
            '拉格朗日力学': ['lagrangian', 'mechanics'],
            '哈密顿力学': ['hamiltonian', 'mechanics'],
            '量子力学': ['quantum'],
            '量子场论': ['quantum', 'field'],
            '统计力学': ['statistical', 'mechanics'],
            '电动力学': ['electrodynamics'],
            '热力学': ['thermodynamics'],
            '统计物理': ['statistical', 'physics'],
            '相对论': ['relativity'],
            '宇宙学': ['cosmology'],
            '天体物理': ['astrophysics'],
            '弦论': ['string'],
            '粒子物理': ['particle'],
            '凝聚态物理': ['condensed'],
            '固体物理': ['solid'],
            '光学': ['optics'],
            '声学': ['acoustics'],
            '电磁学': ['electromagnetism'],
            
            # 计算机
            '算法': ['algorithm'],
            '数据结构': ['data', 'structure'],
            '程序设计': ['programming'],
            '人工智能': ['artificial', 'intelligence'],
            '机器学习': ['machine', 'learning'],
            '深度学习': ['deep', 'learning'],
            '神经网络': ['neural', 'network'],
            '计算机视觉': ['vision', 'computer'],
            '自然语言处理': ['nlp'],
            '数据库': ['database'],
            '计算机网络': ['network', 'computer'],
            '网络安全': ['security', 'network'],
            '密码学': ['cryptography'],
            '分布式系统': ['distributed'],
            '并行计算': ['parallel'],
            '云计算': ['cloud'],
            '操作系统': ['operating'],
            '编译原理': ['compiler'],
            '软件工程': ['software'],
            '计算机图形学': ['graphics'],
            '机器人学': ['robotics'],
            
            # 化学
            '有机化学': ['organic', 'chemistry'],
            '无机化学': ['inorganic', 'chemistry'],
            '物理化学': ['physical', 'chemistry'],
            '分析化学': ['analytical', 'chemistry'],
            '生物化学': ['biochemistry'],
            '光谱学': ['spectroscopy'],
            '色谱法': ['chromatography'],
            '电化学': ['electrochemistry'],
            '化学动力学': ['kinetics'],
            '高分子化学': ['polymer'],
            '药物化学': ['medicinal'],
            '环境化学': ['environmental'],
            '材料化学': ['materials'],
            '纳米化学': ['nanochemistry'],
            
            # 生物
            '细胞学': ['cell'],
            '分子生物学': ['molecular', 'biology'],
            '遗传学': ['genetics'],
            '生态学': ['ecology'],
            '微生物学': ['microbiology'],
            '病毒学': ['virology'],
            '免疫学': ['immunology'],
            '神经科学': ['neuroscience'],
            '进化论': ['evolution'],
            '植物学': ['botany'],
            '动物学': ['zoology'],
            '生理学': ['physiology'],
            '解剖学': ['anatomy'],
            '病理学': ['pathology'],
            '药理学': ['pharmacology'],
            '生物物理学': ['biophysics'],
            '生物信息学': ['bioinformatics'],
            '基因组学': ['genomics'],
            '蛋白质组学': ['proteomics'],
            '代谢组学': ['metabolomics'],
            
            # 数学通用
            '概率论': ['probability'],
            '统计学': ['statistics'],
            '随机过程': ['stochastic'],
            '数值分析': ['numerical'],
            '数值计算': ['numerical'],
            '组合数学': ['combinatorics'],
            '图论': ['graph'],
            '运筹学': ['operations', 'optimization'],
            '定理': ['theorem'],
            '引理': ['lemma'],
            '推论': ['corollary'],
            '证明': ['proof'],
            '公理': ['axiom'],
            '猜想': ['conjecture'],
            '不变量': ['invariant'],
            '对称性': ['symmetry'],
            '对偶性': ['duality'],
            '连续性': ['continuous', 'continuity'],
            '可微性': ['differentiable'],
            '可积性': ['integrable'],
            
            # 音乐
            '和声学': ['harmony'],
            '对位法': ['counterpoint'],
            '乐理': ['theory'],
            '音乐理论': ['theory', 'music'],
            '作曲理论': ['composer', 'theory'],
            '交响乐': ['symphony'],
            '管弦乐': ['orchestra'],
            '室内乐': ['chamber'],
            '声乐': ['vocal'],
            '器乐': ['instrument'],
            '歌剧': ['opera'],
        }
        
        # 合并到chinese_to_english
        for ch, engs in chinese_domain_direct.items():
            if ch not in chinese_to_english:
                chinese_to_english[ch] = []
            for eng in engs:
                if eng not in chinese_to_english[ch]:
                    chinese_to_english[ch].append(eng)
        
        def extract_keywords(text):
            keywords = []
            for kw in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text.lower()):
                if kw.lower() not in stopwords and len(kw) >= 2:
                    keywords.append(kw.lower())
            return list(set(keywords))
        
        file_keywords = extract_keywords(clean)
        
        best_id, best_score = None, 0
        
        for c in courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "").strip().lower()
            
            if not title:
                continue
            
            title_keywords = extract_keywords(title)
            
            matched_domains = set()
            matched_count = 0
            
            # 检查文件名关键词与课程标题的匹配
            for kw in file_keywords:
                # 直接匹配
                if kw in title_keywords:
                    matched_count += 1
                    matched_domains.add(kw)
                    continue
                
                # 检查中文映射
                if kw in domain_keywords:
                    related_ch = domain_keywords[kw]
                    for ch in related_ch:
                        if ch in title_keywords or any(ch in t for t in title_keywords):
                            matched_count += 1
                            matched_domains.add(kw)
                            break
                
                # 检查英文到中文翻译
                if kw in chinese_to_english:
                    related_eng = chinese_to_english[kw]
                    for eng in related_eng:
                        if eng in file_keywords:
                            matched_count += 1
                            matched_domains.add(kw)
                            break
            
            # 检查课程标题关键词
            for kw in title_keywords:
                if kw in file_keywords:
                    matched_count += 1
                    matched_domains.add(kw)
                    continue
                
                # 检查中文到领域的映射
                if kw in chinese_to_english:
                    related_eng = chinese_to_english[kw]
                    for eng in related_eng:
                        if eng in file_keywords:
                            matched_count += 1
                            matched_domains.add(eng)
                            break
                
                # 检查领域映射中的中文
                for eng, chns in domain_keywords.items():
                    if kw in chns or kw == eng:
                        if eng in file_keywords:
                            matched_count += 1
                            matched_domains.add(eng)
                            break
            
            if matched_count > 0:
                score = min(0.2 + len(matched_domains) * 0.15 + matched_count * 0.05, 0.9)
                if score > best_score:
                    best_score = score
                    best_id = cid
        
        return best_id, round(min(best_score, 1.0), 2)
    
    def _match_file_to_courses(self, filename, courses, threshold=0.2):
        """多对多匹配：返回可能匹配的所有课程及置信度"""
        if not courses:
            return []
        
        matches = []
        for c in courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            score = self._match_course_for_file(filename, [c])[1]
            if score >= threshold:
                matches.append((cid, title, score))
        
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    def _batch_import_files(self, course_id):
        """为指定课程批量选择多个文件导入"""
        files = filedialog.askopenfilenames(
            title=f"批量选择文件 — {self.system.get_course_by_id(course_id).get('course_title', course_id) if self.system.get_course_by_id(course_id) else course_id}",
            filetypes=[("PDF", "*.pdf"), ("文档", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                       ("所有文件", "*.*")]
        )
        if not files:
            return
        added = 0
        skipped = 0
        for fp in files:
            if self.system.rmgr.add_pdf(course_id, fp, BASE):
                added += 1
            else:
                skipped += 1
        msg = f"已添加 {added} 个文件"
        if skipped:
            msg += f"，跳过 {skipped} 个（已存在）"
        messagebox.showinfo("批量导入完成", msg)
        self._log(f"batch import: {added} added, {skipped} skipped -> {course_id[:30]}")
        self._show_course_detail(course_id)

    def _batch_import_files_global(self):
        """全局批量导入：选择多个文件，自动匹配课程，未匹配的手动选择"""
        files = filedialog.askopenfilenames(
            title="批量选择文件 — 自动匹配课程",
            filetypes=[
                ("PDF/文档", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.epub"),
                ("代码/LaTeX", "*.c *.cpp *.py *.js *.java *.tex *.rmd *.md"),
                ("音视频", "*.mp3 *.flac *.mp4 *.avi *.mkv *.mov"),
                ("其他", "*.zip *.lrc *.png *.jpg *.jpeg"),
                ("所有文件", "*.*")]
        )
        if not files:
            return
        self._do_batch_import(list(files))

    def _batch_import_dir_global(self):
        """从目录批量导入：扫描目录下所有支持格式的文件，自动匹配课程"""
        dp = filedialog.askdirectory(
            title="选择包含资源文件的目录（递归扫描子目录）"
        )
        if not dp:
            return
        # 扫描目录下所有支持的文件（包括子目录）
        exts = {
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.rmd', '.md', '.tex', '.c', '.cpp', '.py', '.js', '.java',
            '.mp3', '.flac', '.wav', '.m4a', '.ogg',
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
            '.lrc', '.epub', '.zip', '.tar', '.gz',
            '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
        }
        dp = Path(dp)
        # 递归扫描所有文件
        files = []
        total_scanned = 0
        for f in dp.rglob("*"):
            total_scanned += 1
            if f.is_file() and f.suffix.lower() in exts:
                # 排除隐藏文件和临时文件
                if not f.name.startswith('.') and not f.name.startswith('~'):
                    files.append(str(f))
        files = sorted(files)
        
        if not files:
            messagebox.showinfo("提示", f"扫描了 {total_scanned} 个文件，\n该目录下没有可导入的资源文件")
            return
        
        # 显示扫描结果
        self._log(f"📂 递归扫描 {dp}：找到 {len(files)} 个文件")
        messagebox.showinfo("扫描结果", 
                            f"📂 目录：{dp.name}\n"
                            f"📄 共扫描：{total_scanned} 个文件\n"
                            f"✅ 找到：{len(files)} 个可导入文件")
        
        self._do_batch_import(files)

    def _do_batch_import(self, file_paths):
        """执行批量导入：自动匹配 + 多对多分配对话框"""
        courses = self.system.courses
        
        # 预计算所有文件的多对多匹配
        all_matches = {}  # {filepath: [(cid, title, score), ...]}
        unmatched = []
        
        for fp in file_paths:
            matches = self._match_file_to_courses(Path(fp).name, courses, threshold=0.25)
            if matches:
                all_matches[fp] = matches
            else:
                unmatched.append(fp)
        
        # 弹出确认/调整对话框
        dlg = tk.Toplevel(self.root)
        dlg.title("批量导入文件资源 (多对多)")
        dlg.geometry("1500x800")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"📁 批量导入 {len(file_paths)} 个文件（支持一文件分配多课程）",
                  font=("", 14, "bold"), foreground="#2C3E50").pack(pady=(10, 5))

        # 主表格
        tf = ttk.LabelFrame(dlg, text=f"匹配结果 ({len(all_matches)} 个文件)", padding=6)
        tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ("file", "courses", "top_score", "action")
        tree = ttk.Treeview(tf, columns=cols, show="headings", height=20)
        tree.heading("file", text="文件名")
        tree.heading("courses", text="匹配课程（可多选）")
        tree.heading("top_score", text="最高置信度")
        tree.heading("action", text="操作")
        tree.column("file", width=300)
        tree.column("courses", width=450)
        tree.column("top_score", width=80, anchor="center")
        tree.column("action", width=100)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 搜索过滤栏
        filter_frame = ttk.Frame(tf)
        filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        search_var = tk.StringVar(value="")
        ttk.Label(filter_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=(0, 5))
        search_entry = ttk.Entry(filter_frame, textvariable=search_var, width=25)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # 文件类型过滤
        type_var = tk.StringVar(value="全部")
        ttk.Label(filter_frame, text="类型:").pack(side=tk.LEFT, padx=(10, 5))
        type_combo = ttk.Combobox(filter_frame, textvariable=type_var, width=10, state="readonly")
        all_types = ["全部", "PDF", "文档", "图片", "音频", "视频", "代码", "其他"]
        type_combo['values'] = all_types
        type_combo.pack(side=tk.LEFT, padx=5)
        
        # 匹配度过滤
        score_var = tk.StringVar(value="全部")
        ttk.Label(filter_frame, text="匹配度:").pack(side=tk.LEFT, padx=(10, 5))
        score_combo = ttk.Combobox(filter_frame, textvariable=score_var, width=10, state="readonly")
        score_combo['values'] = ["全部", ">=90%", ">=70%", ">=50%", ">=30%"]
        score_combo.pack(side=tk.LEFT, padx=5)
        
        # 课程过滤
        course_filter_var = tk.StringVar(value="全部课程")
        ttk.Label(filter_frame, text="课程:").pack(side=tk.LEFT, padx=(10, 5))
        course_filter_combo = ttk.Combobox(filter_frame, textvariable=course_filter_var, width=15, state="readonly")
        course_options = ["全部课程"] + [f"{c.get('course_title', '')[:20]}" for c in courses[:50]]
        course_filter_combo['values'] = course_options
        course_filter_combo.pack(side=tk.LEFT, padx=5)
        
        # 显示计数
        count_var = tk.StringVar(value=f"显示: {len(all_matches)} / {len(all_matches)}")
        count_label = ttk.Label(filter_frame, textvariable=count_var, foreground="#2980b9")
        count_label.pack(side=tk.RIGHT, padx=10)
        
        # 行映射 {iid: {filepath, selected_cids}}
        row_map = {}
        # 文件名到iid映射
        file_to_iid = {}
        
        # 所有行数据（用于过滤）
        all_tree_items = {}
        
        # 文件类型映射
        FILE_TYPE_MAP = {
            'pdf': 'PDF',
            'doc': '文档', 'docx': '文档',
            'xls': '文档', 'xlsx': '文档',
            'ppt': '文档', 'pptx': '文档',
            'rmd': '文档', 'md': '文档', 'tex': '文档',
            'txt': '文档', 'epub': '文档',
            'png': '图片', 'jpg': '图片', 'jpeg': '图片',
            'gif': '图片', 'svg': '图片', 'webp': '图片',
            'mp3': '音频', 'flac': '音频', 'wav': '音频', 'm4a': '音频', 'ogg': '音频',
            'mp4': '视频', 'avi': '视频', 'mkv': '视频', 'mov': '视频', 'wmv': '视频', 'flv': '视频',
            'py': '代码', 'js': '代码', 'java': '代码', 'c': '代码', 'cpp': '代码',
            'lrc': '其他', 'zip': '其他', 'tar': '其他', 'gz': '其他',
        }
        
        def _get_file_type(filename):
            ext = Path(filename).suffix.lower().lstrip('.')
            return FILE_TYPE_MAP.get(ext, '其他')
        
        def _apply_filter(*args):
            """应用所有过滤器"""
            search_text = search_var.get().lower().strip()
            file_type = type_var.get()
            score_threshold = score_var.get()
            course_filter = course_filter_var.get()
            show_unmatched = show_unmatched_var.get()
            
            # 解析匹配度阈值
            score_min = 0
            if score_threshold == ">=90%":
                score_min = 0.9
            elif score_threshold == ">=70%":
                score_min = 0.7
            elif score_threshold == ">=50%":
                score_min = 0.5
            elif score_threshold == ">=30%":
                score_min = 0.3
            
            # 获取选中的课程ID
            selected_cid_for_filter = None
            if course_filter != "全部课程":
                for c in courses:
                    if c.get('course_title', '')[:20] == course_filter:
                        selected_cid_for_filter = c.get('note_id', c.get('course_title', ''))
                        break
            
            # 清除现有显示
            for iid in tree.get_children():
                tree.delete(iid)
            
            visible_count = 0
            visible_unmatched = 0
            
            # 处理未匹配文件
            if show_unmatched:
                for iid, fp in unmatched_items.items():
                    filename = Path(fp).name.lower()
                    # 检查文件名搜索
                    if search_text and search_text not in filename:
                        continue
                    # 检查文件类型
                    if file_type != "全部":
                        if _get_file_type(fp) != file_type:
                            continue
                    
                    # 添加到树
                    selected_cids = row_map[iid]['selected_cids']
                    if selected_cids:
                        course_names = []
                        for sc in selected_cids:
                            course = self.system.get_course_by_id(sc)
                            if course:
                                course_names.append(f"✓{course.get('course_title', sc)[:20]}")
                        courses_text = " | ".join(course_names)[:50] if course_names else "未选择"
                        tree.insert("", "end", iid=iid, values=(
                            Path(fp).name[:45],
                            courses_text,
                            "手动",
                            "编辑"
                        ))
                    else:
                        tree.insert("", "end", iid=iid, values=(
                            Path(fp).name[:45],
                            "❌ 未匹配",
                            "—",
                            "分配课程"
                        ))
                        tree.item(iid, tags=("unmatched",))
                    visible_count += 1
                    visible_unmatched += 1
            
            # 处理已匹配文件
            for iid, item_data in all_tree_items.items():
                if item_data.get('is_unmatched'):
                    continue  # 已在上方处理
                    
                fp = item_data['filepath']
                matches = all_matches.get(fp, [])
                top_score = matches[0][2] if matches else 0
                
                # 检查文件名搜索
                filename = Path(fp).name.lower()
                if search_text and search_text not in filename:
                    continue
                
                # 检查文件类型
                if file_type != "全部":
                    if _get_file_type(fp) != file_type:
                        continue
                
                # 检查匹配度阈值
                if score_min > 0 and top_score < score_min:
                    continue
                
                # 检查课程过滤
                if selected_cid_for_filter:
                    if not any(cid == selected_cid_for_filter for cid, _, _ in matches):
                        continue
                
                # 添加到树
                selected_cids = row_map[iid]['selected_cids']
                if selected_cids:
                    course_names = []
                    for sc in selected_cids:
                        course = self.system.get_course_by_id(sc)
                        if course:
                            course_names.append(f"✓{course.get('course_title', sc)[:20]}")
                    courses_text = " | ".join(course_names)[:50] if course_names else "未选择"
                    tree.insert("", "end", iid=iid, values=(
                        Path(fp).name[:45],
                        courses_text,
                        f"{int(top_score*100)}%",
                        "编辑"
                    ))
                else:
                    tree.insert("", "end", iid=iid, values=(
                        Path(fp).name[:45],
                        "未选择",
                        f"{int(top_score*100)}%" if top_score > 0 else "—",
                        "编辑"
                    ))
                visible_count += 1
            
            # 更新计数
            matched_count = visible_count - visible_unmatched
            count_var.set(f"显示: {visible_count} ({matched_count}匹配 + {visible_unmatched}未配)")
        
        # 绑定过滤事件
        search_var.trace_add("write", lambda *_: _apply_filter())
        type_var.trace_add("write", lambda *_: _apply_filter())
        score_var.trace_add("write", lambda *_: _apply_filter())
        course_filter_var.trace_add("write", lambda *_: _apply_filter())
        
        def _edit_or_assign_file(iid):
            """编辑已匹配文件 或 分配未匹配文件"""
            fp = row_map[iid]['filepath']
            if iid in unmatched_items:
                # 未匹配文件 - 直接弹出课程选择
                _assign_single_unmatched(fp, iid)
            else:
                # 已匹配文件 - 编辑课程
                _edit_file_courses(iid)
        
        def _assign_single_unmatched(fp, iid):
            """为单个未匹配文件选择课程"""
            sel_dlg = tk.Toplevel(dlg)
            sel_dlg.title(f"分配课程 - {Path(fp).name[:30]}")
            sel_dlg.geometry("400x500")
            sel_dlg.transient(dlg)
            sel_dlg.grab_set()

            ttk.Label(sel_dlg, text=f"为《{Path(fp).name[:30]}》选择课程",
                      font=("", 11, "bold")).pack(pady=8)

            search_var_um = tk.StringVar()
            sf_um = ttk.Frame(sel_dlg)
            sf_um.pack(fill=tk.X, padx=10)
            ttk.Label(sf_um, text="搜索:").pack(side=tk.LEFT)
            se_um = ttk.Entry(sf_um, textvariable=search_var_um, width=30)
            se_um.pack(side=tk.LEFT, padx=5)
            se_um.focus()

            cl_um = tk.Listbox(sel_dlg, height=20, font=("", 10), exportselection=False)
            cl_um.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            cl_um._cid_map = {}

            def _pop_um(ft=""):
                cl_um.delete(0, tk.END)
                idx_um = 0
                for c in courses:
                    cid_i = c.get("note_id", c.get("course_title", ""))
                    title = c.get("course_title", "")
                    domain = c.get("domain", "")
                    dn = DOMAIN_NAMES.get(domain, domain)
                    label = f"[{dn}] {title}"
                    if not ft or ft.lower() in label.lower():
                        cl_um.insert(tk.END, label)
                        cl_um._cid_map[idx_um] = cid_i
                        idx_um += 1
            _pop_um()
            search_var_um.trace_add("write", lambda *_: _pop_um(search_var_um.get()))

            def _sel_um():
                s_um = cl_um.curselection()
                if s_um:
                    new_cid = cl_um._cid_map.get(s_um[0])
                    if new_cid:
                        # 添加到已分配
                        row_map[iid]['selected_cids'].add(new_cid)
                        # 更新表格显示
                        course = self.system.get_course_by_id(new_cid)
                        title = course.get('course_title', new_cid) if course else new_cid
                        tree.item(iid, values=(
                            Path(fp).name[:45],
                            f"✓{title[:20]}",
                            "手动",
                            "编辑"
                        ))
                        tree.item(iid, tags=())
                        # 从unmatched列表移除
                        if fp in unmatched:
                            idx_um_del = unmatched.index(fp)
                            unmatched.pop(idx_um_del)
                            unmatched_list.delete(idx_um_del)
                            uf.config(text=f"未匹配文件 ({len(unmatched)} 个)")
                        sel_dlg.destroy()
                        messagebox.showinfo("已分配", f"已将《{Path(fp).name}》分配到《{title}》", parent=dlg)

            ttk.Button(sel_dlg, text="确认", command=_sel_um).pack(pady=8)
            cl_um.bind("<Double-1>", lambda e: _sel_um())
        
        def _update_row(iid, fp, selected_cids):
            row_map[iid]['selected_cids'] = selected_cids
            if selected_cids:
                course_names = []
                for sc in selected_cids:
                    course = self.system.get_course_by_id(sc)
                    if course:
                        course_names.append(f"✓{course.get('course_title', sc)[:20]}")
                courses_text = " | ".join(course_names)[:50] if course_names else "未选择"
                top_score = all_matches.get(fp, [(None, None, 0)])[0][2] if all_matches.get(fp) else 0
                tree.item(iid, values=(Path(fp).name[:45], courses_text, f"{int(top_score*100)}%", "编辑"))
            else:
                tree.item(iid, values=(Path(fp).name[:45], "未选择", "—", "编辑"))

        def _edit_file_courses(iid):
            fp = row_map[iid]['filepath']
            selected = list(row_map[iid]['selected_cids'])
            
            edit_dlg = tk.Toplevel(dlg)
            edit_dlg.title(f"编辑 - {Path(fp).name[:30]}")
            edit_dlg.geometry("500x500")
            edit_dlg.transient(dlg)
            edit_dlg.grab_set()

            ttk.Label(edit_dlg, text=f"文件: {Path(fp).name[:40]}",
                      font=("", 11, "bold")).pack(pady=8)
            
            ttk.Label(edit_dlg, text="勾选要分配到的课程（可多选）：",
                      font=("", 9)).pack(anchor="w", padx=10)

            canvas = tk.Canvas(edit_dlg, highlightthickness=0)
            scrollbar = ttk.Scrollbar(edit_dlg, orient="vertical", command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)
            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 10))

            check_vars = {}
            suggested = set()
            
            # 添加建议的课程
            if fp in all_matches:
                for cid, title, score in all_matches[fp][:5]:
                    suggested.add(cid)
            
            for c in courses:
                cid = c.get("note_id", c.get("course_title", ""))
                title = c.get("course_title", "")
                domain = c.get("domain", "")
                dn = DOMAIN_NAMES.get(domain, domain)
                
                var = tk.BooleanVar(value=cid in selected or cid in suggested)
                check_vars[cid] = var
                
                cb = ttk.Checkbutton(scroll_frame, text=f"[{dn}] {title[:35]}", variable=var)
                cb.pack(anchor="w", padx=10, pady=2)
                
                # 显示匹配分数
                if fp in all_matches:
                    for c2, t2, score in all_matches[fp]:
                        if c2 == cid:
                            score_label = ttk.Label(scroll_frame, text=f"    匹配度: {int(score*100)}%", 
                                                   foreground="#2980b9", font=("", 8))
                            score_label.pack(anchor="w", padx=30)
                            break

            def _confirm():
                new_selected = [cid for cid, v in check_vars.items() if v.get()]
                _update_row(iid, fp, new_selected)
                edit_dlg.destroy()

            ttk.Button(edit_dlg, text="确认", command=_confirm).pack(pady=10)

        # 填充表格
        for fp, matches in all_matches.items():
            top_score = matches[0][2] if matches else 0
            selected = [cid for cid, _, _ in matches[:3]]  # 默认选中前3个高置信度
            
            course_preview = " | ".join([f"{t[:15]}({int(s*100)}%)" for _, t, s in matches[:3]])
            
            iid = tree.insert("", "end", values=(
                Path(fp).name[:45],
                course_preview[:55],
                f"{int(top_score*100)}%",
                "编辑"
            ))
            row_map[iid] = {'filepath': fp, 'selected_cids': set(selected)}
            file_to_iid[fp] = iid
            all_tree_items[iid] = {'filepath': fp, 'matches': matches}

        tree.tag_configure("low_conf", foreground="#e67e22")
        tree.tag_configure("unmatched", foreground="#95a5a6")
        tree.bind("<Double-1>", lambda e: _edit_or_assign_file(tree.selection()[0]) if tree.selection() else None)

        # 将未匹配文件也添加到主表格（带标记）
        unmatched_items = {}
        for fp in unmatched:
            top_score = 0
            selected = []
            
            iid = tree.insert("", "end", values=(
                Path(fp).name[:45],
                "❌ 未匹配",
                "—",
                "分配课程"
            ))
            row_map[iid] = {'filepath': fp, 'selected_cids': set()}
            file_to_iid[fp] = iid
            all_tree_items[iid] = {'filepath': fp, 'matches': [], 'is_unmatched': True}
            unmatched_items[iid] = fp
        
        # 添加"显示未匹配"复选框
        show_unmatched_var = tk.BooleanVar(value=True)
        show_unmatched_cb = ttk.Checkbutton(
            filter_frame, 
            text="显示未匹配", 
            variable=show_unmatched_var,
            command=lambda: _apply_filter()
        )
        show_unmatched_cb.pack(side=tk.RIGHT, padx=5)
        
        # 绑定show_unmatched的trace（在变量定义后）
        show_unmatched_var.trace_add("write", lambda *_: _apply_filter())

        # 未匹配文件
        uf = ttk.LabelFrame(dlg, text=f"未匹配文件 ({len(unmatched)} 个)", padding=6)
        uf.pack(fill=tk.X, padx=10, pady=5)

        unmatched_list = tk.Listbox(uf, height=min(4, len(unmatched) + 1), font=("Consolas", 9), exportselection=False)
        for fp in unmatched:
            unmatched_list.insert(tk.END, Path(fp).name)
        unmatched_list.pack(fill=tk.X)

        # 未匹配文件按钮
        def _assign_unmatched():
            sel = unmatched_list.curselection()
            if not sel:
                messagebox.showinfo("提示", "请先在列表中选择一个文件", parent=dlg)
                return
            idx = sel[0]
            fp = unmatched[idx]
            # 弹出课程选择（复用逻辑）
            sel_dlg = tk.Toplevel(dlg)
            sel_dlg.title("选择课程")
            sel_dlg.geometry("400x500")
            sel_dlg.transient(dlg)
            sel_dlg.grab_set()

            ttk.Label(sel_dlg, text=f"为《{Path(fp).name[:30]}》选择课程",
                      font=("", 11, "bold")).pack(pady=8)

            search_var2 = tk.StringVar()
            sf2 = ttk.Frame(sel_dlg)
            sf2.pack(fill=tk.X, padx=10)
            ttk.Label(sf2, text="搜索:").pack(side=tk.LEFT)
            se2 = ttk.Entry(sf2, textvariable=search_var2, width=30)
            se2.pack(side=tk.LEFT, padx=5)
            se2.focus()

            cl2 = tk.Listbox(sel_dlg, height=20, font=("", 10), exportselection=False)
            cl2.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            cl2._cid_map = {}

            def _pop2(ft=""):
                cl2.delete(0, tk.END)
                idx2 = 0
                for c in courses:
                    cid_i = c.get("note_id", c.get("course_title", ""))
                    title = c.get("course_title", "")
                    domain = c.get("domain", "")
                    dn = DOMAIN_NAMES.get(domain, domain)
                    label = f"[{dn}] {title}"
                    if not ft or ft.lower() in label.lower():
                        cl2.insert(tk.END, label)
                        cl2._cid_map[idx2] = cid_i
                        idx2 += 1
            _pop2()
            search_var2.trace_add("write", lambda *_: _pop2(search_var2.get()))

            def _sel2():
                s2 = cl2.curselection()
                if s2:
                    new_cid = cl2._cid_map.get(s2[0])
                    if new_cid:
                        # 添加到匹配结果表格
                        course = self.system.get_course_by_id(new_cid)
                        title = course.get("course_title", new_cid) if course else new_cid
                        iid = tree.insert("", "end", values=(Path(fp).name[:45], f"✓{title[:20]}", "手动", "编辑"))
                        row_map[iid] = {'filepath': fp, 'selected_cids': {new_cid}}
                        # 从未匹配列表移除
                        unmatched.pop(idx)
                        unmatched_list.delete(idx)
                        uf.config(text=f"未匹配文件 ({len(unmatched)} 个)")
                        sel_dlg.destroy()

            ttk.Button(sel_dlg, text="确认", command=_sel2).pack(pady=8)
            cl2.bind("<Double-1>", lambda e: _sel2())

        btn_f = ttk.Frame(uf)
        btn_f.pack(fill=tk.X, pady=3)
        ttk.Button(btn_f, text="📋 分配到课程", command=_assign_unmatched).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="📋 全部分配同一课程", command=lambda: self._assign_all_unmatched(
            unmatched, unmatched_list, uf, tree, row_map, courses, dlg)).pack(side=tk.LEFT, padx=5)

        # 底部确认/取消
        bottom = ttk.Frame(dlg)
        bottom.pack(fill=tk.X, padx=10, pady=10)

        def _confirm():
            added, skipped, total_assignments = 0, 0, 0
            for iid in tree.get_children():
                row_data = row_map[iid]
                fp = row_data['filepath']
                selected_cids = row_data['selected_cids']
                
                for cid in selected_cids:
                    if self.system.rmgr.add_pdf(cid, fp, BASE):
                        added += 1
                    else:
                        skipped += 1
                    total_assignments += 1
                
                # 如果没有选中任何课程，尝试用最高匹配
                if not selected_cids:
                    if fp in all_matches and all_matches[fp]:
                        cid = all_matches[fp][0][0]
                        if self.system.rmgr.add_pdf(cid, fp, BASE):
                            added += 1
                        else:
                            skipped += 1
                        total_assignments += 1
            
            msg = f"已分配 {total_assignments} 个资源到课程\n"
            msg += f"成功添加 {added} 个，重复跳过 {skipped} 个"
            if len(unmatched) > 0:
                msg += f"\n{len(unmatched)} 个文件未分配"
            messagebox.showinfo("批量导入完成", msg, parent=self.root)
            self._log(f"batch import: {total_assignments} assigned, {added} added, {skipped} skipped")
            dlg.destroy()
            self._refresh_all()

        def _cancel():
            dlg.destroy()

        ttk.Button(bottom, text="✅ 确认导入", command=_confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(bottom, text="❌ 取消", command=_cancel).pack(side=tk.LEFT, padx=10)

    def _assign_all_unmatched(self, unmatched, unmatched_listbox, uf_frame, tree, row_map, courses, parent_dlg):
        """将所有未匹配文件批量分配到同一课程"""
        if not unmatched:
            messagebox.showinfo("提示", "没有未匹配的文件", parent=parent_dlg)
            return
        # 弹出课程选择
        sel_dlg = tk.Toplevel(parent_dlg)
        sel_dlg.title("选择课程 — 全部分配")
        sel_dlg.geometry("400x500")
        sel_dlg.transient(parent_dlg)
        sel_dlg.grab_set()

        ttk.Label(sel_dlg, text=f"将 {len(unmatched)} 个文件全部分配到：",
                  font=("", 11, "bold")).pack(pady=8)

        search_var = tk.StringVar()
        sf = ttk.Frame(sel_dlg)
        sf.pack(fill=tk.X, padx=10)
        ttk.Label(sf, text="搜索:").pack(side=tk.LEFT)
        se = ttk.Entry(sf, textvariable=search_var, width=30)
        se.pack(side=tk.LEFT, padx=5)
        se.focus()

        cl = tk.Listbox(sel_dlg, height=20, font=("", 10), exportselection=False)
        cl.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cl._cid_map = {}

        def _populate(ft=""):
            cl.delete(0, tk.END)
            idx = 0
            for c in courses:
                cid_i = c.get("note_id", c.get("course_title", ""))
                title = c.get("course_title", "")
                domain = c.get("domain", "")
                dn = DOMAIN_NAMES.get(domain, domain)
                label = f"[{dn}] {title}"
                if not ft or ft.lower() in label.lower():
                    cl.insert(tk.END, label)
                    cl._cid_map[idx] = cid_i
                    idx += 1
        _populate()
        search_var.trace_add("write", lambda *_: _populate(search_var.get()))

        def _select():
            s = cl.curselection()
            if s:
                chosen_cid = cl._cid_map.get(s[0])
                if chosen_cid:
                    course = self.system.get_course_by_id(chosen_cid)
                    title = course.get("course_title", chosen_cid) if course else chosen_cid
                    # 把所有未匹配文件加入 tree
                    for fp in unmatched[:]:
                        iid = tree.insert("", "end", values=(Path(fp).name[:45], f"✓{title[:20]}", "手动", "编辑"))
                        row_map[iid] = {'filepath': fp, 'selected_cids': {chosen_cid}}
                    unmatched.clear()
                    unmatched_listbox.delete(0, tk.END)
                    uf_frame.config(text="未匹配文件 (0 个)")
                    sel_dlg.destroy()

        ttk.Button(sel_dlg, text="确认", command=_select).pack(pady=8)
        cl.bind("<Double-1>", lambda e: _select())

    def _import_from_browser_bookmarks(self, callback):
        """从浏览器书签导入URL（支持Chrome/Edge/Firefox，多选导入）"""
        import os
        import sqlite3

        browsers = [
            ("Chrome", os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Bookmarks"), "json"),
            ("Edge", os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Bookmarks"), "json"),
            ("Firefox", os.path.expanduser("~\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles"), "firefox"),
        ]

        found_info = None
        for browser_name, path, btype in browsers:
            if btype == "firefox":
                if os.path.isdir(path):
                    for sub in os.listdir(path):
                        full_path = os.path.join(path, sub, "places.sqlite")
                        if os.path.exists(full_path):
                            found_info = (browser_name, full_path, btype)
                            break
            else:
                if os.path.exists(path):
                    found_info = (browser_name, path, btype)
                    break

        if not found_info:
            messagebox.showinfo("提示", "未找到支持的浏览器书签文件\n(Chrome/Edge/Firefox)")
            return

        browser_name, bookmark_path, btype = found_info
        bookmarks = []

        try:
            if btype == "json":
                import json
                with open(bookmark_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                def extract(node, parent_name=""):
                    if 'children' in node:
                        folder_name = node.get('name', '')
                        full_name = f"{parent_name}/{folder_name}" if parent_name else folder_name
                        for child in node['children']:
                            extract(child, full_name)
                    elif 'url' in node:
                        name = node.get('name', '') or node['url'][:30]
                        bookmarks.append({
                            'name': name,
                            'url': node['url'],
                            'folder': parent_name
                        })

                roots = data.get('roots', {})
                for root_name, root_node in roots.items():
                    extract(root_node)

            elif btype == "firefox":
                conn = sqlite3.connect(bookmark_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.title, p.url, f.title as folder
                    FROM moz_bookmarks b
                    JOIN moz_places p ON b.fk = p.id
                    LEFT JOIN moz_bookmarks f ON b.parent = f.id
                    WHERE p.url IS NOT NULL
                    ORDER BY b.dateAdded DESC
                """)
                for row in cursor.fetchall():
                    bookmarks.append({
                        'name': row[0] or row[1][:30],
                        'url': row[1],
                        'folder': row[2] or ""
                    })
                conn.close()

            if not bookmarks:
                messagebox.showinfo("提示", "未找到书签")
                return

            dlg = tk.Toplevel(self.root)
            dlg.title(f"📚 {browser_name} 书签")
            dlg.geometry("650x500")
            dlg.transient(self.root)
            dlg.grab_set()

            ttk.Label(dlg, text=f"选择要导入的书签（{browser_name}，支持Ctrl/Shift多选）：",
                      font=("", 10, "bold")).pack(pady=(10, 5), padx=10, anchor="w")

            search_frame = ttk.Frame(dlg)
            search_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
            ttk.Label(search_frame, text="🔍 搜索:").pack(side=tk.LEFT)
            search_var = tk.StringVar()
            search_entry = ttk.Entry(search_frame, textvariable=search_var, width=40)
            search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            list_frame = ttk.Frame(dlg)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, font=("Consolas", 9))
            sb = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=sb.set)
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)

            filtered_bookmarks = list(bookmarks)

            sel_label = ttk.Label(dlg, text="已选择: 0 个 (共0个)", foreground="#2980b9")
            sel_label.pack(anchor="w", padx=10)

            def update_list():
                nonlocal filtered_bookmarks
                keyword = search_var.get().strip().lower()
                if keyword:
                    filtered_bookmarks = [bm for bm in bookmarks 
                                         if keyword in bm['name'].lower() or keyword in bm['url'].lower()]
                else:
                    filtered_bookmarks = list(bookmarks)
                listbox.delete(0, tk.END)
                for i, bm in enumerate(filtered_bookmarks):
                    folder = f" [{bm['folder']}]" if bm['folder'] else ""
                    listbox.insert(tk.END, f"{i+1:4d}. {bm['name']}{folder}")
                sel_label.config(text=f"已选择: 0 个 (共{len(filtered_bookmarks)}个)")

            search_var.trace_add("write", lambda *a: update_list())
            update_list()

            def update_sel():
                sel_label.config(text=f"已选择: {len(listbox.curselection())} 个 (共{len(filtered_bookmarks)}个)")

            listbox.bind('<<ListboxSelect>>', lambda e: update_sel())

            def select_multi():
                idxs = listbox.curselection()
                if not idxs:
                    return
                for idx in idxs:
                    bm = filtered_bookmarks[idx]
                    callback(bm['name'], bm['url'])
                dlg.destroy()

            def select_all():
                listbox.selection_set(0, tk.END)
                update_sel()

            def select_none():
                listbox.selection_clear(0, tk.END)
                update_sel()

            bf = ttk.Frame(dlg)
            bf.pack(pady=10)
            ttk.Button(bf, text="确认导入", command=select_multi).pack(side=tk.LEFT, padx=5)
            ttk.Button(bf, text="全选", command=select_all).pack(side=tk.LEFT, padx=2)
            ttk.Button(bf, text="取消选择", command=select_none).pack(side=tk.LEFT, padx=2)
            ttk.Button(bf, text="关闭", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        except Exception as e:
            messagebox.showerror("错误", f"读取书签失败: {str(e)}")
    
    def _open_browser_for_copy(self):
        """打开浏览器让用户自行复制URL"""
        import webbrowser
        webbrowser.open("https://www.arxiv.org")
        messagebox.showinfo("提示", "浏览器已打开，请访问需要的网页并复制URL，然后返回此窗口粘贴")
    
    def _add_url_resource(self, course_id):
        dlg = tk.Toplevel(self.root)
        dlg.title("添加资源")
        dlg.geometry("480x320")
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=f"课程ID: {course_id[:30]}").pack(pady=(10, 5))
        ttk.Label(dlg, text="名称：").pack()
        ne = ttk.Entry(dlg, width=55)
        ne.pack(pady=2)
        ttk.Label(dlg, text="URL：").pack()
        ue = ttk.Entry(dlg, width=55)
        ue.pack(pady=2)

        try:
            clip = self.root.clipboard_get().strip()
            urls = _detect_urls(clip)
            if urls:
                ue.insert(0, urls[0])
                auto_title = _extract_title_from_url(urls[0])
                if auto_title:
                    ne.insert(0, auto_title)
        except Exception:
            pass

        ne.focus()

        type_var = tk.StringVar(value="auto")
        tf = ttk.Frame(dlg)
        tf.pack(pady=5)
        ttk.Label(tf, text="类型：").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="自动检测", variable=type_var, value="auto").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🌐 链接", variable=type_var, value="url").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🎬 视频", variable=type_var, value="video").pack(side=tk.LEFT, padx=4)

        def ok():
            n, u = ne.get().strip(), ue.get().strip()
            if not u:
                messagebox.showwarning("提示", "请填写URL", parent=dlg)
                return
            if not n:
                n = _extract_title_from_url(u) or u[:30]
            rtype = type_var.get()
            if rtype == "auto":
                rtype = _classify_url(u)
            if rtype == "video":
                ok_ = self.system.rmgr.add_video(course_id, n, url=u)
            else:
                ok_ = self.system.rmgr.add_url(course_id, n, u)
            if ok_:
                messagebox.showinfo("成功", f"{'视频' if rtype == 'video' else '资源'}已添加", parent=self.root)
                dlg.destroy()
                self._show_course_detail(course_id)
            else:
                messagebox.showinfo("提示", "该资源已存在", parent=self.root)

        bf = ttk.Frame(dlg)
        bf.pack(pady=8)
        ttk.Button(bf, text="确认", command=ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="📋 从剪贴板粘贴",
                   command=lambda: self._paste_clipboard_to_entry(ue, ne)).pack(side=tk.LEFT, padx=4)
        
        # 浏览器导入按钮
        bf2 = ttk.Frame(dlg)
        bf2.pack(pady=4)
        ttk.Button(bf2, text="📚 从浏览器书签导入", 
                   command=lambda: self._import_from_browser_bookmarks(
                       lambda name, url: (ue.insert(0, url), ne.insert(0, name))
                   )).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf2, text="🌐 打开浏览器复制", 
                   command=self._open_browser_for_copy).pack(side=tk.LEFT, padx=4)

    def _resolve_resource_path(self, path_str):
        """解析资源路径，支持绝对路径和相对于BASE的相对路径"""
        # 先尝试作为绝对路径
        fp_abs = Path(path_str)
        if fp_abs.is_absolute() and fp_abs.exists():
            return fp_abs
        
        # 再尝试作为相对于BASE的路径
        fp = BASE / path_str
        if fp.exists():
            return fp
        
        # 如果都不存在，返回相对于BASE的路径（用于错误提示）
        return fp

    def _open_resource_pdf(self, path_str):
        """打开资源文件，支持绝对路径和相对于BASE的相对路径"""
        fp = self._resolve_resource_path(path_str)
        if fp.exists():
            self._wf_log_action("open_pdf", detail=str(fp))
            open_file(str(fp))
        else:
            messagebox.showerror("文件不存在", f"找不到文件：\n{fp}")

    def _open_url(self, url):
        self._wf_log_action("open_url", detail=url[:80])
        webbrowser.open(url)

    def _add_lesson_resource(self, course_id, lesson_number, on_success=None):
        """为指定课时添加资源（PDF 或 URL）
        on_success: 添加成功后的回调（用于刷新调用方UI）
        """
        dlg = tk.Toplevel(self.root)
        dlg.title(f"添加课时 {lesson_number} 资源")
        dlg.geometry("500x350")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        course = self.system.get_course_by_id(course_id)
        lesson = None
        if course:
            for l in course.get("lessons", []):
                if l.get("lesson_number") == lesson_number:
                    lesson = l
                    break

        ltitle = lesson.get("lesson_title", "") if lesson else ""
        ttk.Label(dlg, text=f"课程: {course.get('course_title', '')[:30] if course else course_id}",
                  style="Sub.TLabel").pack(pady=(8, 2))
        ttk.Label(dlg, text=f"课时 {lesson_number}: {ltitle}",
                  font=("", 11, "bold")).pack(pady=2)

        ttk.Separator(dlg, orient="horizontal").pack(fill=tk.X, padx=10, pady=5)

        # 类型选择
        type_var = tk.StringVar(value="pdf")
        tf = ttk.Frame(dlg)
        tf.pack(pady=5)
        ttk.Radiobutton(tf, text="📄 文件(PDF)", variable=type_var, value="pdf").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(tf, text="🌐 URL书签", variable=type_var, value="url").pack(side=tk.LEFT, padx=10)

        # 切换区域容器
        switch_frame = ttk.Frame(dlg)
        switch_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # ── PDF 面板 ──
        pdf_frame = ttk.Frame(switch_frame)
        pdf_entry = ttk.Entry(pdf_frame, width=45)
        pdf_entry.pack(side=tk.LEFT, padx=(0, 5))

        def browse_pdf():
            fp = filedialog.askopenfilename(title="选择文件",
                                            filetypes=[("PDF", "*.pdf"), ("所有文件", "*.*")],
                                            parent=dlg)
            if fp:
                pdf_entry.delete(0, tk.END)
                pdf_entry.insert(0, fp)

        ttk.Button(pdf_frame, text="浏览...", command=browse_pdf).pack(side=tk.LEFT)

        # ── URL 面板 ──
        url_frame = ttk.Frame(switch_frame)
        ttk.Label(url_frame, text="名称:").pack(anchor="w")
        name_entry = ttk.Entry(url_frame, width=50)
        name_entry.pack(fill=tk.X, pady=2)
        ttk.Label(url_frame, text="URL:").pack(anchor="w")
        url_entry = ttk.Entry(url_frame, width=50)
        url_entry.pack(fill=tk.X, pady=2)

        # 初始显示
        pdf_frame.pack(fill=tk.X, pady=5)

        # 类型切换回调
        def _switch_type(*_args):
            for w in switch_frame.winfo_children():
                w.pack_forget()
            if type_var.get() == "pdf":
                pdf_frame.pack(fill=tk.X, pady=5)
            else:
                url_frame.pack(fill=tk.X, pady=5)

        type_var.trace_add("write", _switch_type)

        # 作用域选择
        scope_var = tk.StringVar(value="lesson")
        sf = ttk.Frame(dlg)
        sf.pack(pady=5)
        ttk.Radiobutton(sf, text=f"仅课时 {lesson_number}", variable=scope_var, value="lesson").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(sf, text="课程级", variable=scope_var, value="course").pack(side=tk.LEFT, padx=10)

        def ok():
            ln = lesson_number if scope_var.get() == "lesson" else None
            added = False
            if type_var.get() == "pdf":
                fp = pdf_entry.get().strip()
                if fp:
                    if self.system.rmgr.add_pdf(course_id, fp, BASE, lesson_number=ln):
                        added = True
                    else:
                        messagebox.showinfo("提示", "资源已存在", parent=self.root)
                        return
                else:
                    messagebox.showwarning("提示", "请选择文件", parent=dlg)
                    return
            else:
                n, u = name_entry.get().strip(), url_entry.get().strip()
                if n and u:
                    if self.system.rmgr.add_url(course_id, n, u, lesson_number=ln):
                        added = True
                    else:
                        messagebox.showinfo("提示", "URL已存在", parent=self.root)
                        return
                else:
                    messagebox.showwarning("提示", "请填写名称和URL", parent=dlg)
                    return
            if added:
                dlg.destroy()
                # 刷新调用方UI
                if on_success:
                    on_success()
                # 刷新课程详情页（如果当前正在显示）
                if hasattr(self, '_current_detail_course') and self._current_detail_course == course_id:
                    self._show_course_detail(course_id)
                # 刷新执行模式右侧面板
                self._refresh_exec_panel(course_id, lesson_number)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确认添加", command=ok).pack(side=tk.LEFT, padx=4)
        
        # 浏览器导入按钮
        ttk.Button(btn_frame, text="📚 从浏览器书签导入", 
                   command=lambda: self._import_from_browser_bookmarks(
                       lambda name, url: (url_entry.insert(0, url), name_entry.insert(0, name))
                   )).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="🌐 打开浏览器复制", 
                   command=self._open_browser_for_copy).pack(side=tk.LEFT, padx=4)

    def _render_resource_row(self, parent, res, course_id=None, lesson_number=None, on_delete=None):
        """渲染单条资源行（执行模式资源分栏复用）
        
        Args:
            on_delete: 删除后回调（用于刷新 UI），若提供则显示删除按钮
        """
        rt = res.get("type", "")
        label = res.get("label", "")
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        icon = ResourceMgr.RESOURCE_ICONS.get(rt, "📎")
        ttk.Label(row, text=f"  {icon}", font=("", 10)).pack(side=tk.LEFT)
        ttk.Label(row, text=label, font=("", 9), wraplength=350).pack(side=tk.LEFT, fill=tk.X, expand=True)
        if rt == "pdf":
            ttk.Button(row, text="📂", width=3,
                       command=lambda p=res.get("path", ""): self._open_resource_pdf(p)).pack(side=tk.RIGHT)
        elif rt == "url":
            ttk.Button(row, text="🌐", width=3,
                       command=lambda u=res.get("url", ""): self._open_url(u)).pack(side=tk.RIGHT)
        if on_delete and course_id:
            ttk.Button(row, text="✕", width=3,
                       command=lambda: self._delete_resource(course_id, res, on_delete)).pack(side=tk.RIGHT, padx=1)

    def _delete_resource(self, course_id, res, on_done=None):
        """删除资源并确认"""
        label = res.get("label", "")
        if not messagebox.askyesno("确认删除", f"确定要删除资源吗？\n{label}"):
            return
        self.system.rmgr.remove(course_id, res)
        if on_done:
            on_done()

    def _add_course_file_exec(self, course_id, lesson_number):
        """执行模式资源分栏：为课程添加课程级文件"""
        fp = filedialog.askopenfilename(
            title=f"为课程添加课程级文件",
            filetypes=[("PDF", "*.pdf"), ("所有文件", "*.*")])
        if not fp:
            return
        if self.system.rmgr.add_pdf(course_id, fp, BASE):
            self._refresh_exec_panel(course_id, lesson_number)
        else:
            messagebox.showinfo("提示", "该文件已存在")

    def _add_course_url_exec(self, course_id, lesson_number=None):
        """执行模式资源分栏：为课程添加课程级URL"""
        dlg = tk.Toplevel(self.root)
        dlg.title("添加课程级URL")
        dlg.geometry("480x320")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="名称：").pack(pady=(10, 0))
        ne = ttk.Entry(dlg, width=55)
        ne.pack(pady=2)

        ttk.Label(dlg, text="URL：").pack()
        ue = ttk.Entry(dlg, width=55)
        ue.pack(pady=2)

        try:
            clip = self.root.clipboard_get().strip()
            urls = _detect_urls(clip)
            if urls:
                ue.insert(0, urls[0])
                auto_title = _extract_title_from_url(urls[0])
                if auto_title:
                    ne.insert(0, auto_title)
        except Exception:
            pass

        ne.focus()

        type_var = tk.StringVar(value="auto")
        tf = ttk.Frame(dlg)
        tf.pack(pady=5)
        ttk.Label(tf, text="类型：").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="自动检测", variable=type_var, value="auto").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🌐 链接", variable=type_var, value="url").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🎬 视频", variable=type_var, value="video").pack(side=tk.LEFT, padx=4)

        def ok():
            n, u = ne.get().strip(), ue.get().strip()
            if not u:
                messagebox.showwarning("提示", "请填写URL", parent=dlg)
                return
            if not n:
                n = _extract_title_from_url(u) or u[:30]
            rtype = type_var.get()
            if rtype == "auto":
                rtype = _classify_url(u)
            if rtype == "video":
                ok_ = self.system.rmgr.add_video(course_id, n, url=u)
            else:
                ok_ = self.system.rmgr.add_url(course_id, n, u)
            if ok_:
                self.wflogger.log_action("add_resource", course_id, None, detail=f"添加链接 {n[:25]}")
                dlg.destroy()
                self._refresh_exec_panel(course_id, lesson_number)
            else:
                messagebox.showinfo("提示", "该资源已存在", parent=dlg)

        bf = ttk.Frame(dlg)
        bf.pack(pady=8)
        ttk.Button(bf, text="确认添加", command=ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="📋 从剪贴板粘贴",
                   command=lambda: self._paste_clipboard_to_entry(ue, ne)).pack(side=tk.LEFT, padx=4)

        bf2 = ttk.Frame(dlg)
        bf2.pack(pady=4)
        ttk.Button(bf2, text="📚 从浏览器书签导入", 
                   command=lambda: self._import_from_browser_bookmarks(
                       lambda name, url: (ue.insert(0, url), ne.insert(0, name))
                   )).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf2, text="🌐 打开浏览器复制", 
                   command=self._open_browser_for_copy).pack(side=tk.LEFT, padx=4)

    def _add_lesson_file(self, course_id, lesson_number):
        fp = filedialog.askopenfilename(
            title=f"为课时 {lesson_number} 选择文件",
            filetypes=[("PDF", "*.pdf"), ("所有文件", "*.*")])
        if not fp:
            return
        if self.system.rmgr.add_pdf(course_id, fp, BASE, lesson_number=lesson_number):
            fname = Path(fp).name
            self.wflogger.log_action("add_resource", course_id, lesson_number, detail=f"添加文件 {fname[:25]}")
            self._refresh_exec_panel(course_id, lesson_number)
        else:
            messagebox.showinfo("提示", "该文件已存在")

    def _add_lesson_url(self, course_id, lesson_number):
        dlg = tk.Toplevel(self.root)
        dlg.title(f"课时 {lesson_number} — 添加资源")
        dlg.geometry("480x280")
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="名称：").pack(pady=(10, 0))
        ne = ttk.Entry(dlg, width=55)
        ne.pack(pady=2)

        ttk.Label(dlg, text="URL / 文件路径：").pack()
        ue = ttk.Entry(dlg, width=55)
        ue.pack(pady=2)

        try:
            clip = self.root.clipboard_get().strip()
            urls = _detect_urls(clip)
            if urls:
                ue.insert(0, urls[0])
                auto_title = _extract_title_from_url(urls[0])
                if auto_title:
                    ne.insert(0, auto_title)
        except Exception:
            pass

        ne.focus()

        type_var = tk.StringVar(value="auto")

        tf = ttk.Frame(dlg)
        tf.pack(pady=5)
        ttk.Label(tf, text="类型：").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="自动检测", variable=type_var, value="auto").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🌐 链接", variable=type_var, value="url").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(tf, text="🎬 视频", variable=type_var, value="video").pack(side=tk.LEFT, padx=4)

        def ok():
            n, u = ne.get().strip(), ue.get().strip()
            if not u:
                messagebox.showwarning("提示", "请填写URL或路径", parent=dlg)
                return
            if not n:
                n = _extract_title_from_url(u) or u[:30]
            rtype = type_var.get()
            if rtype == "auto":
                rtype = _classify_url(u)
            if rtype == "video":
                ok_ = self.system.rmgr.add_video(course_id, n, url=u, lesson_number=lesson_number)
                detail_prefix = "添加视频"
            else:
                ok_ = self.system.rmgr.add_url(course_id, n, u, lesson_number=lesson_number)
                detail_prefix = "添加链接"
            if ok_:
                self.wflogger.log_action("add_resource", course_id, lesson_number, detail=f"{detail_prefix} {n[:25]}")
                dlg.destroy()
                self._refresh_exec_panel(course_id, lesson_number)
            else:
                messagebox.showinfo("提示", "该资源已存在", parent=dlg)

        bf = ttk.Frame(dlg)
        bf.pack(pady=8)
        ttk.Button(bf, text="确认添加", command=ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="📋 从剪贴板粘贴",
                   command=lambda: self._paste_clipboard_to_entry(ue, ne)).pack(side=tk.LEFT, padx=4)
        
        bf2 = ttk.Frame(dlg)
        bf2.pack(pady=4)
        ttk.Button(bf2, text="📚 从浏览器书签导入", 
                   command=lambda: self._import_from_browser_bookmarks(
                       lambda name, url: (ue.insert(0, url), ne.insert(0, name))
                   )).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf2, text="🌐 打开浏览器复制", 
                   command=self._open_browser_for_copy).pack(side=tk.LEFT, padx=4)

    def _paste_clipboard_to_entry(self, url_entry, name_entry):
        try:
            clip = self.root.clipboard_get().strip()
        except Exception:
            messagebox.showinfo("提示", "剪贴板为空")
            return
        urls = _detect_urls(clip)
        if urls:
            url_entry.delete(0, tk.END)
            url_entry.insert(0, urls[0])
            auto_title = _extract_title_from_url(urls[0])
            if auto_title and not name_entry.get().strip():
                name_entry.delete(0, tk.END)
                name_entry.insert(0, auto_title)
        else:
            url_entry.delete(0, tk.END)
            url_entry.insert(0, clip)

    def _smart_paste_resources(self, course_id, lesson_number):
        dlg = tk.Toplevel(self.root)
        dlg.title("📋 智能粘贴 — 批量导入URL")
        dlg.geometry("600x600")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="粘贴内容（每行一个URL，或整段文本自动提取URL）：",
                  font=("", 10, "bold")).pack(pady=(10, 5), padx=10, anchor="w")

        text_frame = ttk.Frame(dlg)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10))
        sb = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        try:
            clip = self.root.clipboard_get().strip()
            if clip:
                text.insert("1.0", clip)
        except Exception:
            pass

        result_label = ttk.Label(dlg, text="", foreground="#2980b9")
        result_label.pack(padx=10, anchor="w")

        def preview():
            content = text.get("1.0", tk.END).strip()
            urls = _detect_urls(content)
            if not urls:
                result_label.config(text="未检测到URL", foreground="#c0392b")
                return
            lines = [f"  {i+1}. [{_classify_url(u).upper()}] {u[:60]}" for i, u in enumerate(urls)]
            result_label.config(text=f"检测到 {len(urls)} 个URL：\n" + "\n".join(lines),
                               foreground="#2980b9")

        def import_all():
            content = text.get("1.0", tk.END).strip()
            urls = _detect_urls(content)
            if not urls:
                messagebox.showwarning("提示", "未检测到URL", parent=dlg)
                return
            added, skipped = 0, 0
            for u in urls:
                rtype = _classify_url(u)
                label = _extract_title_from_url(u) or u[:30]
                if rtype == "video":
                    ok_ = self.system.rmgr.add_video(course_id, label, url=u, lesson_number=lesson_number)
                else:
                    ok_ = self.system.rmgr.add_url(course_id, label, u, lesson_number=lesson_number)
                if ok_:
                    self.wflogger.log_action("add_resource", course_id, lesson_number,
                                            detail=f"智能粘贴 {rtype} {label[:25]}")
                    added += 1
                else:
                    skipped += 1
            msg = f"已添加 {added} 个资源"
            if skipped:
                msg += f"，跳过 {skipped} 个（已存在）"
            messagebox.showinfo("导入完成", msg, parent=dlg)
            dlg.destroy()
            self._refresh_exec_panel(course_id, lesson_number)

        bf = ttk.Frame(dlg)
        bf.pack(pady=8)
        ttk.Button(bf, text="🔍 预览检测", command=preview).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="📥 全部导入", command=import_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="📋 从剪贴板粘贴",
                   command=lambda: text.delete("1.0", tk.END) or
                       text.insert("1.0", self.root.clipboard_get().strip() if self.root.clipboard_get() else "")
        ).pack(side=tk.LEFT, padx=4)
        
        # 浏览器导入按钮
        bf2 = ttk.Frame(dlg)
        bf2.pack(pady=4)
        ttk.Button(bf2, text="📚 从浏览器书签导入", 
                   command=lambda: self._import_from_browser_bookmarks(
                       lambda name, url: text.insert(tk.END, f"\n{url}")
                   )).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf2, text="🌐 打开浏览器复制", 
                   command=self._open_browser_for_copy).pack(side=tk.LEFT, padx=4)

    def _batch_import_lesson_files(self, course_id, lesson_number):
        """批量导入课时文件：支持文件夹递归扫描"""
        # 选择文件或文件夹
        choice = messagebox.askyesno("选择导入方式", 
                                      "是：选择文件夹（递归扫描）\n否：直接选择文件")
        
        if choice:  # 文件夹模式
            dp = filedialog.askdirectory(
                title=f"选择包含课时 {lesson_number} 资源的目录（递归扫描）"
            )
            if not dp:
                return
            
            exts = {
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
                '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
                '.mp3', '.flac', '.wav', '.m4a', '.ogg',
            }
            dp = Path(dp)
            files = []
            total_scanned = 0
            
            # 递归扫描文件
            for f in dp.rglob("*"):
                total_scanned += 1
                if f.is_file() and f.suffix.lower() in exts:
                    if not f.name.startswith('.') and not f.name.startswith('~'):
                        files.append(str(f))
            
            if not files:
                messagebox.showinfo("提示", f"扫描了 {total_scanned} 个文件，\n该目录下没有可导入的资源文件")
                return
            
            # 显示扫描结果
            self._log(f"📂 递归扫描 {dp}：找到 {len(files)} 个文件")
            messagebox.showinfo("扫描结果", 
                                f"📂 目录：{dp.name}\n"
                                f"📄 共扫描：{total_scanned} 个文件\n"
                                f"✅ 找到：{len(files)} 个可导入文件")
        else:  # 文件模式
            files = filedialog.askopenfilenames(
                title=f"批量选择课时 {lesson_number} 文件",
                filetypes=[("文档/PDF", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                           ("视频", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv"),
                           ("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp"),
                           ("所有文件", "*.*")]
            )
            if not files:
                return
        
        added, skipped = 0, 0
        for fp in files:
            ext = Path(fp).suffix.lower()
            if ext in ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'):
                ok_ = self.system.rmgr.add_video(course_id, Path(fp).stem[:30],
                                                  filepath=fp, base_dir=BASE, lesson_number=lesson_number)
            elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'):
                ok_ = self.system.rmgr.add_image(course_id, fp, BASE, lesson_number=lesson_number)
            else:
                ok_ = self.system.rmgr.add_pdf(course_id, fp, BASE, lesson_number=lesson_number)
            if ok_:
                fname = Path(fp).name
                self.wflogger.log_action("add_resource", course_id, lesson_number, detail=f"批量添加文件 {fname[:25]}")
                added += 1
            else:
                skipped += 1
        msg = f"已添加 {added} 个文件"
        if skipped:
            msg += f"，跳过 {skipped} 个（已存在）"
        messagebox.showinfo("批量导入完成", msg)
        self._refresh_exec_panel(course_id, lesson_number)

    def _batch_import_course_files_exec(self, course_id, lesson_number):
        """课程级文件批量导入：支持文件夹递归扫描"""
        choice = messagebox.askyesno("选择导入方式", 
                                      "是：选择文件夹（递归扫描）\n否：直接选择文件")
        
        if choice:  # 文件夹模式
            dp = filedialog.askdirectory(
                title="选择包含课程级资源的目录（递归扫描）"
            )
            if not dp:
                return
            
            exts = {
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.rmd', '.md', '.tex', '.c', '.cpp', '.py', '.js', '.java',
                '.mp3', '.flac', '.wav', '.m4a', '.ogg',
                '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
                '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
                '.epub', '.zip', '.lrc',
            }
            dp = Path(dp)
            files = []
            total_scanned = 0
            
            for f in dp.rglob("*"):
                total_scanned += 1
                if f.is_file() and f.suffix.lower() in exts:
                    if not f.name.startswith('.') and not f.name.startswith('~'):
                        files.append(str(f))
            
            if not files:
                messagebox.showinfo("提示", f"扫描了 {total_scanned} 个文件，\n该目录下没有可导入的资源文件")
                return
            
            self._log(f"📂 递归扫描 {dp}：找到 {len(files)} 个文件")
            messagebox.showinfo("扫描结果", 
                                f"📂 目录：{dp.name}\n"
                                f"📄 共扫描：{total_scanned} 个文件\n"
                                f"✅ 找到：{len(files)} 个可导入文件")
        else:  # 文件模式
            files = filedialog.askopenfilenames(
                title="批量选择课程级文件",
                filetypes=[("文档/PDF", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                           ("视频", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv"),
                           ("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp"),
                           ("所有文件", "*.*")]
            )
            if not files:
                return
        
        added, skipped = 0, 0
        for fp in files:
            ext = Path(fp).suffix.lower()
            if ext in ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'):
                ok_ = self.system.rmgr.add_video(course_id, Path(fp).stem[:30],
                                                  filepath=fp, base_dir=BASE)
            elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'):
                ok_ = self.system.rmgr.add_image(course_id, fp, BASE)
            else:
                ok_ = self.system.rmgr.add_pdf(course_id, fp, BASE)
            if ok_:
                added += 1
            else:
                skipped += 1
        msg = f"已添加 {added} 个文件"
        if skipped:
            msg += f"，跳过 {skipped} 个（已存在）"
        messagebox.showinfo("批量导入完成", msg)
        self._refresh_exec_panel(course_id, lesson_number)

    def _refresh_exec_panel(self, course_id, lesson_number):
        """刷新执行模式右侧面板（添加资源后调用）"""
        if not (hasattr(self, 'exec_mode_active') and self.exec_mode_active):
            return
        if not (hasattr(self, 'current_lesson_frame') and hasattr(self, 'current_execution_course')):
            return
        course = self.system.get_course_by_id(course_id)
        for l in (course.get("lessons", []) if course else []):
            if l.get("lesson_number") == lesson_number:
                self._render_current_lesson(self.current_lesson_frame, course_id, l)
                break
        # 刷新PDF预览tab的资源列表
        if hasattr(self, '_refresh_pdf_resource_list') and callable(self._refresh_pdf_resource_list):
            try:
                self._refresh_pdf_resource_list()
            except Exception:
                pass

    # ============ 课程笔记 Tab ============

    def _build_course_notes_tab(self, parent, course_id):
        """课程详情中的笔记管理 Tab - 左栏笔记列表 + 右栏课程笔记预览"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        title = course.get("course_title", "")
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:40]
        notes_dir = BASE / "Notes" / safe_title

        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        tb = ttk.Frame(left_frame)
        tb.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(tb, text="📝 课程笔记", font=("", 12, "bold"), foreground="#2C3E50").pack(side=tk.LEFT)
        
        search_frame = ttk.Frame(tb)
        search_frame.pack(side=tk.RIGHT)
        self._detail_notes_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self._detail_notes_search_var, width=20).pack(side=tk.LEFT, padx=(0, 4))
        self._detail_notes_search_var.trace_add("write", lambda *args: self._perform_detail_notes_search(course_id))
        self._detail_notes_search_result_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text="搜索内容", variable=self._detail_notes_search_result_var,
                        command=lambda: self._perform_detail_notes_search(course_id)).pack(side=tk.LEFT, padx=(0, 6))
        
        bf = ttk.Frame(tb)
        bf.pack(side=tk.RIGHT)
        ttk.Button(bf, text="📝 生成全部课时笔记",
                   command=lambda: self._generate_course_notes(course_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="📂 打开笔记目录",
                   command=lambda: (notes_dir.mkdir(parents=True, exist_ok=True),
                                    open_file(str(notes_dir)))).pack(side=tk.LEFT, padx=2)

        lf = ttk.LabelFrame(left_frame, text="笔记文件", padding=6)
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._notes_list_canvas = tk.Canvas(lf, highlightthickness=0, bg="#FAFAFA")
        n_scroll = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._notes_list_canvas.yview)
        self._notes_list_inner = ttk.Frame(self._notes_list_canvas)
        self._notes_list_inner.bind("<Configure>", lambda e: self._notes_list_canvas.configure(scrollregion=self._notes_list_canvas.bbox("all")))
        self._notes_list_canvas.create_window((0, 0), window=self._notes_list_inner, anchor="nw", tags=("scroll_win",))
        self._notes_list_canvas.bind("<Configure>", self._on_notes_list_canvas_configure)
        self._notes_list_canvas.configure(yscrollcommand=n_scroll.set)
        self._notes_list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        n_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        course_note_path, _ = self.system.get_or_create_note(course_id, None)
        row = ttk.Frame(self._notes_list_inner)
        row.pack(fill=tk.X, pady=4, padx=4)
        ttk.Label(row, text="📓", font=("Segoe UI Emoji", 16)).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="课程总笔记", font=("", 11, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text=str(course_note_path.relative_to(BASE)) if course_note_path else "",
                  font=("", 8), foreground="#95a5a6").pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="📝 打开",
                   command=lambda: self._open_note(course_id, None)).pack(side=tk.RIGHT, padx=2)
        ttk.Separator(self._notes_list_inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        lessons = course.get("lessons", [])
        if not lessons:
            ttk.Label(self._notes_list_inner, text="暂无课时", font=("", 11), foreground="#95a5a6").pack(pady=20)
        else:
            existing_files = set()
            if notes_dir.exists():
                existing_files = {f.name for f in notes_dir.glob("*.Rmd")}

            for lesson in lessons:
                lnum = lesson.get("lesson_number", 0)
                ltitle = lesson.get("lesson_title", "")
                safe_ltitle = re.sub(r'[\\/:*?"<>|]', '_', ltitle)[:30]
                fn = f"L{lnum:02d}_{safe_ltitle}.Rmd" if ltitle else f"L{lnum:02d}.Rmd"
                exists = fn in existing_files

                row = ttk.Frame(self._notes_list_inner)
                row.pack(fill=tk.X, pady=3, padx=4)
                icon = "✅" if exists else "⬜"
                ttk.Label(row, text=icon, font=("", 12)).pack(side=tk.LEFT, padx=4)
                ttk.Label(row, text=f"课时 {lnum}: {ltitle}", font=("", 10)).pack(side=tk.LEFT, fill=tk.X, expand=True)
                ttk.Button(row, text="📝 打开/新建",
                           command=lambda lnum=lnum: self._open_note(course_id, lnum)).pack(side=tk.RIGHT, padx=2)
                ttk.Separator(self._notes_list_inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=1)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        self._build_course_note_preview(right_frame, course_id)

    def _perform_detail_notes_search(self, course_id):
        """课程详情页笔记内容搜索"""
        search_query = getattr(self, '_detail_notes_search_var', tk.StringVar(value="")).get().strip()
        search_content = getattr(self, '_detail_notes_search_result_var', tk.BooleanVar()).get()
        
        if not hasattr(self, '_notes_list_inner'):
            return
        
        for w in self._notes_list_inner.winfo_children():
            w.destroy()
        
        if not search_query or not search_content:
            self._rebuild_notes_list(course_id)
            return
        
        course = self.system.get_course_by_id(course_id)
        title = course.get("course_title", "") if course else ""
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:40]
        notes_dir = BASE / "Notes" / safe_title
        
        results = []
        if notes_dir.exists():
            for rmd_file in notes_dir.glob("*.Rmd"):
                try:
                    content = rmd_file.read_text(encoding="utf-8")
                    lines = content.split('\n')
                    in_yaml = False
                    for i, line in enumerate(lines, 1):
                        if line.strip() == '---':
                            in_yaml = not in_yaml
                            continue
                        if in_yaml:
                            continue
                        if search_query.lower() in line.lower():
                            context_start = max(0, i - 2)
                            context_lines = lines[context_start:i + 2]
                            context = '\n'.join(context_lines)
                            results.append({
                                'file': rmd_file,
                                'line': i,
                                'text': line.strip()[:100],
                                'context': context[:200]
                            })
                except Exception:
                    pass
        
        if not results:
            ttk.Label(self._notes_list_inner, text=f"未找到 '{search_query}' 的匹配内容", 
                     font=("", 10), foreground="#95a5a6").pack(pady=20)
            return
        
        ttk.Label(self._notes_list_inner, text=f"📋 搜索 \"{search_query}\" 共找到 {len(results)} 处",
                  font=("", 10, "bold"), foreground="#2C3E50").pack(anchor="w", pady=(0, 8))
        
        for result in results[:30]:
            res_card = ttk.Frame(self._notes_list_inner, relief="groove", borderwidth=1)
            res_card.pack(fill=tk.X, padx=2, pady=2)
            
            title_text = f"📄 {result['file'].name} (行 {result['line']})"
            ttk.Label(res_card, text=title_text, font=("", 9, "bold"),
                     foreground="#2980b9").pack(anchor="w", padx=5, pady=(3, 1))
            
            preview = result['context'].replace('\n', ' ↵ ')[:100]
            ttk.Label(res_card, text=preview, style="Sub.TLabel",
                     font=("Consolas", 8)).pack(anchor="w", padx=5, pady=(0, 3))
            
            def _open_result(f=result['file']):
                open_file(str(f))
            ttk.Button(res_card, text="打开", command=_open_result, width=8).pack(anchor="e", padx=5, pady=(0, 3))
    
    def _rebuild_notes_list(self, course_id):
        """重新构建笔记列表"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            return
        
        title = course.get("course_title", "")
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:40]
        notes_dir = BASE / "Notes" / safe_title
        
        course_note_path, _ = self.system.get_or_create_note(course_id, None)
        row = ttk.Frame(self._notes_list_inner)
        row.pack(fill=tk.X, pady=4, padx=4)
        ttk.Label(row, text="📓", font=("Segoe UI Emoji", 16)).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="课程总笔记", font=("", 11, "bold")).pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text=str(course_note_path.relative_to(BASE)) if course_note_path else "",
                  font=("", 8), foreground="#95a5a6").pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="📝 打开",
                   command=lambda: self._open_note(course_id, None)).pack(side=tk.RIGHT, padx=2)
        ttk.Separator(self._notes_list_inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)
        
        lessons = course.get("lessons", [])
        if not lessons:
            ttk.Label(self._notes_list_inner, text="暂无课时", font=("", 11), foreground="#95a5a6").pack(pady=20)
            return
        
        existing_files = set()
        if notes_dir.exists():
            existing_files = {f.name for f in notes_dir.glob("*.Rmd")}
        
        for lesson in lessons:
            lnum = lesson.get("lesson_number", 0)
            ltitle = lesson.get("lesson_title", "")
            safe_ltitle = re.sub(r'[\\/:*?"<>|]', '_', ltitle)[:30]
            fn = f"L{lnum:02d}_{safe_ltitle}.Rmd" if ltitle else f"L{lnum:02d}.Rmd"
            exists = fn in existing_files
            
            row = ttk.Frame(self._notes_list_inner)
            row.pack(fill=tk.X, pady=3, padx=4)
            icon = "✅" if exists else "⬜"
            ttk.Label(row, text=icon, font=("", 12)).pack(side=tk.LEFT, padx=4)
            ttk.Label(row, text=f"课时 {lnum}: {ltitle}", font=("", 10)).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(row, text="📝 打开/新建",
                       command=lambda lnum=lnum: self._open_note(course_id, lnum)).pack(side=tk.RIGHT, padx=2)
            ttk.Separator(self._notes_list_inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=1)

    def _build_course_note_preview(self, parent, course_id):
        """构建课程级笔记预览编辑器"""
        ttk.Label(parent, text="📓 课程总笔记预览", font=("", 12, "bold"),
                  foreground="#2C3E50").pack(anchor="w", padx=8, pady=(8, 4))

        course_note_path, _ = self.system.get_or_create_note(course_id, None)
        self._course_note_path = course_note_path
        self._course_note_cid = course_id
        self._course_note_preview_mode = True  # 默认预览模式
        self._course_note_full_content = ""  # 保存完整内容

        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(toolbar, text="💾 保存",
                   command=self._save_course_note_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📂 外部编辑",
                   command=lambda: self._open_note(course_id, None)).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 刷新",
                   command=lambda: self._refresh_course_note_preview()).pack(side=tk.LEFT, padx=2)
        self._course_note_toggle_btn = ttk.Button(toolbar, text="👁️ 预览模式",
                                                    command=self._toggle_course_note_mode)
        self._course_note_toggle_btn.pack(side=tk.LEFT, padx=2)

        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._course_note_preview_editor = tk.Text(editor_frame, wrap=tk.WORD, font=("Consolas", 10),
                                                   undo=True, maxundo=50,
                                                   insertbackground="#2c3e50", selectbackground="#3498db",
                                                   selectforeground="white", relief="flat", bg="#FAFAFA",
                                                   padx=8, pady=6)
        preview_scroll = ttk.Scrollbar(editor_frame, orient="vertical",
                                        command=self._course_note_preview_editor.yview)
        self._course_note_preview_editor.configure(yscrollcommand=preview_scroll.set)
        self._course_note_preview_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for tag, fg, bold in [
            ("yaml_delim", "#7f8c8d", True), ("heading", "#2c3e50", True),
            ("heading2", "#34495e", True), ("code_block", "#27ae60", False),
            ("math_block", "#c0392b", False), ("bold", "#2c3e50", True),
            ("italic", "#7f8c8d", False), ("link", "#2980b9", False),
        ]:
            fnt = ("Consolas", 10, "bold") if bold else ("Consolas", 10)
            self._course_note_preview_editor.tag_configure(tag, foreground=fg, font=fnt)

        self._load_course_note_preview(course_note_path)

        self._course_note_auto_save_timer = None
        self._course_note_preview_editor.bind("<<Modified>>", self._on_course_note_modified)
        self._course_note_preview_editor.bind("<FocusOut>", lambda e: self._do_course_note_auto_save_immediate())
        
        self._course_note_status_var = tk.StringVar(value=f"📄 {course_note_path.name if course_note_path else '课程笔记'}")
        status_label = ttk.Label(parent, textvariable=self._course_note_status_var,
                                font=("", 8), foreground="#95a5a6")
        status_label.pack(fill=tk.X, padx=8, pady=(3, 0))
        
        ttk.Label(parent, text="自动保存已启用 | Ctrl+S 手动保存",
                 font=("", 8), foreground="#bdc3c7").pack()

    def _on_course_note_modified(self, event=None):
        """课程笔记内容修改时触发自动保存"""
        if not hasattr(self, '_course_note_auto_save_timer'):
            return
        if not self._course_note_preview_editor.winfo_exists():
            return
        if self._course_note_auto_save_timer:
            self.root.after_cancel(self._course_note_auto_save_timer)
        self._course_note_auto_save_timer = self.root.after(
            5000, self._do_course_note_auto_save)
        self._course_note_status_var.set("📝 已修改...")
    
    def _do_course_note_auto_save_immediate(self):
        """课程笔记立即保存（失焦时）"""
        if not hasattr(self, '_course_note_preview_editor'):
            return
        if not self._course_note_preview_editor.winfo_exists():
            return
        try:
            if self._course_note_auto_save_timer:
                self.root.after_cancel(self._course_note_auto_save_timer)
                self._course_note_auto_save_timer = None
            if not hasattr(self, '_course_note_cid'):
                return
            self._save_course_note_preview()
            self._course_note_status_var.set(f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}")
        except Exception:
            pass

    def _do_course_note_auto_save(self):
        """执行课程笔记自动保存"""
        if not hasattr(self, '_course_note_preview_editor'):
            return
        if not self._course_note_preview_editor.winfo_exists():
            return
        try:
            self._save_course_note_preview()
            self._course_note_status_var.set(f"✅ 自动保存 {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            self._course_note_status_var.set(f"❌ 保存失败")

    def _extract_note_headers(self, content):
        """提取笔记中的YAML头和R配置块（返回 (yaml_header, r_blocks, cleaned_content)"""
        yaml_header = ""
        r_blocks = []
        
        # 提取YAML头（第一个---到第二个---之间的内容）
        first_dash = content.find('---\n')
        if first_dash != -1:
            second_dash = content.find('\n---\n', first_dash + 4)
            if second_dash != -1:
                yaml_header = content[:second_dash + 5]
                content = content[second_dash + 5:]
        
        # 提取前两个R代码块
        import re
        for _ in range(2):
            pattern = r'(`{3})\{[rR][^\}]*\}\s*[\s\S]*?\1\s*\n?'
            match = re.search(pattern, content)
            if match:
                r_blocks.append(match.group(0))
                content = content[:match.start()] + content[match.end():]
        
        return yaml_header, r_blocks, content.strip()
    
    def _restore_note_headers(self, cleaned_content, yaml_header, r_blocks):
        """将YAML头和R配置块恢复到笔记内容中（保持原始顺序：yaml → r1 → r2 → content）"""
        parts = []
        if yaml_header:
            parts.append(yaml_header.rstrip('\n'))
        for block in r_blocks:
            parts.append(block.rstrip('\n'))
        parts.append(cleaned_content)
        return '\n\n'.join(parts)
    
    def _clean_note_content(self, content):
        """清理笔记内容：移除YAML和前两个R配置块（保持文件不变）"""
        _, _, cleaned_content = self._extract_note_headers(content)
        return cleaned_content

    def _load_course_note_preview(self, note_path):
        """加载课程笔记到预览框（合并所有课时笔记，隐藏YAML和R配置块）"""
        if hasattr(self, '_course_note_path') and self._course_note_path != note_path:
            self._do_course_note_auto_save_immediate()
        if not hasattr(self, '_course_note_preview_editor'):
            return
        
        # 读取完整内容（用于保存）
        full_content = []
        # 读取过滤后的内容（用于显示）
        display_parts = []
        # 保存课时笔记的YAML头和R配置块
        self._lesson_note_headers = {}
        
        if note_path and note_path.exists():
            try:
                content = note_path.read_text(encoding="utf-8")
                full_content.append(content)
                display_parts.append(self._clean_note_content(content))
            except Exception:
                pass
        
        # 合并课时笔记（分别保存完整内容和过滤后内容）
        if hasattr(self, '_course_note_cid'):
            course = self.system.get_course_by_id(self._course_note_cid)
            if course:
                lessons = course.get("lessons", [])
                for lesson in lessons:
                    lnum = lesson.get("lesson_number", 0)
                    ltitle = lesson.get("lesson_title", "")
                    lesson_note_path, _ = self.system.get_or_create_note(self._course_note_cid, lnum)
                    if lesson_note_path and lesson_note_path.exists():
                        try:
                            content = lesson_note_path.read_text(encoding="utf-8")
                            
                            # 提取并保存课时笔记的YAML头和R配置块
                            yaml_header, r_blocks, cleaned_content = self._extract_note_headers(content)
                            self._lesson_note_headers[lnum] = {
                                'yaml_header': yaml_header,
                                'r_blocks': r_blocks
                            }
                            
                            # 保存完整内容
                            full_content.append(f"\n\n## 📌 课时 {lnum}: {ltitle}\n" if ltitle else f"\n\n## 📌 课时 {lnum}\n")
                            full_content.append(content)
                            # 保存过滤后内容（用于显示）
                            display_parts.append(f"\n\n## 📌 课时 {lnum}: {ltitle}\n" if ltitle else f"\n\n## 📌 课时 {lnum}\n")
                            display_parts.append(cleaned_content)
                        except Exception:
                            pass
        
        self._course_note_full_content = '\n'.join(full_content) if full_content else ""
        self._course_note_display_content = '\n'.join(display_parts) if display_parts else ""
        self._refresh_course_note_display()

    def _toggle_course_note_mode(self):
        """切换课程详情页笔记预览的预览/完整显示模式"""
        if self._course_note_preview_mode:
            # 预览模式 -> 完整模式：只更新编辑部分，保持头部不变
            current_edit = self._course_note_preview_editor.get("1.0", tk.END).rstrip('\n')
            cleaned = self._clean_note_content(self._course_note_full_content)
            if current_edit.strip() and current_edit.strip() != cleaned.strip():
                # 使用中间件提取和恢复头部
                yaml_header, r_blocks, _ = self._extract_note_headers(self._course_note_full_content)
                self._course_note_full_content = self._restore_note_headers(current_edit, yaml_header, r_blocks)
        # 完整模式 -> 预览模式：保持完整内容不变，只更新显示
        # 不要覆盖 _course_note_full_content
        
        self._course_note_preview_mode = not self._course_note_preview_mode
        self._refresh_course_note_display()

    def _refresh_course_note_display(self):
        """刷新课程详情页笔记预览的显示内容"""
        if hasattr(self, '_course_note_toggle_btn'):
            btn_text = "👁️ 预览模式" if self._course_note_preview_mode else "📝 完整模式"
            self._course_note_toggle_btn.config(text=btn_text)
        self._course_note_preview_editor.delete("1.0", tk.END)
        if not self._course_note_full_content:
            self._course_note_preview_editor.insert("1.0", "（课程笔记为空，点击保存或外部编辑创建）")
        else:
            if self._course_note_preview_mode:
                # 预览模式：使用已过滤的显示内容
                self._course_note_preview_editor.insert("1.0", self._course_note_display_content or self._course_note_full_content)
            else:
                # 完整模式：使用完整内容
                self._course_note_preview_editor.insert("1.0", self._course_note_full_content)
        self._apply_preview_highlighting()

    def _apply_preview_highlighting(self):
        """预览框语法高亮"""
        if not hasattr(self, '_course_note_preview_editor'):
            return
        te = self._course_note_preview_editor
        for tag in ("yaml_delim", "heading", "heading2", "code_block", "math_block", "bold", "italic", "link"):
            te.tag_remove(tag, "1.0", tk.END)
        content = te.get("1.0", tk.END)
        lines = content.split('\n')
        in_code = False
        code_start = 0
        for i, line in enumerate(lines):
            li = i + 1
            stripped = line.strip()
            if stripped.startswith('```'):
                te.tag_add("code_block", f"{li}.0", f"{li}.end")
                if in_code:
                    in_code = False
                else:
                    in_code = True
                    code_start = li
                continue
            if in_code:
                continue
            if stripped.startswith('$$'):
                te.tag_add("math_block", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('# ') and not stripped.startswith('## '):
                te.tag_add("heading", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('## ') and not stripped.startswith('### '):
                te.tag_add("heading2", f"{li}.0", f"{li}.end")
                continue

    def _save_course_note_preview(self):
        """保存课程笔记预览（双向同步：课程笔记 + 课时笔记）"""
        if not hasattr(self, '_course_note_preview_editor') or not hasattr(self, '_course_note_path'):
            return
        if not hasattr(self, '_course_note_cid'):
            return
        
        # 保存前同步当前编辑内容到完整内容
        current_edit = self._course_note_preview_editor.get("1.0", tk.END).rstrip('\n')
        if self._course_note_preview_mode:
            # 预览模式：使用中间件合并头部和编辑内容
            cleaned = self._clean_note_content(self._course_note_full_content)
            if current_edit.strip() and current_edit.strip() != cleaned.strip():
                # 使用中间件提取和恢复头部
                yaml_header, r_blocks, _ = self._extract_note_headers(self._course_note_full_content)
                self._course_note_full_content = self._restore_note_headers(current_edit, yaml_header, r_blocks)
        else:
            # 完整模式：直接使用编辑内容
            self._course_note_full_content = current_edit
        
        # 使用完整内容进行保存
        content = self._course_note_full_content
        if content.startswith("（课程笔记为空") or not content.strip():
            return

        course = self.system.get_course_by_id(self._course_note_cid)
        if not course:
            return

        import re
        sections = re.split(r'(\n\n## 📌 课时 \d+:.+)', content)
        
        course_content = sections[0].strip() if sections else ""
        
        # 检查并移除重复的yaml头（如果sections[0]包含多个---块）
        import re as re2
        yaml_matches = list(re2.finditer(r'---[\s\S]*?---', course_content))
        if len(yaml_matches) > 1:
            # 有多个yaml头，只保留第一个
            first_yaml_end = yaml_matches[0].end()
            course_content = course_content[first_yaml_end:]
        
        course_note_path = self._course_note_path
        try:
            if course_note_path:
                course_note_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 检查course_content是否已经有完整头信息
                course_yaml, course_r_blocks, _ = self._extract_note_headers(course_content)
                if course_yaml or course_r_blocks:
                    # 已经有头，直接保存
                    course_note_path.write_text(course_content, encoding="utf-8")
                else:
                    # 没有头，需要添加
                    yaml_header = ""
                    r_blocks = []
                    
                    # 先尝试从原文件读取
                    if course_note_path.exists():
                        existing_content = course_note_path.read_text(encoding="utf-8")
                        yaml_header, r_blocks, _ = self._extract_note_headers(existing_content)
                    
                    # 如果没有头信息，生成新的
                    if not yaml_header:
                        yaml_str, _ = self.system.generate_note_yaml(course, None)
                        yaml_end = yaml_str.find('\n---\n', 4)
                        if yaml_end != -1:
                            yaml_header = yaml_str[:yaml_end + 5]
                    
                    # 使用中间件恢复完整内容
                    course_content = self._restore_note_headers(course_content, yaml_header, r_blocks)
                    
                    course_note_path.write_text(course_content, encoding="utf-8")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存课程笔记失败: {str(e)}")
            return

        saved_count = 1
        
        for i in range(1, len(sections), 2):
            title = sections[i]
            body = sections[i + 1] if i + 1 < len(sections) else ""
            
            match = re.search(r'课时 (\d+):', title)
            if match:
                lnum = int(match.group(1))
                lesson_note_path, _ = self.system.get_or_create_note(self._course_note_cid, lnum)
                if lesson_note_path:
                    try:
                        lesson_note_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        lesson_content = body.strip()
                        
                        # 检查并移除重复的yaml头（如果body包含多个---块）
                        import re as re2
                        yaml_matches = list(re2.finditer(r'^---\n[\s\S]*?\n---\n', lesson_content, re2.MULTILINE))
                        if len(yaml_matches) > 1:
                            first_yaml_end = yaml_matches[0].end()
                            lesson_content = lesson_content[first_yaml_end:]
                        
                        # 检查body是否已经有完整头信息
                        body_yaml, body_r_blocks, body_cleaned = self._extract_note_headers(lesson_content)
                        if body_yaml or body_r_blocks:
                            # body已经有头，使用它自己的内容（不再添加额外的头）
                            lesson_note_path.write_text(lesson_content, encoding="utf-8")
                            saved_count += 1
                            continue
                        
                        # body没有头，需要添加
                        yaml_header = ""
                        r_blocks = []
                        
                        # 优先使用加载时保存的YAML头和R配置块
                        if hasattr(self, '_lesson_note_headers') and lnum in self._lesson_note_headers:
                            headers = self._lesson_note_headers[lnum]
                            yaml_header = headers['yaml_header']
                            r_blocks = headers['r_blocks']
                        # 备用方案：从原文件读取
                        elif lesson_note_path.exists():
                            existing_content = lesson_note_path.read_text(encoding="utf-8")
                            yaml_header, r_blocks, _ = self._extract_note_headers(existing_content)
                        
                        # 如果没有头，生成新的
                        if not yaml_header:
                            lesson = self.system.get_lesson(self._course_note_cid, lnum)
                            if lesson:
                                yaml_str, _ = self.system.generate_note_yaml(course, lesson)
                                yaml_end = yaml_str.find('\n---\n', 4)
                                if yaml_end != -1:
                                    yaml_header = yaml_str[:yaml_end + 5]
                            else:
                                print(f"警告：未找到课时信息，lnum={lnum}")
                        
                        # 使用中间件恢复完整内容
                        lesson_content = self._restore_note_headers(lesson_content, yaml_header, r_blocks)
                        
                        lesson_note_path.write_text(lesson_content, encoding="utf-8")
                        saved_count += 1
                    except Exception as e:
                        messagebox.showwarning("保存警告", f"保存课时 {lnum} 笔记失败: {str(e)}")

        messagebox.showinfo("保存成功", f"已同步保存 {saved_count} 个笔记文件\n（课程笔记 + 课时笔记）")

        # === 自动重新分析笔记并刷新图谱 ===
        self._auto_reanalyze_notes()

    def _auto_reanalyze_notes(self):
        """自动重新分析笔记并刷新所有视图"""
        if not hasattr(self, '_current_srm') or not hasattr(self, '_current_note_path'):
            return
        try:
            note_path = self._current_note_path
            if not note_path or not note_path.exists():
                return
            
            from note_analyzer import NoteAnalyzer
            
            # 重新提取元素
            elements = NoteAnalyzer.extract_from_file(
                note_path, 
                self._current_course_id, 
                self._current_lesson_num
            )
            
            # 清空旧数据，保留复习进度
            existing_data = self._current_srm.review_data
            # 只清空元素，保留元数据
            reviews = existing_data.get("reviews", {})
            # 保存每个元素的复习数据（进度和分类
            saved_review_state = {}
            for elem_id, data in reviews.items():
                saved_review_state[elem_id] = {
                    "category": data.get("category"),
                    "triples": data.get("triples", []),
                    "interval": data.get("interval"),
                    "ease_factor": data.get("ease_factor"),
                    "repetitions": data.get("repetitions"),
                    "next_review": data.get("next_review"),
                    "last_reviewed": data.get("last_reviewed"),
                    "review_history": data.get("review_history", [])
                }
                
            # 清空并重新加载
            existing_data["reviews"] = {}
            for elem in elements:
                NoteAnalyzer.auto_classify_elements([elem])
                NoteAnalyzer.auto_extract_triples([elem])
                # 恢复之前的状态
                elem_id = elem.id
                if elem_id in saved_review_state:
                    elem.categories = saved_review_state[elem_id]["category"]
                    saved_triples = saved_review_state[elem_id]["triples"]
                    elem.triples = saved_triples
                self._current_srm.add_element(elem)
                
            # 重新添加元素
            self._current_srm._save()
            
            # 刷新视图
            if hasattr(self, '_current_refresh_list_view'):
                self._current_refresh_list_view()
            if hasattr(self, '_current_refresh_graph_view'):
                self._current_refresh_graph_view()
                
        except Exception as e:
            pass

    def _refresh_course_note_preview(self):
        """刷新课程笔记预览（自动保存后再刷新）"""
        self._do_course_note_auto_save_immediate()
        if hasattr(self, '_course_note_path'):
            self._load_course_note_preview(self._course_note_path)

    # ============ 笔记管理页 ============

    def _show_notes_page(self):
        """笔记管理页面"""
        self._clear_content()
        self._highlight_nav("notes")
        self.nav_title.config(text="笔记管理")

        ttk.Label(self.content_frame, text="📝 课程笔记 (Rmd)",
                  font=("", 14, "bold"), foreground="#2C3E50").pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(self.content_frame, text="为课时生成 R Markdown 笔记文件，含 YAML front-matter 适配 RStudio 渲染",
                  font=("", 9), foreground="#7F8C8D").pack(anchor="w", padx=10, pady=(0, 6))

        # 笔记目录信息
        notes_dir = BASE / "Notes"
        notes_dir.mkdir(exist_ok=True)
        rmd_count = len(list(notes_dir.rglob("*.Rmd")))

        info_frame = ttk.Frame(self.content_frame)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"📂 笔记目录: {notes_dir}", font=("", 10)).pack(anchor="w")
        ttk.Label(info_frame, text=f"📊 已有 {rmd_count} 个笔记文件", font=("", 10)).pack(anchor="w")

        ttk.Button(info_frame, text="📂 打开笔记目录",
                   command=lambda: open_file(str(notes_dir))).pack(anchor="w", pady=5)

        # 搜索栏
        search_frame = ttk.Frame(self.content_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(search_frame, text="🔍 搜索：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._notes_search_var = tk.StringVar()
        self._notes_search_var.trace_add("write", lambda *args: self._refresh_notes_cards())
        notes_search_entry = ttk.Entry(search_frame, textvariable=self._notes_search_var)
        notes_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        notes_search_entry.bind("<Return>", lambda e: self._perform_notes_content_search())
        self._notes_content_search_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_frame, text="搜索内容", variable=self._notes_content_search_var,
                        command=self._perform_notes_content_search).pack(side=tk.LEFT, padx=(0, 6))
        def _clear_notes_search():
            self._notes_search_var.set("")
            self._notes_content_search_var.set(False)
            self._perform_notes_content_search()
            notes_search_entry.focus()
        ttk.Button(search_frame, text="清除", width=8,
                   command=_clear_notes_search).pack(side=tk.RIGHT)
        
        # 内容搜索结果区域
        self._notes_search_results_frame = ttk.Frame(self.content_frame)
        self._notes_search_results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        self._notes_search_results_container = None

        # 顶部操作
        bf = ttk.Frame(self.content_frame)
        bf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(bf, text="📝 为选中课程生成全部笔记",
                   command=self._generate_all_notes).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="🔄 刷新", command=self._refresh_notes_cards).pack(side=tk.LEFT, padx=3)

        # 主区域双栏布局
        paned = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左栏：课程列表
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        self._notes_canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self._notes_canvas.yview)
        self._notes_canvas.configure(yscrollcommand=scrollbar.set)
        self._notes_scroll_frame = ttk.Frame(self._notes_canvas)
        self._notes_canvas.create_window((0, 0), window=self._notes_scroll_frame,
                                         anchor="nw", tags="scroll_win")
        self._notes_scroll_frame.bind("<Configure>",
            lambda e: self._notes_canvas.configure(scrollregion=self._notes_canvas.bbox("all")))
        self._notes_canvas.bind("<Configure>", self._on_notes_canvas_configure)
        self._notes_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._notes_canvas.bind("<Enter>", lambda e: self._notes_canvas.bind_all(
            "<MouseWheel>", lambda ev: _on_mousewheel(ev, self._notes_canvas)))
        self._notes_canvas.bind("<Leave>", lambda e: self._notes_canvas.unbind_all("<MouseWheel>"))

        # 右栏：课程笔记预览
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        ttk.Label(right_frame, text="📓 课程笔记预览", font=("", 11, "bold"),
                  foreground="#2C3E50").pack(anchor="w", padx=8, pady=(8, 2))

        notes_toolbar = ttk.Frame(right_frame)
        notes_toolbar.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(notes_toolbar, text="💾 保存",
                   command=self._save_notes_page_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(notes_toolbar, text="📂 外部编辑",
                   command=self._open_notes_page_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(notes_toolbar, text="🔄 刷新",
                   command=self._refresh_notes_page_preview).pack(side=tk.LEFT, padx=2)
        self._notes_page_toggle_btn = ttk.Button(notes_toolbar, text="👁️ 预览模式",
                                                    command=self._toggle_notes_page_mode)
        self._notes_page_toggle_btn.pack(side=tk.LEFT, padx=2)
        self._notes_page_preview_mode = True  # 默认预览模式
        self._notes_page_full_content = ""  # 保存完整内容

        notes_editor_frame = ttk.Frame(right_frame)
        notes_editor_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._notes_page_editor = tk.Text(notes_editor_frame, wrap=tk.WORD, font=("Consolas", 10),
                                           undo=True, maxundo=50,
                                           insertbackground="#2c3e50", selectbackground="#3498db",
                                           selectforeground="white", relief="flat", bg="#FAFAFA",
                                           padx=8, pady=6)
        notes_scroll = ttk.Scrollbar(notes_editor_frame, orient="vertical",
                                      command=self._notes_page_editor.yview)
        self._notes_page_editor.configure(yscrollcommand=notes_scroll.set)
        self._notes_page_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for tag, fg, bold in [
            ("yaml_delim", "#7f8c8d", True), ("heading", "#2c3e50", True),
            ("heading2", "#34495e", True), ("code_block", "#27ae60", False),
            ("math_block", "#c0392b", False), ("bold", "#2c3e50", True),
            ("italic", "#7f8c8d", False), ("link", "#2980b9", False),
        ]:
            fnt = ("Consolas", 10, "bold") if bold else ("Consolas", 10)
            self._notes_page_editor.tag_configure(tag, foreground=fg, font=fnt)

        self._notes_page_editor.insert("1.0", "（选择课程查看笔记预览）")

        self._notes_page_auto_save_timer = None
        self._notes_page_editor.bind("<<Modified>>", self._on_notes_page_modified)
        self._notes_page_editor.bind("<FocusOut>", lambda e: self._do_notes_page_auto_save_immediate())
        
        self._notes_page_status_var = tk.StringVar(value="📄 选择课程查看笔记")
        status_label = ttk.Label(right_frame, textvariable=self._notes_page_status_var,
                                font=("", 8), foreground="#95a5a6")
        status_label.pack(fill=tk.X, padx=8, pady=(3, 0))
        
        ttk.Label(right_frame, text="自动保存已启用 | Ctrl+S 手动保存",
                 font=("", 8), foreground="#bdc3c7").pack(padx=8)

        self._refresh_notes_cards()

    def _on_notes_page_modified(self, event=None):
        """笔记页面内容修改时触发自动保存"""
        if not hasattr(self, '_notes_page_auto_save_timer'):
            return
        if not self._notes_page_editor.winfo_exists():
            return
        if self._notes_page_auto_save_timer:
            self.root.after_cancel(self._notes_page_auto_save_timer)
        self._notes_page_auto_save_timer = self.root.after(
            5000, self._do_notes_page_auto_save)
        self._notes_page_status_var.set("📝 已修改...")
    
    def _do_notes_page_auto_save_immediate(self):
        """笔记页面立即保存（失焦时）"""
        if not hasattr(self, '_notes_page_editor'):
            return
        if not self._notes_page_editor.winfo_exists():
            return
        try:
            if self._notes_page_auto_save_timer:
                self.root.after_cancel(self._notes_page_auto_save_timer)
                self._notes_page_auto_save_timer = None
            if not hasattr(self, '_notes_page_cid'):
                return
            self._save_notes_page_preview()
            self._notes_page_status_var.set(f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}")
        except Exception:
            pass

    def _do_notes_page_auto_save(self):
        """执行笔记页面自动保存"""
        if not hasattr(self, '_notes_page_editor'):
            return
        if not self._notes_page_editor.winfo_exists():
            return
        try:
            self._save_notes_page_preview()
            self._notes_page_status_var.set(f"✅ 自动保存 {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            self._notes_page_status_var.set(f"❌ 保存失败")

    def _perform_notes_content_search(self):
        """执行笔记内容搜索"""
        search_query = getattr(self, '_notes_search_var', tk.StringVar(value="")).get().strip()
        search_content = getattr(self, '_notes_content_search_var', tk.BooleanVar()).get()
        
        results_frame = getattr(self, '_notes_search_results_frame', None)
        if not results_frame:
            return
        
        for w in results_frame.winfo_children():
            w.destroy()
        
        if not search_query or not search_content:
            self._notes_search_results_container = None
            return
        
        results = []
        notes_dir = BASE / "Notes"
        if notes_dir.exists():
            for rmd_file in notes_dir.rglob("*.Rmd"):
                try:
                    content = rmd_file.read_text(encoding="utf-8")
                    lines = content.split('\n')
                    in_yaml = False
                    for i, line in enumerate(lines, 1):
                        if line.strip() == '---':
                            in_yaml = not in_yaml
                            continue
                        if in_yaml:
                            continue
                        if search_query.lower() in line.lower():
                            context_start = max(0, i - 2)
                            context_lines = lines[context_start:i + 2]
                            context = '\n'.join(context_lines)
                            results.append({
                                'file': rmd_file,
                                'line': i,
                                'text': line.strip()[:100],
                                'context': context[:200]
                            })
                except Exception:
                    pass
        
        container = ttk.Frame(results_frame)
        container.pack(fill=tk.BOTH, expand=True)
        self._notes_search_results_container = container
        
        ttk.Label(container, text=f"📋 搜索 \"{search_query}\" 共找到 {len(results)} 处",
                  font=("", 9, "bold"), foreground="#2C3E50").pack(anchor="w", pady=(0, 4))
        
        if not results:
            ttk.Label(container, text="未找到匹配内容", style="Sub.TLabel").pack(anchor="w")
            return
        
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for result in results[:50]:
            rel_path = result['file'].relative_to(BASE)
            res_card = ttk.Frame(scroll_frame, relief="groove", borderwidth=1)
            res_card.pack(fill=tk.X, padx=2, pady=2)
            
            title = f"📄 {rel_path} (行 {result['line']})"
            ttk.Label(res_card, text=title, font=("", 9, "bold"),
                     foreground="#2980b9").pack(anchor="w", padx=5, pady=(3, 1))
            
            preview = result['context'].replace('\n', ' ↵ ')[:120]
            ttk.Label(res_card, text=preview, style="Sub.TLabel",
                     font=("Consolas", 8)).pack(anchor="w", padx=5, pady=(0, 3))
            
            def _open_result(f=result['file']):
                open_file(str(f))
            ttk.Button(res_card, text="打开文件", command=_open_result,
                      width=10).pack(anchor="e", padx=5, pady=(0, 3))

    def _refresh_notes_cards(self):
        """刷新笔记管理页面课程卡片，支持搜索过滤"""
        scroll_frame = getattr(self, '_notes_scroll_frame', None)
        if not scroll_frame or not scroll_frame.winfo_exists():
            return
        for w in scroll_frame.winfo_children():
            w.destroy()

        search_query = getattr(self, '_notes_search_var', tk.StringVar(value="")).get().strip().lower()

        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            domain = c.get("domain", "UNKNOWN")
            color = DOMAIN_COLORS.get(domain, "#7f8c8d")
            n_lessons = len(c.get("lessons", []))

            if search_query:
                match_text = f"{title} {domain} {DOMAIN_NAMES.get(domain, domain)}".lower()
                if search_query not in match_text:
                    continue

            safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:40]
            course_notes_dir = BASE / "Notes" / safe_title
            existing_notes = set()
            if course_notes_dir.exists():
                existing_notes = {f.stem for f in course_notes_dir.glob("*.Rmd")}

            card = ttk.Frame(scroll_frame, relief="groove", borderwidth=1)
            card.pack(fill=tk.X, padx=5, pady=3)
            tk.Canvas(card, width=6, bg=color, highlightthickness=0).pack(side=tk.LEFT, fill=tk.Y)

            info = ttk.Frame(card)
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=5)
            ttk.Label(info, text=title, font=("", 11, "bold")).pack(anchor="w")
            n_notes = len(existing_notes)
            ttk.Label(info, text=f"{n_lessons}课时 | 笔记: {n_notes}/{n_lessons}",
                      style="Sub.TLabel").pack(anchor="w")

            btn_frame = ttk.Frame(card)
            btn_frame.pack(side=tk.RIGHT, padx=10, pady=5)
            ttk.Button(btn_frame, text="👁 预览",
                       command=lambda cid=cid: self._load_notes_page_preview(cid)).pack(pady=1)
            ttk.Button(btn_frame, text="📖 详情",
                       command=lambda cid=cid: self._show_course_detail(cid)).pack(pady=1)
            ttk.Button(btn_frame, text="📝 生成笔记",
                       command=lambda cid=cid: self._generate_course_notes(cid)).pack(pady=1)

    def _load_notes_page_preview(self, course_id):
        """加载课程笔记到笔记管理页预览框（合并所有课时笔记，隐藏YAML和R配置块）"""
        if hasattr(self, '_notes_page_cid') and self._notes_page_cid != course_id:
            self._do_notes_page_auto_save_immediate()
        self._notes_page_cid = course_id
        
        if not hasattr(self, '_notes_page_editor'):
            return
        
        # 读取完整内容（用于保存）
        full_content = []
        # 读取过滤后的内容（用于显示）
        display_parts = []
        # 保存课时笔记的YAML头和R配置块
        self._lesson_note_headers = {}
        
        course_note_path, _ = self.system.get_or_create_note(course_id, None)
        if course_note_path and course_note_path.exists():
            try:
                content = course_note_path.read_text(encoding="utf-8")
                full_content.append(content)
                display_parts.append(self._clean_note_content(content))
            except Exception:
                pass

        course = self.system.get_course_by_id(course_id)
        if course:
            lessons = course.get("lessons", [])
            for lesson in lessons:
                lnum = lesson.get("lesson_number", 0)
                ltitle = lesson.get("lesson_title", "")
                lesson_note_path, _ = self.system.get_or_create_note(course_id, lnum)
                if lesson_note_path and lesson_note_path.exists():
                    try:
                        content = lesson_note_path.read_text(encoding="utf-8")
                        
                        # 提取并保存课时笔记的YAML头和R配置块
                        yaml_header, r_blocks, cleaned_content = self._extract_note_headers(content)
                        self._lesson_note_headers[lnum] = {
                            'yaml_header': yaml_header,
                            'r_blocks': r_blocks
                        }
                        
                        # 保存完整内容
                        full_content.append(f"\n\n## 📌 课时 {lnum}: {ltitle}\n" if ltitle else f"\n\n## 📌 课时 {lnum}\n")
                        full_content.append(content)
                        # 保存过滤后内容（用于显示）
                        display_parts.append(f"\n\n## 📌 课时 {lnum}: {ltitle}\n" if ltitle else f"\n\n## 📌 课时 {lnum}\n")
                        display_parts.append(cleaned_content)
                    except Exception:
                        pass

        self._notes_page_full_content = '\n'.join(full_content) if full_content else ""
        self._notes_page_display_content = '\n'.join(display_parts) if display_parts else ""
        self._refresh_notes_page_display()

    def _toggle_notes_page_mode(self):
        """切换笔记管理页笔记预览的预览/完整显示模式"""
        if self._notes_page_preview_mode:
            # 预览模式 -> 完整模式：使用中间件合并头部和编辑内容
            current_edit = self._notes_page_editor.get("1.0", tk.END).rstrip('\n')
            cleaned = self._clean_note_content(self._notes_page_full_content)
            if current_edit.strip() and current_edit.strip() != cleaned.strip():
                # 使用中间件提取和恢复头部
                yaml_header, r_blocks, _ = self._extract_note_headers(self._notes_page_full_content)
                self._notes_page_full_content = self._restore_note_headers(current_edit, yaml_header, r_blocks)
        # 完整模式 -> 预览模式：保持完整内容不变，只更新显示
        # 不要覆盖 _notes_page_full_content
        
        self._notes_page_preview_mode = not self._notes_page_preview_mode
        self._refresh_notes_page_display()

    def _refresh_notes_page_display(self):
        """刷新笔记管理页笔记预览的显示内容"""
        if hasattr(self, '_notes_page_toggle_btn'):
            btn_text = "👁️ 预览模式" if self._notes_page_preview_mode else "📝 完整模式"
            self._notes_page_toggle_btn.config(text=btn_text)
        self._notes_page_editor.delete("1.0", tk.END)
        if not self._notes_page_full_content:
            self._notes_page_editor.insert("1.0", "（课程笔记为空，点击保存或外部编辑创建）")
        else:
            if self._notes_page_preview_mode:
                # 预览模式：使用已过滤的显示内容
                self._notes_page_editor.insert("1.0", self._notes_page_display_content or self._notes_page_full_content)
            else:
                # 完整模式：使用完整内容
                self._notes_page_editor.insert("1.0", self._notes_page_full_content)
        self._apply_notes_page_highlighting()

    def _apply_notes_page_highlighting(self):
        """笔记管理页预览框语法高亮"""
        if not hasattr(self, '_notes_page_editor'):
            return
        te = self._notes_page_editor
        for tag in ("yaml_delim", "heading", "heading2", "code_block", "math_block", "bold", "italic", "link"):
            te.tag_remove(tag, "1.0", tk.END)
        content = te.get("1.0", tk.END)
        lines = content.split('\n')
        in_code = False
        for i, line in enumerate(lines):
            li = i + 1
            stripped = line.strip()
            if stripped.startswith('```'):
                te.tag_add("code_block", f"{li}.0", f"{li}.end")
                if in_code:
                    in_code = False
                else:
                    in_code = True
                continue
            if in_code:
                continue
            if stripped.startswith('$$'):
                te.tag_add("math_block", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('# ') and not stripped.startswith('## '):
                te.tag_add("heading", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('## ') and not stripped.startswith('### '):
                te.tag_add("heading2", f"{li}.0", f"{li}.end")
                continue

    def _save_notes_page_preview(self):
        """保存笔记管理页预览（双向同步：课程笔记 + 课时笔记）"""
        if not hasattr(self, '_notes_page_editor') or not hasattr(self, '_notes_page_cid'):
            return
        
        # 保存前同步当前编辑内容到完整内容
        current_edit = self._notes_page_editor.get("1.0", tk.END).rstrip('\n')
        if self._notes_page_preview_mode:
            # 预览模式：使用中间件合并头部和编辑内容
            cleaned = self._clean_note_content(self._notes_page_full_content)
            if current_edit.strip() and current_edit.strip() != cleaned.strip():
                yaml_header, r_blocks, _ = self._extract_note_headers(self._notes_page_full_content)
                self._notes_page_full_content = self._restore_note_headers(current_edit, yaml_header, r_blocks)
        else:
            # 完整模式：直接使用编辑内容
            self._notes_page_full_content = current_edit
        
        # 使用完整内容进行保存
        content = self._notes_page_full_content
        if content.startswith("（课程笔记为空") or content.startswith("（选择课程查看笔记预览）") or not content.strip():
            return

        course = self.system.get_course_by_id(self._notes_page_cid)
        if not course:
            return

        import re
        sections = re.split(r'(\n\n## 📌 课时 \d+:.+)', content)
        
        course_content = sections[0].strip() if sections else ""
        
        # 检查并移除重复的yaml头
        import re as re2
        yaml_matches = list(re2.finditer(r'---[\s\S]*?---', course_content))
        if len(yaml_matches) > 1:
            first_yaml_end = yaml_matches[0].end()
            course_content = course_content[first_yaml_end:]
        
        course_note_path, _ = self.system.get_or_create_note(self._notes_page_cid, None)
        try:
            if course_note_path:
                course_note_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 检查course_content是否已经有完整头信息
                course_yaml, course_r_blocks, _ = self._extract_note_headers(course_content)
                if course_yaml or course_r_blocks:
                    course_note_path.write_text(course_content, encoding="utf-8")
                else:
                    yaml_header = ""
                    r_blocks = []
                    if course_note_path.exists():
                        existing_content = course_note_path.read_text(encoding="utf-8")
                        yaml_header, r_blocks, _ = self._extract_note_headers(existing_content)
                    
                    if not yaml_header:
                        yaml_str, _ = self.system.generate_note_yaml(course, None)
                        yaml_end = yaml_str.find('\n---\n', 4)
                        if yaml_end != -1:
                            yaml_header = yaml_str[:yaml_end + 5]
                    
                    course_content = self._restore_note_headers(course_content, yaml_header, r_blocks)
                    course_note_path.write_text(course_content, encoding="utf-8")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存课程笔记失败: {str(e)}")
            return

        saved_count = 1
        
        for i in range(1, len(sections), 2):
            title = sections[i]
            body = sections[i + 1] if i + 1 < len(sections) else ""
            
            match = re.search(r'课时 (\d+):', title)
            if match:
                lnum = int(match.group(1))
                lesson_note_path, _ = self.system.get_or_create_note(self._notes_page_cid, lnum)
                if lesson_note_path:
                    try:
                        lesson_note_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        lesson_content = body.strip()
                        
                        # 检查并移除重复的yaml头
                        yaml_matches = list(re2.finditer(r'---[\s\S]*?---', lesson_content))
                        if len(yaml_matches) > 1:
                            first_yaml_end = yaml_matches[0].end()
                            lesson_content = lesson_content[first_yaml_end:]
                        
                        # 检查body是否已经有完整头信息
                        body_yaml, body_r_blocks, body_cleaned = self._extract_note_headers(lesson_content)
                        if body_yaml or body_r_blocks:
                            lesson_note_path.write_text(lesson_content, encoding="utf-8")
                            saved_count += 1
                            continue
                        
                        yaml_header = ""
                        r_blocks = []
                        if lesson_note_path.exists():
                            existing_content = lesson_note_path.read_text(encoding="utf-8")
                            yaml_header, r_blocks, _ = self._extract_note_headers(existing_content)
                        
                        if not yaml_header:
                            lesson = self.system.get_lesson(self._notes_page_cid, lnum)
                            if lesson:
                                yaml_str, _ = self.system.generate_note_yaml(course, lesson)
                                yaml_end = yaml_str.find('\n---\n', 4)
                                if yaml_end != -1:
                                    yaml_header = yaml_str[:yaml_end + 5]
                        
                        lesson_content = self._restore_note_headers(lesson_content, yaml_header, r_blocks)
                        lesson_note_path.write_text(lesson_content, encoding="utf-8")
                        saved_count += 1
                    except Exception as e:
                        messagebox.showwarning("保存警告", f"保存课时 {lnum} 笔记失败: {str(e)}")

        messagebox.showinfo("保存成功", f"已同步保存 {saved_count} 个笔记文件\n（课程笔记 + 课时笔记）")

    def _open_notes_page_preview(self):
        """外部编辑笔记管理页预览的课程笔记"""
        if not hasattr(self, '_notes_page_cid'):
            messagebox.showinfo("提示", "请先选择课程预览笔记")
            return
        self._open_note(self._notes_page_cid, None)

    def _refresh_notes_page_preview(self):
        """刷新笔记管理页预览（自动保存后再刷新）"""
        self._do_notes_page_auto_save_immediate()
        if hasattr(self, '_notes_page_cid'):
            self._load_notes_page_preview(self._notes_page_cid)

    def _on_notes_canvas_configure(self, event):
        """笔记管理页Canvas宽度变化时，内部Frame自适应"""
        self._notes_canvas.itemconfig("scroll_win", width=event.width)

    def _generate_course_notes(self, course_id):
        """为单门课程生成笔记文件"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            messagebox.showerror("错误", "找不到课程")
            return

        # 先生成课程级笔记
        path, created = self.system.get_or_create_note(course_id, None)
        count = 1 if created else 0

        # 为每个课时生成笔记
        for lesson in course.get("lessons", []):
            lnum = lesson.get("lesson_number")
            if lnum is not None:
                _, c = self.system.get_or_create_note(course_id, lnum)
                if c:
                    count += 1

        title = course.get("course_title", "")
        total = len(course.get("lessons", [])) + 1
        existing = total - count
        messagebox.showinfo("笔记生成", f"《{title}》\n新建 {count} 个笔记\n已有 {existing} 个\n共 {total} 个文件")
        self._refresh_notes_cards()

    def _generate_all_notes(self):
        """为所有课程生成笔记"""
        if not messagebox.askyesno("确认", "为所有课程生成笔记？\n已存在的笔记不会被覆盖。"):
            return
        total_new = 0
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            _, c0 = self.system.get_or_create_note(cid, None)
            total_new += 1 if c0 else 0
            for lesson in c.get("lessons", []):
                lnum = lesson.get("lesson_number")
                if lnum is not None:
                    _, c1 = self.system.get_or_create_note(cid, lnum)
                    total_new += 1 if c1 else 0
        messagebox.showinfo("完成", f"新建 {total_new} 个笔记文件")
        self._refresh_notes_cards()

    def _open_note(self, course_id, lesson_number=None):
        path, created = self.system.get_or_create_note(course_id, lesson_number)
        if path and path.exists():
            tag = "创建笔记" if created else "打开笔记"
            self.wflogger.log_open_note(course_id, lesson_number, detail=f"{tag} 课时{lesson_number}" if lesson_number else f"{tag} 课程级")
            open_file(str(path))
        else:
            messagebox.showerror("错误", "笔记文件不存在")

    # ============ 课程资源页 (全局) ============

    def _show_resource_page(self):
        """全局资源管理页面"""
        self._clear_content()
        self._highlight_nav("resource")
        self.nav_title.config(text="课程资源")

        ttk.Label(self.content_frame, text="🔗 选择课程查看和管理资源",
                  style="Heading.TLabel").pack(pady=10)

        # 全局批量操作栏
        batch_bar = ttk.Frame(self.content_frame)
        batch_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Button(batch_bar, text="📁 批量导入文件到课程",
                   command=self._batch_import_files_global).pack(side=tk.LEFT, padx=3)
        ttk.Button(batch_bar, text="📂 从目录批量导入",
                   command=self._batch_import_dir_global).pack(side=tk.LEFT, padx=3)
        ttk.Button(batch_bar, text="📋 手动分配导入",
                   command=lambda: self._manual_batch_import()).pack(side=tk.LEFT, padx=3)

        # ── 搜索栏 ──
        search_bar = ttk.Frame(self.content_frame)
        search_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(search_bar, text="🔍 搜索：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._resource_search_var = tk.StringVar()
        self._resource_search_var.trace_add("write", lambda *args: self._refresh_resource_cards())
        resource_search_entry = ttk.Entry(search_bar, textvariable=self._resource_search_var)
        resource_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(search_bar, text="✕", width=3,
                   command=lambda: (self._resource_search_var.set(""), resource_search_entry.focus())).pack(side=tk.RIGHT)

        # ── 域过滤栏 ──
        filter_bar = ttk.Frame(self.content_frame)
        filter_bar.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(filter_bar, text="按域过滤：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        existing_domains = sorted(set(c.get("domain", "UNKNOWN") for c in self.system.courses))
        self._resource_filter_vars = {}
        all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_bar, text="全部", variable=all_var,
                        command=lambda: self._toggle_resource_filter_all(all_var)).pack(side=tk.LEFT, padx=3)

        for domain in existing_domains:
            dn = DOMAIN_NAMES.get(domain, domain)
            var = tk.BooleanVar(value=True)
            self._resource_filter_vars[domain] = var
            ttk.Checkbutton(filter_bar, text=f"{dn}", variable=var,
                            command=lambda: self._refresh_resource_cards()).pack(side=tk.LEFT, padx=3)

        # 课程列表 — 独立容器以便刷新
        self._resource_cards_container = ttk.Frame(self.content_frame)
        self._resource_cards_container.pack(fill=tk.BOTH, expand=True)
        self._build_resource_cards(self._resource_cards_container)

    def _toggle_resource_filter_all(self, all_var):
        """全选/取消全选资源页域过滤"""
        val = all_var.get()
        for var in self._resource_filter_vars.values():
            var.set(val)
        self._refresh_resource_cards()

    def _refresh_resource_cards(self):
        """根据域过滤条件刷新资源页卡片"""
        for w in self._resource_cards_container.winfo_children():
            w.destroy()
        self._build_resource_cards(self._resource_cards_container)

    def _build_resource_cards(self, parent):
        """构建资源页可滚动的课程卡片列表"""
        cards = ttk.Frame(parent)
        cards.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(cards)
        scrollbar = ttk.Scrollbar(cards, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _handle_scroll(event):
            if canvas.winfo_exists():
                _on_mousewheel(event, canvas)
        canvas.bind_all("<MouseWheel>", _handle_scroll)

        active_filters = getattr(self, '_resource_filter_vars', {})
        search_query = getattr(self, '_resource_search_var', tk.StringVar(value="")).get().strip().lower()
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            domain = c.get("domain", "UNKNOWN")
            # 域过滤判断
            if active_filters and not active_filters.get(domain, tk.BooleanVar(value=True)).get():
                continue
            title = c.get("course_title", "")
            # 搜索过滤判断
            if search_query:
                match_text = f"{title} {domain} {DOMAIN_NAMES.get(domain, domain)}".lower()
                if search_query not in match_text:
                    continue
            color = DOMAIN_COLORS.get(domain, "#7f8c8d")
            n_res = len(self.system.rmgr.get(cid))
            n_lesson_res = len([r for r in self.system.rmgr.get(cid) if "lesson_number" in r])
            n_course_res = n_res - n_lesson_res

            card = ttk.Frame(scroll_frame, relief="groove", borderwidth=1)
            card.pack(fill=tk.X, padx=5, pady=3)
            tk.Canvas(card, width=6, bg=color, highlightthickness=0).pack(side=tk.LEFT, fill=tk.Y)

            info = ttk.Frame(card)
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=5)
            ttk.Label(info, text=title, font=("", 11, "bold")).pack(anchor="w")
            res_detail = f"资源: {n_res}项 (课程级{n_course_res} | 课时级{n_lesson_res})" if n_res else "暂无资源"
            ttk.Label(info, text=res_detail, style="Sub.TLabel").pack(anchor="w")

            ttk.Button(card, text="📖 查看资源",
                       command=lambda cid=cid: self._show_course_detail(cid)).pack(side=tk.RIGHT, padx=10, pady=5)

    # ============ 导入与管理页 ============

    def _show_management_page(self):
        """数据库导入与管理页面"""
        self._clear_content()
        self._highlight_nav("manage")
        self.nav_title.config(text="导入与管理")

        # 标题
        ttk.Label(self.content_frame, text="🗄️ 课程数据库管理",
                  font=("", 14, "bold"), foreground="#2C3E50").pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(self.content_frame, text="JSON 导入自动校验格式，不满足则拒绝并提示原因。MD 导入自动解析 Syllabus。",
                  font=("", 9), foreground="#7F8C8D").pack(anchor="w", padx=10, pady=(0, 6))

        # 操作按钮区
        bf = ttk.Frame(self.content_frame)
        bf.pack(fill=tk.X, padx=10)

        ttk.Button(bf, text="📥 导入 JSON", command=self._import_json).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="📄 导入 MD/Rmd", command=self._import_md).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="📂 批量导入", command=self._import_md_dir).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="📝 新建课程", command=self._new_course).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="✏️ 编辑当前", command=self._edit_course).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="🔄 刷新", command=self._refresh_all).pack(side=tk.LEFT, padx=3)

        # 转换工具按钮
        bf_conv = ttk.Frame(self.content_frame)
        bf_conv.pack(fill=tk.X, padx=10, pady=(5, 0))
        ttk.Button(bf_conv, text="🔄 格式转换 (JSON↔CSV↔XLSX)", command=self._show_data_converter).pack(side=tk.LEFT, padx=3)
        ttk.Label(bf_conv, text=" 支持CSV和Excel导入导出", font=("", 9), foreground="#7F8C8D").pack(side=tk.LEFT)

        # 清理管理按钮区
        bf2 = ttk.Frame(self.content_frame)
        bf2.pack(fill=tk.X, padx=10, pady=(4, 0))
        ttk.Button(bf2, text="🔍 检测重复", command=self._show_duplicates).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf2, text="🗑️ 批量删除", command=self._show_batch_delete).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf2, text="📋 表格视图", command=self._show_tree_editor).pack(side=tk.LEFT, padx=3)
        # 当前数据库文件
        ttk.Label(self.content_frame, text="\n当前数据库文件：",
                  font=("", 11, "bold")).pack(anchor="w", padx=10)

        self.dbt = tk.Text(self.content_frame, height=4, font=("Consolas", 9), fg="#555", bg="#FAFAFA", relief=tk.SUNKEN)
        self.dbt.pack(fill=tk.X, padx=10, pady=4)

        # 数据库统计
        self.dbi = ttk.Label(self.content_frame, text="", font=("", 10))
        self.dbi.pack(anchor="w", padx=10, pady=4)
        self._update_db_ui()

        # 格式说明
        ttk.Label(self.content_frame, text="JSON 格式要求（TS2）：",
                  font=("", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        ft = tk.Text(self.content_frame, height=10, font=("Consolas", 9), fg="#2C3E50", bg="#F8F9FA", relief=tk.SUNKEN)
        ft.pack(fill=tk.X, padx=10, pady=2)
        ft.insert("1.0",
                  '{\n'
                  '  "metadata": { "framework": "..." },\n'
                  '  "courses": [\n'
                  '    {\n'
                  '      "note_id": "唯一标识(可选,自动生成)",\n'
                  '      "course_title": "必填",\n'
                  '      "total_hours": 120,\n'
                  '      "domain": "CS",\n'
                  '      "lessons": [{"lesson_number":1, "lesson_title":"第一课"}],\n'
                  '      "sections": [],\n'
                  '      "prerequisites": [],\n'
                  '      "references": []\n'
                  '    }\n'
                  '  ]\n'
                  '}\n\n'
                  '必填: course_title, total_hours, domain, lessons[].lesson_title\n'
                  '导入自动校验，格式错误拒绝导入')
        ft.config(state=tk.DISABLED)

        # 导入日志区
        ttk.Label(self.content_frame, text="\n导入日志：",
                  font=("", 11, "bold")).pack(anchor="w", padx=10, pady=(5, 2))
        self.log_text = tk.Text(self.content_frame, height=6, font=("Consolas", 9), fg="#555", bg="#FAFAFA", relief=tk.SUNKEN)
        self.log_text.pack(fill=tk.X, padx=10, pady=4)
        self.log_text.config(state=tk.DISABLED)

    def _log(self, msg):
        """追加日志"""
        # 检查log_text组件是否仍然存在（防止窗口关闭后调用）
        if not hasattr(self, 'log_text'):
            return
        try:
            # 检查组件是否已被销毁
            if not self.log_text.winfo_exists():
                return
        except:
            return
        
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{datetime.now():%H:%M:%S}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            # 组件可能在检查后被销毁
            return

    def _update_db_ui(self):
        self.dbt.delete("1.0", tk.END)
        for p in self.system.db_paths:
            sz = len(p.read_text(encoding="utf-8")) if p.exists() else 0
            self.dbt.insert(tk.END, f"  {'✅' if p.exists() else '❌'} {p.name} ({sz}b)\n")
        hc = self.system.courses_with_hours_count()
        self.dbi.config(text=f"共 {len(self.system.courses)} 门 | 有课时: {hc} | 总课时: {self.system.total_hours}τ | 条目: {self.system.total_lessons}")

    # ─── 导入操作 ─────────────────────────────────────────────────────────

    def _import_json(self):
        """导入 JSON 格式课程数据"""
        fp = filedialog.askopenfilename(title="导入课程 JSON", filetypes=[("JSON", "*.json")], initialdir=str(BASE))
        if not fp:
            return
        data = load_json_safe(Path(fp))
        if data is None:
            messagebox.showerror("导入失败", "无法解析 JSON")
            self._log(f"❌ JSON解析失败: {fp}")
            return
        ok, msg = validate_course_json(data)
        if not ok:
            messagebox.showerror("校验不通过", msg + "\n\n请参照格式要求")
            self._log(f"❌ 校验不通过: {msg}")
            return

        target = simpledialog.askstring("保存到", f"✅ {msg}\n输入目标JSON文件名：",
                                        initialvalue="imported.json")
        if not target:
            return
        tp = BASE / target
        if tp.exists() and not messagebox.askyesno("覆盖?", f"{target} 已存在，覆盖？"):
            return

        # 写入文件
        tp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.system.add_db_path(tp)
        self.system.reload_all_sources()
        n = len(data['courses'])
        messagebox.showinfo("成功", f"导入 {n} 门课程")
        self._log(f"✅ JSON导入: {n}门课程 -> {target}")
        self._refresh_all()

    def _import_md(self):
        """从单个 Markdown/Rmd Syllabus 文件导入课程"""
        fp = filedialog.askopenfilename(
            title="选择 Markdown / Rmd Syllabus 文件",
            filetypes=[("Markdown/Rmd", "*.md *.Rmd *.rmd"), ("Markdown", "*.md"), ("R Markdown", "*.Rmd *.rmd"), ("所有文件", "*.*")],
            initialdir=str(BASE.parent / "Courses")
        )
        if not fp:
            return
        self._log(f"📄 解析MD: {fp}")
        course = parse_md_file(fp)
        if not course:
            messagebox.showerror("导入失败", f"无法解析 MD 文件:\n{fp}")
            self._log("❌ MD解析失败")
            return
        if not course.get("lessons"):
            messagebox.showwarning("提示", f"《{course['course_title']}》未提取到课时条目")
            self._log(f"⚠️ 无课时: {course['course_title']}")
            return

        # 校验
        data = {"courses": [course]}
        ok, msg = validate_course_json(data)
        if not ok:
            messagebox.showerror("校验不通过", msg)
            self._log(f"❌ 校验不通过: {msg}")
            return

        target = simpledialog.askstring(
            "保存到",
            f"✅ {msg}\n课程：《{course['course_title']}》\n"
            f"课时：{course.get('total_hours', '?')}τ | 条目：{len(course['lessons'])}\n"
            f"域：{course.get('domain', '?')}\n\n输入目标JSON文件名：",
            initialvalue="md_imported.json"
        )
        if not target:
            return
        tp = BASE / target
        if tp.exists() and not messagebox.askyesno("覆盖?", f"{target} 已存在，覆盖？"):
            return

        # 如果目标文件已有内容，追加课程
        existing = load_json_safe(tp) or {"metadata": {}, "courses": []}
        if "courses" not in existing:
            existing["courses"] = []
        existing["courses"].append(course)
        tp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        self.system.add_db_path(tp)
        self.system.reload_all_sources()
        messagebox.showinfo("成功", f"已导入《{course['course_title']}》")
        self._log(f"✅ MD导入: 《{course['course_title']}》{course.get('total_hours', '?')}τ {len(course['lessons'])}条目 -> {target}")
        self._refresh_all()

    def _import_md_dir(self):
        """批量导入目录下所有 Markdown Syllabus 文件"""
        dp = filedialog.askdirectory(
            title="选择包含 MD Syllabus 的目录",
            initialdir=str(BASE.parent / "Courses")
        )
        if not dp:
            return
        self._log(f"📂 扫描目录: {dp}")
        courses = parse_md_directory(dp)
        if not courses:
            messagebox.showinfo("提示", "未找到可解析的 MD Syllabus 文件")
            self._log("⚠️ 未找到可解析文件")
            return

        # 校验
        data = {"courses": courses}
        ok, msg = validate_course_json(data)
        if not ok:
            messagebox.showerror("校验不通过", msg)
            self._log(f"❌ 批量校验不通过: {msg}")
            return

        target = simpledialog.askstring(
            "保存到",
            f"✅ 解析 {len(courses)} 门课程\n{msg}\n\n输入目标JSON文件名：",
            initialvalue="md_batch_imported.json"
        )
        if not target:
            return
        tp = BASE / target
        if tp.exists() and not messagebox.askyesno("覆盖?", f"{target} 已存在，覆盖？"):
            return

        build_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source": "md_batch_import",
                "framework": "课程处理方程：符号化建模、最佳实践与全日程时刻表",
            },
            "courses": courses,
        }
        tp.write_text(json.dumps(build_data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.system.add_db_path(tp)
        self.system.reload_all_sources()
        messagebox.showinfo("成功", f"已批量导入 {len(courses)} 门课程")
        self._log(f"✅ 批量MD导入: {len(courses)}门课程 -> {target}")
        self._refresh_all()

    def _show_data_converter(self):
        """数据格式转换工具"""
        import data_converter
        
        dlg = tk.Toplevel(self.root)
        dlg.title("🔄 数据格式转换工具")
        dlg.geometry("700x550")
        dlg.transient(self.root)
        dlg.grab_set()
        
        ttk.Label(dlg, text="数据格式转换 (JSON ↔ CSV ↔ XLSX)", 
                  font=("", 14, "bold"), foreground="#2C3E50").pack(pady=(15, 5))
        
        ttk.Label(dlg, text="支持格式转换：\n"
                  "• JSON → CSV (扁平格式，每行一个课时)\n"
                  "• JSON → XLSX (多工作表，结构清晰)\n"
                  "• CSV → JSON (从扁平格式重建)\n"
                  "• XLSX → JSON (从Excel导入)\n",
                  justify="center").pack(pady=5)
        
        # 输入文件选择
        input_frame = ttk.LabelFrame(dlg, text="输入文件", padding=10)
        input_frame.pack(fill="x", padx=15, pady=5)
        
        input_path_var = tk.StringVar()
        input_entry = ttk.Entry(input_frame, textvariable=input_path_var, width=50)
        input_entry.pack(side="left", padx=(0, 5))
        
        def select_input():
            filetypes = [("JSON/CSV/XLSX", "*.json *.csv *.xlsx *.xls"),
                         ("JSON文件", "*.json"),
                         ("CSV文件", "*.csv"),
                         ("Excel文件", "*.xlsx *.xls"),
                         ("所有文件", "*.*")]
            f = filedialog.askopenfilename(filetypes=filetypes, title="选择输入文件")
            if f:
                input_path_var.set(f)
                # 自动设置输出格式选项
                suffix = Path(f).suffix.lower()
                if suffix == ".json":
                    output_format_var.set("csv")
                else:
                    output_format_var.set("json")
        
        ttk.Button(input_frame, text="📁 浏览", command=select_input).pack(side="left")
        
        # 输出格式选择
        format_frame = ttk.LabelFrame(dlg, text="输出格式", padding=10)
        format_frame.pack(fill="x", padx=15, pady=5)
        
        output_format_var = tk.StringVar(value="csv")
        radio_frame = ttk.Frame(format_frame)
        radio_frame.pack()
        
        ttk.Radiobutton(radio_frame, text="CSV格式", variable=output_format_var, value="csv").pack(side="left", padx=10)
        ttk.Radiobutton(radio_frame, text="XLSX格式", variable=output_format_var, value="xlsx").pack(side="left", padx=10)
        ttk.Radiobutton(radio_frame, text="JSON格式", variable=output_format_var, value="json").pack(side="left", padx=10)
        
        # 输出文件
        output_frame = ttk.LabelFrame(dlg, text="输出文件", padding=10)
        output_frame.pack(fill="x", padx=15, pady=5)
        
        output_path_var = tk.StringVar()
        output_entry = ttk.Entry(output_frame, textvariable=output_path_var, width=50)
        output_entry.pack(side="left", padx=(0, 5))
        
        def auto_output_path(*args):
            input_path = input_path_var.get()
            output_format = output_format_var.get()
            if input_path:
                p = Path(input_path)
                default = p.parent / (p.stem + "." + output_format)
                output_path_var.set(str(default))
        
        input_path_var.trace_add("write", auto_output_path)
        output_format_var.trace_add("write", auto_output_path)
        
        def select_output(fmt):
            ext_map = {"csv": ".csv", "xlsx": ".xlsx", "json": ".json"}
            filetypes = [
                ("CSV文件", "*.csv"),
                ("Excel文件", "*.xlsx"),
                ("JSON文件", "*.json")
            ]
            f = filedialog.asksaveasfilename(
                filetypes=filetypes, 
                defaultextension=ext_map.get(fmt, ".json"),
                title="保存输出文件"
            )
            if f:
                output_path_var.set(f)
        
        ttk.Button(output_frame, text="📁 选择", command=lambda: select_output(output_format_var.get())).pack(side="left")
        
        # 状态标签
        status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(dlg, textvariable=status_var, foreground="#7f8c8d")
        status_label.pack(pady=5)
        
        def do_convert():
            input_path = input_path_var.get()
            output_format = output_format_var.get()
            output_path = output_path_var.get()
            
            if not input_path or not output_path:
                messagebox.showwarning("提示", "请选择输入和输出文件")
                return
            
            if not Path(input_path).exists():
                messagebox.showerror("错误", "输入文件不存在")
                return
            
            try:
                status_var.set("转换中...")
                result = data_converter.convert_file(Path(input_path), output_format, Path(output_path))
                status_var.set(f"✅ 成功: {result.name}")
                messagebox.showinfo("成功", f"转换成功！\n输出文件: {result}")
                
                # 自动将转换后的JSON导入（如果是JSON输出）
                if output_format == "json" and messagebox.askyesno("导入", "是否立即导入这个JSON文件？"):
                    self.system.add_db_path(result)
                    self.system.reload_all_sources()
                    self._refresh_all()
                    self._log(f"✅ 导入转换的JSON: {result.name}")
                    
            except Exception as e:
                status_var.set("❌ 转换失败")
                messagebox.showerror("错误", f"转换失败：{str(e)}")
        
        # 按钮
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="🔄 开始转换", command=do_convert).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side="left", padx=5)
        
        # 保存当前数据
        ttk.Separator(dlg).pack(fill="x", padx=10, pady=10)
        
        ttk.Label(dlg, text="或者：导出当前数据库", font=("", 11)).pack()
        
        def export_current(fmt):
            if not self.system.dbs:
                messagebox.showinfo("提示", "没有加载的数据库")
                return
                
            # 使用第一个数据库
            db_path = self.system.dbs[0]
            if not db_path.exists():
                messagebox.showerror("错误", "数据库文件不存在")
                return
            
            def_suffix = {"csv": ".csv", "xlsx": ".xlsx"}.get(fmt, fmt)
            filetypes = {"csv": [("CSV", "*.csv")], "xlsx": [("Excel", "*.xlsx")]}.get(fmt, [])
            
            f = filedialog.asksaveasfilename(
                filetypes=filetypes,
                defaultextension=def_suffix,
                initialfile=f"courses_export.{fmt}",
                title=f"导出到{fmt.upper()}"
            )
            
            if f:
                try:
                    result = data_converter.convert_file(db_path, fmt, Path(f))
                    messagebox.showinfo("成功", f"导出成功！\n{result}")
                    status_var.set(f"✅ 导出成功: {Path(f).name}")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败：{str(e)}")
        
        export_frame = ttk.Frame(dlg)
        export_frame.pack(pady=5)
        ttk.Button(export_frame, text="📤 导出为CSV", command=lambda: export_current("csv")).pack(side="left", padx=5)
        ttk.Button(export_frame, text="📤 导出为XLSX", command=lambda: export_current("xlsx")).pack(side="left", padx=5)

    # ─── 课程管理操作 ─────────────────────────────────────────────────────

    def _new_course(self):
        title = simpledialog.askstring("新建课程", "课程名称：")
        if not title:
            return
        domain = simpledialog.askstring("学科域", "学科域代码 (P/A/N/CS/SE/DS/DE/D/LM)：", initialvalue="UNKNOWN")
        if domain is None:
            domain = "UNKNOWN"

        course = self.system.create_course(title, domain)
        target = simpledialog.askstring("保存到", "目标JSON文件名：", initialvalue="courses_structured.json")
        if not target:
            return
        tp = BASE / target
        existing = load_json_safe(tp) or {"metadata": {}, "courses": []}
        if "courses" not in existing:
            existing["courses"] = []
        existing["courses"].append(course)
        tp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        self.system.add_db_path(tp)
        self.system.reload_all_sources()
        messagebox.showinfo("成功", f"已新建《{title}》\n请在编辑功能中补充详细信息")
        self._log(f"✅ 新建课程: 《{title}》[{domain}]")
        self._refresh_all()

    def _edit_course(self):
        cid = self._sel_course_id
        if not cid:
            messagebox.showwarning("提示", "请先从总览选择一门课程（点击详情）")
            return
        course = self.system.get_course_by_id(cid)
        if not course:
            return
        title = course.get("course_title", "")

        # 导出到临时文件编辑
        tmp = BASE / f"__edit_{title[:15].replace('/', '_')}.json"
        tmp.write_text(json.dumps(course, ensure_ascii=False, indent=2), encoding="utf-8")
        open_file(str(tmp))

        if messagebox.askyesno("确认", "编辑完成点击「是」导入修改？"):
            edited = load_json_safe(tmp)
            if edited and validate_course_json({"courses": [edited]})[0]:
                # 更新到源文件
                for p in self.system.db_paths:
                    data = load_json_safe(p)
                    if not data:
                        continue
                    for ci, c in enumerate(data.get("courses", [])):
                        if c.get("note_id") == cid or c.get("course_title") == title:
                            data["courses"][ci] = edited
                            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                            self.system.reload_all_sources()
                            messagebox.showinfo("成功", f"《{title}》已更新")
                            self._log(f"✅ 编辑完成: 《{title}》")
                            self._refresh_all()
                            tmp.unlink(missing_ok=True)
                            return
                messagebox.showerror("错误", "未找到该课程在数据库中的记录")
            else:
                messagebox.showerror("错误", "JSON 格式错误，未保存")
            tmp.unlink(missing_ok=True)

    def _refresh_all(self):
        """全局刷新"""
        self.system.reload_all_sources()
        self._update_overall_label()
        self._show_overview()
        try:
            self._update_db_ui()
        except (tk.TclError, AttributeError):
            pass

    # ============ 执行模式 (核心) ============

    def _show_execution_mode(self, course_id: str = None):
        """执行模式：按顺序完成课时，完成一个消除一个，弹出下一步"""
        self._clear_content()
        self._highlight_nav("exec")

        if course_id is None:
            # 选择课程
            self.nav_title.config(text="执行模式 - 选择课程")

            # 顶部统计汇总
            summary_frame = ttk.Frame(self.content_frame)
            summary_frame.pack(fill=tk.X, pady=(10, 15))

            total_courses = len(self.system.courses)
            completed_courses = 0
            in_progress_courses = 0
            total_lessons_all = 0
            completed_lessons_all = 0
            total_hours_all = 0

            for c in self.system.courses:
                cid = c.get("note_id", c.get("course_title", ""))
                lessons = c.get("lessons", [])
                total_lessons = len(lessons)
                completed = set(self.system.get_course_progress(cid).get("completed_lessons", []))
                completed_count = len(completed)
                total_lessons_all += total_lessons
                completed_lessons_all += completed_count
                total_hours_all += sum(l.get("estimated_hours", 0) for l in lessons)
                if completed_count == total_lessons and total_lessons > 0:
                    completed_courses += 1
                elif completed_count > 0:
                    in_progress_courses += 1

            summary_cards = [
                ("📚 总课程", f"{total_courses} 门"),
                ("✅ 已完成", f"{completed_courses} 门"),
                ("⏳ 进行中", f"{in_progress_courses} 门"),
                ("📝 总课时", f"{total_lessons_all} 节"),
                ("📖 已学课时", f"{completed_lessons_all} 节"),
                ("⏱️ 总时长", f"{total_hours_all:.1f} 小时"),
            ]
            for label_text, value_text in summary_cards:
                card = ttk.LabelFrame(summary_frame, text=label_text, padding=(10, 5))
                card.pack(side=tk.LEFT, padx=5, pady=2)
                ttk.Label(card, text=value_text, font=("", 11, "bold")).pack()

            # 搜索栏
            search_frame = ttk.Frame(self.content_frame)
            search_frame.pack(fill=tk.X, padx=5, pady=(5, 10))
            ttk.Label(search_frame, text="🔍 搜索：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
            if not hasattr(self, '_exec_search_var'):
                self._exec_search_var = tk.StringVar(self.root)
            self._exec_search_var.trace_add("write", lambda *args: self._refresh_exec_cards())
            search_entry = ttk.Entry(search_frame, textvariable=self._exec_search_var)
            search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
            ttk.Button(search_frame, text="清除", width=8,
                       command=lambda: (self._exec_search_var.set(""), search_entry.focus())).pack(side=tk.RIGHT)

            ttk.Label(self.content_frame, text="选择要继续的课程：", style="Heading.TLabel").pack(anchor="w", padx=10, pady=(5, 5))

            cards = ttk.Frame(self.content_frame)
            cards.pack(fill=tk.BOTH, expand=True, padx=5)

            self._exec_canvas = tk.Canvas(cards, highlightthickness=0)
            scrollbar = ttk.Scrollbar(cards, orient="vertical", command=self._exec_canvas.yview)
            self._exec_scroll_frame = ttk.Frame(self._exec_canvas)
            self._exec_scroll_frame.bind("<Configure>", lambda e: self._exec_canvas.configure(scrollregion=self._exec_canvas.bbox("all")))
            self._exec_canvas.create_window((0, 0), window=self._exec_scroll_frame, anchor="nw")
            self._exec_canvas.configure(yscrollcommand=scrollbar.set)
            self._exec_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            def _on_mousewheel(event):
                if self._exec_canvas.winfo_exists():
                    self._exec_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            self._exec_canvas.bind("<Enter>", lambda e: self._exec_canvas.bind_all("<MouseWheel>", _on_mousewheel))
            self._exec_canvas.bind("<Leave>", lambda e: self._exec_canvas.unbind_all("<MouseWheel>"))

            self._exec_cards_container = self._exec_scroll_frame
            self._refresh_exec_cards()
            return

        # ===== 单课程执行模式 =====
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        self.exec_mode_active = True
        self.current_execution_course = course_id

        self._sel_course_id = course_id
        cid = course_id
        self.nav_title.config(text=f"执行: {course.get('course_title', '')}")

        # 顶栏：导航 + 统计卡片
        top = ttk.Frame(self.content_frame)
        top.pack(fill=tk.X, pady=5)

        nav_btns = ttk.Frame(top)
        nav_btns.pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_btns, text="← 返回", command=self._show_overview).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_btns, text="📋 换课程",
                   command=lambda: self._show_execution_mode(None)).pack(side=tk.LEFT, padx=2)

        stats_frame = ttk.Frame(top)
        stats_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        domain_name = course.get("domain", "")
        course_title = course.get("course_title", "")
        total_lessons = len(course.get("lessons", []))
        completed_set = set(self.system.get_course_progress(cid).get("completed_lessons", []))
        completed_count = len(completed_set)
        remaining_count = total_lessons - completed_count
        total_hours = sum(l.get("estimated_hours", 0) for l in course.get("lessons", []))
        pct = self.system.get_completion_pct(cid)

        stat_cards = [
            ("🌐 课程领域", domain_name or "未分类"),
            ("⏱️ 总课时数", f"{total_lessons} 节"),
            ("📖 总学习时长", f"{total_hours:.1f} 小时"),
            ("✅ 已完成", f"{completed_count} 节"),
            ("⏳ 剩余课时", f"{remaining_count} 节"),
            ("📊 完成率", f"{pct}%"),
        ]
        for label_text, value_text in stat_cards:
            card = ttk.LabelFrame(stats_frame, text=label_text, padding=(8, 4))
            card.pack(side=tk.LEFT, padx=4, pady=2)
            ttk.Label(card, text=value_text, font=("", 10, "bold")).pack()

        pct_frame = ttk.Frame(top)
        pct_frame.pack(side=tk.RIGHT, padx=10)
        pbar = ttk.Progressbar(pct_frame, length=200, mode="determinate", maximum=100)
        pbar["value"] = pct
        pbar.pack(fill=tk.X)
        ttk.Label(pct_frame, text=f"完成 {pct}%", font=("", 9, "bold")).pack()

        # 主区域分两栏
        paned = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左栏: 剩余课时列表 (未完成的)
        left_frame = ttk.LabelFrame(paned, text="📋 剩余课时")
        paned.add(left_frame, weight=2)

        lessons = course.get("lessons", [])

        self.exec_tree = ttk.Treeview(left_frame, columns=("num", "title"), show="headings", height=30)
        self.exec_tree.heading("num", text="#")
        self.exec_tree.heading("title", text="课时标题")
        self.exec_tree.column("num", width=50, anchor="center")
        self.exec_tree.column("title", width=350)

        exec_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.exec_tree.yview)
        self.exec_tree.configure(yscrollcommand=exec_scroll.set)
        self.exec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        exec_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for lesson in lessons:
            lnum = lesson.get("lesson_number", 0)
            if lnum not in completed_set:
                self.exec_tree.insert("", "end", values=(lnum, lesson.get("lesson_title", "")),
                                      tags=(str(lnum),))

        # 左栏点击: 切换到选中课时
        def _on_exec_tree_click(event):
            sel = self.exec_tree.selection()
            if not sel:
                return
            item = self.exec_tree.item(sel[0])
            clicked_lnum = int(item["values"][0])
            # 找到该课时对象
            for l in lessons:
                if l.get("lesson_number") == clicked_lnum:
                    self._render_current_lesson(self.current_lesson_frame, cid, l)
                    break

        self.exec_tree.bind("<Double-1>", _on_exec_tree_click)

        # 右栏: 当前课时 + 操作
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        # 当前课时卡片
        self.current_lesson_frame = ttk.LabelFrame(right_frame, text="🎯 当前课时")
        self.current_lesson_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        next_lesson = self.system.get_next_lesson(cid)
        self._render_current_lesson(self.current_lesson_frame, cid, next_lesson)

    def _render_current_lesson(self, parent, course_id, lesson):
        self._stop_log_refresh()
        for w in parent.winfo_children():
            w.destroy()

        if lesson is None:
            self._exec_current_lnum = None
            self._exec_timer_running = False
            ttk.Label(parent, text="🎉", font=("", 48)).pack(pady=20)
            ttk.Label(parent, text="恭喜！本课程全部课时已完成！",
                      font=("", 16, "bold"), foreground="#27ae60").pack(pady=10)
            ttk.Button(parent, text="返回总览", command=self._show_overview).pack(pady=10)
            return

        lnum = lesson.get("lesson_number", 0)
        title = lesson.get("lesson_title", "")
        question = lesson.get("central_question", "")
        description = lesson.get("description", "")
        course = self.system.get_course_by_id(course_id)
        cid = course_id

        self._exec_current_lnum = lnum
        self._exec_timer_running = True
        self.wflogger.start_timer(cid, lnum)
        self._wf_log_action("view_lesson", detail=f"课时{lnum}: {title}")

        # === 单栏布局：可滚动内容区 ===
        scroll_host = ttk.Frame(parent)
        scroll_host.pack(fill=tk.BOTH, expand=True)

        self._left_canvas = tk.Canvas(scroll_host, highlightthickness=0, bg="#FAFAFA")
        left_sb = ttk.Scrollbar(scroll_host, orient="vertical", command=self._left_canvas.yview)
        self._left_canvas.configure(yscrollcommand=left_sb.set)

        self._scrollable_left = ttk.Frame(self._left_canvas)
        self._left_canvas.create_window((0, 0), window=self._scrollable_left, anchor="nw",
                                         tags=("scroll_win",))
        self._scrollable_left.bind("<Configure>",
            lambda e: self._left_canvas.configure(scrollregion=self._left_canvas.bbox("all")))
        self._left_canvas.bind("<Configure>", self._on_left_canvas_configure)

        self._left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._left_canvas.bind("<Enter>", lambda e: self._left_canvas.bind_all(
            "<MouseWheel>", lambda ev: _on_mousewheel(ev, self._left_canvas)))
        self._left_canvas.bind("<Leave>", lambda e: self._left_canvas.unbind_all("<MouseWheel>"))

        sl = self._scrollable_left

        # ── 1. 课时标题 ──
        ttk.Label(sl, text=f"课时 {lnum}", font=("", 14), foreground="#2980b9").pack(anchor="w", padx=15, pady=(10, 0))
        ttk.Label(sl, text=title, font=("", 18, "bold")).pack(anchor="w", padx=15, pady=5)

        # ── 2. Section 归属 ──
        sec = self.system.get_lesson_section(cid, lnum)
        if sec:
            sec_info = f"📂 Section {sec.get('section_number', '?')}: {sec.get('section_title', '')}"
            ttk.Label(sl, text=sec_info, font=("", 10), foreground="#8e44ad").pack(anchor="w", padx=15, pady=2)

        # ── 3. 描述 ──
        if description:
            ttk.Separator(sl, orient="horizontal").pack(fill=tk.X, padx=15, pady=5)
            df = ttk.LabelFrame(sl, text="📝 描述", padding=8)
            df.pack(fill=tk.X, padx=15, pady=5)
            ttk.Label(df, text=description, font=("", 10), wraplength=self._adaptive_wraplength(0.6),
                      foreground="#2c3e50").pack(anchor="w")

        # ── 4. 中心问题 ──
        if question:
            ttk.Separator(sl, orient="horizontal").pack(fill=tk.X, padx=15, pady=5)
            qf = ttk.LabelFrame(sl, text="❓ 中心问题", padding=8)
            qf.pack(fill=tk.X, padx=15, pady=5)
            ttk.Label(qf, text=question, font=("", 11), wraplength=self._adaptive_wraplength(0.6),
                      foreground="#c0392b").pack(anchor="w")

        # ── 5. 参考书 ──
        course_refs = course.get("references", []) if course else []
        lesson_refs = lesson.get("references", []) if lesson else []
        if course_refs or lesson_refs:
            ref_frame = ttk.LabelFrame(sl, text="📚 参考书", padding=6)
            ref_frame.pack(fill=tk.X, padx=15, pady=5)
            if lesson_refs:
                for ref in lesson_refs[:8]:
                    ref_text = ref if isinstance(ref, str) else ref.get("title", str(ref))
                    ttk.Label(ref_frame, text=f"  • {ref_text}", style="Sub.TLabel", wraplength=self._adaptive_wraplength(0.55)).pack(anchor="w")
            if course_refs:
                for ref in course_refs[:8]:
                    if isinstance(ref, dict):
                        ref_text = ref.get("title", str(ref))
                    else:
                        ref_text = str(ref)
                    ttk.Label(ref_frame, text=f"  • {ref_text}", style="Sub.TLabel", wraplength=self._adaptive_wraplength(0.55)).pack(anchor="w")

        # ── 6. 资源区域 ──
        self._build_resource_section(sl, cid, lnum)

        # ── 7. 快捷操作区 ──
        ttk.Separator(sl, orient="horizontal").pack(fill=tk.X, padx=15, pady=8)
        action_frame = ttk.Frame(sl)
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        timer_frame = ttk.Frame(action_frame)
        timer_frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(timer_frame, text="⏱️", font=("", 12)).pack(side=tk.LEFT)
        self._timer_label = ttk.Label(timer_frame, text="00:00:00", font=("Consolas", 12, "bold"),
                                       foreground="#2980b9")
        self._timer_label.pack(side=tk.LEFT, padx=4)
        self._update_timer()
        action_frame_util = self._scrollable_button_bar(action_frame)
        ttk.Button(action_frame_util, text="📋 课程详情",
                  command=lambda: self._show_course_detail(cid)).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame_util, text="📝 打开笔记",
                  command=lambda: self._open_note(cid, lnum)).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame_util, text="📋 辅助工具",
                  command=lambda: self._show_execution_popup(cid, lnum)).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame_util, text="🔄 复习",
                  command=lambda: self._show_review_reminder(cid)).pack(side=tk.LEFT, padx=4)


        course_name = course.get("name", "") if course else ""
        ai_query = f"{course_name} {title}".strip()
        if question:
            ai_query += f" {question}"

        l_search0 = course.get("references", "") if course else "" 
        l_search1 = f"{l_search0}"

        def _ask_ai(q=ai_query):
            if q:
                self.root.clipboard_clear()
                self.root.clipboard_append(q)
            webbrowser.open("https://chat.deepseek.com/")
       
        def _lib_search(s=l_search1):
            if s:
                self.root.clipboard_clear()
                self.root.clipboard_append(s)                
            webbrowser.open("https://zh.ttt101.ru/")  
            webbrowser.open("https://zh.annas-archive.gl/")
            webbrowser.open("https://libgen.li") 
            webbrowser.open("http://www.dangdang.com") 
            webbrowser.open("https://www.xhsd.com") 
            webbrowser.open("http://www.kongfz.com") 
            webbrowser.open("https://www.goofish.com/")
            webbrowser.open("https://lib.gdufs.edu.cn/")
            
         

        ttk.Button(action_frame_util, text="🤖 问AI",
                  command=_ask_ai).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame_util, text="📝图书馆导引",
                  command=_lib_search).pack(side=tk.LEFT, padx=4)

        # ── 8. 进度 & 完成 ──
        ttk.Separator(sl, orient="horizontal").pack(fill=tk.X, padx=15, pady=8)

        pct = self.system.get_completion_pct(cid)
        remaining = self.system.get_remaining_count(cid)
        total = len(course.get("lessons", [])) if course else 0

        stats = ttk.Frame(sl)
        stats.pack(fill=tk.X, padx=15)
        ttk.Label(stats, text=f"进度: {total - remaining}/{total}  |  完成 {pct}%", style="Sub.TLabel").pack(anchor="w")
        pbar = ttk.Progressbar(stats, length=400, mode="determinate", maximum=100)
        pbar["value"] = pct
        pbar.pack(fill=tk.X, pady=5)

        # ── 9. 工作量 & 耗散 ──
        wl = self.wflogger.get_lesson_workload(cid, lnum)
        if wl["session_count"] > 0:
            ttk.Separator(sl, orient="horizontal").pack(fill=tk.X, padx=15, pady=4)
            ws_frame = ttk.Frame(sl)
            ws_frame.pack(fill=tk.X, padx=15)
            eff_min = wl["effective_sec"] / 60
            dis_min = wl["dissipation_sec"] / 60
            ttk.Label(ws_frame, text=f"⚡ 工作量: {wl['workload']}",
                      font=("", 10, "bold"), foreground="#2980b9").pack(anchor="w")
            ttk.Label(ws_frame,
                      text=f"✅ 贡献: {eff_min:.0f}分 ({wl['contribution_count']}次)  |  "
                           f"💨 耗散: {dis_min:.0f}分 ({wl['dissipation_count']}次)",
                      font=("", 9), foreground="#7F8C8D").pack(anchor="w")
            ttk.Label(ws_frame,
                      text=f"📝 笔记{wl['note_count']}  📂 资源{wl['resource_count']}  "
                           f"🎬 动作{wl['action_count']}",
                      font=("", 9), foreground="#7F8C8D").pack(anchor="w")

        btn_frame = ttk.Frame(sl)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="✅ 完成此课时 → 进入下一步",
                  command=lambda: self._complete_and_next(cid, lnum)).pack(side=tk.LEFT, padx=10, ipady=5, ipadx=15)

    def _on_left_canvas_configure(self, event):
        """左栏Canvas宽度变化时，内部Frame自适应"""
        self._left_canvas.itemconfig("scroll_win", width=event.width)

    def _update_timer(self):
        """更新计时器显示"""
        if self._exec_timer_running and hasattr(self, '_timer_label'):
            try:
                start = self.wflogger._timer_start
                if start:
                    delta = datetime.now() - start
                    hrs, rem = divmod(int(delta.total_seconds()), 3600)
                    mins, secs = divmod(rem, 60)
                    self._timer_label.config(text=f"{hrs:02d}:{mins:02d}:{secs:02d}")
            except:
                pass
            self.root.after(1000, self._update_timer)

    def _show_execution_popup(self, cid, lnum):
        """弹窗显示执行模式的详情面板（日志/笔记/代码/PDF四个Tab）"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"执行详情 - 课时{lnum}")
        dlg.geometry("900x700")
        dlg.transient(self.root)
        dlg.grab_set()
        
        nb = ttk.Notebook(dlg)
        nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        note_tab = ttk.Frame(nb)
        nb.add(note_tab, text="📝 笔记预览")
        self._build_inline_note_editor(note_tab, cid, lnum)
        
        code_tab = ttk.Frame(nb)
        nb.add(code_tab, text="💻 程序实验")
        self._build_lesson_code_panel(code_tab, cid, lnum)
        
        pdf_tab = ttk.Frame(nb)
        nb.add(pdf_tab, text="📚 PDF预览")
        self._build_pdf_preview_tab(pdf_tab, cid, lnum)

        log_tab = ttk.Frame(nb)
        nb.add(log_tab, text="📋 日志")
        self._build_quick_notes(log_tab, cid, lnum)
        
        analysis_tab = ttk.Frame(nb)
        nb.add(analysis_tab, text="🔍 笔记分析")
        self._build_note_analysis_panel(analysis_tab, cid, lnum)
        
        review_tab = ttk.Frame(nb)
        nb.add(review_tab, text="🔄 间隔复习")
        self._build_spaced_review_panel(review_tab, cid, lnum)
        
        
        ttk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=5)

    def _build_note_analysis_panel(self, parent, course_id, lesson_num):
        """构建笔记分析面板"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from note_analyzer import NoteAnalyzer, NoteElement

        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        note_path, _ = self.system.get_or_create_note(course_id, lesson_num)
        
        ttk.Label(frame, text="📊 笔记分析 - 提取定义、定理、推论等", 
                  font=("", 12, "bold")).pack(pady=(0, 10))

        # 按钮区域
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)

        elements = []
        result_text = tk.Text(frame, wrap=tk.WORD, height=15, font=("Consolas", 9), bg="#F8F9FA")
        result_text.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=result_text.yview)
        result_text.configure(yscrollcommand=scrollbar.set)

        def analyze_note():
            """分析笔记"""
            result_text.delete("1.0", tk.END)
            if not note_path or not note_path.exists():
                result_text.insert("1.0", "笔记文件不存在！")
                return

            try:
                nonlocal elements
                elements = NoteAnalyzer.extract_from_file(note_path, course_id, lesson_num)
                
                output = []
                output.append(f"=== 分析结果 ===\n")
                output.append(f"共提取到 {len(elements)} 个元素\n\n")

                type_stats = {}
                for elem in elements:
                    if elem.elem_type not in type_stats:
                        type_stats[elem.elem_type] = 0
                    type_stats[elem.elem_type] += 1

                for elem_type, count in type_stats.items():
                    output.append(f"{elem_type}: {count}\n")

                output.append("\n=== 详细内容 ===\n")
                for elem in elements:
                    output.append(f"\n--- {elem.elem_type.upper()}: {elem.title} ---\n")
                    output.append(elem.content[:200])
                    if len(elem.content) > 200:
                        output.append("...\n")

                result_text.insert("1.0", "".join(output))
            except Exception as e:
                result_text.insert("1.0", f"分析失败: {e}")
                import traceback
                result_text.insert(tk.END, f"\n{traceback.format_exc()}")

        ttk.Button(btn_frame, text="🔍 分析笔记", command=analyze_note).pack(side=tk.LEFT, padx=2)

        def export_json():
            if not elements:
                messagebox.showwarning("提示", "请先分析笔记！")
                return
            path = filedialog.asksaveasfilename(
                title="导出JSON", defaultextension=".json", initialfile="note_elements.json"
            )
            if path:
                try:
                    NoteAnalyzer.to_json(elements, Path(path))
                    messagebox.showinfo("成功", "JSON导出成功！")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")

        def export_csv():
            if not elements:
                messagebox.showwarning("提示", "请先分析笔记！")
                return
            path = filedialog.asksaveasfilename(
                title="导出CSV", defaultextension=".csv", initialfile="note_elements.csv"
            )
            if path:
                try:
                    NoteAnalyzer.to_csv(elements, Path(path))
                    messagebox.showinfo("成功", "CSV导出成功！")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")

        def export_xlsx():
            if not elements:
                messagebox.showwarning("提示", "请先分析笔记！")
                return
            path = filedialog.asksaveasfilename(
                title="导出XLSX", defaultextension=".xlsx", initialfile="note_elements.xlsx"
            )
            if path:
                try:
                    NoteAnalyzer.to_xlsx(elements, Path(path))
                    messagebox.showinfo("成功", "XLSX导出成功！")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")

        ttk.Button(btn_frame, text="📤 导出JSON", command=export_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📤 导出CSV", command=export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📤 导出XLSX", command=export_xlsx).pack(side=tk.LEFT, padx=2)

    def _build_spaced_review_panel(self, parent, course_id, lesson_num):
        """构建间隔重复复习面板（卡片式+列表式+填空测验）"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from note_analyzer import NoteAnalyzer, NoteElement, SpacedRepetitionManager

        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        note_path, _ = self.system.get_or_create_note(course_id, lesson_num)
        review_data_path = BASE / "spaced_review_data.json"
        srm = SpacedRepetitionManager(review_data_path)
        
        # === 保存引用，便于以后自动重新分析
        self._current_srm = srm
        self._current_note_path = note_path
        self._current_course_id = course_id
        self._current_lesson_num = lesson_num

        # === 先定义所有函数和UI元素
        # === 顶部UI
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(top_frame, text="🔄 间隔复习系统", 
                  font=("", 12, "bold")).pack(side=tk.LEFT, padx=(0, 20))

        status_label = ttk.Label(top_frame, text="准备就绪")
        status_label.pack(side=tk.RIGHT, padx=10)
        
        view_mode = tk.StringVar(value="card")
        
        # === 主内容 Notebook
        content_notebook = ttk.Notebook(main_frame)
        content_notebook.pack(fill=tk.BOTH, expand=True)
        
        # === 1. 列表视图
        list_frame = ttk.Frame(content_notebook)
        content_notebook.add(list_frame, text="📋 列表视图")
        list_tree = ttk.Treeview(list_frame, columns=("type", "title"), show="headings")
        list_tree.heading("type", text="类型")
        list_tree.heading("title", text="标题")
        list_tree.column("type", width=100)
        list_tree.column("title", width=400)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=list_tree.yview)
        list_tree.configure(yscrollcommand=list_scroll.set)
        list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # === 列表点击事件：双击触发填空测验 ===
        fill_vars_holder = {"fill_queue": [], "fill_index": 0}
        
        def on_list_double_click(event):
            """列表双击事件：跳转到填空视图并开始测验"""
            selection = list_tree.selection()
            if not selection:
                return
            item_id = selection[0]
            item_values = list_tree.item(item_id, "values")
            if not item_values:
                return
            
            elem_type, elem_title = item_values[0], item_values[1]
            all_elems = srm.get_all_elements()
            clicked_elem = None
            clicked_index = 0
            for idx, elem in enumerate(all_elems):
                display_t = elem.title if elem.title else (elem.content[:40] + "..." if elem.content else "无标题")
                if elem.elem_type == elem_type and display_t == elem_title:
                    clicked_elem = elem
                    clicked_index = idx
                    break
            
            if clicked_elem:
                fill_vars_holder["fill_queue"] = all_elems
                fill_vars_holder["fill_index"] = clicked_index
                view_mode.set("fill")
                content_notebook.select(2)
                self._fill_view_started = True
        
        list_tree.bind("<Double-Button-1>", on_list_double_click)
        
        # === 现在定义所有函数
        def update_status(text):
            status_label.config(text=text)
        
        def refresh_list_view():
            """刷新列表视图"""
            for item in list_tree.get_children():
                list_tree.delete(item)
            for elem in srm.get_all_elements():
                display_title = elem.title if elem.title else (elem.content[:40] + "..." if elem.content else "无标题")
                list_tree.insert("", tk.END, values=(elem.elem_type, display_title))
        
        def switch_view():
            """切换视图"""
            if view_mode.get() == "list":
                content_notebook.select(0)
                refresh_list_view()
            elif view_mode.get() == "card":
                content_notebook.select(1)
            elif view_mode.get() == "graph":
                content_notebook.select(3)
                refresh_graph_view()
            else:
                content_notebook.select(2)
        
        def load_to_review():
            """加载到复习系统"""
            if not note_path or not note_path.exists():
                messagebox.showwarning("提示", "笔记文件不存在！")
                return
            try:
                elements = NoteAnalyzer.extract_from_file(note_path, course_id, lesson_num)
                # 自动分类和提取三元组
                NoteAnalyzer.auto_classify_elements(elements)
                NoteAnalyzer.auto_extract_triples(elements)
                for elem in elements:
                    srm.add_element(elem)
                update_status(f"✅ 已加载 {len(elements)} 个元素！")
                refresh_list_view()
            except Exception as e:
                update_status(f"❌ 添加失败: {e}")
        
        def reload_from_scratch():
            """清空旧数据并重新加载"""
            if not messagebox.askyesno("确认", "清空所有复习数据并重新加载笔记元素？"):
                return
            srm.review_data["reviews"] = {}
            srm._save()
            load_to_review()
        
        def start_review():
            """启动复习"""
            due = srm.get_due_reviews()
            if not due:
                all_elems = srm.get_all_elements()
                if all_elems:
                    if messagebox.askyesno("提示", "暂无待复习内容！要复习所有卡片吗？"):
                        view_mode.set("card")
                        switch_view()
                        update_status(f"准备复习 {len(all_elems)} 个元素")
                else:
                    messagebox.showinfo("提示", "还没有卡片！请先加载笔记")
                return
            view_mode.set("card")
            switch_view()
            update_status(f"准备复习 {len(due)} 个元素")
        
        # === 现在添加按钮和其它视图
        mode_frame = ttk.Frame(top_frame)
        mode_frame.pack(side=tk.RIGHT, padx=10)
        ttk.Radiobutton(mode_frame, text="📋 列表", variable=view_mode, value="list", 
                        command=switch_view).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="💳 卡片", variable=view_mode, value="card", 
                        command=switch_view).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="✏️ 填空", variable=view_mode, value="fill", 
                        command=switch_view).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="🌐 图谱", variable=view_mode, value="graph", 
                        command=switch_view).pack(side=tk.LEFT)
        
        ttk.Button(top_frame, text="📥 加载", command=load_to_review).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_frame, text="🔄 重置", command=reload_from_scratch).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_frame, text="🎯 开始", command=start_review).pack(side=tk.RIGHT, padx=2)
        
        # === 构建其它视图
        card_frame = ttk.Frame(content_notebook)
        content_notebook.add(card_frame, text="💳 卡片视图")
        self._build_card_view(card_frame, srm, update_status, refresh_list_view)
        
        fill_frame = ttk.Frame(content_notebook)
        content_notebook.add(fill_frame, text="✏️ 填空测验")
        self._build_fill_view(fill_frame, srm, update_status, refresh_list_view, fill_vars_holder)
        
        graph_frame = ttk.Frame(content_notebook)
        content_notebook.add(graph_frame, text="🌐 知识图谱")
        # 这里我们先构建一个基础视图，可以用Text显示Graphviz DOT和统计信息
        # 以及分类标签展示
        refresh_graph_view = self._build_graph_view(graph_frame, srm, update_status)
        
        # === 保存引用，便于自动刷新
        self._current_refresh_graph_view = refresh_graph_view
        self._current_refresh_list_view = refresh_list_view
    
    def _build_card_view(self, parent, srm, update_status, refresh_callback):
        """构建卡片式记忆测验，支持Markdown渲染和TeX公式翻译"""
        # 尝试导入Markdown解析库
        try:
            import markdown
            has_markdown = True
        except ImportError:
            has_markdown = False
        try:
            from tkhtmlview import HTMLLabel
            has_htmlview = True
        except ImportError:
            has_htmlview = False
        # 导入TeX翻译模块
        try:
            from tex_to_utf8 import TeXToUTF8
            has_tex_translator = True
        except ImportError:
            has_tex_translator = False
        
        # === 卡片区域 ===
        card_container = ttk.Frame(parent)
        card_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部工具栏
        toolbar = ttk.Frame(card_container)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        use_render_var = tk.BooleanVar(value=(has_markdown and has_htmlview))
        use_tex_translate_var = tk.BooleanVar(value=True)
        
        render_toggle_btn = None
        if has_markdown and has_htmlview:
            render_toggle_btn = ttk.Checkbutton(
                toolbar, 
                text="🎨 渲染Markdown", 
                variable=use_render_var,
                onvalue=True, 
                offvalue=False
            )
            render_toggle_btn.pack(side=tk.LEFT, padx=2)
        
        tex_translate_btn = ttk.Checkbutton(
            toolbar,
            text="🔤 TeX翻译",
            variable=use_tex_translate_var,
            onvalue=True,
            offvalue=False
        )
        tex_translate_btn.pack(side=tk.LEFT, padx=2)
        
        # === 搜索框 ===
        ttk.Label(toolbar, text="🔍 搜索:").pack(side=tk.LEFT, padx=(10, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=search_var, width=20)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 卡片显示区域
        card_display_frame = ttk.LabelFrame(card_container, text="记忆卡片", padding=10)
        card_display_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 卡片正面（问题/题目）
        front_text = tk.Text(card_display_frame, wrap=tk.WORD, height=6, font=("Microsoft YaHei UI", 11), 
                             bg="#FFF9E6", borderwidth=2, relief="groove")
        front_text.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(card_display_frame, text="▼ 点击显示答案 ▼", font=("", 9, "italic")).pack(pady=(0, 5))
        
        # 卡片背面（答案/内容）- 同时支持两种模式
        back_container = ttk.Frame(card_display_frame)
        back_container.pack(fill=tk.BOTH, expand=True)
        
        # 纯文本视图
        back_text = tk.Text(back_container, wrap=tk.WORD, height=8, font=("Microsoft YaHei UI", 11), 
                            bg="#E8F5E9", borderwidth=2, relief="groove")
        
        # HTML渲染视图
        back_html = None
        if has_markdown and has_htmlview:
            back_html = HTMLLabel(back_container, html="", background="#E8F5E9", borderwidth=2, relief="groove")
        
        # 根据模式初始显示
        if use_render_var.get() and back_html:
            back_html.pack(fill=tk.BOTH, expand=True)
        else:
            back_text.pack(fill=tk.BOTH, expand=True)

        # === 进度 ===
        progress_frame = ttk.Frame(card_container)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        progress_label = ttk.Label(progress_frame, text="0 / 0")
        progress_label.pack()

        # === 控制面板 ===
        control_frame = ttk.Frame(card_container)
        control_frame.pack(fill=tk.X)

        # 显示控制按钮
        show_btn = ttk.Button(control_frame, text="👁️ 显示答案", width=20)
        show_btn.pack(side=tk.LEFT, padx=(0, 10))

        # 难度评分按钮
        quality_frame = ttk.Frame(control_frame)
        quality_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        quality_desc = {0: "❌ 完全忘记", 1: "😰 几乎忘记", 2: "😅 有些模糊", 
                     3: "🤔 记不清了", 4: "😊 记住了", 5: "😄 非常熟悉"}

        quality_var = tk.IntVar(value=3)
        for q in range(0, 6):
            btn = ttk.Radiobutton(quality_frame, text=quality_desc[q], 
                                  variable=quality_var, value=q)
            btn.pack(side=tk.LEFT, padx=2)

        # 导航按钮
        nav_frame = ttk.Frame(control_frame)
        nav_frame.pack(side=tk.RIGHT)
        
        prev_btn = ttk.Button(nav_frame, text="◀ 上一张", width=12)
        prev_btn.pack(side=tk.LEFT, padx=2)
        
        next_btn = ttk.Button(nav_frame, text="下一张 ▶", width=12)
        next_btn.pack(side=tk.LEFT, padx=2)
        
        # === 状态管理 - 简化版 ===
        current_index = 0
        is_answer_shown = False
        current_elem_content = ""
        source_elems = srm.get_all_elements()  # 所有可用元素，始终从这里开始
        working_queue = source_elems.copy()  # 当前工作队列，初始化为所有元素
        
        def process_content_for_display(content):
            """处理内容用于显示，包括可选的TeX翻译"""
            processed = content
            if has_tex_translator and use_tex_translate_var.get():
                try:
                    processed = TeXToUTF8.translate_tex(processed)
                except Exception:
                    pass
            return processed
        
        def render_markdown(md_text):
            """简单Markdown渲染辅助函数"""
            if not has_markdown or not has_htmlview:
                return None
            # 先处理TeX翻译
            processed = process_content_for_display(md_text)
            html_content = markdown.markdown(processed, extensions=['tables', 'fenced_code', 'nl2br'])
            styled_html = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Microsoft YaHei', Arial, sans-serif;
                        font-size: 13px;
                        margin: 10px;
                        background-color: #E8F5E9;
                    }}
                    pre {{
                        background: #f0f0f0;
                        padding: 8px;
                        border-radius: 4px;
                    }}
                    code {{
                        background: #f0f0f0;
                        padding: 2px 4px;
                        border-radius: 2px;
                    }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """
            return styled_html
        
        def filter_cards():
            """根据搜索词过滤卡片 - 简化版"""
            nonlocal current_index, working_queue
            search_term = search_var.get().lower().strip()
            if not search_term:
                working_queue = source_elems.copy()
            else:
                working_queue = []
                for elem in source_elems:
                    title = (elem.title or "").lower()
                    content = (elem.content or "").lower()
                    elem_type = (elem.elem_type or "").lower()
                    if search_term in title or search_term in content or search_term in elem_type:
                        working_queue.append(elem)
                if not working_queue:
                    working_queue = source_elems.copy()
            current_index = 0
            display_current_card()
        
        def switch_display_mode():
            """切换显示模式"""
            for widget in back_container.winfo_children():
                widget.pack_forget()
            if use_render_var.get() and back_html:
                back_html.pack(fill=tk.BOTH, expand=True)
                if is_answer_shown:
                    html_content = render_markdown(current_elem_content)
                    if html_content:
                        back_html.set_html(html_content)
                    else:
                        translated = process_content_for_display(current_elem_content)
                        back_html.set_html(f"<html><body><pre>{translated}</pre></body></html>")
            else:
                back_text.pack(fill=tk.BOTH, expand=True)
                back_text.config(bg="#E8F5E9")
                if is_answer_shown:
                    back_text.delete("1.0", tk.END)
                    translated = process_content_for_display(current_elem_content)
                    back_text.insert("1.0", translated)
                else:
                    back_text.config(bg="#F0F0F0")
                    back_text.delete("1.0", tk.END)
        
        def update_tex_translation():
            """更新TeX翻译开关时刷新显示"""
            if is_answer_shown:
                # 重新显示当前内容，应用翻译
                toggle_answer()
                toggle_answer()
        
        if render_toggle_btn:
            render_toggle_btn.config(command=switch_display_mode)
        
        tex_translate_btn.config(command=update_tex_translation)
        
        def reset_ui():
            """重置UI状态"""
            front_text.delete("1.0", tk.END)
            if use_render_var.get() and back_html:
                back_html.set_html("")
            else:
                back_text.delete("1.0", tk.END)
                back_text.config(bg="#F0F0F0")
        
        def update_progress():
            """更新进度显示"""
            total = len(working_queue)
            if total > 0:
                progress_label.config(text=f"{current_index + 1} / {total}")
            else:
                progress_label.config(text="0 / 0")

        def display_current_card():
            """显示当前卡片"""
            nonlocal is_answer_shown, current_elem_content
            reset_ui()
            is_answer_shown = False
            back_text.config(bg="#F0F0F0")
            show_btn.config(text="👁️ 显示答案")
            
            if not working_queue or current_index >= len(working_queue):
                front_text.insert("1.0", "🎉 复习完成！")
                return

            elem = working_queue[current_index]
            current_elem_content = elem.content if elem.content else ""
            
            display_title = elem.title
            if not display_title:
                display_title = elem.content[:40] + "..." if elem.content else "无标题"
            
            # 对标题进行翻译
            translated_title = process_content_for_display(display_title)
            front_content = f"[{elem.elem_type.upper()}]  {translated_title}\n"
            front_text.insert("1.0", front_content)
            update_progress()

        def toggle_answer():
            """显示/隐藏答案"""
            nonlocal is_answer_shown
            if not working_queue:
                return
            
            if not is_answer_shown:
                if use_render_var.get() and back_html:
                    html_content = render_markdown(current_elem_content)
                    if html_content:
                        back_html.set_html(html_content)
                    else:
                        # 即使是纯文本显示，也先处理翻译
                        translated = process_content_for_display(current_elem_content)
                        back_html.set_html(f"<html><body><pre>{translated}</pre></body></html>")
                else:
                    back_text.config(bg="#E8F5E9")
                    back_text.delete("1.0", tk.END)
                    translated = process_content_for_display(current_elem_content)
                    back_text.insert("1.0", translated)
                show_btn.config(text="🙈 隐藏答案")
                is_answer_shown = True
            else:
                reset_ui()
                show_btn.config(text="👁️ 显示答案")
                is_answer_shown = False

        def record_review():
            """记录本次复习"""
            if not working_queue or current_index >= len(working_queue):
                return
            elem = working_queue[current_index]
            srm.review(elem.id, quality_var.get())
            update_status(f"已记录: {quality_desc[quality_var.get()]}")
            refresh_callback()

        def go_next():
            """下一张卡片"""
            nonlocal current_index
            if working_queue:
                record_review()
                current_index = (current_index + 1) % len(working_queue)
                display_current_card()

        def go_prev():
            """上一张卡片"""
            nonlocal current_index
            if working_queue:
                record_review()
                if current_index == 0:
                    current_index = len(working_queue) - 1
                else:
                    current_index -= 1
                display_current_card()
        
        def start_review():
            """开始复习"""
            nonlocal source_elems, current_index
            due = srm.get_due_reviews()
            if not due:
                all_elems = srm.get_all_elements()
                if all_elems:
                    if messagebox.askyesno("提示", "暂无待复习内容！要复习所有卡片吗？"):
                        source_elems = all_elems
                        current_index = 0
                        search_var.set("")
                        filter_cards()
                        update_status(f"复习所有 {len(source_elems)} 张卡片")
                else:
                    messagebox.showinfo("提示", "还没有卡片！请先加载笔记")
                return
            source_elems = due
            current_index = 0
            search_var.set("")
            filter_cards()
            update_status(f"开始复习 {len(source_elems)} 张卡片")
        
        # 绑定按钮
        show_btn.config(command=toggle_answer)
        prev_btn.config(command=go_prev)
        next_btn.config(command=go_next)
        
        # 绑定搜索事件
        search_entry.bind("<KeyRelease>", lambda e: filter_cards())
        search_entry.bind("<Escape>", lambda e: (search_var.set(""), filter_cards()))
        
        # === 键盘快捷键绑定 ===
        def on_key_press(event):
            """处理键盘快捷键 - 检查当前视图是否可见"""
            # 检查卡片视图是否可见
            if not (card_container.winfo_ismapped() and card_container.winfo_viewable()):
                return
            key = event.keysym
            if key == "Left":
                go_prev()
                return "break"
            elif key == "Right":
                go_next()
                return "break"
            elif key in ("space", "Return"):
                toggle_answer()
                return "break"
            elif key in ("1", "2", "3", "4", "5"):
                # 数字键快速评分并下一张
                quality_var.set(int(key))
                record_review()
                go_next()
                return "break"
            elif key == "n" or key == "N":
                go_next()
                return "break"
            elif key == "p" or key == "P":
                go_prev()
                return "break"
        
        # 绑定全局快捷键
        card_container.bind_all("<Key>", on_key_press)
        
        # 添加提示标签
        hint_frame = ttk.Frame(card_container)
        hint_frame.pack(fill=tk.X, pady=(5, 0))
        hint_label = ttk.Label(hint_frame, 
            text="💡 快捷键: ←/→ 导航 | Space/Enter 显示答案 | 1-5 评分 | N/P 下一张/上一张",
            font=("", 8), foreground="gray")
        hint_label.pack()
        
        # 添加卡片视图专属的启动按钮
        ttk.Button(card_container, text="🎯 开始复习", command=start_review).pack(pady=10)
        
        # 初始显示所有元素
        def load_all():
            nonlocal source_elems, current_index
            source_elems = srm.get_all_elements()
            if source_elems:
                current_index = 0
                search_var.set("")
                filter_cards()
                update_status(f"显示全部 {len(source_elems)} 张卡片")
        ttk.Button(card_container, text="📚 查看全部", command=load_all).pack()
        
        # === 初始化显示 ===
        if source_elems:
            filter_cards()
    
    def _build_fill_view(self, parent, srm, update_status, refresh_callback, external_vars=None):
        """构建填空测验视图，可接收外部传入的填空队列和TeX公式翻译"""
        import random
        
        # 导入TeX翻译模块
        try:
            from tex_to_utf8 import TeXToUTF8
            has_tex_translator = True
        except ImportError:
            has_tex_translator = False
        
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        title_frame = ttk.LabelFrame(main_container, text="✏️ 填空测验", padding=10)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_frame, text="提示：系统会从定义/定理的内容中挖空，你来填写关键部分").pack()
        
        # 工具栏：搜索框和翻译开关
        toolbar_frame = ttk.Frame(title_frame)
        toolbar_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(toolbar_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=(0, 5))
        fill_search_var = tk.StringVar()
        fill_search_entry = ttk.Entry(toolbar_frame, textvariable=fill_search_var, width=20)
        fill_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        use_tex_translate_var = tk.BooleanVar(value=True)
        tex_translate_btn = None
        if has_tex_translator:
            tex_translate_btn = ttk.Checkbutton(
                toolbar_frame,
                text="🔤 TeX翻译",
                variable=use_tex_translate_var,
                onvalue=True,
                offvalue=False
            )
            tex_translate_btn.pack(side=tk.LEFT, padx=5)
        
        quiz_frame = ttk.LabelFrame(main_container, text="当前题目", padding=10)
        quiz_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        question_display = tk.Text(quiz_frame, wrap=tk.WORD, height=6, font=("Microsoft YaHei UI", 11),
                                   bg="#FFF9E6", borderwidth=2, relief="groove")
        question_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 填空框容器
        fill_entry_frame = ttk.Frame(quiz_frame)
        fill_entry_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(fill_entry_frame, text="✏️ 你的答案：", font=("", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        answer_entry = tk.Text(fill_entry_frame, wrap=tk.WORD, height=3, font=("Microsoft YaHei UI", 12),
                              borderwidth=2, relief="groove")
        answer_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        feedback_label = ttk.Label(quiz_frame, text="")
        feedback_label.pack()
        
        check_btn = ttk.Button(quiz_frame, text="✅ 检查答案", width=15)
        check_btn.pack(pady=5)
        
        show_answer_btn = ttk.Button(quiz_frame, text="👁️ 显示答案", width=15)
        show_answer_btn.pack(pady=2)
        
        # === 进度和导航
        control_frame = ttk.Frame(main_container)
        control_frame.pack(fill=tk.X)
        
        ttk.Label(control_frame, text="当前进度：").pack(side=tk.LEFT)
        
        progress_var = ttk.Label(control_frame, text="0 / 0")
        progress_var.pack(side=tk.LEFT, padx=5)
        
        prev_fill_btn = ttk.Button(control_frame, text="◀ 上一题")
        prev_fill_btn.pack(side=tk.RIGHT, padx=5)
        
        next_fill_btn = ttk.Button(control_frame, text="下一题 ▶")
        next_fill_btn.pack(side=tk.RIGHT, padx=5)
        
        # === 状态管理 - 简化版 ===
        fill_index = 0
        current_answers = []  # 支持多个答案
        current_masked = ""
        current_full = ""
        fill_source_elems = srm.get_all_elements()  # 所有可用元素
        fill_working_queue = fill_source_elems.copy()  # 当前工作队列
        
        def process_content_for_display(content):
            """处理内容用于显示，包括可选的TeX翻译"""
            processed = content
            if has_tex_translator and use_tex_translate_var.get():
                try:
                    processed = TeXToUTF8.translate_tex(processed)
                except Exception:
                    pass
            return processed
        
        def update_fill_progress():
            total = len(fill_working_queue)
            progress_var.config(text=f"{fill_index + 1} / {total}")
        
        def filter_fill_questions():
            """根据搜索词过滤填空题目 - 简化版"""
            nonlocal fill_index, fill_working_queue
            search_term = fill_search_var.get().lower().strip()
            if not search_term:
                fill_working_queue = fill_source_elems.copy()
            else:
                fill_working_queue = []
                for elem in fill_source_elems:
                    title = (elem.title or "").lower()
                    content = (elem.content or "").lower()
                    elem_type = (elem.elem_type or "").lower()
                    if search_term in title or search_term in content or search_term in elem_type:
                        fill_working_queue.append(elem)
                if not fill_working_queue:
                    fill_working_queue = fill_source_elems.copy()
            fill_index = 0
            display_fill_question()
        
        def create_fill_in_blank(elem):
            """从内容中生成填空题 - 使用智能解析函数"""
            content = elem.content if elem.content else ""
            if not content:
                return "无内容", [], ""
            
            from note_analyzer import NoteAnalyzer
            masked, answers, full = NoteAnalyzer.generate_fill_in_blank(content)
            return masked, answers, full
        
        def display_fill_question():
            nonlocal current_answers, current_masked, current_full
            if not fill_working_queue:
                question_display.delete("1.0", tk.END)
                question_display.insert("1.0", "还没有题目！")
                return
            
            elem = fill_working_queue[fill_index]
            display_title = elem.title if elem.title else "无标题"
            question_display.delete("1.0", tk.END)
            q_text = f"[{elem.elem_type.upper()}] {display_title}\n\n"
            question_display.insert("1.0", q_text)
            
            masked, answers, full = create_fill_in_blank(elem)
            current_masked = masked
            current_answers = answers
            current_full = full
            
            # 翻译显示内容
            translated_masked = process_content_for_display(current_masked)
            question_display.insert(tk.END, "\n" + translated_masked)
            answer_entry.delete("1.0", tk.END)
            
            # 显示答案提示
            if answers:
                if len(answers) == 1:
                    feedback_label.config(text=f"共有 1 个空需要填写", foreground="gray")
                else:
                    feedback_label.config(text=f"共有 {len(answers)} 个空需要填写", foreground="gray")
            else:
                feedback_label.config(text="", foreground="black")
            
            feedback_label.pack(fill=tk.X, pady=5)
            update_fill_progress()
        
        def update_tex_translation():
            """更新TeX翻译开关时刷新显示"""
            display_fill_question()
        
        def check_answer():
            user_ans = answer_entry.get("1.0", tk.END + "-1c").strip().lower()
            
            if not current_answers:
                feedback_label.config(text="✅ 完成！", foreground="green")
                if fill_working_queue and fill_index < len(fill_working_queue):
                    elem = fill_working_queue[fill_index]
                    srm.review(elem.id, 4)
                    update_status(f"已记录复习: {elem.elem_type}")
                    refresh_callback()
                return
            
            # 检查答案是否匹配任何一个正确答案
            is_correct = False
            for answer in current_answers:
                if answer.strip().lower() in user_ans or user_ans in answer.strip().lower():
                    is_correct = True
                    break
            
            if is_correct:
                feedback_label.config(text="✅ 正确！", foreground="green")
                if fill_working_queue and fill_index < len(fill_working_queue):
                    elem = fill_working_queue[fill_index]
                    srm.review(elem.id, 4)
                    update_status(f"已记录复习: {elem.elem_type}")
                    refresh_callback()
            else:
                feedback_label.config(text="❌ 再想想...", foreground="red")
        
        def show_full_answer():
            if current_answers:
                if len(current_answers) == 1:
                    # 翻译答案
                    translated_answer = process_content_for_display(current_answers[0])
                    ans_text = f"答案：{translated_answer}"
                else:
                    # 翻译多个答案
                    translated_answers = [process_content_for_display(a) for a in current_answers]
                    ans_text = f"答案：{'; '.join(translated_answers)}"
                    combined_answer = '; '.join(translated_answers)
                feedback_label.config(text=ans_text, foreground="blue")
                
                # 将答案填入输入框
                if len(current_answers) == 1:
                    combined_answer = process_content_for_display(current_answers[0])
                else:
                    combined_answer = '; '.join([process_content_for_display(a) for a in current_answers])
                answer_entry.delete("1.0", tk.END)
                answer_entry.insert("1.0", combined_answer)
            else:
                translated_full = process_content_for_display(current_full)
                feedback_label.config(text=f"完整内容：{translated_full}", foreground="blue")
            
            if fill_working_queue and fill_index < len(fill_working_queue):
                elem = fill_working_queue[fill_index]
                srm.review(elem.id, 2)
                update_status(f"已查看答案: {elem.elem_type}")
                refresh_callback()
        
        def next_fill():
            nonlocal fill_index
            if not fill_working_queue:
                return
            fill_index = (fill_index + 1) % len(fill_working_queue)
            display_fill_question()
        
        def prev_fill():
            nonlocal fill_index
            if not fill_working_queue:
                return
            if fill_index == 0:
                fill_index = len(fill_working_queue) - 1
            else:
                fill_index -= 1
            display_fill_question()
        
        def start_fill_quiz():
            nonlocal fill_source_elems, fill_index
            if external_vars and external_vars.get("fill_queue"):
                fill_source_elems = external_vars["fill_queue"]
                fill_index = external_vars.get("fill_index", 0)
                fill_search_var.set("")
                filter_fill_questions()
                update_status(f"开始 {len(fill_source_elems)} 道题目")
                return
            
            due = srm.get_due_reviews()
            if not due:
                all_elems = srm.get_all_elements()
                if all_elems:
                    if messagebox.askyesno("提示", "暂无待复习！要测验所有内容吗？"):
                        fill_source_elems = all_elems
                        fill_index = 0
                        fill_search_var.set("")
                        filter_fill_questions()
                        update_status(f"开始 {len(fill_source_elems)} 道题目")
                else:
                    messagebox.showinfo("提示", "还没有题目！请先加载笔记")
                return
            fill_source_elems = due
            fill_index = 0
            fill_search_var.set("")
            filter_fill_questions()
            update_status(f"开始 {len(fill_source_elems)} 道题目")
        
        check_btn.config(command=check_answer)
        show_answer_btn.config(command=show_full_answer)
        next_fill_btn.config(command=next_fill)
        prev_fill_btn.config(command=prev_fill)
        ttk.Button(main_container, text="🎯 开始测验", command=start_fill_quiz).pack(pady=10)
        
        # 绑定TeX翻译按钮
        if tex_translate_btn:
            tex_translate_btn.config(command=update_tex_translation)
        
        # 绑定搜索事件
        fill_search_entry.bind("<KeyRelease>", lambda e: filter_fill_questions())
        fill_search_entry.bind("<Escape>", lambda e: (fill_search_var.set(""), filter_fill_questions()))
        
        # === 填空视图键盘快捷键绑定 ===
        def fill_on_key_press(event):
            """处理填空视图键盘快捷键 - 检查当前视图是否可见"""
            # 检查填空视图是否可见
            if not (main_container.winfo_ismapped() and main_container.winfo_viewable()):
                return
            key = event.keysym
            if key == "Left":
                prev_fill()
                return "break"
            elif key == "Right":
                next_fill()
                return "break"
            elif key == "Return":
                # 如果只按了回车键没有配合 Shift，检查答案
                if not (event.state & 0x1):  # 0x1 是 Shift 键
                    check_answer()
                    return "break"
            elif key == "space":
                show_full_answer()
                return "break"
            elif key == "n" or key == "N":
                next_fill()
                return "break"
            elif key == "p" or key == "P":
                prev_fill()
                return "break"
        
        # 绑定全局快捷键
        main_container.bind_all("<Key>", fill_on_key_press)
        
        # 添加提示标签
        hint_frame = ttk.Frame(main_container)
        hint_frame.pack(fill=tk.X, pady=(5, 0))
        hint_label = ttk.Label(hint_frame,
            text="💡 快捷键: ←/→ 导航 | Enter 检查答案 | Space 显示答案 | N/P 下一题/上一题",
            font=("", 8), foreground="gray")
        hint_label.pack()
        
        # === 初始化显示 ===
        if fill_source_elems:
            filter_fill_questions()
    
    def _build_graph_view(self, parent, srm, update_status):
        """构建知识图谱视图"""
        from note_analyzer import KnowledgeGraph, KnowledgeCategory, KnowledgeRelation, KnowledgeTriple
        
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部工具条
        toolbar = ttk.Frame(main_container)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(toolbar, text="📊 知识图谱视图", font=("", 12, "bold")).pack(side=tk.LEFT, padx=(0, 20))
        
        # 使用PanedWindow分割左右区域
        paned = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：图显示和统计
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)
        
        # 右侧：分类和三元组编辑
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=1)
        
        # 右侧用Notebook分两个标签页
        right_notebook = ttk.Notebook(right_panel)
        right_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 标签页1：分类编辑
        category_frame = ttk.Frame(right_notebook, padding=10)
        right_notebook.add(category_frame, text="🏷️ 分类编辑")
        
        # 分类编辑区
        category_edit_text = tk.Text(category_frame, height=15, font=("Microsoft YaHei UI", 10),
                                    wrap=tk.WORD, bg="#FFF9E6", borderwidth=2, relief="groove")
        category_edit_text.pack(fill=tk.BOTH, expand=True)
        
        def update_category_display():
            """更新分类编辑区"""
            category_edit_text.delete("1.0", tk.END)
            elements = srm.get_all_elements()
            if not elements:
                category_edit_text.insert("1.0", "暂无数据！\n请先加载笔记。")
                return
            
            category_edit_text.insert("1.0", "📚 问题分类编辑\n\n")
            category_edit_text.insert(tk.END, "6种分类说明：\n")
            for cat in KnowledgeCategory.ALL:
                display_name = KnowledgeCategory.get_display_name(cat)
                desc = KnowledgeCategory.get_description(cat)
                category_edit_text.insert(tk.END, f"\n{display_name}\n")
                category_edit_text.insert(tk.END, f"  {desc}\n")
            
            category_edit_text.insert(tk.END, "\n\n📋 当前元素的分类：\n")
            for elem in elements[:15]:
                title = elem.title if elem.title else elem.elem_type
                cats = ", ".join([KnowledgeCategory.get_display_name(c) for c in elem.categories]) if elem.categories else "未分类"
                category_edit_text.insert(tk.END, f"\n• {title}\n")
                category_edit_text.insert(tk.END, f"  分类: {cats}\n")
        
        # 标签页2：三元组关系编辑
        triple_frame = ttk.Frame(right_notebook, padding=10)
        right_notebook.add(triple_frame, text="🔗 关系编辑")
        
        # 三元组显示区
        triple_text = tk.Text(triple_frame, height=10, font=("Microsoft YaHei UI", 10),
                             wrap=tk.WORD, bg="#E6F7FF", borderwidth=2, relief="groove")
        triple_text.pack(fill=tk.X, pady=(0, 10))
        
        # 关系选择说明
        relation_desc_label = ttk.Label(triple_frame, text="📖 学科探索关系类型：", font=("", 9, "bold"))
        relation_desc_label.pack(anchor=tk.W)
        
        relation_info = (
            "• 问题引出: 问题 → 理论 (通过问题探索引出理论)\n"
            "• 启发: 启发 → 新理论 (由启发式思考得出新理论)\n"
            "• 推广: 一般 → 特殊 (从特殊案例推广到一般规律)\n"
            "• 推论: 推论 → 定理 (推论是定理的逻辑结果)\n"
            "• 应用: 理论 → 应用 (将理论应用到真实情境)\n"
            "• 练习巩固/理解: 练习 → 知识点 (通过练习巩固知识点)\n"
            "💡 提示：边文本可自定义，输入自定义文本即可"
        )
        relation_desc = ttk.Label(triple_frame, text=relation_info, font=("", 9), foreground="#666666")
        relation_desc.pack(anchor=tk.W, pady=(5, 10))
        
        def update_triple_display():
            """更新三元组显示区"""
            triple_text.delete("1.0", tk.END)
            elements = srm.get_all_elements()
            if not elements:
                triple_text.insert("1.0", "暂无数据！\n请先加载笔记。")
                return
            
            triple_text.insert("1.0", "🔗 知识三元组关系\n\n")
            count = 0
            for elem in elements:
                if elem.triples:
                    title = elem.title if elem.title else elem.elem_type
                    triple_text.insert(tk.END, f"📌 {title}:\n")
                    for triple in elem.triples:
                        triple_text.insert(tk.END, f"   → {triple.subject} [ {triple.predicate} ] {triple.object}\n")
                        count += 1
                    triple_text.insert(tk.END, "\n")
            
            if count == 0:
                triple_text.insert(tk.END, "暂无三元组关系，请点击「编辑关系」添加！\n")
        
        # 统计和图显示
        stats_graph_frame = ttk.Frame(left_frame)
        stats_graph_frame.pack(fill=tk.BOTH, expand=True)
        
        # 统计信息
        stats_frame = ttk.LabelFrame(stats_graph_frame, text="📈 统计信息", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        stats_text = tk.Text(stats_frame, height=6, font=("Microsoft YaHei UI", 10),
                             wrap=tk.WORD, bg="#F5F5F5", borderwidth=2, relief="groove")
        stats_text.pack(fill=tk.X)
        
        # Canvas绘图区
        canvas_frame = ttk.LabelFrame(left_frame, text="📊 视图切换", padding=10)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # 视图切换按钮
        view_tab_frame = ttk.Frame(canvas_frame)
        view_tab_frame.pack(fill=tk.X, pady=(0, 5))
        
        view_var = tk.StringVar(value="graph")
        
        ttk.Radiobutton(view_tab_frame, text="🔗 知识图谱", variable=view_var, value="graph", 
                       command=lambda: switch_view("graph")).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(view_tab_frame, text="🎯 分类聚类", variable=view_var, value="cluster", 
                       command=lambda: switch_view("cluster")).pack(side=tk.LEFT, padx=2)
        
        # 知识图谱画布
        graph_canvas = tk.Canvas(canvas_frame, width=600, height=400, bg="white", 
                                 scrollregion=(0, 0, 1000, 800))
        
        # 聚类视图画布
        cluster_canvas = tk.Canvas(canvas_frame, width=600, height=400, bg="white", 
                                   scrollregion=(0, 0, 1000, 800))
        
        canvas_scroll_y = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        canvas_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas_scroll_x = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        canvas_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 当前画布引用
        current_canvas = graph_canvas
        current_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        current_canvas.configure(yscrollcommand=canvas_scroll_y.set, xscrollcommand=canvas_scroll_x.set)
        
        def switch_view(view_name):
            """切换视图"""
            nonlocal current_canvas
            # 隐藏所有画布
            graph_canvas.pack_forget()
            cluster_canvas.pack_forget()
            
            # 显示选择的画布
            if view_name == "graph":
                current_canvas = graph_canvas
                draw_graph()
            else:
                current_canvas = cluster_canvas
                draw_cluster()
            
            current_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            current_canvas.configure(yscrollcommand=canvas_scroll_y.set, xscrollcommand=canvas_scroll_x.set)
            canvas_scroll_y.configure(command=current_canvas.yview)
            canvas_scroll_x.configure(command=current_canvas.xview)
        
        def draw_graph():
            """绘制知识图谱"""
            graph_canvas.delete("all")
            elements = srm.get_all_elements()
            if not elements:
                graph_canvas.create_text(300, 200, text="暂无数据", font=("Microsoft YaHei", 16))
                return
            
            graph = KnowledgeGraph.load_from_elements(elements)
            graph_data = graph.get_graph_data_for_drawing()
            
            if not graph_data["nodes"]:
                graph_canvas.create_text(300, 200, text="没有可显示的节点", font=("Microsoft YaHei", 14))
                return
            
            node_map = {}
            # 先画边（底层）
            for edge in graph_data["edges"]:
                source = edge["source"]
                target = edge["target"]
                # 找到源和目标节点
                source_node = None
                target_node = None
                for node in graph_data["nodes"]:
                    if node["id"] == source:
                        source_node = node
                    if node["id"] == target:
                        target_node = node
                if source_node and target_node:
                    x1, y1 = source_node["x"], source_node["y"]
                    x2, y2 = target_node["x"], target_node["y"]
                    graph_canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill="#999999", width=1.5)
                    # 关系标签
                    rel_text = edge["relation"][:6] if len(edge["relation"]) > 6 else edge["relation"]
                    mid_x, mid_y = (x1+x2)//2, (y1+y2)//2
                    # 画标签背景
                    rel_box = graph_canvas.create_text(mid_x, mid_y, text=rel_text, font=("Microsoft YaHei", 8), anchor=tk.CENTER)
                    bbox = graph_canvas.bbox(rel_box)
                    if bbox:
                        graph_canvas.create_rectangle(bbox[0]-2, bbox[1]-2, bbox[2]+2, bbox[3]+2, 
                                                     fill="#f0f0f0", outline="#ccc", tags="bg")
                        # 重新把文字放在前面
                        graph_canvas.tag_raise(rel_box)
            
            # 再画节点（上层）
            for node in graph_data["nodes"]:
                node_id = node["id"]
                x, y = node["x"], node["y"]
                color = node["color"]
                label = node["label"]
                
                # 绘制节点圈
                node_radius = 35
                graph_canvas.create_oval(x-node_radius, y-node_radius, x+node_radius, y+node_radius, 
                                       fill=color, outline="#333", width=2)
                
                # 绘制文字，分多行
                text_lines = []
                max_line_len = 10
                for i in range(0, len(label), max_line_len):
                    text_lines.append(label[i:i+max_line_len])
                
                # 多行文字显示
                line_height = 14
                total_height = len(text_lines) * line_height
                start_y = y - (total_height // 2)
                
                for i, line in enumerate(text_lines):
                    text_y = start_y + i * line_height
                    txt = graph_canvas.create_text(x, text_y, text=line, 
                                                  font=("Microsoft YaHei", 9), anchor=tk.CENTER)
                    # 确保文字在最上层
                    graph_canvas.tag_raise(txt)
                
                node_map[node_id] = (x, y)
            
            update_status(f"✅ 已绘制 {len(graph_data['nodes'])} 个节点, {len(graph_data['edges'])} 条边")
        
        def draw_cluster():
            """绘制分类聚类图（类似Venn图）"""
            cluster_canvas.delete("all")
            elements = srm.get_all_elements()
            if not elements:
                cluster_canvas.create_text(300, 200, text="暂无数据", font=("Microsoft YaHei", 16))
                return
            
            # 分类到颜色和位置的映射
            category_info = {
                "practice":   {"color": "#FFE082", "name": "🔧 练习", "x": 150, "y": 150, "radius": 130},
                "heuristic":  {"color": "#81D4FA", "name": "💡 启发", "x": 450, "y": 150, "radius": 130},
                "generalization": {"color": "#A5D6A7", "name": "🌉 推广", "x": 300, "y": 370, "radius": 130},
                "reasoning":  {"color": "#CE93D8", "name": "🔗 推理", "x": 150, "y": 370, "radius": 130},
                "kernel":     {"color": "#EF9A9A", "name": "⚡ 要诀", "x": 450, "y": 370, "radius": 130},
                "application": {"color": "#FFAB91", "name": "🏭 应用", "x": 300, "y": 150, "radius": 130},
            }
            
            # 先画分类的圆圈（底层）
            for cat, info in category_info.items():
                x, y, r = info["x"], info["y"], info["radius"]
                # 半透明填充
                cluster_canvas.create_oval(x-r, y-r, x+r, y+r, 
                                          fill=info["color"], outline="", stipple="gray25")
                # 边框
                cluster_canvas.create_oval(x-r, y-r, x+r, y+r, 
                                          outline=info["color"], width=2)
                # 分类名称
                cluster_canvas.create_text(x, y-r-15, text=info["name"], 
                                          font=("Microsoft YaHei", 10, "bold"))
            
            # 按分类收集元素
            category_elements = {}
            for cat in category_info.keys():
                category_elements[cat] = []
            
            for elem in elements:
                for cat in elem.categories:
                    if cat in category_elements:
                        category_elements[cat].append(elem)
            
            # 在每个分类中绘制元素
            # 计算每个分类中的元素位置
            for cat, info in category_info.items():
                elems = category_elements.get(cat, [])
                if not elems:
                    continue
                
                x_center, y_center, r = info["x"], info["y"], info["radius"]
                count = len(elems)
                
                # 计算元素分布位置（螺旋分布，避免重叠）
                import math
                # 缩小圆的半径，避免超出
                r_inner = r - 35
                
                # 元素大小
                elem_width = 110
                elem_height = 28
                
                for i, elem in enumerate(elems):
                    # 螺旋式计算位置
                    angle = 2 * math.pi * i / count
                    # 越后面的元素稍微向外移，并且有角度偏移
                    spiral_factor = 0.3 + (i / max(count, 1)) * 0.5
                    offset = (i % 4) * 0.1 * r_inner
                    
                    # 计算位置
                    x = x_center + (r_inner - offset) * math.cos(angle)
                    y = y_center + (r_inner - offset) * math.sin(angle)
                    
                    # 元素标题
                    title = elem.title if elem.title else elem.elem_type
                    # 截断过长标题，但至少显示一点
                    short_title = title[:12] if len(title) > 12 else title
                    
                    # 先画文字获取宽度
                    txt_obj = cluster_canvas.create_text(0, 0, text=short_title, 
                                                         font=("Microsoft YaHei", 8))
                    bbox = cluster_canvas.bbox(txt_obj)
                    cluster_canvas.delete(txt_obj)
                    
                    if bbox:
                        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                        # 加上额外的边框
                        box_w = max(w + 12, elem_width)
                        box_h = max(h + 8, elem_height)
                    else:
                        box_w = elem_width
                        box_h = elem_height
                    
                    # 绘制背景框
                    cluster_canvas.create_rectangle(x - box_w/2, y - box_h/2, 
                                                   x + box_w/2, y + box_h/2, 
                                                   fill="white", outline=info["color"], 
                                                   width=2)
                    
                    # 绘制文字
                    cluster_canvas.create_text(x, y, text=short_title, 
                                              font=("Microsoft YaHei", 8), anchor=tk.CENTER)
            
            # 绘制中心的统计信息 - 加框
            stat_text = f"📊 总元素数: {len(elements)}"
            stat_obj = cluster_canvas.create_text(300, 260, text=stat_text, 
                                                 font=("Microsoft YaHei", 11, "bold"))
            bbox = cluster_canvas.bbox(stat_obj)
            if bbox:
                cluster_canvas.create_rectangle(bbox[0]-8, bbox[1]-4, bbox[2]+8, bbox[3]+4, 
                                              fill="#ffffff", outline="#333", width=1)
                cluster_canvas.tag_raise(stat_obj)
            
            update_status(f"✅ 已绘制聚类图: {len(elements)}个元素分布在{len(category_info)}个分类中")
        
        def refresh_graph():
            """刷新知识图谱显示"""
            elements = srm.get_all_elements()
            if not elements:
                stats_text.delete("1.0", tk.END)
                stats_text.insert("1.0", "暂无数据，请先加载笔记！")
                graph_canvas.delete("all")
                graph_canvas.create_text(300, 200, text="暂无数据", font=("Microsoft YaHei", 16))
                update_category_display()
                update_triple_display()
                return
            
            graph = KnowledgeGraph.load_from_elements(elements)
            stats = graph.get_statistics()
            
            stats_text.delete("1.0", tk.END)
            stats_text.insert("1.0", f"总节点数: {stats['total_nodes']}\n")
            stats_text.insert(tk.END, f"总边数: {stats['total_edges']}\n\n")
            stats_text.insert(tk.END, "节点类型分布:\n")
            for node_type, count in stats['node_types'].items():
                stats_text.insert(tk.END, f"  - {node_type}: {count}\n")
            
            stats_text.insert(tk.END, "\n分类分布:\n")
            for category, count in stats['category_distribution'].items():
                display_name = KnowledgeCategory.get_display_name(category)
                stats_text.insert(tk.END, f"  - {display_name}: {count}\n")
            
            # 根据当前选择的视图刷新
            if view_var.get() == "graph":
                draw_graph()
            else:
                draw_cluster()
            
            update_category_display()
            update_triple_display()
            update_status(f"✅ 知识图谱已刷新: {stats['total_nodes']}节点, {stats['total_edges']}边")
        
        def export_dot():
            """导出为DOT文件"""
            elements = srm.get_all_elements()
            if not elements:
                messagebox.showwarning("提示", "暂无数据可导出！")
                return
            
            file_path = filedialog.asksaveasfilename(
                title="导出知识图谱",
                defaultextension=".dot",
                initialfile="knowledge_graph.dot",
                filetypes=[("Graphviz DOT files", "*.dot"), ("All files", "*.*")]
            )
            if file_path:
                graph = KnowledgeGraph.load_from_elements(elements)
                dot_content = graph.to_graphviz_dot()
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(dot_content)
                messagebox.showinfo("成功", f"知识图谱已导出到: {file_path}")
                update_status("✅ 知识图谱导出成功")
        
        # 操作按钮
        button_frame = ttk.Frame(main_container)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def edit_element_category():
            """编辑元素分类"""
            elements = srm.get_all_elements()
            if not elements:
                messagebox.showinfo("提示", "暂无数据可编辑！")
                return
            
            edit_win = tk.Toplevel(main_container)
            edit_win.title("编辑知识分类")
            edit_win.geometry("650x550")
            
            # 分割布局
            main_paned = ttk.PanedWindow(edit_win, orient=tk.HORIZONTAL)
            main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # 左侧：元素列表
            left_frame = ttk.Frame(main_paned, padding=5)
            main_paned.add(left_frame, weight=1)
            
            ttk.Label(left_frame, text="📋 选择要编辑的元素：", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
            
            # 元素筛选按钮
            filter_frame = ttk.Frame(left_frame)
            filter_frame.pack(fill=tk.X, pady=(0, 5))
            
            filter_var = tk.StringVar(value="all")
            
            def apply_filter():
                listbox.delete(0, tk.END)
                filter_val = filter_var.get()
                for idx, elem in enumerate(elements):
                    title = elem.title if elem.title else elem.elem_type
                    elem_type = elem.elem_type
                    
                    if filter_val == "all":
                        listbox.insert(tk.END, f"{idx+1}. [{elem_type}] {title}")
                    elif filter_val == "problem":
                        # 问题类：remark, problem, exercise, question
                        if elem_type in ["remark", "problem", "exercise", "question"]:
                            listbox.insert(tk.END, f"{idx+1}. [{elem_type}] {title}")
                    elif filter_val == "theory":
                        if elem_type in ["definition", "theorem", "corollary", "lemma", "axiom", "proposition", "postulate"]:
                            listbox.insert(tk.END, f"{idx+1}. [{elem_type}] {title}")
                    elif filter_val == "example":
                        if elem_type in ["example", "note"]:
                            listbox.insert(tk.END, f"{idx+1}. [{elem_type}] {title}")
            
            ttk.Radiobutton(filter_frame, text="全部", variable=filter_var, value="all", command=apply_filter).pack(side=tk.LEFT)
            ttk.Radiobutton(filter_frame, text="问题类", variable=filter_var, value="problem", command=apply_filter).pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(filter_frame, text="理论类", variable=filter_var, value="theory", command=apply_filter).pack(side=tk.LEFT)
            ttk.Radiobutton(filter_frame, text="例子类", variable=filter_var, value="example", command=apply_filter).pack(side=tk.LEFT, padx=5)
            
            list_frame = ttk.Frame(left_frame)
            list_frame.pack(fill=tk.BOTH, expand=True)
            
            listbox = tk.Listbox(list_frame, height=15, font=("Microsoft YaHei UI", 9))
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
            listbox.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 初始化填充
            for idx, elem in enumerate(elements):
                title = elem.title if elem.title else elem.elem_type
                listbox.insert(tk.END, f"{idx+1}. [{elem.elem_type}] {title}")
            
            # 右侧：分类选择
            right_frame = ttk.Frame(main_paned, padding=10)
            main_paned.add(right_frame, weight=1)
            
            ttk.Label(right_frame, text="🏷️ 选择知识分类（可多选）：", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
            
            category_vars = {}
            
            # 按类型分组显示分类
            groups = [
                ("🔍 探索类", [
                    (KnowledgeCategory.HEURISTIC, "💡 启发 - 制造认知冲突，引出新概念"),
                    (KnowledgeCategory.PRACTICE, "🔧 练习 - 巩固基本技能"),
                ]),
                ("🔬 理论类", [
                    (KnowledgeCategory.REASONING, "🔗 推理 - 训练逻辑链条"),
                    (KnowledgeCategory.GENERALIZATION, "🌉 推广 - 从特殊到一般"),
                ]),
                ("💡 应用类", [
                    (KnowledgeCategory.KERNEL, "⚡ 要诀 - 提炼核心思想"),
                    (KnowledgeCategory.APPLICATION, "🏭 应用 - 对接真实情境"),
                ]),
            ]
            
            for group_name, cats in groups:
                ttk.Label(right_frame, text=group_name, font=("", 9, "bold")).pack(anchor=tk.W, pady=(5, 2))
                for cat, desc in cats:
                    var = tk.BooleanVar(value=False)
                    category_vars[cat] = var
                    ttk.Checkbutton(right_frame, text=desc, variable=var).pack(anchor=tk.W)
            
            # 元素内容预览
            preview_frame = ttk.LabelFrame(right_frame, text="📝 元素内容预览", padding=5)
            preview_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
            
            preview_text = tk.Text(preview_frame, height=8, font=("Microsoft YaHei UI", 9), wrap=tk.WORD)
            preview_text.pack(fill=tk.BOTH, expand=True)
            
            # 快速建议按钮
            suggest_frame = ttk.Frame(right_frame)
            suggest_frame.pack(fill=tk.X, pady=(10, 0))
            
            def auto_suggest():
                """根据元素类型自动建议分类"""
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("提示", "请先选择一个元素！")
                    return
                
                idx = int(listbox.get(selection[0]).split(".", 1)[0]) - 1
                elem = elements[idx]
                
                # 先清空所有选择
                for var in category_vars.values():
                    var.set(False)
                
                # 根据元素类型和内容自动建议
                elem_type = elem.elem_type
                text = (elem.title + " " + elem.content).lower()
                
                # 根据元素类型初步分类
                # 理论类元素 - 主要标记为推理
                if elem_type in ["definition", "theorem", "corollary", "lemma", "proposition", "axiom", "postulate"]:
                    category_vars[KnowledgeCategory.REASONING].set(True)
                    
                    # 如果是推论，标记为推广
                    if elem_type == "corollary":
                        category_vars[KnowledgeCategory.GENERALIZATION].set(True)
                
                # 问题/练习类元素 - 默认标记为练习
                elif elem_type in ["remark", "problem", "exercise", "question"]:
                    category_vars[KnowledgeCategory.PRACTICE].set(True)
                
                # 例子类元素 - 应用
                elif elem_type in ["example", "note"]:
                    category_vars[KnowledgeCategory.APPLICATION].set(True)
                
                # 解答/证明类元素 - 推理
                elif elem_type in ["solution", "proof"]:
                    category_vars[KnowledgeCategory.REASONING].set(True)
                
                # 启发类 - 根据关键词判断
                if any(w in text for w in ["如果", "假设", "猜想", "会怎样", "猜一猜", "为什么", "有趣", "奇妙"]):
                    category_vars[KnowledgeCategory.HEURISTIC].set(True)
                
                # 推理类 - 根据关键词判断（理论类已默认添加）
                if elem_type not in ["definition", "theorem", "corollary", "lemma", "proposition", "axiom", "postulate", "solution", "proof"]:
                    if any(w in text for w in ["证明", "推导", "验证", "补全", "推出", "因为", "所以", "从而", "因此"]):
                        category_vars[KnowledgeCategory.REASONING].set(True)
                
                # 推广类 - 根据关键词判断
                if any(w in text for w in ["推广到", "一般化", "任意", "n维", "更一般", "从...到..."]):
                    category_vars[KnowledgeCategory.GENERALIZATION].set(True)
                
                # 要诀类 - 根据关键词判断
                if any(w in text for w in ["步骤", "关键", "要诀", "核心", "易错", "注意", "小结", "总结", "套路"]):
                    category_vars[KnowledgeCategory.KERNEL].set(True)
                
                # 应用类 - 根据关键词判断（例子类已默认添加）
                if elem_type not in ["example", "note"]:
                    if any(w in text for w in ["应用", "估算", "设计", "真实", "实际", "情境", "工程", "生活"]):
                        category_vars[KnowledgeCategory.APPLICATION].set(True)
                
                # 练习类 - 根据关键词判断（问题类已默认添加）
                if elem_type not in ["remark", "problem", "exercise", "question"]:
                    if any(w in text for w in ["练习题", "作业", "习题", "练习", "自测", "测验"]):
                        category_vars[KnowledgeCategory.PRACTICE].set(True)
                
                messagebox.showinfo("提示", "已根据元素类型自动建议分类！")
            
            ttk.Button(suggest_frame, text="✨ 智能建议", command=auto_suggest).pack(side=tk.LEFT)
            
            def on_select_element(evt):
                """选择元素时更新显示"""
                selection = listbox.curselection()
                if not selection:
                    return
                
                # 从列表项解析索引
                list_item = listbox.get(selection[0])
                idx = int(list_item.split(".", 1)[0]) - 1
                
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    
                    # 更新分类选择
                    for cat, var in category_vars.items():
                        var.set(cat in elem.categories)
                    
                    # 更新预览
                    preview_text.delete("1.0", tk.END)
                    preview_content = f"【{elem.elem_type}】\n"
                    if elem.title:
                        preview_content += f"标题: {elem.title}\n"
                    preview_content += f"\n内容:\n{elem.content}"
                    preview_text.insert("1.0", preview_content)
            
            listbox.bind('<<ListboxSelect>>', on_select_element)
            
            def save_category():
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("提示", "请先选择一个元素！")
                    return
                
                # 从列表项解析索引
                list_item = listbox.get(selection[0])
                idx = int(list_item.split(".", 1)[0]) - 1
                
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    
                    elem.categories = []
                    for cat, var in category_vars.items():
                        if var.get():
                            elem.categories.append(cat)
                    
                    srm.review_data["reviews"][elem.id]["elem"]["categories"] = elem.categories
                    srm._save()
                    
                    cats_str = ", ".join([KnowledgeCategory.get_display_name(c) for c in elem.categories]) if elem.categories else "未分类"
                    messagebox.showinfo("成功", f"分类已保存！\n当前分类: {cats_str}")
                    refresh_graph()
            
            # 底部按钮
            btn_frame = ttk.Frame(edit_win)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Button(btn_frame, text="💾 保存分类", command=save_category).pack(side=tk.RIGHT)
            ttk.Button(btn_frame, text="❌ 取消", command=edit_win.destroy).pack(side=tk.RIGHT, padx=5)
        
        def edit_element_triple():
            """编辑元素三元组关系"""
            elements = srm.get_all_elements()
            if not elements:
                messagebox.showinfo("提示", "暂无数据可编辑！")
                return
            
            edit_win = tk.Toplevel(main_container)
            edit_win.title("编辑知识三元组关系")
            edit_win.geometry("1350x975")
            
            # 主布局：左右分栏
            main_frame = ttk.Frame(edit_win, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 左侧：元素列表（选择主语和宾语）
            left_frame = ttk.LabelFrame(main_frame, text="📋 元素列表（点击选择）", padding=10)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
            
            ttk.Label(left_frame, text="点击元素可以快速填充到输入框中", font=("", 9)).pack(anchor=tk.W, pady=(0, 5))
            
            elem_list_frame = ttk.Frame(left_frame)
            elem_list_frame.pack(fill=tk.BOTH, expand=True)
            
            elem_listbox = tk.Listbox(elem_list_frame, selectmode=tk.EXTENDED, height=20, font=("Microsoft YaHei UI", 10))
            elem_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            elem_scrollbar = ttk.Scrollbar(elem_list_frame, orient=tk.VERTICAL, command=elem_listbox.yview)
            elem_listbox.configure(yscrollcommand=elem_scrollbar.set)
            elem_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 存储元素引用，方便查找
            elem_index_to_title = {}
            for idx, elem in enumerate(elements):
                title = elem.title if elem.title else elem.elem_type
                # 清理反斜转义字符
                title = title.replace('\\*', '*')
                display_text = f"{idx+1}. [{elem.elem_type}] {title}"
                elem_listbox.insert(tk.END, display_text)
                elem_index_to_title[idx] = title
            
            # 右侧：输入框和关系显示
            right_frame = ttk.Frame(main_frame)
            right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # 输入区域
            input_frame = ttk.LabelFrame(right_frame, text="📝 输入三元组（语法：主语 [关系] 宾语）", padding=10)
            input_frame.pack(fill=tk.X, pady=(0, 10))
            
            # 说明
            help_text = ttk.Label(input_frame, text="语法示例：\n例题1 [启发] 简单例子\n定义 [推论] 定理\n定理 [推广] 推论", 
                                   font=("", 9), foreground="#666666")
            help_text.pack(anchor=tk.W, pady=(0, 5))
            
            # 输入框
            entry_frame = ttk.Frame(input_frame)
            entry_frame.pack(fill=tk.X, pady=(0, 5))
            
            triple_entry = ttk.Entry(entry_frame, font=("Microsoft YaHei UI", 11))
            triple_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
            
            # 按钮：添加
            add_btn = ttk.Button(entry_frame, text="➕ 添加")
            add_btn.pack(side=tk.LEFT)
            
            # 快捷按钮：点击元素填充
            def fill_as_subject():
                """将选中元素填充为主语（支持多选：顿号分隔）"""
                sel = elem_listbox.curselection()
                if not sel:
                    return
                titles = [elem_index_to_title[idx] for idx in sel]
                if len(titles) == 1:
                    title = titles[0]
                    current = triple_entry.get()
                    if "[" in current and "]" in current:
                        after_rel = current.split("]", 1)[1].strip()
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{title} [] {after_rel}")
                    else:
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{title} [] ")
                else:
                    subject_part = "、".join(titles)
                    current = triple_entry.get()
                    if "[" in current and "]" in current:
                        after_rel = current.split("]", 1)[1].strip()
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{subject_part} [] {after_rel}")
                    else:
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{subject_part} [] ")
            
            def fill_as_object():
                """将选中元素填充为宾语（支持多选：顿号分隔）"""
                sel = elem_listbox.curselection()
                if not sel:
                    return
                titles = [elem_index_to_title[idx] for idx in sel]
                if len(titles) == 1:
                    title = titles[0]
                    current = triple_entry.get()
                    if "[" in current and "]" in current:
                        before_rel = current.split("[", 1)[0].strip()
                        relation_part = current.split("]", 1)[1].split("]", 1)[0].strip()
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{before_rel} [{relation_part}] {title}")
                    else:
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"[] {title}")
                else:
                    object_part = "、".join(titles)
                    current = triple_entry.get()
                    if "[" in current and "]" in current:
                        before_rel = current.split("[", 1)[0].strip()
                        relation_part = current.split("]", 1)[1].split("]", 1)[0].strip()
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"{before_rel} [{relation_part}] {object_part}")
                    else:
                        triple_entry.delete(0, tk.END)
                        triple_entry.insert(0, f"[] {object_part}")
            
            quick_btn_frame = ttk.Frame(input_frame)
            quick_btn_frame.pack(fill=tk.X, pady=(5, 0))
            
            ttk.Button(quick_btn_frame, text="← 选为主语", command=fill_as_subject).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(quick_btn_frame, text="选为宾语 →", command=fill_as_object).pack(side=tk.LEFT)
            
            # 关系选择快捷按钮
            rel_frame = ttk.Frame(input_frame)
            rel_frame.pack(fill=tk.X, pady=(5, 0))
            
            ttk.Label(rel_frame, text="快捷关系：", font=("", 9)).pack(side=tk.LEFT, padx=(0, 5))
            
            simple_relations = ["启发", "推论", "推广", "应用", "练习", "前提", "依赖"]
            
            def insert_relation(rel):
                """插入关系到输入框中"""
                current = triple_entry.get()
                # 替换 [] 中的内容
                if "[" in current and "]" in current:
                    before = current.split("[", 1)[0]
                    after = current.split("]", 1)[1]
                    triple_entry.delete(0, tk.END)
                    triple_entry.insert(0, f"{before}[{rel}]{after}")
                else:
                    triple_entry.insert(tk.INSERT, f"[{rel}]")
            
            for rel in simple_relations:
                btn = ttk.Button(rel_frame, text=rel, width=6, command=lambda r=rel: insert_relation(r))
                btn.pack(side=tk.LEFT, padx=2)
            
            # 当前关系显示
            triples_frame = ttk.LabelFrame(right_frame, text="🔗 当前所有关系", padding=10)
            triples_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            triples_text = tk.Text(triples_frame, height=10, font=("Microsoft YaHei UI", 10))
            triples_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            triples_scroll = ttk.Scrollbar(triples_frame, orient=tk.VERTICAL, command=triples_text.yview)
            triples_text.configure(yscrollcommand=triples_scroll.set)
            triples_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 按钮区
            btn_frame = ttk.Frame(right_frame)
            btn_frame.pack(fill=tk.X)
            
            def refresh_triples_display():
                """刷新关系显示"""
                triples_text.delete("1.0", tk.END)
                all_triples = []
                for elem in elements:
                    if elem.triples:
                        all_triples.extend(elem.triples)
                if all_triples:
                    for i, t in enumerate(all_triples):
                        triples_text.insert(tk.END, f"{i+1}. {t.subject} [ {t.predicate} ] {t.object}\n")
                else:
                    triples_text.insert(tk.END, "暂无关系，请在上方输入框中添加！")
            
            def add_triple_from_entry():
                """从输入框添加三元组（支持多个主语）"""
                text = triple_entry.get().strip()
                if not text:
                    messagebox.showwarning("提示", "请输入内容！")
                    return
                
                # 解析语法：主语 [关系] 宾语
                import re
                match = re.match(r'^(.*?)\s*\[([^\]]+)\]\s*(.*)$', text)
                if match:
                    subject_part = match.group(1).strip()
                    relation = match.group(2).strip()
                    obj = match.group(3).strip()
                else:
                    messagebox.showerror("错误", "格式不对！使用：\n主语 [关系] 宾语\n例如：例题1 [启发] 简单例子")
                    return
                
                if not subject_part or not relation or not obj:
                    messagebox.showerror("错误", "主语、关系、宾语都不能为空！")
                    return
                
                # 分割多个主语（顿号分隔）
                subjects = [s.strip() for s in subject_part.split('、') if s.strip()]
                
                # 处理每个主语
                added_count = 0
                for subj in subjects:
                    # 清理转义
                    subj = subj.replace('\\*', '*')
                    
                    # 查找元素
                    found = False
                    for elem in elements:
                        elem_title = elem.title if elem.title else elem.elem_type
                        # 清理比较
                        if elem_title == subj or elem_title == subj.replace('**', ''):
                            new_triple = KnowledgeTriple(elem_title, relation, obj)
                            elem.add_triple(new_triple)
                            # 保存
                            srm.review_data["reviews"][elem.id]["elem"]["triples"] = [t.to_dict() for t in elem.triples]
                            found = True
                            added_count += 1
                            break
                    
                    if not found:
                        messagebox.showerror("警告", f"找不到主语元素：{subj}\n跳过该元素")
                
                srm._save()
                
                if added_count > 0:
                    messagebox.showinfo("成功", f"已添加 {added_count} 个关系！")
                    # 清空输入框
                    triple_entry.delete(0, tk.END)
                    # 刷新显示
                    refresh_triples_display()
                    refresh_graph()
            
            # 绑定回车键添加
            triple_entry.bind("<Return>", lambda event: add_triple_from_entry())
            add_btn.configure(command=add_triple_from_entry)
            
            def delete_all_triples():
                """清空所有关系"""
                if messagebox.askyesno("确认", "确定要清空所有关系吗？"):
                    for elem in elements:
                        elem.triples = []
                        srm.review_data["reviews"][elem.id]["elem"]["triples"] = []
                    srm._save()
                    refresh_triples_display()
                    refresh_graph()
            
            ttk.Button(btn_frame, text="🔄 刷新", command=refresh_triples_display).pack(side=tk.LEFT, padx=2)
            ttk.Button(btn_frame, text="🗑️ 清空所有", command=delete_all_triples).pack(side=tk.LEFT, padx=2)
            ttk.Button(btn_frame, text="✅ 完成", command=edit_win.destroy).pack(side=tk.RIGHT, padx=2)
            
            # 初始刷新
            refresh_triples_display()
        
        ttk.Button(button_frame, text="🔄 刷新图谱", command=refresh_graph).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="📥 导出DOT", command=export_dot).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="✏️ 编辑分类", command=edit_element_category).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="🔗 编辑关系", command=edit_element_triple).pack(side=tk.LEFT, padx=2)
        
        # 初始刷新
        refresh_graph()
        
        return refresh_graph

    @staticmethod
    def _scrollable_button_bar(parent, **kw):
        bar_canvas = tk.Canvas(parent, height=32, highlightthickness=0)
        bar_scroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=bar_canvas.xview)
        bar_canvas.configure(xscrollcommand=bar_scroll.set, scrollregion=bar_canvas.bbox("all"))
        inner = ttk.Frame(bar_canvas)
        bar_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: bar_canvas.configure(scrollregion=bar_canvas.bbox("all")))
        bar_canvas.pack(fill=tk.X, side=tk.TOP)
        bar_scroll.pack(fill=tk.X, side=tk.BOTTOM)

        def _on_enter(e):
            bar_canvas.bind_all("<MouseWheel>", lambda ev: _on_mousewheel_h(ev, bar_canvas))
        def _on_leave(e):
            bar_canvas.unbind_all("<MouseWheel>")
        bar_canvas.bind("<Enter>", _on_enter)
        bar_canvas.bind("<Leave>", _on_leave)
        return inner

    def _build_resource_section(self, parent, cid, lnum):
        """构建执行模式的资源区域，支持搜索过滤"""
        lesson_only_res = self.system.rmgr.get_for_lesson(cid, lnum) if self.system.rmgr else []
        course_only_res = self.system.rmgr.get_for_course(cid) if self.system.rmgr else []
        
        self._exec_resource_cid = cid
        self._exec_resource_lnum = lnum
        self._exec_lesson_resources = lesson_only_res
        self._exec_course_resources = course_only_res
        
        # 资源容器（支持paned或普通frame）
        if isinstance(parent, ttk.PanedWindow):
            res_panel = ttk.Frame(parent, padding=5, width=400)
            res_panel.pack_propagate(False)
            parent.add(res_panel, weight=1)
        else:
            res_panel = ttk.Frame(parent, padding=5)
            res_panel.pack(fill=tk.BOTH, expand=True)
        
        # 搜索框
        search_frame = ttk.Frame(res_panel)
        search_frame.pack(fill=tk.X, padx=5, pady=(5, 2))
        ttk.Label(search_frame, text="🔍 搜索资源：", font=("", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._exec_resource_search_var = tk.StringVar()
        self._exec_resource_search_var.trace_add("write", 
            lambda *args: self._filter_resource_section())
        search_entry = ttk.Entry(search_frame, textvariable=self._exec_resource_search_var, width=20)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(search_frame, text="✕", width=3,
                   command=lambda: (self._exec_resource_search_var.set(""), 
                                   self._filter_resource_section())).pack(side=tk.RIGHT)

        # 课时资源
        self._lr_frame = ttk.LabelFrame(res_panel, text=f"🔗 课时资源 ({len(lesson_only_res)})", padding=6)
        self._lr_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(2, 2))
        
        # 课程资源
        self._cr_frame = ttk.LabelFrame(res_panel, text=f"📚 课程资源 ({len(course_only_res)})", padding=6)
        self._cr_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(2, 5))
        
        self._render_resource_section()
    
    def _filter_resource_section(self):
        """根据搜索关键词过滤资源"""
        self._render_resource_section()
    
    def _render_resource_section(self):
        """渲染资源区域（支持搜索过滤）"""
        cid = self._exec_resource_cid
        lnum = self._exec_resource_lnum
        lesson_only_res = self._exec_lesson_resources
        course_only_res = self._exec_course_resources
        
        search_query = getattr(self, '_exec_resource_search_var', tk.StringVar(value="")).get().strip().lower()
        
        # 过滤资源
        def filter_resources(resources):
            if not search_query:
                return resources
            filtered = []
            for res in resources:
                label = res.get("label", "").lower()
                url = res.get("url", "").lower()
                path = res.get("path", "").lower()
                if search_query in label or search_query in url or search_query in path:
                    filtered.append(res)
            return filtered
        
        filtered_lesson_res = filter_resources(lesson_only_res)
        filtered_course_res = filter_resources(course_only_res)
        
        # 清空并重建课时资源区域
        for w in self._lr_frame.winfo_children():
            w.destroy()
        
        if filtered_lesson_res:
            lr_host = ttk.Frame(self._lr_frame)
            lr_host.pack(fill=tk.X)
            self._lr_tree = ttk.Treeview(lr_host, columns=("icon", "name"), show="headings",
                                         height=3, selectmode="browse")
            self._lr_tree.heading("icon", text="")
            self._lr_tree.heading("name", text="资源名称")
            self._lr_tree.column("icon", width=30, anchor="center", stretch=False)
            self._lr_tree.column("name", width=300, stretch=True)
            lr_scroll = ttk.Scrollbar(lr_host, orient="vertical", command=self._lr_tree.yview)
            self._lr_tree.configure(yscrollcommand=lr_scroll.set)
            self._lr_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            lr_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            for res in filtered_lesson_res:
                icon = ResourceMgr.RESOURCE_ICONS.get(res.get("type"), "📎")
                name = res.get("label", "") or res.get("url", "") or res.get("path", "")
                self._lr_tree.insert("", "end", values=(icon, name))
            self._lr_tree.bind("<Double-Button-1>", lambda e: self._open_resource_from_tree(
                self._lr_tree, filtered_lesson_res, cid, "lesson"))
            self._lr_tree.selection_set(self._lr_tree.get_children()[0])
        else:
            ttk.Label(self._lr_frame, text="暂无课时级资源" if not search_query else "未找到匹配的课时资源",
                      style="Sub.TLabel", foreground="#95a5a6").pack(pady=3)
        
        lr_btn_frame = self._scrollable_button_bar(self._lr_frame)
        ttk.Button(lr_btn_frame, text="打开",
                  command=lambda: self._open_resource_from_tree(
                      self._lr_tree, filtered_lesson_res, cid, "lesson")).pack(side=tk.LEFT, padx=2)
        ttk.Button(lr_btn_frame, text="🔍 预览",
                  command=lambda: self._preview_resource_from_tree(
                      self._lr_tree, filtered_lesson_res, cid, "lesson")).pack(side=tk.LEFT, padx=2)
        ttk.Button(lr_btn_frame, text="📁 批量导入",
                  command=lambda: self._batch_import_lesson_files(cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(lr_btn_frame, text="🌐 链接/视频",
                  command=lambda: self._add_lesson_url(cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(lr_btn_frame, text="📋 智能粘贴URL",
                  command=lambda: self._smart_paste_resources(cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(lr_btn_frame, text="🗑️ 多选删除",
                  command=lambda: self._batch_delete_lesson_resources_exec(cid, lnum)).pack(side=tk.LEFT, padx=2)
        
        # 清空并重建课程资源区域
        for w in self._cr_frame.winfo_children():
            w.destroy()
        
        if filtered_course_res:
            cr_host = ttk.Frame(self._cr_frame)
            cr_host.pack(fill=tk.X)
            self._cr_tree = ttk.Treeview(cr_host, columns=("icon", "name"), show="headings",
                                         height=3, selectmode="browse")
            self._cr_tree.heading("icon", text="")
            self._cr_tree.heading("name", text="资源名称")
            self._cr_tree.column("icon", width=30, anchor="center", stretch=False)
            self._cr_tree.column("name", width=300, stretch=True)
            cr_scroll = ttk.Scrollbar(cr_host, orient="vertical", command=self._cr_tree.yview)
            self._cr_tree.configure(yscrollcommand=cr_scroll.set)
            self._cr_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            cr_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            for res in filtered_course_res:
                icon = ResourceMgr.RESOURCE_ICONS.get(res.get("type"), "📎")
                name = res.get("label", "") or res.get("url", "") or res.get("path", "")
                self._cr_tree.insert("", "end", values=(icon, name))
            self._cr_tree.bind("<Double-Button-1>", lambda e: self._open_resource_from_tree(
                self._cr_tree, filtered_course_res, cid, "course"))
            self._cr_tree.selection_set(self._cr_tree.get_children()[0])
        else:
            ttk.Label(self._cr_frame, text="暂无课程级资源" if not search_query else "未找到匹配的课程资源",
                      style="Sub.TLabel", foreground="#95a5a6").pack(pady=3)
        
        cr_btn_frame = self._scrollable_button_bar(self._cr_frame)
        ttk.Button(cr_btn_frame, text="打开",
                  command=lambda: self._open_resource_from_tree(
                      self._cr_tree, filtered_course_res, cid, "course")).pack(side=tk.LEFT, padx=2)
        ttk.Button(cr_btn_frame, text="🔍 预览",
                  command=lambda: self._preview_resource_from_tree(
                      self._cr_tree, filtered_course_res, cid, "course")).pack(side=tk.LEFT, padx=2)
        ttk.Button(cr_btn_frame, text="📁 批量导入",
                  command=lambda: self._batch_import_course_files_exec(cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(cr_btn_frame, text="🌐 链接/视频",
                  command=lambda: self._add_course_url_exec(cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(cr_btn_frame, text="📋 智能粘贴URL",
                  command=lambda: self._smart_paste_resources(cid, None)).pack(side=tk.LEFT, padx=2)
        ttk.Button(cr_btn_frame, text="🗑️ 多选删除",
                  command=lambda: self._batch_delete_course_resources_exec(cid, lnum)).pack(side=tk.LEFT, padx=2)

    def _open_resource_from_tree(self, tree, resource_list, course_id, res_type):
        if not resource_list:
            messagebox.showinfo("提示", "暂无资源可打开", parent=self.root)
            return
        if tree is None or not tree.selection():
            if len(resource_list) == 1:
                idx = 0
            else:
                messagebox.showinfo("提示", "请先在列表中选择一个资源", parent=self.root)
                return
        else:
            selection = tree.selection()
            if not selection:
                return
            idx = tree.index(selection[0])
        
        if idx < len(resource_list):
            res = resource_list[idx]
            res_name = res.get("label", "") or res.get("url", "") or res.get("path", "")
            lnum = getattr(self, '_exec_current_lnum', None)
            rtype = res.get("type", "url")
            if rtype in ("pdf", "image"):
                path_str = res.get("path", "")
                full_path = self._resolve_resource_path(path_str)
                if full_path.exists():
                    self.wflogger.log_open_resource(course_id, lnum, detail=f"打开{rtype} {res_name[:30]}")
                    if rtype == "image":
                        self._show_image_preview(full_path, res_name)
                    else:
                        open_file(str(full_path))
                else:
                    messagebox.showwarning("提示", f"文件不存在:\n{full_path}")
            elif rtype == "video":
                url = res.get("url", "")
                path = res.get("path", "")
                if path:
                    full_path = self._resolve_resource_path(path)
                    if full_path.exists():
                        self.wflogger.log_open_resource(course_id, lnum, detail=f"播放视频 {res_name[:30]}")
                        open_file(str(full_path))
                    else:
                        messagebox.showwarning("提示", f"文件不存在:\n{full_path}")
                elif url:
                    self.wflogger.log_open_resource(course_id, lnum, detail=f"播放视频 {res_name[:30]}")
                    webbrowser.open(url)
                else:
                    messagebox.showwarning("提示", "视频URL/路径为空")
            else:
                url = res.get("url", "")
                if url:
                    self.wflogger.log_open_resource(course_id, lnum, detail=f"打开链接 {res_name[:30]}")
                    webbrowser.open(url)
                else:
                    messagebox.showwarning("提示", "URL为空")

    def _preview_resource_from_tree(self, tree, resource_list, course_id, res_type):
        """从资源树中预览资源 - 在PDF预览tab中显示"""
        if not resource_list:
            messagebox.showinfo("提示", "暂无资源可预览", parent=self.root)
            return
        if tree is None or not tree.selection():
            if len(resource_list) == 1:
                idx = 0
            else:
                messagebox.showinfo("提示", "请先在列表中选择一个资源", parent=self.root)
                return
        else:
            selection = tree.selection()
            if not selection:
                return
            idx = tree.index(selection[0])
        
        if idx < len(resource_list):
            res = resource_list[idx]
            rtype = res.get("type", "url")
            if rtype == "pdf":
                path_str = res.get("path", "")
                fp = self._resolve_resource_path(path_str)
                
                # 刷新资源列表
                if hasattr(self, '_refresh_pdf_resource_list'):
                    self._refresh_pdf_resource_list()
                
                # 找到并选中这个PDF
                if hasattr(self, '_pdf_resource_map') and hasattr(self, '_pdf_resource_var'):
                    name = res.get("label", "") or path_str.split("/")[-1]
                    prefix = "[课时] " if res_type == "lesson" else "[课程] "
                    search_key = f"{prefix}{name}"
                    if search_key in self._pdf_resource_map:
                        self._pdf_resource_var.set(search_key)
                    else:
                        for k in self._pdf_resource_map.keys():
                            if name in k or k.endswith(name):
                                self._pdf_resource_var.set(k)
                                break
                    if hasattr(self, '_on_pdf_selected'):
                        self._on_pdf_selected()
                
                self.wflogger.log_action("preview_pdf", course_id, lnum, detail=str(fp)[:50])
            elif rtype == "image":
                path_str = res.get("path", "")
                full_path = self._resolve_resource_path(path_str)
                if full_path.exists():
                    res_name = res.get("label", "") or res.get("path", "")
                    lnum = getattr(self, '_exec_current_lnum', None)
                    self.wflogger.log_open_resource(course_id, lnum, detail=f"预览图片 {res_name[:30]}")
                    self._show_image_preview(full_path, res_name)
                else:
                    messagebox.showwarning("提示", f"文件不存在:\n{full_path}")
            else:
                # 非PDF/图片资源，用系统打开
                self._open_resource_from_tree(tree, resource_list, course_id, res_type)

    def _batch_delete_lesson_resources_exec(self, course_id, lesson_number):
        """执行模式：多选删除课时级资源，删除后刷新执行面板"""
        rmgr = self.system.rmgr
        all_res = rmgr.get_for_lesson(course_id, lesson_number)
        if not all_res:
            messagebox.showinfo("提示", f"课时 {lesson_number} 暂无资源")
            return

        course = self.system.get_course_by_id(course_id)
        course_title = course.get("course_title", course_id) if course else course_id
        self._do_resource_deletion_dlg(course_id, lesson_number, all_res,
                                       f"课时 {lesson_number} — {course_title}")

    def _batch_delete_course_resources_exec(self, course_id, lesson_number):
        """执行模式：多选删除课程级资源，删除后刷新执行面板"""
        rmgr = self.system.rmgr
        all_res = rmgr.get_for_course(course_id)
        if not all_res:
            messagebox.showinfo("提示", "该课程暂无课程级资源")
            return

        course = self.system.get_course_by_id(course_id)
        course_title = course.get("course_title", course_id) if course else course_id
        self._do_resource_deletion_dlg(course_id, lesson_number, all_res,
                                       f"课程级 — {course_title}")

    def _do_resource_deletion_dlg(self, course_id, refresh_lnum, all_res, title):
        """通用的多选删除弹窗 - TreeView 实现，支持 Ctrl/Shift 多选"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"🗑️ 多选删除资源 — {title}")
        dlg.geometry("750x550")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"🗑️ 选择要删除的资源（支持 Ctrl/Shift 多选）",
                  font=("", 12, "bold"), foreground="#c0392b").pack(pady=(10, 5))

        # TreeView 区域
        list_frame = ttk.Frame(dlg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(list_frame, selectmode='extended', columns=('icon', 'label'), show='headings')
        tree.heading('icon', text='')
        tree.heading('label', text='资源名称')
        tree.column('icon', width=40, anchor='center')
        tree.column('label', width=600)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        res_list = []
        for idx, res in enumerate(all_res):
            rt = res.get("type", "")
            label = res.get("label", "")
            icon = ResourceMgr.RESOURCE_ICONS.get(rt, "📎")
            tree.insert('', 'end', values=(icon, label))
            res_list.append(res)

        # 底部
        bottom = ttk.Frame(dlg)
        bottom.pack(fill=tk.X, padx=10, pady=10)

        selected_label = ttk.Label(bottom, text="已选 0 项")
        selected_label.pack(side=tk.LEFT, padx=10)

        def _update_count(*_):
            count = len(tree.selection())
            selected_label.config(text=f"已选 {count} 项")

        tree.bind('<<TreeviewSelect>>', _update_count)

        def _confirm_delete():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("提示", "未选择任何资源", parent=dlg)
                return
            if not messagebox.askyesno("确认删除", f"确定要删除 {len(selection)} 个资源吗？\n此操作不可撤销。", parent=dlg):
                return
            deleted = 0
            for item in selection:
                idx = tree.index(item)
                res = res_list[idx]
                if self.system.rmgr.remove(course_id, res):
                    deleted += 1
            messagebox.showinfo("删除完成", f"已删除 {deleted} 个资源", parent=self.root)
            dlg.destroy()
            self._refresh_exec_panel(course_id, refresh_lnum)

        ttk.Button(bottom, text="🗑️ 确认删除", command=_confirm_delete).pack(side=tk.RIGHT, padx=10)
        ttk.Button(bottom, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=5)

    def _show_image_preview(self, image_path, title=""):
        dlg = tk.Toplevel(self.root)
        dlg.title(f"🖼️ {title or image_path.name}")
        dlg.geometry("800x600")
        dlg.transient(self.root)
        try:
            from PIL import Image, ImageTk
            img = Image.open(str(image_path))
            img.thumbnail((780, 580), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = ttk.Label(dlg, image=photo)
            lbl.image = photo
            lbl.pack(fill=tk.BOTH, expand=True)
        except ImportError:
            try:
                import tkinter as _tk
                photo = _tk.PhotoImage(file=str(image_path))
                lbl = ttk.Label(dlg, image=photo)
                lbl.image = photo
                lbl.pack(fill=tk.BOTH, expand=True)
            except Exception:
                open_file(str(image_path))
                dlg.destroy()
                return
        except Exception:
            open_file(str(image_path))
            dlg.destroy()
            return
        ttk.Button(dlg, text="用系统程序打开",
                   command=lambda: open_file(str(image_path))).pack(pady=5)

    def _build_quick_notes(self, parent, cid, lnum):
        """构建课时级日志流 - 捕捉各类事件，支持批注和搜索"""
        note_frame = ttk.LabelFrame(parent, text="课时日志", padding=5)
        note_frame.pack(fill=tk.BOTH, expand=True)

        # 搜索栏
        search_frame = ttk.Frame(note_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="🔍 搜索：", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._log_search_var = tk.StringVar()
        self._log_search_var.trace_add("write", lambda *args: self._refresh_filtered_logs(cid, lnum))
        log_search_entry = ttk.Entry(search_frame, textvariable=self._log_search_var)
        log_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(search_frame, text="清除", width=8,
                   command=lambda: (self._log_search_var.set(""), log_search_entry.focus())).pack(side=tk.RIGHT)

        # 输入区：输入内容自动判断是笔记还是批注
        input_frame = ttk.Frame(note_frame)
        input_frame.pack(fill=tk.X, pady=(0, 5))

        self.note_entry = ttk.Entry(input_frame, font=("", 14))
        self.note_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=3)
        self.note_entry.insert(0, "选中事件后可追加批注，直接回车添加笔记...")
        self.note_entry.bind('<FocusIn>', lambda e: self._on_note_entry_focus(e, True))
        self.note_entry.bind('<FocusOut>', lambda e: self._on_note_entry_focus(e, False))
        self.note_entry.bind('<Return>', lambda e: self._submit_log_input(cid, lnum))

        ttk.Button(input_frame, text="📌",width=4,
                  command=lambda: self._submit_log_input(cid, lnum)).pack(side=tk.RIGHT,padx=(0, 1))
        ttk.Button(input_frame, text="批注",width=4,
                  command=lambda: self._annotate_selected(cid, lnum)).pack(side=tk.RIGHT)

        # 日志列表 - 课时级，三列：时间/事件/批注
        columns = ("time", "event", "annotation")
        self.note_tree = ttk.Treeview(note_frame, columns=columns, show="headings",
                                       height=15, selectmode="browse")
        self.note_tree.heading("time", text="累计")
        self.note_tree.heading("event", text="事件")
        self.note_tree.heading("annotation", text="批注")
        self.note_tree.column("time", width=65, anchor="center", stretch=False)
        self.note_tree.column("event", width=160, stretch=True)
        self.note_tree.column("annotation", width=80, stretch=True)

        self.note_tree.configure(style="Log.Treeview")

        # 颜色标签
        self.note_tree.tag_configure("timer_start", foreground="#2e7d32", font=("", 15, "bold"))
        self.note_tree.tag_configure("timer_stop", foreground="#1565c0", font=("", 15, "bold"))
        self.note_tree.tag_configure("action", foreground="#6a1b9a")
        self.note_tree.tag_configure("note", foreground="#e65100", font=("", 16))
        self.note_tree.tag_configure("blur", foreground="#9e9e9e",font=("", 9, "bold"))
        self.note_tree.tag_configure("focus_return", foreground="#00838f",font=("", 9, "bold"))
        self.note_tree.tag_configure("lesson_complete", foreground="#c62828")
        self.note_tree.tag_configure("open_note", foreground="#00695c")
        self.note_tree.tag_configure("open_resource", foreground="#4e342e")

        # 右键菜单：批注/删除批注
        self._log_menu = tk.Menu(self.note_tree, tearoff=0)
        self._log_menu.add_command(label="添加批注", command=lambda: self._annotate_selected(cid, lnum))
        self._log_menu.add_command(label="清除批注", command=lambda: self._clear_annotation(cid, lnum))
        self.note_tree.bind("<Button-3>", lambda e: self._show_log_menu(e))

        note_scroll = ttk.Scrollbar(note_frame, orient="vertical", command=self.note_tree.yview)
        self.note_tree.configure(yscrollcommand=note_scroll.set)

        self.note_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        note_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 批注存储：entry index -> annotation
        self._log_annotations = {}
        # 已显示的日志条目数，用于增量刷新
        self._log_displayed_count = 0

        self._load_notes_for_lesson(cid, lnum)
        self._start_log_refresh(cid, lnum)

    def _get_lesson_title(self, course_id, lesson_num):
        """获取课时标题"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            return ""
        lessons = course.get("lessons", [])
        for l in lessons:
            if l.get("lesson_number") == lesson_num:
                return l.get("lesson_title", "")
        return ""

    def _build_lesson_code_panel(self, parent, cid, lnum):
        """构建课时代码与资源管理面板（含子 Notebook）"""
        course = self.system.get_course_by_id(cid)
        course_title = course.get("course_title", "未知课程") if course else "未知课程"
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', course_title)[:40]
        lesson_title = self._get_lesson_title(cid, lnum)
        safe_lesson_title = re.sub(r'[\\/:*?"<>|]', '_', lesson_title)[:40] or f"L{lnum:04d}"
        lesson_code_dir = BASE / "Notes" / safe_title / safe_lesson_title
        lesson_code_dir.mkdir(parents=True, exist_ok=True)
        self._current_lesson_code_dir = lesson_code_dir  # 保存引用

        sub_nb = ttk.Notebook(parent)
        sub_nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 1. 文件管理标签
        files_tab = ttk.Frame(sub_nb)
        sub_nb.add(files_tab, text="📁 文件管理")
        self._build_code_files_tab(files_tab, lesson_code_dir, cid, lnum)
        
        # 2. 实验开发技术文档标签
        docs_tab = ttk.Frame(sub_nb)
        sub_nb.add(docs_tab, text="📝 实验开发技术文档")
        self._build_dev_docs_tab(docs_tab, lesson_code_dir, cid, lnum)
    
    def _build_code_files_tab(self, parent, lesson_code_dir, cid, lnum):
        """构建程序实验的文件管理子标签页"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        header = ttk.LabelFrame(main_frame, text="📁 代码目录", padding=8)
        header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(header, text=f"路径: {lesson_code_dir.relative_to(BASE)}",
                  font=("", 8), foreground="#7F8C8D").pack(anchor="w")

        btn_canvas = tk.Canvas(header, height=32, highlightthickness=0, bg="#f0f0f0")
        btn_scroll = ttk.Scrollbar(header, orient="horizontal", command=btn_canvas.xview)
        btn_canvas.configure(xscrollcommand=btn_scroll.set)
        btn_scroll.pack(fill=tk.X, pady=(5, 0))
        btn_canvas.pack(fill=tk.X)

        btn_frame = ttk.Frame(btn_canvas)
        btn_canvas.create_window((0, 0), window=btn_frame, anchor="nw")
        btn_frame.bind("<Configure>", lambda e: btn_canvas.configure(scrollregion=btn_canvas.bbox("all")))

        def _scroll_btn(dx):
            btn_canvas.xview_scroll(dx, "units")

        ttk.Button(btn_frame, text="📂 打开空间", width=10,
                   command=lambda: open_file(str(lesson_code_dir))).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="➕ 新建程序", width=10,
                   command=lambda: self._create_new_code_file(lesson_code_dir, cid, lnum)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔬 打开编辑器", width=10,
                   command=lambda: self._open_in_positron(lesson_code_dir)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="◀", width=3,
                   command=lambda: _scroll_btn(-3)).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btn_frame, text="▶", width=3,
                   command=lambda: _scroll_btn(3)).pack(side=tk.LEFT)

        file_list = ttk.LabelFrame(main_frame, text="📄 文件列表", padding=5)
        file_list.pack(fill=tk.BOTH, expand=True)

        self._code_file_canvas = tk.Canvas(file_list, highlightthickness=0)
        scrollbar = ttk.Scrollbar(file_list, orient="vertical", command=self._code_file_canvas.yview)
        self._code_scroll_frame = ttk.Frame(self._code_file_canvas)
        self._code_scroll_frame.bind("<Configure>",
            lambda e: self._code_file_canvas.configure(scrollregion=self._code_file_canvas.bbox("all")))
        self._code_file_canvas.create_window((0, 0), window=self._code_scroll_frame,
                                              anchor="nw", tags=("scroll_win",))
        self._code_file_canvas.bind("<Configure>", self._on_code_canvas_configure)
        self._code_file_canvas.configure(yscrollcommand=scrollbar.set)
        self._code_file_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_code_file_list(self._code_scroll_frame, lesson_code_dir)
    
    def _build_dev_docs_tab(self, parent, lesson_code_dir, cid, lnum):
        """构建实验开发技术文档编辑器 — 参考笔记编辑器的实现方法"""
        self._current_dev_docs_dir = lesson_code_dir
        self._current_dev_cid = cid
        self._current_dev_lnum = lnum
        self._current_doc_path = None  # 当前选中/编辑的文档
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # === 上部分：文件选择区 ===
        file_frame = ttk.LabelFrame(main_frame, text="📄 文档文件选择", padding=8)
        file_frame.pack(fill=tk.X, pady=(0, 8))
        
        file_list_frame = ttk.Frame(file_frame)
        file_list_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(file_list_frame, text="文档列表：").pack(side=tk.LEFT, padx=(0, 5))
        
        self._dev_doc_var = tk.StringVar()
        self._dev_doc_combo = ttk.Combobox(file_list_frame, textvariable=self._dev_doc_var, 
                                           state="readonly", width=40)
        self._dev_doc_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self._dev_doc_combo.bind("<<ComboboxSelected>>", self._on_dev_doc_selected)
        
        # 文件操作按钮
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="📁 新建文档", width=15, 
                   command=self._create_new_dev_doc).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🎨 从模板新建", width=15, 
                   command=self._create_dev_doc_from_template).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📂 外部打开", width=15, 
                   command=self._open_current_dev_doc_external).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 删除", width=10, 
                   command=self._delete_current_dev_doc).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔄 刷新", width=10, 
                   command=self._refresh_dev_doc_list).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))
        
        # === 下部分：编辑器 ===
        editor_frame = ttk.LabelFrame(main_frame, text="✏️ 文档编辑器", padding=8)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # 编辑器工具栏
        toolbar = self._scrollable_button_bar(editor_frame)
        ttk.Button(toolbar, text="💾 保存",
                   command=self._save_dev_doc).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📁 目录",
                   command=lambda: open_file(str(lesson_code_dir))).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        ttk.Button(toolbar, text="🖼️ 插图",
                   command=self._insert_image_to_dev_doc).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💻 代码块",
                   command=lambda: self._insert_template_to_dev_doc("code")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📐 公式",
                   command=lambda: self._insert_template_to_dev_doc("math")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📋 链接",
                   command=lambda: self._insert_template_to_dev_doc("link")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📊 表格",
                   command=lambda: self._insert_template_to_dev_doc("table")).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        ttk.Button(toolbar, text="📌 标题",
                   command=lambda: self._wrap_selection_with("# ")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💡 列表",
                   command=lambda: self._wrap_selection_with("- ")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✅ 粗体",
                   command=lambda: self._wrap_selection_with("**", "**")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✳️ 斜体",
                   command=lambda: self._wrap_selection_with("*", "*")).pack(side=tk.LEFT, padx=2)
        
        # 编辑区
        text_frame = ttk.Frame(editor_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        
        self._dev_doc_editor = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10),
                                       undo=True, maxundo=50,
                                       insertbackground="#2c3e50", selectbackground="#3498db",
                                       selectforeground="white", relief="flat", bg="#FAFAFA",
                                       padx=8, pady=6)
        dev_doc_scroll = ttk.Scrollbar(text_frame, orient="vertical", 
                                      command=self._dev_doc_editor.yview)
        self._dev_doc_editor.configure(yscrollcommand=dev_doc_scroll.set)
        self._dev_doc_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dev_doc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 语法高亮标签
        self._dev_doc_editor.tag_configure("heading", foreground="#2c3e50", 
                                           font=("Consolas", 11, "bold"))
        self._dev_doc_editor.tag_configure("heading2", foreground="#34495e", 
                                           font=("Consolas", 10, "bold"))
        self._dev_doc_editor.tag_configure("code_block", foreground="#27ae60", 
                                           font=("Consolas", 10))
        self._dev_doc_editor.tag_configure("code_delim", foreground="#95a5a6", 
                                           font=("Consolas", 10, "bold"))
        self._dev_doc_editor.tag_configure("math_block", foreground="#c0392b", 
                                           font=("Consolas", 10))
        self._dev_doc_editor.tag_configure("bold", foreground="#2c3e50", 
                                           font=("Consolas", 10, "bold"))
        self._dev_doc_editor.tag_configure("italic", foreground="#7f8c8d")
        self._dev_doc_editor.tag_configure("link", foreground="#2980b9", underline=True)
        self._dev_doc_editor.tag_configure("blockquote", foreground="#7f8c8d", 
                                           font=("Consolas", 10, "italic"))
        self._dev_doc_editor.tag_configure("list_item", foreground="#8e44ad")
        
        # 状态栏
        status_frame = ttk.Frame(editor_frame)
        status_frame.pack(fill=tk.X, pady=(5, 0))
        self._dev_doc_status = ttk.Label(status_frame, text="📄 请选择或新建文档",
                                        font=("", 8), foreground="#95a5a6")
        self._dev_doc_status.pack(side=tk.LEFT)
        
        # 快捷键绑定
        self._dev_doc_editor.bind("<Control-s>", lambda e: self._save_dev_doc())
        self._dev_doc_editor.bind("<Control-b>", 
                                  lambda e: self._wrap_selection_with("**", "**"))
        self._dev_doc_editor.bind("<Control-i>", 
                                  lambda e: self._wrap_selection_with("*", "*"))
        self._dev_doc_editor.bind("<KeyRelease>", 
                                  lambda e: self._schedule_dev_doc_highlight())
        
        # 自动保存
        self._dev_doc_auto_save_timer = None
        self._dev_doc_editor.bind("<<Modified>>", self._on_dev_doc_modified)
        
        # 初始化文件列表
        self._refresh_dev_doc_list()
    
    def _refresh_dev_doc_list(self):
        """刷新文档文件列表"""
        if not hasattr(self, "_dev_doc_combo"):
            return
        
        doc_dir = self._current_dev_docs_dir
        if not doc_dir.exists():
            self._dev_doc_combo["values"] = []
            self._dev_doc_var.set("")
            return
        
        doc_extensions = [".md", ".Rmd", ".txt", ".tex"]
        doc_files = []
        try:
            for f in doc_dir.iterdir():
                if f.is_file() and f.suffix in doc_extensions:
                    doc_files.append(f)
        except Exception:
            pass
        
        doc_files.sort(key=lambda f: f.name)
        self._dev_doc_files = doc_files
        self._dev_doc_combo["values"] = [f.name for f in doc_files]
        
        if doc_files:
            # 尝试保持当前选择
            current_name = self._dev_doc_var.get()
            if current_name in [f.name for f in doc_files]:
                pass  # 保持
            else:
                self._dev_doc_var.set(doc_files[0].name)
                self._on_dev_doc_selected()
        else:
            self._dev_doc_var.set("")
            self._dev_doc_editor.delete("1.0", tk.END)
            self._dev_doc_status.config(text="📄 暂无文档，请新建或从模板创建", 
                                       foreground="#95a5a6")
    
    def _on_dev_doc_selected(self, event=None):
        """文档选择变化时加载内容"""
        name = self._dev_doc_var.get()
        if not name:
            self._current_doc_path = None
            self._dev_doc_editor.delete("1.0", tk.END)
            self._dev_doc_status.config(text="📄 请选择文档", foreground="#95a5a6")
            return
        
        for f in self._dev_doc_files:
            if f.name == name:
                self._current_doc_path = f
                try:
                    content = f.read_text(encoding="utf-8")
                    self._dev_doc_editor.delete("1.0", tk.END)
                    self._dev_doc_editor.insert("1.0", content)
                    self._dev_doc_status.config(text=f"📄 {name}", foreground="#7f8c8d")
                    self._apply_dev_doc_highlighting()
                except Exception as e:
                    self._dev_doc_status.config(text=f"❌ 读取失败: {e}", foreground="#c0392b")
                return
    
    def _create_new_dev_doc(self):
        """新建空白文档"""
        filename = simpledialog.askstring("新建文档", "请输入文档文件名（不含后缀）:",
                                        initialvalue="新文档.md")
        if not filename:
            return
        
        if not (filename.endswith(".md") or filename.endswith(".Rmd") or 
                filename.endswith(".txt") or filename.endswith(".tex")):
            filename += ".md"
        
        file_path = self._current_dev_docs_dir / filename
        if file_path.exists():
            if not messagebox.askyesno("文件存在", f"{filename} 已存在，是否覆盖？"):
                return
        
        try:
            file_path.write_text("# 新文档\n\n在此处开始编写...\n", encoding="utf-8")
            self._refresh_dev_doc_list()
            self._dev_doc_var.set(filename)
            self._on_dev_doc_selected()
        except Exception as e:
            messagebox.showerror("错误", f"创建文档失败: {e}")
    
    def _create_dev_doc_from_template(self):
        """从模板新建文档"""
        dlg = tk.Toplevel(self.root)
        dlg.title("📚 选择文档模板")
        dlg.geometry("500x400")
        dlg.transient(self.root)
        dlg.grab_set()
        
        ttk.Label(dlg, text="请选择要使用的文档模板：", 
                  font=("", 11, "bold")).pack(pady=(15, 10), padx=15)
        
        template_var = tk.StringVar(value="technical")
        
        ttk.Radiobutton(dlg, text="🏭 技术设计文档（工业级）", 
                      variable=template_var, value="technical").pack(anchor="w", 
                                                                     padx=30, pady=3)
        ttk.Radiobutton(dlg, text="📖 教程编写（通用）", 
                      variable=template_var, value="tutorial").pack(anchor="w", 
                                                                   padx=30, pady=3)
        ttk.Radiobutton(dlg, text="📝 实验报告", 
                      variable=template_var, value="report").pack(anchor="w", 
                                                                  padx=30, pady=3)
        ttk.Radiobutton(dlg, text="📓 学习笔记", 
                      variable=template_var, value="notes").pack(anchor="w", 
                                                                  padx=30, pady=3)
        
        ttk.Label(dlg, text="\n文件名：").pack(anchor="w", padx=30, pady=(10, 0))
        
        filename_var = tk.StringVar(value=f"L{self._current_dev_lnum:04d}_技术文档")
        ttk.Entry(dlg, textvariable=filename_var, width=50).pack(padx=30, pady=5)
        
        def do_create():
            template = template_var.get()
            filename = filename_var.get()
            if not filename:
                return
            
            if not filename.endswith(".md"):
                filename += ".md"
            
            file_path = self._current_dev_docs_dir / filename
            if file_path.exists():
                if not messagebox.askyesno("文件存在", f"{filename} 已存在，是否覆盖？", parent=dlg):
                    return
            
            course = self.system.get_course_by_id(self._current_dev_cid)
            lesson_title = self._get_lesson_title(self._current_dev_cid, 
                                                 self._current_dev_lnum)
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            
            try:
                content = self._get_dev_doc_template(template, course, 
                                                   lesson_title, self._current_dev_lnum, today)
                file_path.write_text(content, encoding="utf-8")
                self._refresh_dev_doc_list()
                self._dev_doc_var.set(filename)
                self._on_dev_doc_selected()
                dlg.destroy()
                messagebox.showinfo("成功", f"文档已创建：\n{filename}")
            except Exception as e:
                messagebox.showerror("错误", f"创建文档失败: {e}")
        
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="✅ 创建", width=15, 
                   command=do_create).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", width=10, 
                   command=dlg.destroy).pack(side=tk.LEFT, padx=5)
    
    def _get_dev_doc_template(self, template_type, course, lesson_title, lnum, today):
        """获取文档模板内容"""
        course_name = course.get("course_title", "未知课程") if course else "未知课程"
        
        if template_type == "technical":
            return self._get_technical_doc_template(course, lesson_title, lnum, today)
        elif template_type == "tutorial":
            return self._get_tutorial_template(course, lesson_title, lnum, today)
        elif template_type == "report":
            return self._get_experiment_report_template(course, lesson_title, lnum, today)
        else:
            return self._get_study_notes_template(course, lesson_title, lnum, today)
    
    def _open_current_dev_doc_external(self):
        """在外部编辑器打开当前文档"""
        if not self._current_doc_path or not self._current_doc_path.exists():
            messagebox.showinfo("提示", "请先选择一个文档")
            return
        self._open_file_with_positron(self._current_doc_path)
    
    def _delete_current_dev_doc(self):
        """删除当前选中的文档"""
        if not self._current_doc_path:
            messagebox.showinfo("提示", "请先选择要删除的文档")
            return
        
        if messagebox.askyesno("确认删除", f"确定要删除 {self._current_doc_path.name} 吗？"):
            try:
                self._current_doc_path.unlink()
                self._refresh_dev_doc_list()
            except Exception as e:
                messagebox.showerror("错误", f"删除失败: {e}")
    
    def _save_dev_doc(self):
        """保存当前文档"""
        if not self._current_doc_path:
            messagebox.showinfo("提示", "请先选择一个文档")
            return
        
        try:
            content = self._dev_doc_editor.get("1.0", tk.END)
            self._current_doc_path.write_text(content, encoding="utf-8")
            self._dev_doc_status.config(
                text=f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}", 
                foreground="#27ae60")
        except Exception as e:
            self._dev_doc_status.config(text=f"❌ 保存失败: {e}", foreground="#c0392b")
    
    def _on_dev_doc_modified(self, event=None):
        """文档内容修改时触发自动保存（3秒延迟）"""
        if not hasattr(self, "_dev_doc_auto_save_timer"):
            return
        
        if self._dev_doc_auto_save_timer:
            self.root.after_cancel(self._dev_doc_auto_save_timer)
        
        self._dev_doc_auto_save_timer = self.root.after(3000, self._auto_save_dev_doc)
        
        if self._current_doc_path:
            self._dev_doc_status.config(text=f"📝 {self._current_doc_path.name} (已修改...)", 
                                       foreground="#f39c12")
    
    def _auto_save_dev_doc(self):
        """自动保存"""
        self._dev_doc_auto_save_timer = None
        if self._current_doc_path:
            self._save_dev_doc()
    
    def _insert_image_to_dev_doc(self):
        """插入图片到文档"""
        if not self._current_doc_path:
            messagebox.showinfo("提示", "请先选择一个文档")
            return
        
        file_path = filedialog.askopenfilename(title="选择图片", 
                                               filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.svg")])
        if file_path:
            import shutil
            image_name = Path(file_path).name
            images_dir = self._current_doc_path.parent / "images"
            images_dir.mkdir(exist_ok=True)
            dest_path = images_dir / image_name
            shutil.copy(file_path, dest_path)
            
            md_text = f"\n![{image_name}](images/{image_name})\n"
            self._dev_doc_editor.insert(tk.INSERT, md_text)
    
    def _insert_template_to_dev_doc(self, tpl_type):
        """插入预定义模板到文档"""
        templates = {
            "code": "\n```\n# 在此编写代码\n\n```\n",
            "math": "\n$$\n% 在此编写公式\n\n$$\n",
            "link": "[链接文字](https://example.com)",
            "table": "\n| 列1 | 列2 | 列3 |\n|-----|-----|-----|\n| A | B | C |\n| D | E | F |\n"
        }
        
        if tpl_type in templates:
            self._dev_doc_editor.insert(tk.INSERT, templates[tpl_type])
    
    def _wrap_selection_with(self, prefix, suffix=None):
        """在选中文本周围包裹内容"""
        try:
            sel = self._dev_doc_editor.get(tk.SEL_FIRST, tk.SEL_LAST)
            if suffix is None:
                self._dev_doc_editor.replace(tk.SEL_FIRST, tk.SEL_LAST, prefix + sel)
            else:
                self._dev_doc_editor.replace(tk.SEL_FIRST, tk.SEL_LAST, prefix + sel + suffix)
        except tk.TclError:
            # 没有选中文本，只插入前缀
            if suffix is None:
                self._dev_doc_editor.insert(tk.INSERT, prefix)
            else:
                self._dev_doc_editor.insert(tk.INSERT, prefix + suffix)
                # 移动光标到中间
                self._dev_doc_editor.mark_set(tk.INSERT, 
                                             f"{tk.INSERT}-{len(suffix)}c")
    
    def _schedule_dev_doc_highlight(self):
        """调度语法高亮"""
        if hasattr(self, "_dev_doc_highlight_timer"):
            try:
                self.root.after_cancel(self._dev_doc_highlight_timer)
            except:
                pass
        self._dev_doc_highlight_timer = self.root.after(300, 
                                                       self._apply_dev_doc_highlighting)
    
    def _apply_dev_doc_highlighting(self):
        """应用语法高亮（简化版）"""
        if not hasattr(self, "_dev_doc_editor") or not self._dev_doc_editor.winfo_exists():
            return
        
        te = self._dev_doc_editor
        for tag in ("heading", "heading2", "code_block", "code_delim", 
                   "math_block", "bold", "italic", "link", "blockquote", "list_item"):
            te.tag_remove(tag, "1.0", tk.END)
        
        content = te.get("1.0", tk.END)
        lines = content.split('\n')
        in_code = False
        code_start = 0
        
        for i, line in enumerate(lines):
            li = i + 1
            stripped = line.strip()
            
            if stripped.startswith('```'):
                te.tag_add("code_delim", f"{li}.0", f"{li}.end")
                if in_code:
                    in_code = False
                    te.tag_add("code_block", f"{code_start}.0", f"{li}.end")
                else:
                    in_code = True
                    code_start = li
                continue
            
            if in_code:
                continue
            
            if stripped.startswith('$$'):
                te.tag_add("math_block", f"{li}.0", f"{li}.end")
                continue
            
            if stripped.startswith('# ') and not stripped.startswith('## '):
                te.tag_add("heading", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('## ') and not stripped.startswith('### '):
                te.tag_add("heading2", f"{li}.0", f"{li}.end")
                continue
            
            if stripped.startswith('> '):
                te.tag_add("blockquote", f"{li}.0", f"{li}.end")
                continue
            
            if re.match(r'^\s*[-*]\s', line):
                te.tag_add("list_item", f"{li}.0", f"{li}.end")
                continue
    
    def _get_technical_doc_template(self, course, lesson_title, lnum, today):
        """获取严谨工业级开发技术文档模板内容"""
        course_name = course.get("course_title", "未知课程") if course else "未知课程"
        return f"""# 技术设计说明书（Technical Design Document）

| **文档编号**   | TDD-{course_name.replace(' ', '')[:10]}-{lnum:04d} | **版本**     | V1.0 |
| -------------- | ------------------------------------------------- | ------------ | ---- |
| **项目名称**   | {course_name} | **密级**     | 内部 |
| **子系统名称** | {lesson_title} | **总页数**   | [XX] |
| **编制人**     | [姓名] | **审核人**   | [姓名] |
| **批准人**     | [姓名] | **生效日期** | {today} |

---

## 修订记录

| 版本号 | 日期       | 修订人 | 变更内容摘要 | 审核人 |
| ------ | ---------- | ------ | ------------ | ------ |
| V1.0   | {today} | [姓名] | 初始发布     | [姓名] |

---

## 1. 范围与目的

### 1.1 范围
本文档适用于{course_name}的{lesson_title}开发阶段，涵盖[功能模块/硬件单元]的需求分解、架构设计、接口定义、安全机制及测试准则。

### 1.2 目的
- 为开发人员提供明确、无歧义的技术实现依据
- 为测试团队提供功能验证与接口验证的基线
- 为维护人员提供系统行为与配置参数的权威参考

### 1.3 适用对象
[开发工程师 / 测试工程师 / 系统集成工程师 / 运维工程师]

---

## 2. 引用与术语

### 2.1 引用文件
| 文件编号 | 文件名称 | 版本 | 来源 |
| -------- | -------- | ---- | ---- |
|          |          |      |      |

### 2.2 术语与缩略语
| 术语/缩写 | 解释 |
| --------- | ---- |
|           |      |

---

## 3. 系统架构概述

### 3.1 逻辑架构图
[此处插入框图] 描述模块划分、数据流向、控制依赖关系。

### 3.2 物理拓扑
描述板卡/机柜/端子排/总线连接方式。
关键硬件部件：CPU型号、通信接口（RS485/CAN/以太网）、I/O数量、电源范围。

### 3.3 设计约束
- 实时性要求：任务周期 ≤ [XX] ms
- 工作环境：温度 [-40℃, +85℃] / 湿度 5% ~ 95% (无凝露)
- 供电容差：DC 24V ± 20%
- 安全完整性等级（如适用）：SIL 2 / PL d

---

## 4. 功能与接口设计（核心章节）

### 4.1 功能分解
| 功能ID | 功能名称 | 输入源 | 输出目标 | 触发条件 | 响应时间上限 |
| ------ | -------- | ------ | -------- | -------- | ------------ |
| F-01   |          |        |          |          |              |

### 4.2 外部接口定义
#### 4.2.1 通信接口
| 接口名称 | 物理层 | 协议 | 数据格式 | 角色（主/从） | 帧周期 |
| -------- | ------ | ---- | -------- | ------------- | ------ |
|          |        |      |          |               |        |

#### 4.2.2 硬件接口定义
| 信号名 | 端子号 | 类型 | 电气规格 | 功能描述 |
| ------ | ------ | ---- | -------- | -------- |
|        |        |      |          |          |

### 4.3 内部接口与数据结构
- 关键全局变量命名规则：[模块前缀]_[变量名]_[单位后缀]
- 消息队列定义：消息ID、优先级、数据长度（字节对齐规则）

---

## 5. 行为与状态设计（工业逻辑）

### 5.1 状态机（FSM）
[此处定义状态图]

状态转移表：
| 当前状态 | 事件 | 动作 | 下一状态 |
| -------- | ---- | ---- | -------- |
|          |      |      |          |

### 5.2 故障码表
| 故障码 | 描述 | 恢复方式 | 关联SIL等级 |
| ------ | ---- | -------- | ----------- |
|        |      |          |             |

---

## 6. 安全性、可靠性设计

### 6.1 安全机制
- 冗余设计：关键输出（急停、安全继电器）采用双通道互检
- 看门狗：独立外置看门狗，最大喂狗周期 200 ms
- 数据校验：Flash存储区使用CRC-32，参数校验失败则恢复出厂值

### 6.2 可靠性指标（预计/实测）
| 指标 | 目标值 |
| ---- | ------ |
| MTBF | ≥ 50,000 小时 |
| 上电自检覆盖率 | > 97% (注入测试) |
| ESD 接触放电 | ±8 kV (性能判据A) |

---

## 7. 测试与验证准则

### 7.1 单元/集成测试要点
- 每个功能ID至少对应一个正向测试用例和一个边界/异常测试用例
- 时序测试：使用示波器/逻辑分析仪验证最坏情况下的响应时间

### 7.2 型式试验参考标准
- [列出相关标准]

### 7.3 验收判定
- 所有强制功能测试通过率 100%
- 无A类、B类缺陷

---

## 8. 配置与交付物

### 8.1 软件/固件配置
- 编译工具链：[工具名称]
- 烧录文件格式：[格式]
- 参数分区表：偏移地址、默认值、写保护区域

### 8.2 物理交付清单
- 原理图PDF + 源文件
- BOM表（含MPN、替代物料等级）
- 固件二进制文件 + 校验值MD5
- 调试日志接口说明

---

## 9. 附录

### 9.1 时序图示例（Mermaid）
```mermaid
sequenceDiagram
    [在此插入时序图]
```

### 9.2 寄存器映射表
| 地址（十进制） | 读写 | 数据类型 | 描述 | 单位/系数 |
| -------------- | ---- | -------- | ---- | --------- |
|                |      |          |      |           |

---

## 10. 文档一致性声明

本人（编制人）确认本技术文档内容与当前开发基线一致。任何后续变更须遵循项目配置管理流程，更新本文档版本。

**签字：** _______________ **日期：** _______________
"""
    
    def _get_tutorial_template(self, course, lesson_title, lnum, today):
        """获取通用教程编写模板内容"""
        course_name = course.get("course_title", "未知课程") if course else "未知课程"
        return f"""# 教程：{lesson_title}

## 课程信息
- **课程名称**：{course_name}
- **课时编号**：L{lnum:04d}
- **创建日期**：{today}
- **目标读者**：[填写目标读者，如：初中级学员]
- **预计学习时长**：[填写预计时长，如：45分钟]

---

## 1. 概述

### 1.1 为什么学习这个？
[描述学习本教程的意义和价值]

### 1.2 你将学到什么
- 核心概念 1
- 核心概念 2
- 实际应用技巧
- 常见问题解决方案

### 1.3 前置知识
- [列出必要的前置知识]
- [列出必要的前置知识]

---

## 2. 核心概念讲解

### 2.1 概念名称
**定义**
[清晰简洁地给出定义]

**关键点**
- 要点 1
- 要点 2

**示例代码**
```python
# 示例代码
```

### 2.2 概念名称 2
[同上格式]

---

## 3. 实际动手

### 3.1 简单练习
[题目内容]

### 3.2 进阶挑战
[题目内容]

### 3.3 完整案例
[完整案例讲解]

---

## 4. 常见问题

| 问题 | 答案 |
|------|------|
| [问题1] | [回答1] |
| [问题2] | [回答2] |

---

## 5. 总结与延伸

### 5.1 要点回顾
- 回顾点 1
- 回顾点 2

### 5.2 延伸学习
- [推荐阅读 1]
- [推荐阅读 2]

---

## 附录

### A. 完整代码
[完整代码]
"""
    
    def _get_experiment_report_template(self, course, lesson_title, lnum, today):
        """获取实验报告模板内容"""
        course_name = course.get("course_title", "未知课程") if course else "未知课程"
        return f"""# 实验报告：{lesson_title}

## 基本信息
- **课程名称**：{course_name}
- **实验编号**：L{lnum:04d}
- **学生姓名**：[填写姓名]
- **实验日期**：{today}
- **同组人员**：[填写同组人员]

---

## 一、实验目的
[填写实验目的]

## 二、实验原理
[描述实验原理]

## 三、实验环境
- **操作系统**：[填写操作系统]
- **软件版本**：[填写软件版本]
- **硬件配置**：[填写硬件配置]

## 四、实验步骤
### 4.1 步骤一
[步骤内容]

### 4.2 步骤二
[步骤内容]

## 五、实验结果
### 5.1 数据记录
[数据]

### 5.2 图表
[图表]

## 六、结果分析
[分析结果]

## 七、实验结论
[结论]

## 八、问题与讨论
[问题与讨论]
"""
    
    def _get_study_notes_template(self, course, lesson_title, lnum, today):
        """获取学习笔记模板内容"""
        course_name = course.get("course_title", "未知课程") if course else "未知课程"
        return f"""# 学习笔记：{lesson_title}

## 基本信息
- **课程**：{course_name}
- **时间**：{today}
- **笔记作者**：[填写姓名]

---

## 重要概念
- [概念1]：[简要解释]
- [概念2]：[简要解释]

## 关键要点
### 1. [标题]
[内容]

### 2. [标题]
[内容]

## 笔记区
在此自由记录学习过程中的想法、疑问和感悟...

## 遗留问题
- [问题1]
- [问题2]

## 参考资料
- [参考1]
- [参考2]
"""

    def _on_code_canvas_configure(self, event):
        """代码文件Canvas宽度变化时，内部Frame自适应"""
        self._code_file_canvas.itemconfig("scroll_win", width=event.width)

    def _on_notes_list_canvas_configure(self, event):
        """课程详情笔记列表Canvas宽度变化时，内部Frame自适应"""
        self._notes_list_canvas.itemconfig("scroll_win", width=event.width)

    def _refresh_code_file_list(self, parent, code_dir):
        for w in parent.winfo_children():
            w.destroy()
        if not code_dir.exists():
            ttk.Label(parent, text="目录不存在", foreground="#95a5a6").pack(pady=10)
            return
        
        # 先列出目录，再列出文件
        items = []
        try:
            for f in code_dir.iterdir():
                items.append(f)
        except Exception as e:
            ttk.Label(parent, text=f"读取目录失败: {e}", foreground="#c0392b").pack(pady=10)
            return
        
        if not items:
            ttk.Label(parent, text="暂无文件，点击「新建文件」创建",
                      foreground="#95a5a6").pack(pady=10)
            return
        
        # 排序：目录在前，然后按文件名
        items.sort(key=lambda f: (not f.is_dir(), f.name))
        
        for f in items:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=2, padx=5)
            icon = "📄"
            if f.is_dir():
                icon = "📁"
            elif f.suffix == ".py":
                icon = "🐍"
            elif f.suffix in [".R", ".Rmd"]:
                icon = "📊"
            elif f.suffix == ".json":
                icon = "📋"
            ttk.Label(row, text=icon, font=("", 12)).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(row, text=f.name, wraplength=200, font=("", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
            if f.is_dir():
                ttk.Button(row, text="📂", width=3,
                           command=lambda ff=f: open_file(str(ff))).pack(side=tk.RIGHT, padx=1)
            else:
                ttk.Button(row, text="📂", width=5,
                           command=lambda ff=f: self._open_file_with_positron(ff)).pack(side=tk.RIGHT, padx=1)
            ttk.Button(row, text="✕", width=3,
                       command=lambda ff=f: self._delete_code_file(ff)).pack(side=tk.RIGHT, padx=1)

    def _open_file_with_positron(self, file_path):
        """使用Positron编辑器打开文件，回退到系统默认"""
        try:
            import subprocess
            subprocess.Popen(["positron", str(file_path)])
        except FileNotFoundError:
            try:
                subprocess.Popen([str(file_path)])
            except Exception:
                open_file(str(file_path))

    def _delete_code_file(self, file_path):
        """删除代码文件或目录"""
        if file_path.is_dir():
            msg = f"确定要删除文件夹吗？\n{file_path.name}"
        else:
            msg = f"确定要删除文件吗？\n{file_path.name}"
        if messagebox.askyesno("确认删除", msg):
            try:
                if file_path.is_dir():
                    import shutil
                    shutil.rmtree(file_path)
                else:
                    file_path.unlink()
                if hasattr(self, "_code_scroll_frame") and hasattr(self, "_current_lesson_code_dir"):
                    self._refresh_code_file_list(self._code_scroll_frame, self._current_lesson_code_dir)
            except Exception as e:
                messagebox.showerror("错误", f"删除失败: {e}")

    def _create_new_code_file(self, code_dir, cid, lnum):
        filename = simpledialog.askstring("新建文件", "输入文件名:", initialvalue="未命名")
        if not filename:
            return
        file_path = code_dir / filename
        if file_path.exists():
            if not messagebox.askyesno("文件存在", f"{filename} 已存在，是否覆盖?"):
                return
        try:
            ext = Path(filename).suffix
            if ext == ".py":
                content = f'"""\n课程: {cid}\n课时: {lnum}\n"""\n\n'
            elif ext == ".R":
                content = f'## 课程: {cid} | 课时: {lnum}\n\n'
            elif ext == ".Rmd":
                content = f'''---
title: "课时{lnum}"
output: html_document
---

```r
# 代码开始

```
'''
            else:
                content = f"// 课程: {cid} | 课时: {lnum}\n\n"
            file_path.write_text(content, encoding="utf-8")
            open_file(str(file_path))
            # 刷新文件列表
            if hasattr(self, "_code_scroll_frame") and hasattr(self, "_current_lesson_code_dir"):
                self._refresh_code_file_list(self._code_scroll_frame, self._current_lesson_code_dir)
        except Exception as e:
            messagebox.showerror("错误", f"创建文件失败: {e}")

    def _build_pdf_preview_tab(self, parent, cid, lnum):
        """构建PDF预览tab - 支持页码选择和记忆"""
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 资源选择区域
        sel_frame = ttk.LabelFrame(main_frame, text="📑 选择PDF文件", padding=5)
        sel_frame.pack(fill=tk.X, pady=(0, 5))

        self._pdf_resource_var = tk.StringVar()
        resource_combo = ttk.Combobox(sel_frame, textvariable=self._pdf_resource_var, state="readonly")
        resource_combo.pack(fill=tk.X)

        # 页码控制区域
        page_frame = ttk.Frame(main_frame)
        page_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(page_frame, text="页码:").pack(side=tk.LEFT, padx=(0, 5))
        self._pdf_page_var = tk.StringVar(value="1")
        page_spin = ttk.Spinbox(page_frame, from_=1, to=999, width=6, textvariable=self._pdf_page_var)
        page_spin.pack(side=tk.LEFT)
        
        self._pdf_total_pages_var = tk.StringVar(value="")
        ttk.Label(page_frame, textvariable=self._pdf_total_pages_var).pack(side=tk.LEFT, padx=5)
        
        # 渲染按钮
        ttk.Button(page_frame, text="◀ 上一页", width=8,
                   command=self._pdf_prev_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_frame, text="下一页 ▶", width=8,
                   command=self._pdf_next_page).pack(side=tk.LEFT, padx=2)

        # 刷新资源列表函数
        def _refresh_resource_list():
            try:
                if not resource_combo.winfo_exists():
                    return
            except Exception:
                return
            
            resources = []
            lesson_res = self.system.rmgr.get_for_lesson(cid, lnum) if self.system.rmgr else []
            for res in lesson_res:
                rt = res.get("type", "")
                if rt == "pdf":
                    path_str = res.get("path", "")
                    fp = self._resolve_resource_path(path_str)
                    name = res.get("label", "") or fp.name if fp else path_str.split("/")[-1]
                    resources.append((f"[课时] {name}", res))
            course_res = self.system.rmgr.get_for_course(cid) if self.system.rmgr else []
            for res in course_res:
                rt = res.get("type", "")
                if rt == "pdf":
                    path_str = res.get("path", "")
                    fp = self._resolve_resource_path(path_str)
                    name = res.get("label", "") or fp.name if fp else path_str.split("/")[-1]
                    resources.append((f"[课程] {name}", res))
            try:
                if resources:
                    resource_combo['values'] = [r[0] for r in resources]
                    self._pdf_resource_map = {r[0]: r[1] for r in resources}
                    if self._pdf_resource_var.get() not in self._pdf_resource_map:
                        resource_combo.current(0)
                else:
                    resource_combo['values'] = ["暂无PDF资源"]
                    self._pdf_resource_map = {}
                    self._pdf_resource_var.set("暂无PDF资源")
            except Exception:
                pass

        self._refresh_pdf_resource_list = _refresh_resource_list
        _refresh_resource_list()

        # 预览区域
        preview_frame = ttk.LabelFrame(main_frame, text="👁️ 预览", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas用于显示图片
        self._pdf_canvas = tk.Canvas(preview_frame, bg="#E8E8E8", highlightthickness=0)
        self._pdf_canvas.pack(fill=tk.BOTH, expand=True)
        
        scroll_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self._pdf_canvas.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x = ttk.Scrollbar(preview_frame, orient="horizontal", command=self._pdf_canvas.xview)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._pdf_canvas.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)

        self._pdf_preview_label = ttk.Label(preview_frame, text="选择PDF后点击「渲染」按钮预览",
                                             foreground="#7f8c8d", anchor="center", justify="center")
        self._pdf_preview_label.pack_forget()

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(btn_frame, text="🎨 渲染当前页", command=self._render_pdf_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📂 系统打开", command=self._open_pdf_with_system).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔄 刷新列表", command=_refresh_resource_list).pack(side=tk.RIGHT, padx=2)

        self._current_pdf_cid = cid
        self._current_pdf_lnum = lnum
        self._current_pdf_path = None
        self._pdf_page_mem = {}  # 记忆每个PDF的页码

        # 绑定切换PDF时加载页数
        resource_combo.bind('<<ComboboxSelected>>', lambda e: self._on_pdf_selected())

    def _on_pdf_selected(self):
        """切换PDF时获取页数并恢复记忆"""
        sel_text = self._pdf_resource_var.get()
        if not sel_text or sel_text == "暂无PDF资源":
            return
        res = self._pdf_resource_map.get(sel_text)
        if not res:
            return
        path_str = res.get("path", "")
        fp = self._resolve_resource_path(path_str)
        if not fp.exists():
            return
        
        self._current_pdf_path = fp
        # 尝试获取页数
        try:
            from pdf2image import convert_from_path
            info = convert_from_path(str(fp), first_page=1, last_page=1, dpi=72, poppler_path=None)
            if hasattr(info, '__len__'):
                page_count = len(info)
            else:
                page_count = 1
            self._pdf_total_pages_var.set(f"/ {max(1, page_count)} 页")
        except Exception:
            self._pdf_total_pages_var.set("")
        
        # 恢复记忆的页码
        mem_key = str(fp)
        if mem_key in self._pdf_page_mem:
            self._pdf_page_var.set(str(self._pdf_page_mem[mem_key]))
        else:
            self._pdf_page_var.set("1")
        
        # 自动渲染选中的PDF
        self._render_pdf_page()

    def _pdf_prev_page(self):
        """上一页"""
        current = int(self._pdf_page_var.get() or 1)
        if current > 1:
            self._pdf_page_var.set(str(current - 1))
            self._render_pdf_page()

    def _pdf_next_page(self):
        """下一页"""
        current = int(self._pdf_page_var.get() or 1)
        self._pdf_page_var.set(str(current + 1))
        self._render_pdf_page()

    def _render_pdf_page(self):
        """渲染PDF当前页"""
        if not self._current_pdf_path or not self._current_pdf_path.exists():
            sel_text = self._pdf_resource_var.get()
            if not sel_text or sel_text == "暂无PDF资源":
                return
            res = self._pdf_resource_map.get(sel_text)
            if not res:
                return
            path_str = res.get("path", "")
            self._current_pdf_path = self._resolve_resource_path(path_str)
            if not self._current_pdf_path.exists():
                messagebox.showerror("文件不存在", str(self._current_pdf_path))
                return

        page_num = int(self._pdf_page_var.get() or 1)
        # 记忆页码
        self._pdf_page_mem[str(self._current_pdf_path)] = page_num

        self._pdf_canvas.delete("all")
        self._pdf_preview_label.pack_forget()

        try:
            from pdf2image import convert_from_path
            from PIL import Image, ImageTk
            
            # 清理之前的图片引用
            if hasattr(self, '_pdf_preview_image') and self._pdf_preview_image:
                del self._pdf_preview_image
            
            # 渲染指定页
            images = convert_from_path(str(self._current_pdf_path), 
                                      first_page=page_num, last_page=page_num, dpi=150)
            if images:
                img = images[0]
                MAX_W = self._pdf_canvas.winfo_width() or 680
                MAX_H = self._pdf_canvas.winfo_height() or 1000
                img.thumbnail((MAX_W, MAX_H), Image.LANCZOS)
                
                self._pdf_preview_image = ImageTk.PhotoImage(img)
                self._pdf_canvas.create_image(0, 0, anchor="nw", image=self._pdf_preview_image)
                self._pdf_canvas.configure(scrollregion=self._pdf_canvas.bbox("all"))
                
                self.wflogger.log_action("preview_pdf_page", 
                    self._current_pdf_cid, self._current_pdf_lnum,
                    detail=f"第{page_num}页 {self._current_pdf_path.name}")
        except ImportError:
            messagebox.showinfo("提示", "请安装 pdf2image 和 PIL:\npip install pdf2image pillow")
            open_file(str(self._current_pdf_path))
        except Exception as e:
            messagebox.showerror("渲染失败", str(e))
            open_file(str(self._current_pdf_path))

    def _open_pdf_with_system(self):
        """用系统程序打开PDF"""
        sel_text = self._pdf_resource_var.get()
        if not sel_text or sel_text == "暂无PDF资源":
            return
        res = self._pdf_resource_map.get(sel_text)
        if not res:
            return
        path_str = res.get("path", "")
        fp = self._resolve_resource_path(path_str)
        if fp.exists():
            self.wflogger.log_action("open_pdf", 
                self._current_pdf_cid, self._current_pdf_lnum,
                detail=str(fp))
            open_file(str(fp))
        else:
            messagebox.showerror("文件不存在", str(fp))

    def _open_in_positron(self, target_path):
        """使用Positron编辑器打开文件或目录"""
        import sys
        try:
            import subprocess
            # 处理 Windows 上的中文路径问题
            if sys.platform == "win32":
                import os
                # 在 Windows 上确保用正确的编码传递路径
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                subprocess.Popen(["positron", os.fspath(target_path)], 
                               creationflags=CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen(["positron", str(target_path)])
        except FileNotFoundError:
            possible_paths = [
                Path.home() / "AppData" / "Local" / "Programs" / "Positron" / "Positron.exe",
                Path("C:/Program Files/Positron/Positron.exe"),
                Path("C:/Program Files (x86)/Positron/Positron.exe"),
            ]
            for pp in possible_paths:
                if pp.exists():
                    if sys.platform == "win32":
                        import os
                        CREATE_NEW_PROCESS_GROUP = 0x00000200
                        subprocess.Popen([os.fspath(pp), os.fspath(target_path)], 
                                       creationflags=CREATE_NEW_PROCESS_GROUP)
                    else:
                        subprocess.Popen([str(pp), str(target_path)])
                    return
            open_file(str(target_path))

    def _build_inline_note_editor(self, parent, cid, lnum):
        """构建内置多媒体笔记编辑器 — 支持 Rmd 编辑、图片嵌入、代码块、LaTeX"""
        note_path, _ = self.system.get_or_create_note(cid, lnum)
        self._current_note_path = note_path
        self._current_note_cid = cid
        self._current_note_lnum = lnum
        self._inline_note_preview_mode = True  # 默认预览模式
        self._inline_note_full_content = ""  # 保存完整内容

        toolbar = self._scrollable_button_bar(parent)
        ttk.Button(toolbar, text="💾 保存",
                   command=self._save_inline_note).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📂 外部",
                   command=lambda: self._open_note(cid, lnum)).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        self._inline_note_toggle_btn = ttk.Button(toolbar, text="👁️ 预览模式",
                                                    command=self._toggle_inline_note_mode)
        self._inline_note_toggle_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Button(toolbar, text="🖼️ 插图",
                   command=self._insert_image_to_note).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💻 代码",
                   command=lambda: self._insert_template("code")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📐 公式",
                   command=lambda: self._insert_template("math")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📋 链接",
                   command=lambda: self._insert_template("link")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📊 表格",
                   command=lambda: self._insert_template("table")).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Button(toolbar, text="📌 定义",
                   command=lambda: self._insert_env("definition")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📜 定理",
                   command=lambda: self._insert_env("theorem")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💡 推论",
                   command=lambda: self._insert_env("corollary")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🎯 例子",
                   command=lambda: self._insert_env("example")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="❓ 问题",
                   command=lambda: self._insert_env("problem")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✅ 解答",
                   command=lambda: self._insert_env("solution")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📝 注解",
                   command=lambda: self._insert_env("remark")).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        ttk.Button(toolbar, text="❓ 问题解答",
                   command=self._show_problem_solution_panel).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(toolbar, text="📐 定理证明",
                   command=self._show_theorem_proof_panel).pack(side=tk.LEFT, padx=2)

        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self._note_editor = tk.Text(editor_frame, wrap=tk.WORD, font=("Consolas", 10),
                                     undo=True, maxundo=50,
                                     insertbackground="#2c3e50", selectbackground="#3498db",
                                     selectforeground="white", relief="flat", bg="#FAFAFA",
                                     padx=8, pady=6)
        editor_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self._note_editor.yview)
        self._note_editor.configure(yscrollcommand=editor_scroll.set)
        self._note_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._note_editor.tag_configure("yaml_delim", foreground="#7f8c8d", font=("Consolas", 10, "bold"))
        self._note_editor.tag_configure("yaml_key", foreground="#8e44ad")
        self._note_editor.tag_configure("yaml_val", foreground="#2980b9")
        self._note_editor.tag_configure("heading", foreground="#2c3e50", font=("Consolas", 11, "bold"))
        self._note_editor.tag_configure("heading2", foreground="#34495e", font=("Consolas", 10, "bold"))
        self._note_editor.tag_configure("code_block", foreground="#27ae60", font=("Consolas", 10))
        self._note_editor.tag_configure("code_delim", foreground="#95a5a6", font=("Consolas", 10, "bold"))
        self._note_editor.tag_configure("math_block", foreground="#c0392b", font=("Consolas", 10))
        self._note_editor.tag_configure("bold", foreground="#2c3e50", font=("Consolas", 10, "bold"))
        self._note_editor.tag_configure("italic", foreground="#7f8c8d")
        self._note_editor.tag_configure("link", foreground="#2980b9", underline=True)
        self._note_editor.tag_configure("image_ref", foreground="#e67e22")
        self._note_editor.tag_configure("blockquote", foreground="#7f8c8d", font=("Consolas", 10, "italic"))
        self._note_editor.tag_configure("list_item", foreground="#8e44ad")

        if note_path and note_path.exists():
            try:
                self._inline_note_full_content = note_path.read_text(encoding="utf-8")
                self._refresh_inline_note_display()
            except Exception:
                pass

        self._note_editor.bind("<KeyRelease>", lambda e: self._schedule_highlight())
        self._note_editor.bind("<Control-s>", lambda e: self._save_inline_note())
        self._note_editor.bind("<Control-b>", lambda e: self._wrap_selection("**"))
        self._note_editor.bind("<Control-i>", lambda e: self._wrap_selection("*"))

        status = ttk.Frame(parent)
        status.pack(fill=tk.X, pady=(3, 0))
        self._note_status = ttk.Label(status, text=f"📄 {note_path.name if note_path else '新笔记'}",
                                       font=("", 8), foreground="#95a5a6")
        self._note_status.pack(side=tk.LEFT)
        ttk.Label(status, text="自动保存 | Ctrl+S 手动保存 | Ctrl+B 粗体 | Ctrl+I 斜体",
                  font=("", 8), foreground="#bdc3c7").pack(side=tk.RIGHT)
        
        self._note_auto_save_delay = 5000
        self._note_auto_save_timer = None
        self._note_editor.bind("<<Modified>>", self._on_note_modified)
        self._note_editor.bind("<FocusOut>", lambda e: self._do_auto_save_immediate())

        self._highlight_after_id = None

    def _on_note_modified(self, event=None):
        """笔记内容修改时触发自动保存"""
        if not hasattr(self, '_note_auto_save_timer') or not hasattr(self, '_note_editor'):
            return
        if not self._note_editor.winfo_exists():
            return
        if self._note_auto_save_timer:
            self.root.after_cancel(self._note_auto_save_timer)
        self._note_auto_save_timer = self.root.after(
            self._note_auto_save_delay, self._do_auto_save)
        self._note_status.config(text="📝 已修改...", foreground="#f39c12")
    
    def _do_auto_save_immediate(self):
        """独立笔记立即保存（失焦时）"""
        if not hasattr(self, '_note_editor') or not self._note_editor.winfo_exists():
            return
        if not self._current_note_path:
            return
        try:
            if self._note_auto_save_timer:
                self.root.after_cancel(self._note_auto_save_timer)
                self._note_auto_save_timer = None
            current_edit = self._note_editor.get("1.0", tk.END + "-1c")
            if self._inline_note_preview_mode:
                cleaned = self._clean_note_content(self._inline_note_full_content)
                if current_edit.strip() and current_edit.strip() != cleaned.strip():
                    yaml_end = self._inline_note_full_content.find('\n---\n', 4)
                    if yaml_end != -1:
                        header = self._inline_note_full_content[:yaml_end + 5]
                        self._inline_note_full_content = header + current_edit
                    else:
                        self._inline_note_full_content = current_edit
            else:
                self._inline_note_full_content = current_edit
            
            self._current_note_path.parent.mkdir(parents=True, exist_ok=True)
            self._current_note_path.write_text(self._inline_note_full_content, encoding="utf-8")
            self._note_status.config(text=f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}",
                                      foreground="#27ae60")
            lnum = self._current_note_lnum
            self.wflogger.log_action("save_note", self._current_note_cid, lnum,
                                     detail="失焦自动保存")
        except Exception:
            pass

    def _do_auto_save(self):
        """执行自动保存"""
        if not hasattr(self, '_note_editor') or not self._note_editor.winfo_exists():
            return
        if not self._current_note_path:
            return
        try:
            current_edit = self._note_editor.get("1.0", tk.END + "-1c")
            if self._inline_note_preview_mode:
                cleaned = self._clean_note_content(self._inline_note_full_content)
                if current_edit.strip() and current_edit.strip() != cleaned.strip():
                    yaml_end = self._inline_note_full_content.find('\n---\n', 4)
                    if yaml_end != -1:
                        header = self._inline_note_full_content[:yaml_end + 5]
                        self._inline_note_full_content = header + current_edit
                    else:
                        self._inline_note_full_content = current_edit
            else:
                self._inline_note_full_content = current_edit
            
            self._current_note_path.parent.mkdir(parents=True, exist_ok=True)
            self._current_note_path.write_text(self._inline_note_full_content, encoding="utf-8")
            self._note_status.config(text=f"✅ 自动保存 {datetime.now().strftime('%H:%M:%S')}",
                                      foreground="#27ae60")
            lnum = self._current_note_lnum
            self.wflogger.log_action("save_note", self._current_note_cid, lnum,
                                     detail="自动保存")
        except Exception as e:
            self._note_status.config(text=f"❌ 保存失败: {e}", foreground="#c0392b")

    def _toggle_inline_note_mode(self):
        """切换执行模式笔记编辑器的预览/完整显示模式"""
        # 获取当前编辑的内容
        current_edit = self._note_editor.get("1.0", tk.END + "-1c")
        
        if self._inline_note_preview_mode:
            # 预览模式 -> 完整模式：只更新编辑部分，保持头部不变
            cleaned = self._clean_note_content(self._inline_note_full_content)
            if current_edit.strip() and current_edit.strip() != cleaned.strip():
                # 合并头部和编辑内容
                yaml_end = self._inline_note_full_content.find('\n---\n', 4)
                if yaml_end != -1:
                    header = self._inline_note_full_content[:yaml_end + 5]
                    self._inline_note_full_content = header + current_edit
                else:
                    self._inline_note_full_content = current_edit
        else:
            # 完整模式 -> 预览模式：直接使用完整内容
            self._inline_note_full_content = current_edit
        
        self._inline_note_preview_mode = not self._inline_note_preview_mode
        self._refresh_inline_note_display()



    def _refresh_inline_note_display(self):
        """刷新执行模式笔记编辑器的显示内容"""
        if hasattr(self, '_inline_note_toggle_btn'):
            btn_text = "👁️ 预览模式" if self._inline_note_preview_mode else "📝 完整模式"
            self._inline_note_toggle_btn.config(text=btn_text)
        
        self._note_editor.delete("1.0", tk.END)
        
        if self._inline_note_preview_mode:
            # 预览模式：显示清理后的内容
            display_content = self._clean_note_content(self._inline_note_full_content)
            self._note_editor.insert("1.0", display_content)
        else:
            # 完整模式：直接显示原始内容
            self._note_editor.insert("1.0", self._inline_note_full_content)
        
        self._apply_syntax_highlighting()

    def _schedule_highlight(self):
        if self._highlight_after_id:
            try:
                self.root.after_cancel(self._highlight_after_id)
            except:
                pass
        self._highlight_after_id = self.root.after(500, self._apply_syntax_highlighting)

    def _apply_syntax_highlighting(self):
        if not hasattr(self, '_note_editor') or not self._note_editor.winfo_exists():
            return
        te = self._note_editor
        cursor_pos = te.index(tk.INSERT)
        for tag in ("yaml_delim", "yaml_key", "yaml_val", "heading", "heading2",
                     "code_block", "code_delim", "math_block", "bold", "italic",
                     "link", "image_ref", "blockquote", "list_item"):
            te.tag_remove(tag, "1.0", tk.END)

        content = te.get("1.0", tk.END)
        lines = content.split('\n')
        in_yaml = False
        yaml_done = False
        in_code = False
        code_start = 0

        for i, line in enumerate(lines):
            li = i + 1
            stripped = line.strip()

            if not yaml_done and stripped == '---':
                te.tag_add("yaml_delim", f"{li}.0", f"{li}.end")
                if in_yaml:
                    yaml_done = True
                    in_yaml = False
                else:
                    in_yaml = True
                continue

            if in_yaml:
                m = re.match(r'^(\s*[\w_-]+)(\s*:\s*)(.*)', line)
                if m:
                    te.tag_add("yaml_key", f"{li}.0", f"{li}.{m.end(1)}")
                    if m.group(3).strip():
                        te.tag_add("yaml_val", f"{li}.{m.start(3)}", f"{li}.end")
                continue

            if stripped.startswith('```'):
                te.tag_add("code_delim", f"{li}.0", f"{li}.end")
                if in_code:
                    in_code = False
                    te.tag_add("code_block", f"{code_start}.0", f"{li}.end")
                else:
                    in_code = True
                    code_start = li
                continue

            if in_code:
                continue

            if stripped.startswith('$$'):
                te.tag_add("math_block", f"{li}.0", f"{li}.end")
                continue

            if stripped.startswith('# ') and not stripped.startswith('## '):
                te.tag_add("heading", f"{li}.0", f"{li}.end")
                continue
            if stripped.startswith('## ') and not stripped.startswith('### '):
                te.tag_add("heading2", f"{li}.0", f"{li}.end")
                continue

            if stripped.startswith('> '):
                te.tag_add("blockquote", f"{li}.0", f"{li}.end")
                continue

            if re.match(r'^\s*[-*]\s', line):
                te.tag_add("list_item", f"{li}.0", f"{li}.end")
                continue

            for m in re.finditer(r'\*\*(.+?)\*\*', line):
                te.tag_add("bold", f"{li}.{m.start()}", f"{li}.{m.end()}")
            for m in re.finditer(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', line):
                te.tag_add("italic", f"{li}.{m.start()}", f"{li}.{m.end()}")
            for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', line):
                te.tag_add("link", f"{li}.{m.start()}", f"{li}.{m.end()}")
            for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', line):
                te.tag_add("image_ref", f"{li}.{m.start()}", f"{li}.{m.end()}")

        te.mark_set(tk.INSERT, cursor_pos)

    def _save_inline_note(self):
        if not hasattr(self, '_note_editor') or not self._note_editor.winfo_exists():
            return
        if not self._current_note_path:
            return
        try:
            # 保存前同步当前编辑内容到完整内容
            current_edit = self._note_editor.get("1.0", tk.END + "-1c")
            if self._inline_note_preview_mode:
                # 预览模式：合并头部和编辑内容
                cleaned = self._clean_note_content(self._inline_note_full_content)
                if current_edit.strip() and current_edit.strip() != cleaned.strip():
                    yaml_end = self._inline_note_full_content.find('\n---\n', 4)
                    if yaml_end != -1:
                        header = self._inline_note_full_content[:yaml_end + 5]
                        self._inline_note_full_content = header + current_edit
                    else:
                        self._inline_note_full_content = current_edit
            else:
                # 完整模式：直接使用编辑内容
                self._inline_note_full_content = current_edit
            
            # 保存完整内容
            self._current_note_path.parent.mkdir(parents=True, exist_ok=True)
            self._current_note_path.write_text(self._inline_note_full_content, encoding="utf-8")
            self._note_status.config(text=f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}",
                                      foreground="#27ae60")
            self.root.after(3000, lambda: self._note_status.config(
                text=f"📄 {self._current_note_path.name}", foreground="#95a5a6"))
            lnum = self._current_note_lnum
            self.wflogger.log_action("save_note", self._current_note_cid, lnum,
                                     detail="内置编辑器保存")
        except Exception as e:
            self._note_status.config(text=f"❌ 保存失败: {e}", foreground="#c0392b")

    def _insert_image_to_note(self):
        fp = filedialog.askopenfilename(
            title="选择图片插入笔记",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp"), ("所有文件", "*.*")],
            initialdir=str(BASE)
        )
        if not fp:
            return
        try:
            img_path = Path(fp)
            try:
                rel = img_path.relative_to(BASE)
                ref_path = str(rel.as_posix())
            except ValueError:
                img_dir = self._current_note_path.parent / "images"
                img_dir.mkdir(exist_ok=True)
                import shutil
                dest = img_dir / img_path.name
                shutil.copy2(str(img_path), str(dest))
                ref_path = f"images/{img_path.name}"
            caption = img_path.stem
            self._note_editor.insert(tk.INSERT, f'\n![{caption}]({ref_path})\n')
            self._apply_syntax_highlighting()
            if self.system.rmgr:
                self.system.rmgr.add_image(self._current_note_cid, fp, BASE,
                                           lesson_number=self._current_note_lnum, caption=caption)
        except Exception as e:
            messagebox.showwarning("提示", f"插入图片失败: {e}")

    def _insert_template(self, template_type):
        templates = {
            "code": '\n```{r chunk_name, echo=TRUE}\n# R code here\n```\n',
            "math": '\n$$\nE = mc^2\n$$\n',
            "link": '[链接文字](https://example.com)',
            "table": '\n| 列1 | 列2 | 列3 |\n|------|------|------|\n| 数据 | 数据 | 数据 |\n',
        }
        tpl = templates.get(template_type, "")
        if tpl:
            self._note_editor.insert(tk.INSERT, tpl)
            self._apply_syntax_highlighting()

    def _insert_env(self, env_type):
        env_templates = {
            "definition": '\n::: definition\n**定义名称**\n在这里输入定义内容\n:::\n',
            "theorem": '\n::: theorem\n**定理名称**\n在这里输入定理内容\n:::\n',
            "corollary": '\n::: corollary\n**推论名称**\n在这里输入推论内容\n:::\n',
            "example": '\n::: example\n**例子名称**\n在这里输入例子内容\n:::\n',
            "problem": '\n::: problem\n**问题名称**\n在这里输入问题内容\n:::\n',
            "solution": '\n::: solution\n**解答名称**\n在这里输入解答内容\n:::\n',
            "remark": '\n::: remark\n**注解名称**\n在这里输入注解内容\n:::\n',
        }
        tpl = env_templates.get(env_type, "")
        if tpl:
            self._note_editor.insert(tk.INSERT, tpl)
            self._apply_syntax_highlighting()

    def _show_problem_solution_panel(self):
        """显示问题解答面板（支持重读写入）"""
        if not hasattr(self, '_current_note_path'):
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("❓ 问题解答 - 重读写入")
        dlg.geometry("1425x975")
        dlg.transient(self.root)
        dlg.grab_set()

        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from note_analyzer import NoteAnalyzer

        ttk.Label(dlg, text="选择一个问题并添加/更新解答（已有解答=✅）", 
                  font=("", 12, "bold")).pack(pady=(10, 5))

        main_frame = ttk.Frame(dlg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：问题列表
        left_frame = ttk.LabelFrame(main_frame, text="📋 问题列表", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        problems_tree = ttk.Treeview(left_frame, columns=("title", "has_solution", "preview"), show="headings")
        problems_tree.heading("title", text="问题标题")
        problems_tree.heading("has_solution", text="状态")
        problems_tree.heading("preview", text="预览")
        problems_tree.column("title", width=180)
        problems_tree.column("has_solution", width=45, anchor="center")
        problems_tree.column("preview", width=260)
        problems_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scroll_v = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=problems_tree.yview)
        scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
        problems_tree.configure(yscrollcommand=scroll_v.set)

        # 右侧：解答编辑
        right_frame = ttk.LabelFrame(main_frame, text="✏️ 解答编辑（重读写入）", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ttk.Label(right_frame, text="问题内容（可编辑）:").pack(anchor="w", pady=(0, 2))
        problem_content_text = tk.Text(right_frame, height=7, wrap=tk.WORD, bg="#FFFFFF")
        problem_content_text.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(right_frame, text="你的解答:").pack(anchor="w", pady=(5, 2))
        solution_text = tk.Text(right_frame, height=15, wrap=tk.WORD, font=("Consolas", 10))
        solution_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        problem_solution_pairs = []  # 存储 (problem, solution) 对

        def load_problems():
            """加载笔记中的所有问题及对应的解答"""
            problems_tree.delete(*problems_tree.get_children())
            problem_solution_pairs.clear()
            
            if not self._current_note_path.exists():
                return
            
            try:
                elements = NoteAnalyzer.extract_from_file(
                    self._current_note_path,
                    self._current_note_cid,
                    self._current_note_lnum
                )
                
                pairs = NoteAnalyzer.find_problem_solution_pair(elements)
                
                for problem, solution in pairs:
                    problem_solution_pairs.append((problem, solution))
                    has_sol = "✅" if solution else ""
                    preview = problem.content[:100] + "..." if len(problem.content) > 100 else problem.content
                    problems_tree.insert("", "end", values=(problem.title, has_sol, preview))
            except Exception as e:
                import traceback
                print(f"加载问题失败: {e}")
                traceback.print_exc()

        load_problems()

        ttk.Button(btn_frame, text="🔄 刷新", command=load_problems).pack(side=tk.LEFT, padx=2)

        def on_problem_selected(event):
            """选择问题时显示内容和已有解答"""
            sel = problems_tree.selection()
            if not sel:
                return
            idx = problems_tree.index(sel[0])
            if 0 <= idx < len(problem_solution_pairs):
                problem, solution = problem_solution_pairs[idx]
                problem_content_text.delete("1.0", tk.END)
                problem_content_text.insert("1.0", problem.content)
                
                # 加载已有解答（如果有）
                solution_text.delete("1.0", tk.END)
                if solution:
                    solution_text.insert("1.0", solution.content)

        problems_tree.bind("<<TreeviewSelect>>", on_problem_selected)

        def save_solution():
            """保存问题和解答到笔记（支持重读写入）"""
            sel = problems_tree.selection()
            if not sel:
                messagebox.showwarning("提示", "请先选择一个问题！")
                return
            
            idx = problems_tree.index(sel[0])
            if idx >= len(problem_solution_pairs):
                return

            problem_content = problem_content_text.get("1.0", tk.END + "-1c").strip()
            solution_content = solution_text.get("1.0", tk.END + "-1c").strip()
            if not problem_content:
                messagebox.showwarning("提示", "问题内容不能为空！")
                return
            if not solution_content:
                messagebox.showwarning("提示", "解答内容不能为空！")
                return

            try:
                problem, old_solution = problem_solution_pairs[idx]
                solution_title = f"{problem.title} - 解答"
                
                note_content = self._current_note_path.read_text(encoding="utf-8")
                
                # 构建问题和解答的完整内容
                problem_env = f"::: problem\n**{problem.title}**\n{problem_content}\n:::"
                solution_env = f"::: solution\n**{solution_title}**\n{solution_content}\n:::"
                
                # 先确定需要替换的范围
                start_replace = problem.raw_start
                
                if old_solution:
                    # 有旧解答，替换从问题开始到解答结束的范围
                    end_replace = old_solution.raw_end
                    combined_env = problem_env + "\n\n" + solution_env
                    new_content = note_content[:start_replace] + combined_env + note_content[end_replace:]
                else:
                    # 没有旧解答，替换问题本身，然后在问题后面添加解答
                    end_replace = problem.raw_end
                    # 替换问题
                    temp_content = note_content[:start_replace] + problem_env + note_content[end_replace:]
                    # 找到问题结束位置，在后面添加解答
                    # 重新解析临时内容
                    temp_elements = NoteAnalyzer.parse_note(temp_content)
                    current_problem = None
                    for e in temp_elements:
                        if e.elem_type == "problem" and e.title == problem.title:
                            current_problem = e
                            break
                    
                    if current_problem and current_problem.raw_start != -1:
                        end_idx = NoteAnalyzer._find_closing_triple_colon_simple(temp_content, current_problem.raw_start, "problem")
                        if end_idx != -1:
                            triple_colon_end = temp_content.find("\n", end_idx + 3)
                            if triple_colon_end != -1:
                                insert_pos = triple_colon_end + 1
                            else:
                                insert_pos = end_idx + 3
                            new_content = temp_content[:insert_pos] + "\n" + solution_env + temp_content[insert_pos:]
                        else:
                            # 找不到，追加到末尾
                            new_content = temp_content + "\n" + solution_env
                    else:
                        # 找不到问题，追加到末尾
                        new_content = temp_content + "\n" + solution_env
                
                # 保存文件
                self._current_note_path.write_text(new_content, encoding="utf-8")
                
                # 更新编辑器和重新加载
                self._inline_note_full_content = new_content
                self._refresh_inline_note_display()
                load_problems()
                
                messagebox.showinfo("成功", "问题和解答已保存（重读写入）！")
            except Exception as e:
                import traceback
                messagebox.showerror("错误", f"保存失败: {e}")
                traceback.print_exc()

        ttk.Button(btn_frame, text="💾 保存/更新（问题+解答）", command=save_solution).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 清空解答", command=lambda: solution_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=2)

    def _show_theorem_proof_panel(self):
        """显示理论证明面板（支持重读写入）"""
        if not hasattr(self, '_current_note_path'):
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("📐 定理证明 - 重读写入")
        dlg.geometry("1425x975")
        dlg.transient(self.root)
        dlg.grab_set()

        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from note_analyzer import NoteAnalyzer

        ttk.Label(dlg, text="选择一个定理/推论并添加/更新证明（已有证明=✅）", 
                  font=("", 12, "bold")).pack(pady=(10, 5))

        main_frame = ttk.Frame(dlg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：定理列表
        left_frame = ttk.LabelFrame(main_frame, text="📋 定理/推论列表", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        theorems_tree = ttk.Treeview(left_frame, columns=("type", "title", "has_proof", "preview"), show="headings")
        theorems_tree.heading("type", text="类型")
        theorems_tree.heading("title", text="标题")
        theorems_tree.heading("has_proof", text="状态")
        theorems_tree.heading("preview", text="预览")
        theorems_tree.column("type", width=80, anchor="center")
        theorems_tree.column("title", width=180)
        theorems_tree.column("has_proof", width=45, anchor="center")
        theorems_tree.column("preview", width=260)
        theorems_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scroll_v = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=theorems_tree.yview)
        scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
        theorems_tree.configure(yscrollcommand=scroll_v.set)

        # 右侧：证明编辑
        right_frame = ttk.LabelFrame(main_frame, text="✏️ 证明编辑（重读写入）", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ttk.Label(right_frame, text="定理内容（可编辑）:").pack(anchor="w", pady=(0, 2))
        theorem_content_text = tk.Text(right_frame, height=7, wrap=tk.WORD, bg="#FFFFFF")
        theorem_content_text.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(right_frame, text="你的证明:").pack(anchor="w", pady=(5, 2))
        proof_text = tk.Text(right_frame, height=15, wrap=tk.WORD, font=("Consolas", 10))
        proof_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        theorem_proof_pairs = []  # 存储 (theorem, proof) 对

        def load_theorems():
            """加载笔记中的所有定理/推论及对应的证明"""
            theorems_tree.delete(*theorems_tree.get_children())
            theorem_proof_pairs.clear()
            
            if not self._current_note_path.exists():
                return
            
            try:
                elements = NoteAnalyzer.extract_from_file(
                    self._current_note_path,
                    self._current_note_cid,
                    self._current_note_lnum
                )
                
                pairs = NoteAnalyzer.find_theorem_proof_pair(elements)
                
                for theorem, proof in pairs:
                    theorem_proof_pairs.append((theorem, proof))
                    # 类型名称美化
                    type_name = {
                        "theorem": "定理",
                        "corollary": "推论",
                        "lemma": "引理",
                        "proposition": "命题",
                        "axiom": "公理",
                        "postulate": "公设"
                    }.get(theorem.elem_type, theorem.elem_type)
                    has_proof = "✅" if proof else ""
                    preview = theorem.content[:90] + "..." if len(theorem.content) > 90 else theorem.content
                    theorems_tree.insert("", "end", values=(type_name, theorem.title, has_proof, preview))
            except Exception as e:
                import traceback
                print(f"加载定理失败: {e}")
                traceback.print_exc()

        load_theorems()

        ttk.Button(btn_frame, text="🔄 刷新", command=load_theorems).pack(side=tk.LEFT, padx=2)

        def on_theorem_selected(event):
            """选择定理时显示内容和已有证明"""
            sel = theorems_tree.selection()
            if not sel:
                return
            idx = theorems_tree.index(sel[0])
            if 0 <= idx < len(theorem_proof_pairs):
                theorem, proof = theorem_proof_pairs[idx]
                theorem_content_text.delete("1.0", tk.END)
                theorem_content_text.insert("1.0", theorem.content)
                
                # 加载已有证明（如果有）
                proof_text.delete("1.0", tk.END)
                if proof:
                    proof_text.insert("1.0", proof.content)

        theorems_tree.bind("<<TreeviewSelect>>", on_theorem_selected)

        def save_proof():
            """保存定理和证明到笔记（支持重读写入）"""
            sel = theorems_tree.selection()
            if not sel:
                messagebox.showwarning("提示", "请先选择一个定理/推论！")
                return
            
            idx = theorems_tree.index(sel[0])
            if idx >= len(theorem_proof_pairs):
                return

            theorem_content = theorem_content_text.get("1.0", tk.END + "-1c").strip()
            proof_content = proof_text.get("1.0", tk.END + "-1c").strip()
            if not theorem_content:
                messagebox.showwarning("提示", "定理内容不能为空！")
                return
            if not proof_content:
                messagebox.showwarning("提示", "证明内容不能为空！")
                return

            try:
                theorem, old_proof = theorem_proof_pairs[idx]
                proof_title = f"{theorem.title} - 证明"
                
                note_content = self._current_note_path.read_text(encoding="utf-8")
                
                # 构建定理和证明的完整内容
                theorem_env = f"::: {theorem.elem_type}\n**{theorem.title}**\n{theorem_content}\n:::"
                proof_env = f"::: proof\n**{proof_title}**\n{proof_content}\n:::"
                
                # 先确定需要替换的范围
                start_replace = theorem.raw_start
                
                if old_proof:
                    # 有旧证明，替换从定理开始到证明结束的范围
                    end_replace = old_proof.raw_end
                    combined_env = theorem_env + "\n\n" + proof_env
                    new_content = note_content[:start_replace] + combined_env + note_content[end_replace:]
                else:
                    # 没有旧证明，替换定理本身，然后在定理后面添加证明
                    end_replace = theorem.raw_end
                    # 替换定理
                    temp_content = note_content[:start_replace] + theorem_env + note_content[end_replace:]
                    # 找到定理结束位置，在后面添加证明
                    # 重新解析临时内容
                    temp_elements = NoteAnalyzer.parse_note(temp_content)
                    current_theorem = None
                    for e in temp_elements:
                        if e.elem_type == theorem.elem_type and e.title == theorem.title:
                            current_theorem = e
                            break
                    
                    if current_theorem and current_theorem.raw_start != -1:
                        end_idx = NoteAnalyzer._find_closing_triple_colon_simple(temp_content, current_theorem.raw_start, theorem.elem_type)
                        if end_idx != -1:
                            triple_colon_end = temp_content.find("\n", end_idx + 3)
                            if triple_colon_end != -1:
                                insert_pos = triple_colon_end + 1
                            else:
                                insert_pos = end_idx + 3
                            new_content = temp_content[:insert_pos] + "\n" + proof_env + temp_content[insert_pos:]
                        else:
                            # 找不到，追加到末尾
                            new_content = temp_content + "\n" + proof_env
                    else:
                        # 找不到定理，追加到末尾
                        new_content = temp_content + "\n" + proof_env
                
                # 保存文件
                self._current_note_path.write_text(new_content, encoding="utf-8")
                
                # 更新编辑器和重新加载
                self._inline_note_full_content = new_content
                self._refresh_inline_note_display()
                load_theorems()
                
                messagebox.showinfo("成功", "定理和证明已保存（重读写入）！")
            except Exception as e:
                import traceback
                messagebox.showerror("错误", f"保存失败: {e}")
                traceback.print_exc()

        ttk.Button(btn_frame, text="💾 保存/更新（定理+证明）", command=save_proof).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 清空证明", command=lambda: proof_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=2)

    def _wrap_selection(self, wrapper):
        try:
            if self._note_editor.tag_ranges(tk.SEL):
                start = self._note_editor.index(tk.SEL_FIRST)
                end = self._note_editor.index(tk.SEL_LAST)
                selected = self._note_editor.get(start, end)
                self._note_editor.delete(start, end)
                self._note_editor.insert(start, f"{wrapper}{selected}{wrapper}")
            else:
                self._note_editor.insert(tk.INSERT, f"{wrapper}文本{wrapper}")
            self._apply_syntax_highlighting()
        except:
            pass

    def _show_log_menu(self, event):
        """显示日志右键菜单"""
        try:
            item = self.note_tree.identify_row(event.y)
            if item:
                self.note_tree.selection_set(item)
                self._log_menu.post(event.x_root, event.y_root)
        except:
            pass

    def _start_log_refresh(self, cid, lnum):
        if hasattr(self, '_log_refresh_after_id') and self._log_refresh_after_id:
            try:
                self.root.after_cancel(self._log_refresh_after_id)
            except:
                pass
        self._log_refresh_after_id = None
        self._do_log_refresh(cid, lnum)

    def _do_log_refresh(self, cid, lnum):
        if not (hasattr(self, '_exec_timer_running') and self._exec_timer_running):
            self._log_refresh_after_id = None
            return
        self._refresh_new_entries(cid, lnum)
        self._log_refresh_after_id = self.root.after(3000, lambda: self._do_log_refresh(cid, lnum))

    def _stop_log_refresh(self):
        if hasattr(self, '_log_refresh_after_id') and self._log_refresh_after_id:
            try:
                self.root.after_cancel(self._log_refresh_after_id)
            except:
                pass
            self._log_refresh_after_id = None

    def _refresh_new_entries(self, cid, lnum):
        try:
            if not hasattr(self, 'note_tree') or self.note_tree is None:
                return
            if not self.note_tree.winfo_exists():
                return
            # 更新缓存并重新应用搜索过滤
            entries = self.wflogger.get_entries()
            self._lesson_entries_cache = [
                e for e in entries
                if e.get('lesson_number') == lnum and e.get('course_id') == cid
            ]
            self._log_displayed_count = len(self._lesson_entries_cache)
            self._refresh_filtered_logs(cid, lnum)
        except Exception as e:
            print(f"增量刷新错误: {e}")

    def _on_note_entry_focus(self, event, entering):
        """输入框焦点处理"""
        try:
            placeholder = "选中事件后可追加批注，直接回车添加笔记..."
            if entering:
                current = self.note_entry.get().strip()
                if current == placeholder:
                    self.note_entry.delete(0, tk.END)
            else:
                current = self.note_entry.get().strip()
                if not current or current == placeholder:
                    self.note_entry.delete(0, tk.END)
                    self.note_entry.insert(0, placeholder)
        except:
            pass

    def _annotate_selected(self, cid, lnum):
        """选中事件后加载已有批注到输入框，供追加"""
        # 暂停自动刷新，防止刷新清空选中状态
        if hasattr(self, '_log_refresh_after_id') and self._log_refresh_after_id:
            try:
                self.root.after_cancel(self._log_refresh_after_id)
                self._log_refresh_after_id = None
            except:
                pass
        
        try:
            selection = self.note_tree.selection()
            if not selection:
                messagebox.showinfo("提示", "请先选择一条日志事件", parent=self.root)
                return
            item = selection[0]
            vals = self.note_tree.item(item, "values")
            if not vals or len(vals) < 2:
                return
            
            ts = vals[0] if vals else ""
            event_text = vals[1] if len(vals) > 1 else ""
            idx = self.note_tree.index(item)
            key = f"{cid}|{lnum}|{idx}|{ts}"
            existing = self._log_annotations.get(key, "")

            self.note_entry.delete(0, tk.END)
            self.note_entry.insert(0, existing if existing else "追加批注内容...")
            self.note_entry.select_range(0, tk.END)
            self.note_entry.focus()
        except Exception as e:
            print(f"批注加载错误: {e}")

    def _submit_log_input(self, cid, lnum):
        """提交输入：追加批注，或作为新笔记"""
        try:
            text = self.note_entry.get().strip()
            placeholder = "选中事件后可追加批注，直接回车添加笔记..."
            if not text or text == placeholder:
                return
            selection = self.note_tree.selection()
            if selection:
                self._apply_annotation(selection[0], text, cid, lnum)
                self.note_entry.delete(0, tk.END)
                self.note_entry.insert(0, placeholder)
            else:
                self.wflogger.log_note(text, cid, lnum)
                self._lesson_entries_cache = None
                self._refresh_filtered_logs(cid, lnum)
                self.note_entry.delete(0, tk.END)
                self.note_entry.insert(0, placeholder)
            
            # 恢复自动刷新
            if hasattr(self, '_exec_timer_running') and self._exec_timer_running:
                self._start_log_refresh(cid, lnum)
        except Exception as e:
            print(f"提交错误: {e}")

    def _apply_annotation(self, tree_item, text, cid, lnum):
        """追加批注到指定日志行"""
        try:
            vals = self.note_tree.item(tree_item, "values")
            ts = vals[0] if vals else ""
            event_text = vals[1] if len(vals) > 1 else ""
            idx = self.note_tree.index(tree_item)
            key = f"{cid}|{lnum}|{idx}|{ts}"
            existing = self._log_annotations.get(key, "")
            self._log_annotations[key] = existing + (" " if existing else "") + text
            display_text = self._log_annotations[key][:30]
            self.note_tree.item(tree_item, values=(ts, event_text, display_text))
            self._save_annotations(cid, lnum)
        except Exception as e:
            print(f"应用批注错误: {e}")

    def _clear_annotation(self, cid, lnum):
        """清除选中事件的批注"""
        # 暂停自动刷新，防止刷新清空选中状态
        if hasattr(self, '_log_refresh_after_id') and self._log_refresh_after_id:
            try:
                self.root.after_cancel(self._log_refresh_after_id)
                self._log_refresh_after_id = None
            except:
                pass
        
        try:
            selection = self.note_tree.selection()
            if not selection:
                return
            item = selection[0]
            vals = self.note_tree.item(item, "values")
            ts = vals[0] if vals else ""
            event_text = vals[1] if len(vals) > 1 else ""
            idx = self.note_tree.index(item)
            key = f"{cid}|{lnum}|{idx}|{ts}"
            if key in self._log_annotations:
                del self._log_annotations[key]
            self.note_tree.item(item, values=(ts, event_text, ""))
            self._save_annotations(cid, lnum)
        except Exception as e:
            print(f"清除批注错误: {e}")

    def _save_annotations(self, cid, lnum):
        """保存批注到文件"""
        try:
            ann_file = BASE / "log_annotations.json"
            data = {}
            if ann_file.exists():
                data = json.loads(ann_file.read_text(encoding="utf-8"))
            key = f"{cid}|{lnum}"
            data[key] = self._log_annotations
            ann_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"保存批注错误: {e}")

    def _load_annotations(self, cid, lnum):
        """加载批注"""
        try:
            ann_file = BASE / "log_annotations.json"
            if ann_file.exists():
                data = json.loads(ann_file.read_text(encoding="utf-8"))
                key = f"{cid}|{lnum}"
                self._log_annotations = data.get(key, {})
            else:
                self._log_annotations = {}
        except:
            self._log_annotations = {}

    def _add_note_to_tree(self, content):
        try:
            if not hasattr(self, 'note_tree') or self.note_tree is None:
                return
            elapsed = ""
            if self.wflogger._timer_start:
                delta = (datetime.now() - self.wflogger._timer_start).total_seconds()
                m, s = divmod(int(delta), 60)
                h, m = divmod(m, 60)
                if h > 0:
                    elapsed = f"{h}:{m:02d}:{s:02d}"
                else:
                    elapsed = f"{m:02d}:{s:02d}"
            self.note_tree.insert("", 0, values=(elapsed, f"📝 {content[:40]}", ""),
                                   tags=("note",))
        except Exception as e:
            print(f"显示笔记错误: {e}")

    def _load_notes_for_lesson(self, cid, lnum):
        """首次加载课时级日志 - 之后由增量刷新接管"""
        self._lesson_entries_cache = None  # 清除缓存
        self._refresh_filtered_logs(cid, lnum)

    def _refresh_filtered_logs(self, cid, lnum):
        """根据搜索过滤刷新日志显示"""
        try:
            if not hasattr(self, 'note_tree') or self.note_tree is None:
                return

            for item in self.note_tree.get_children():
                self.note_tree.delete(item)

            self._load_annotations(cid, lnum)

            # 使用缓存或重新获取
            if not hasattr(self, '_lesson_entries_cache') or self._lesson_entries_cache is None:
                entries = self.wflogger.get_entries()
                self._lesson_entries_cache = [
                    e for e in entries
                    if e.get('lesson_number') == lnum and e.get('course_id') == cid
                ]
                self._log_displayed_count = len(self._lesson_entries_cache)

            lesson_entries = self._lesson_entries_cache
            search_query = getattr(self, '_log_search_var', tk.StringVar(value="")).get().strip().lower()

            type_labels = {
                "timer_start": "▶ 开始计时",
                "timer_stop": "⏹ 停止计时",
                "action": "⚡ 动作",
                "note": "📝 笔记",
                "blur": "👋 离开",
                "focus_return": "✅ 返回",
                "lesson_complete": "🎯 完成课时",
                "open_note": "📓 打开笔记",
                "open_resource": "📂 打开资源",
            }

            for idx, entry in enumerate(lesson_entries):
                elapsed = self.wflogger.get_lesson_elapsed(entry, lesson_entries)
                etype = entry.get("type", "")
                detail = entry.get("detail", "")
                action = entry.get("action", "")
                label = type_labels.get(etype, etype)
                if detail:
                    label += f" {detail[:25]}"
                elif action:
                    label += f" {action[:25]}"

                ann_key = f"{cid}|{lnum}|{idx}|{elapsed}"
                annotation = self._log_annotations.get(ann_key, "")

                # 搜索过滤
                if search_query:
                    match_text = f"{label} {elapsed} {detail} {action} {annotation}".lower()
                    if search_query not in match_text:
                        continue

                self.note_tree.insert("", 0, values=(elapsed, label, annotation[:30]),
                                       tags=(etype,))
        except Exception as e:
            print(f"加载日志错误: {e}")

    def _timer_tick(self):
        """计时器每秒刷新"""
        if not (hasattr(self, '_exec_timer_running') and self._exec_timer_running):
            return
        if not (hasattr(self, 'wflogger') and self.wflogger._timer_start):
            return
        if hasattr(self, '_timer_label') and self._timer_label and self._timer_label.winfo_exists():
            elapsed = (datetime.now() - self.wflogger._timer_start).total_seconds()
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.root.after(1000, self._timer_tick)

    def _quick_note(self, course_id, lesson_number):
        """快速笔记 — 在日志流中插入文本笔记"""
        dlg = tk.Toplevel(self.root)
        dlg.title("📌 快速笔记")
        dlg.geometry("400x200")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="输入笔记内容：", font=("", 10, "bold")).pack(pady=(10, 5))
        note_var = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=note_var, width=45, font=("", 10))
        entry.pack(padx=15)
        entry.focus()

        def _submit():
            text = note_var.get().strip()
            if text:
                self.wflogger.log_note(text, course_id, lesson_number)
            dlg.destroy()

        entry.bind("<Return>", lambda e: _submit())
        ttk.Button(dlg, text="确认", command=_submit).pack(pady=10)

    def _complete_and_next(self, course_id, lesson_num):
        """完成当前课时，消除，弹出下一步"""
        # 工作流日志：完成课时
        self._exec_current_lnum = lesson_num
        self.wflogger.log_lesson_complete(course_id, lesson_num)

        next_lesson = self.system.complete_lesson(course_id, lesson_num)
        self._update_overall_label()

        workload_info = self.wflogger.get_lesson_workload(course_id, lesson_num)
        self.system.update_review_schedule(course_id, lesson_num, workload_info["workload"])

        # 从执行列表中消除已完成的
        for item in self.exec_tree.get_children():
            values = self.exec_tree.item(item)["values"]
            if int(values[0]) == lesson_num:
                self.exec_tree.delete(item)
                break

        # 刷新当前课时卡片
        self._render_current_lesson(self.current_lesson_frame, course_id, next_lesson)

        # 更新顶栏进度
        pct = self.system.get_completion_pct(course_id)
        for w in self.content_frame.winfo_children():
            if isinstance(w, ttk.Frame):
                for child in w.winfo_children():
                    if isinstance(child, ttk.Progressbar):
                        child["value"] = pct
                    elif isinstance(child, ttk.Label) and "完成" in str(child.cget("text")):
                        child.config(text=f"完成 {pct}%")

        # 弹出下一步通知
        if next_lesson:
            self._popup_next(course_id, next_lesson)
        else:
            self._popup_complete(course_id)

    def _popup_next(self, course_id, next_lesson):
        """弹出下一步课时窗口"""
        popup = tk.Toplevel(self.root)
        popup.title("👉 下一步")
        popup.geometry("420x250")
        popup.attributes("-topmost", True)
        popup.grab_set()

        # 居中
        popup.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        popup.geometry(f"+{x}+{y}")

        lnum = next_lesson.get("lesson_number", 0)
        title = next_lesson.get("lesson_title", "")
        pct = self.system.get_completion_pct(course_id)

        ttk.Label(popup, text="✅ 上一课时已完成！", font=("", 12), foreground="#27ae60").pack(pady=(15, 5))
        ttk.Label(popup, text=f"下一步: 课时 {lnum}", font=("", 10), foreground="#2980b9").pack()
        ttk.Label(popup, text=title, font=("", 14, "bold"), wraplength=380).pack(pady=10)
        ttk.Label(popup, text=f"课程进度: {pct}%", style="Sub.TLabel").pack()

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="继续", command=popup.destroy).pack(side=tk.LEFT, padx=10, ipady=3, ipadx=20)

        # 自动3秒后关闭
        popup.after(3000, lambda: popup.destroy() if popup.winfo_exists() else None)

    def _popup_complete(self, course_id):
        """弹出课程完成窗口"""
        popup = tk.Toplevel(self.root)
        popup.title("🎉 课程完成")
        popup.geometry("400x200")
        popup.attributes("-topmost", True)
        popup.grab_set()

        popup.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        popup.geometry(f"+{x}+{y}")

        course = self.system.get_course_by_id(course_id)
        title = course.get("course_title", "") if course else ""

        ttk.Label(popup, text="🎉", font=("", 36)).pack(pady=10)
        ttk.Label(popup, text=f"{title}", font=("", 14, "bold"), wraplength=350).pack()
        ttk.Label(popup, text="全部课时已完成！", font=("", 12), foreground="#27ae60").pack(pady=5)

        ttk.Button(popup, text="返回", command=popup.destroy).pack(pady=10)

    # ============ 工作流日志统计分析页面 ============

    def _show_workflow_log(self, period="all"):
        """工作日志：增强统计 + 日志流 + 可视化"""
        self._clear_content()
        self._highlight_nav("wflog")
        self.nav_title.config(text="工作日志")

        # 标题操作栏
        header = ttk.Frame(self.content_frame)
        header.pack(fill=tk.X, pady=5)
        
        ttk.Label(header, text="📊 学习统计与工作日志", font=("", 14, "bold"),
                  foreground="#2C3E50").pack(side=tk.LEFT)
        
        # 时间筛选下拉框
        period_frame = ttk.Frame(header)
        period_frame.pack(side=tk.RIGHT, padx=5)
        
        period_var = tk.StringVar(value=period)
        periods = [
            ("全部", "all"),
            ("今日", "today"),
            ("昨日", "yesterday"),
            ("本周", "week"),
            ("上周", "last_week"),
            ("本月", "month"),
            ("上月", "last_month"),
            ("本年", "year"),
        ]
        
        ttk.Label(period_frame, text="时间范围:").pack(side=tk.LEFT, padx=2)
        period_combo = ttk.Combobox(period_frame, textvariable=period_var, 
                                    values=[p[0] for p in periods], width=10, state="readonly")
        period_combo.pack(side=tk.LEFT)
        
        def _on_period_change(event=None):
            selected_period = next(p[1] for p in periods if p[0] == period_var.get())
            self._show_workflow_log(selected_period)
        
        period_combo.bind("<<ComboboxSelected>>", _on_period_change)
        
        ttk.Button(header, text="🔄 刷新", command=self._show_workflow_log).pack(side=tk.RIGHT, padx=5)
        ttk.Button(header, text="🗑️ 清空日志", command=self._clear_workflow_log).pack(side=tk.RIGHT, padx=5)

        entries = self.wflogger.get_entries()

        if not entries:
            ttk.Label(self.content_frame, text="暂无工作日志\n\n进入执行模式开始学习后会自动记录",
                      font=("", 12), foreground="#95a5a6").pack(pady=60)
            return

        # 根据时间范围获取统计数据
        stats = self.wflogger.get_stats_by_period(period)

        # 创建标签页：可视化统计 / 详细统计 / 日志流
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        notebook.bind("<Configure>", lambda e, nb=notebook: self._on_notebook_resize(nb))

        # ── Tab 1: 可视化统计 ──
        viz_tab = ttk.Frame(notebook)
        notebook.add(viz_tab, text="📈 可视化统计")
        self._build_visualization_stats(viz_tab, stats, period)

        # ── Tab 2: 详细统计 ──
        stats_tab = ttk.Frame(notebook)
        notebook.add(stats_tab, text="📊 详细统计")
        self._build_detailed_stats(stats_tab, stats)

        # ── Tab 3: 日志流 ──
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="📜 日志流")
        self._build_log_stream(log_tab, entries, period)

    def _on_notebook_resize(self, notebook):
        """处理标签页大小变化"""
        width = notebook.winfo_width()
        height = notebook.winfo_height()
        # 更新所有子组件
        for tab in notebook.tabs():
            frame = notebook.nametowidget(tab)
            for child in frame.winfo_children():
                if hasattr(child, 'config'):
                    try:
                        child.config(width=width, height=height)
                    except:
                        pass

    def _build_visualization_stats(self, parent, stats, period="all"):
        """构建可视化统计Tab - 增强折线图显示"""
        # 使用 PanedWindow 实现左右分栏
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：图表区域
        left_frame = ttk.Frame(paned, padding=10)
        paned.add(left_frame, weight=3)

        # 右侧：评价指标卡片
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=1)

        # 图表容器
        chart_container = ttk.Frame(left_frame)
        chart_container.pack(fill=tk.BOTH, expand=True)

        # 获取父容器尺寸
        parent.update_idletasks()
        width = max(900, parent.winfo_width() * 0.65)
        height = max(700, parent.winfo_height() - 50)
        
        # 创建自适应大小的图表
        dpi = 100
        fig_width = min(width / dpi, 14)
        fig_height = min(height / dpi, 11)
        
        fig = Figure(figsize=(fig_width, fig_height), dpi=dpi)
        fig.patch.set_facecolor('white')

        # ============= 第一行: 进度统计 (两个图表) =============
        # 图1: 课程完成进度条形图 (左上)
        ax1 = fig.add_subplot(3, 2, 1)
        courses_data = []
        labels = []
        colors = []
        pcts = []

        for c in self.system.courses[:8]:
            cid = c.get("note_id", c.get("course_title", ""))
            pct = self.system.get_completion_pct(cid)
            title = c.get("course_title", "")[:15]
            domain = c.get("domain", "UNKNOWN")
            if pct > 0 or len(c.get("lessons", [])) > 0:
                labels.append(title)
                pcts.append(pct)
                colors.append(DOMAIN_COLORS.get(domain, "#7f8c8d"))

        if labels:
            y_pos = range(len(labels))
            ax1.barh(y_pos, [100] * len(y_pos), color='#f0f0f0', zorder=0)
            bars = ax1.barh(y_pos, pcts, color=colors, edgecolor='white', linewidth=1)
            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(labels, fontsize=8)
            ax1.set_xlim(0, 100)
            ax1.set_xlabel('完成百分比 (%)', fontsize=8)
            ax1.set_title('课程完成进度', fontsize=11, fontweight='bold')
            ax1.tick_params(axis='both', labelsize=7)
            ax1.grid(axis='x', alpha=0.3, linestyle='--')
            for i, v in enumerate(pcts):
                ax1.text(v + 1, i, f'{v:.0f}%', va='center', fontsize=7, fontweight='bold')
        else:
            ax1.text(0.5, 0.5, '暂无课程数据', ha='center', va='center', 
                    fontsize=12, color='#95a5a6')
            ax1.set_title('课程完成进度', fontsize=11, fontweight='bold')

        # 图2: 月进度折线图 (右上) - 显示每月完成进度趋势
        ax2 = fig.add_subplot(3, 2, 2)
        daily = stats.get("daily", {})
        if daily:
            # 按月聚合数据
            monthly_data = {}
            for day_str, count in daily.items():
                try:
                    year_month = day_str[:7]  # YYYY-MM
                    monthly_data[year_month] = monthly_data.get(year_month, 0) + count
                except:
                    pass
            
            if monthly_data:
                sorted_months = sorted(monthly_data.keys())
                months = [m[5:] for m in sorted_months]  # 显示 MM
                counts = [monthly_data[m] for m in sorted_months]
                
                # 绘制月进度折线图
                ax2.plot(months, counts, marker='o', linewidth=2.5, color='#27ae60', 
                        markersize=8, markeredgecolor='white', markeredgewidth=2)
                ax2.fill_between(months, counts, alpha=0.3, color='#27ae60')
                
                # 添加数值标签
                for i, (m, c) in enumerate(zip(months, counts)):
                    ax2.annotate(f'{c}', (m, c), textcoords="offset points", 
                               xytext=(0, 10), ha='center', fontsize=8, fontweight='bold')
                
                ax2.set_xlabel('月份', fontsize=8)
                ax2.set_ylabel('累计活动次数', fontsize=8)
                ax2.set_title('月进度趋势', fontsize=11, fontweight='bold')
                ax2.tick_params(axis='x', labelsize=8, rotation=45)
                ax2.tick_params(axis='y', labelsize=8)
                ax2.grid(axis='y', alpha=0.3, linestyle='--')
            else:
                ax2.text(0.5, 0.5, '暂无月进度数据', ha='center', va='center', 
                        fontsize=12, color='#95a5a6')
                ax2.set_title('月进度趋势', fontsize=11, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, '暂无月进度数据', ha='center', va='center', 
                    fontsize=12, color='#95a5a6')
            ax2.set_title('月进度趋势', fontsize=11, fontweight='bold')

        # ============= 第二行: 学习趋势折线图 (两个图表) =============
        # 图3: 每日学习活动趋势 (左中) - 增强版
        ax3 = fig.add_subplot(3, 2, 3)
        daily = stats.get("daily", {})
        if daily:
            days = []
            counts = []
            sorted_days = sorted(daily.items())
            # 至少取最近30天，如果不足则全部
            display_days = sorted_days[-30:] if len(sorted_days) > 30 else sorted_days
            for day, count in display_days:
                days.append(day[5:])  # 显示 MM-DD
                counts.append(count)
            if days:
                # 绘制双折线图（带移动平均线）
                ax3.plot(days, counts, marker='o', linewidth=2, color='#3498db', 
                        label='每日活动', markersize=4)
                ax3.fill_between(days, counts, alpha=0.2, color='#3498db')
                # 添加移动平均线
                if len(counts) >= 3:
                    import numpy as np
                    window = min(5, len(counts))
                    ma = np.convolve(counts, np.ones(window)/window, mode='same')
                    ax3.plot(days, ma, linewidth=1.5, color='#e74c3c', 
                            label=f'{window}日移动平均', linestyle='--')
                    ax3.legend(fontsize=7)
                ax3.set_ylabel('活动次数', fontsize=8)
                ax3.set_title('每日学习趋势', fontsize=11)
                # 旋转标签并减少显示数量
                if len(days) > 10:
                    ax3.set_xticks(range(0, len(days), max(1, len(days)//10)))
                    ax3.set_xticklabels([days[i] for i in range(0, len(days), max(1, len(days)//10))])
                ax3.tick_params(axis='x', rotation=45, labelsize=7)
                ax3.tick_params(axis='y', labelsize=7)
                ax3.grid(axis='y', alpha=0.3, linestyle='--')

        # 图4: 星期分布折线图 (右中)
        ax4 = fig.add_subplot(3, 2, 4)
        weekday = stats.get("weekday", {})
        if weekday:
            week_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            week_counts = [weekday.get(i, 0) for i in range(7)]
            # 绘制折线图而不是条形图
            ax4.plot(week_labels, week_counts, marker='s', linewidth=2.5, 
                    color='#9b59b6', markersize=6)
            ax4.fill_between(week_labels, week_counts, alpha=0.25, color='#9b59b6')
            ax4.set_xlabel('星期', fontsize=8)
            ax4.set_ylabel('活动次数', fontsize=8)
            ax4.set_title('学习活跃度(按星期)', fontsize=11)
            ax4.tick_params(axis='x', labelsize=7)
            ax4.tick_params(axis='y', labelsize=7)
            ax4.grid(axis='y', alpha=0.3, linestyle='--')
            # 在每个点上添加数值
            for i, count in enumerate(week_counts):
                if count > 0:
                    ax4.text(i, count + max(week_counts) * 0.03, str(count), 
                            ha='center', va='bottom', fontsize=7, color='#9b59b6', fontweight='bold')

        # ============= 第三行: 综合统计 (两个图表) =============
        # 图5: 动作类型分布 (左下)
        ax5 = fig.add_subplot(3, 2, 5)
        action_categories = stats.get("action_categories", {}).get("counts", {})
        if action_categories:
            categories = list(action_categories.keys())
            counts = list(action_categories.values())
            # 过滤无效counts，避免NaN或0导致的错误
            valid_pairs = [(cat, cnt) for cat, cnt in zip(categories, counts) 
                          if isinstance(cnt, (int, float)) and cnt > 0 and not (isinstance(cnt, float) and np.isnan(cnt))]
            if valid_pairs:
                categories = [p[0] for p in valid_pairs]
                counts = [p[1] for p in valid_pairs]
                # 用水平条形图展示动作类型
                cat_colors = ['#e74c3c', '#3498db', '#27ae60', '#f39c12', '#9b59b6', '#1abc9c', '#95a5a6', '#34495e']
                y_pos = range(len(categories))
                bars = ax5.barh(y_pos, counts, color=cat_colors[:len(categories)])
                ax5.set_yticks(y_pos)
                ax5.set_yticklabels(categories, fontsize=7.5)
                ax5.set_xlabel('次数', fontsize=8)
                ax5.set_title('动作类型分布', fontsize=11)
                ax5.tick_params(axis='x', labelsize=7)
                ax5.grid(axis='x', alpha=0.3, linestyle='--')
                # 添加数值标签
                for i, (bar, count) in enumerate(zip(bars, counts)):
                    width = bar.get_width()
                    ax5.text(width + max(counts)*0.01, i, str(count), 
                            va='center', fontsize=7)
            else:
                ax5.text(0.5, 0.5, '无有效数据', ha='center', va='center', 
                        fontsize=12, color='#95a5a6')
                ax5.set_title('动作类型分布', fontsize=11)
        else:
            ax5.text(0.5, 0.5, '暂无动作数据', ha='center', va='center', 
                    fontsize=12, color='#95a5a6')
            ax5.set_title('动作类型分布', fontsize=11)

        # 图6: 课程时间分布 (右下)
        ax6 = fig.add_subplot(3, 2, 6)
        course_times = stats.get("course_times", {})
        if course_times and len(course_times) > 0:
            # 准备数据
            course_names = []
            times_hours = []
            for course_id, seconds in sorted(course_times.items(), key=lambda x: -x[1])[:5]:
                course = self.system.get_course_by_id(course_id)
                name = course.get("course_title", course_id)[:12] if course else course_id[:12]
                course_names.append(name)
                times_hours.append(seconds / 3600)
            
            # 绘制水平条形图
            y_pos = range(len(course_names))
            colors_course = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#e74c3c']
            bars = ax6.barh(y_pos, times_hours, color=colors_course[:len(course_names)], 
                          edgecolor='white', linewidth=2)
            
            ax6.set_yticks(y_pos)
            ax6.set_yticklabels(course_names, fontsize=7.5)
            ax6.set_xlabel('专注时长 (小时)', fontsize=8)
            ax6.set_title('课程用时分布', fontsize=11)
            ax6.tick_params(axis='x', labelsize=7)
            ax6.grid(axis='x', alpha=0.3, linestyle='--')
            
            # 添加数值标签
            for i, (bar, time) in enumerate(zip(bars, times_hours)):
                width = bar.get_width()
                ax6.text(width + max(times_hours)*0.02, i, f'{time:.1f}h', 
                        va='center', fontsize=7, fontweight='bold')
        else:
            ax6.text(0.5, 0.5, '暂无课程时间数据', ha='center', va='center', 
                    fontsize=12, color='#95a5a6')
            ax6.set_title('课程时间分布', fontsize=11)

        fig.tight_layout(pad=2.0, w_pad=2.5, h_pad=3.0)
        chart_canvas = FigureCanvasTkAgg(fig, master=chart_container)
        chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 右侧：评价卡片
        evaluation = stats.get("evaluation", {})
        overall_score = evaluation.get("overall", 0)
        overall_grade = evaluation.get("overall_grade", "")
        overall_color = evaluation.get("overall_color", "#7f8c8d")

        # 综合评分卡片
        score_card = ttk.LabelFrame(right_frame, text="🏆 综合评价", padding=15)
        score_card.pack(fill=tk.X, pady=5)

        score_frame = ttk.Frame(score_card)
        score_frame.pack(pady=10)
        
        score_label = ttk.Label(score_frame, text=f"{overall_score}", font=("", 48, "bold"),
                               foreground=overall_color)
        score_label.pack()
        grade_label = ttk.Label(score_frame, text=overall_grade, font=("", 14, "bold"),
                               foreground=overall_color)
        grade_label.pack(pady=5)

        # 分项指标
        detail_frame = ttk.LabelFrame(right_frame, text="📊 分项指标", padding=10)
        detail_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        grade_details = evaluation.get("grade_details", {})
        for name, info in grade_details.items():
            row = ttk.Frame(detail_frame)
            row.pack(fill=tk.X, pady=3)
            
            ttk.Label(row, text=name, width=12, font=("", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=f"{info['score']}", font=("", 10, "bold"), 
                      foreground=info['grade'][1]).pack(side=tk.RIGHT)

        # 统计概览
        overview_frame = ttk.LabelFrame(right_frame, text="📈 统计概览", padding=10)
        overview_frame.pack(fill=tk.X, pady=5)

        focus_time = stats.get("total_focus_time", 0)
        note_count = stats.get("note_count", 0)
        complete_count = stats.get("complete_count", 0)

        ttk.Label(overview_frame, text=f"⏱️ 专注时长: {focus_time/3600:.1f}h", font=("", 9)).pack(anchor=tk.W, pady=1)
        ttk.Label(overview_frame, text=f"📝 笔记数量: {note_count}", font=("", 9)).pack(anchor=tk.W, pady=1)
        ttk.Label(overview_frame, text=f"✅ 完成课时: {complete_count}", font=("", 9)).pack(anchor=tk.W, pady=1)

    def _build_detailed_stats(self, parent, stats):
        """构建详细统计Tab - 自适应布局，增强显示"""
        # 创建子标签页：详细数据 / 日历视图
        inner_notebook = ttk.Notebook(parent)
        inner_notebook.pack(fill=tk.BOTH, expand=True)
        
        # ── 详细数据 Tab ──
        detail_tab = ttk.Frame(inner_notebook)
        inner_notebook.add(detail_tab, text="📊 详细数据")
        
        # 创建滚动容器 - 正确处理canvas宽度自适应
        canvas = tk.Canvas(detail_tab, highlightthickness=0)
        scroll = ttk.Scrollbar(detail_tab, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        
        # 配置canvas自适应宽度
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 设置canvas窗口宽度适应框架宽度
            canvas.itemconfig(1, width=event.width)
        
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(1, width=e.width))
        
        canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(frame, text="详细统计数据", font=("", 14, "bold")).pack(pady=10)

        # 基本统计卡片
        basic_frame = ttk.LabelFrame(frame, text="📊 基本统计", padding=15)
        basic_frame.pack(fill=tk.X, padx=10, pady=5)

        total_focus_h = stats.get("total_focus_time", 0) / 3600
        total_blur_h = stats.get("total_blur_time", 0) / 3600
        total_focus = stats.get("total_focus_time", 0)
        complete_count = stats.get("complete_count", 0)
        efficiency = complete_count / (total_focus / 3600) if total_focus > 0 else 0

        basic_data = [
            ("日志条目", f"{stats.get('total_entries', 0)}", "条"),
            ("专注时间", f"{total_focus_h:.1f}", "小时"),
            ("离开时间", f"{total_blur_h:.1f}", "小时"),
            ("完成课时", f"{complete_count}", "个"),
            ("笔记记录", f"{stats.get('note_count', 0)}", "条"),
            ("离开次数", f"{stats.get('blur_count', 0)}", "次"),
        ]

        for i, (label, value, unit) in enumerate(basic_data):
            row = ttk.Frame(basic_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=f"{label}:", font=("", 10), width=12).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 12, "bold"), foreground="#2980b9").pack(side=tk.LEFT)
            ttk.Label(row, text=f" {unit}", font=("", 10), foreground="#7f8c8d").pack(side=tk.LEFT)

        # 学习效率
        efficiency_frame = ttk.LabelFrame(frame, text="📈 学习效率", padding=15)
        efficiency_frame.pack(fill=tk.X, padx=10, pady=5)

        total_time = stats.get('total_focus_time', 0) + stats.get('total_blur_time', 0)
        focus_rate = (stats.get('total_focus_time', 0) / total_time * 100) if total_time > 0 else 0
        avg_per_lesson = (total_focus / complete_count / 60) if complete_count > 0 else 0

        eff_data = [
            ("专注时间占比", f"{focus_rate:.1f}%"),
            ("平均每课时时长", f"{avg_per_lesson:.0f} 分钟" if avg_per_lesson > 0 else "N/A"),
            ("学习效率", f"{efficiency:.2f} 课时/小时"),
            ("每课时平均笔记", f"{stats.get('note_count', 0) / complete_count:.1f} 条" if complete_count > 0 else "N/A"),
        ]

        for label, value in eff_data:
            row = ttk.Frame(efficiency_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=f"{label}:", font=("", 10), width=18).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 11, "bold"), foreground="#27ae60").pack(side=tk.LEFT)

        # 课程专注时间
        course_frame = ttk.LabelFrame(frame, text="⏱️ 课程专注时间", padding=15)
        course_frame.pack(fill=tk.X, padx=10, pady=5)

        course_times = stats.get("course_times", {})
        if course_times:
            max_t = max(course_times.values()) if course_times else 1
            for cid, seconds in sorted(course_times.items(), key=lambda x: -x[1])[:10]:
                course = self.system.get_course_by_id(cid)
                title = course.get("course_title", "")[:35] if course else cid[:35]
                h = seconds / 3600
                row = ttk.Frame(course_frame)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=f"{title}:", font=("", 9)).pack(side=tk.LEFT, padx=(0, 5))
                
                # 动态宽度的进度条
                bar_container = ttk.Frame(row)
                bar_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
                bar = tk.Canvas(bar_container, height=16, bg="#ecf0f1", highlightthickness=0)
                bar.pack(fill=tk.X, expand=True)
                
                # 计算进度条宽度（延迟到绘制时计算）
                def draw_bar(canvas=bar, sec=seconds, max_sec=max_t):
                    w = canvas.winfo_width()
                    if w <= 1:
                        # 还没完全显示，稍后重试
                        canvas.after(100, lambda: draw_bar(canvas, sec, max_sec))
                        return
                    bar_w = int(sec / max_sec * w) if max_sec > 0 else 0
                    canvas.create_rectangle(0, 0, bar_w, 16, fill="#3498db", outline="")
                
                bar.after(50, draw_bar)
                
                ttk.Label(row, text=f"{h:.1f}h", font=("", 9), width=8).pack(side=tk.LEFT)
        else:
            ttk.Label(course_frame, text="暂无课时数据", foreground="#95a5a6").pack()

        # 动作统计
        action_frame = ttk.LabelFrame(frame, text="🎯 动作统计", padding=15)
        action_frame.pack(fill=tk.X, padx=10, pady=5)

        action_counts = stats.get("action_counts", {})
        if action_counts:
            max_count = max(action_counts.values()) if action_counts else 1
            for action, count in sorted(action_counts.items(), key=lambda x: -x[1])[:15]:
                row = ttk.Frame(action_frame)
                row.pack(fill=tk.X, pady=1)
                ttk.Label(row, text=f"• {action}", font=("", 9), width=25).pack(side=tk.LEFT)
                
                # 动态宽度的进度条
                bar_container = ttk.Frame(row)
                bar_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
                bar = tk.Canvas(bar_container, height=12, bg="#ecf0f1", highlightthickness=0)
                bar.pack(fill=tk.X, expand=True)
                
                def draw_action_bar(canvas=bar, cnt=count, max_cnt=max_count):
                    w = canvas.winfo_width()
                    if w <= 1:
                        canvas.after(100, lambda: draw_action_bar(canvas, cnt, max_cnt))
                        return
                    pct = cnt / max_cnt * 100
                    bar_w = int(pct / 100 * w)
                    canvas.create_rectangle(0, 0, bar_w, 12, fill="#9b59b6", outline="")
                
                bar.after(50, draw_action_bar)
                
                ttk.Label(row, text=f"{count}次", font=("", 9), width=8).pack(side=tk.LEFT)
        else:
            ttk.Label(action_frame, text="暂无动作数据", foreground="#95a5a6").pack()
        
        # 添加底部padding
        ttk.Frame(frame, height=20).pack()
        
        # ── 日历视图 Tab ──
        calendar_tab = ttk.Frame(inner_notebook)
        inner_notebook.add(calendar_tab, text="📅 日历视图")
        self._build_calendar_view(calendar_tab, stats)

    def _build_calendar_view(self, parent, stats):
        """构建增强版日历视图"""
        # 保存 stats 引用
        self._cal_current_stats = stats
        
        # 整体容器
        calendar_main = ttk.Frame(parent)
        calendar_main.pack(fill=tk.BOTH, expand=True)
        
        # ========== 顶部控制栏 ==========
        control_frame = ttk.LabelFrame(calendar_main, text="📅 日历导航", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        nav_frame = ttk.Frame(control_frame)
        nav_frame.pack(fill=tk.X)
        
        # 年份选择器
        year_frame = ttk.Frame(nav_frame)
        year_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(year_frame, text="年份:").pack(side=tk.LEFT)
        self.cal_year = tk.IntVar(value=datetime.now().year)
        year_spin = ttk.Spinbox(year_frame, from_=2020, to=2030, textvariable=self.cal_year, 
                               width=6, command=lambda: self._render_calendar(stats))
        year_spin.pack(side=tk.LEFT, padx=3)
        
        # 月份选择器
        month_frame = ttk.Frame(nav_frame)
        month_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(month_frame, text="月份:").pack(side=tk.LEFT)
        self.cal_month = tk.IntVar(value=datetime.now().month)
        months = ["1月", "2月", "3月", "4月", "5月", "6月", 
                  "7月", "8月", "9月", "10月", "11月", "12月"]
        month_combo = ttk.Combobox(month_frame, textvariable=self.cal_month, 
                                   values=list(range(1, 13)), width=4, state="readonly")
        month_combo.pack(side=tk.LEFT, padx=3)
        month_combo.bind("<<ComboboxSelected>>", lambda e: self._render_calendar(stats))
        
        # 导航按钮
        nav_buttons = ttk.Frame(nav_frame)
        nav_buttons.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(nav_buttons, text="◀ 上月", 
                  command=lambda: self._change_month(-1)).pack(side=tk.LEFT, padx=2)
        
        self._cal_month_label = ttk.Label(nav_buttons, text="", 
                                         font=("", 12, "bold"), width=15)
        self._cal_month_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(nav_buttons, text="下月 ▶", 
                  command=lambda: self._change_month(1)).pack(side=tk.LEFT, padx=2)
        
        # 返回今天按钮
        ttk.Button(nav_frame, text="📌 今天", 
                  command=lambda: self._go_to_today(stats)).pack(side=tk.RIGHT, padx=5)
        
        # ========== 日历网格 ==========
        calendar_grid_frame = ttk.Frame(calendar_main)
        calendar_grid_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        # 日历网格容器
        self._cal_container = ttk.Frame(calendar_grid_frame)
        self._cal_container.pack(fill=tk.BOTH, expand=True)
        
        # 星期标题
        week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i, day in enumerate(week_days):
            bg_color = "#e74c3c" if i >=5 else "#2c3e50"
            lbl = tk.Label(self._cal_container, text=day, 
                           font=("", 10, "bold"),
                           bg=bg_color, fg="white",
                           padx=5, pady=8)
            lbl.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
        
        # 配置列权重
        for i in range(7):
            self._cal_container.grid_columnconfigure(i, weight=1)
        
        # 日期网格
        self._cal_days = {}
        self._render_calendar(stats)
        
        # ========== 图例说明 ==========
        legend_frame = ttk.LabelFrame(calendar_main, text="📊 活动强度图例", padding=10)
        legend_frame.pack(fill=tk.X, padx=10, pady=10)
        
        legend_inner = ttk.Frame(legend_frame)
        legend_inner.pack(fill=tk.X)
        
        # 活动强度图例
        intensity_labels = [
            ("无活动", "#ecf0f1"),
            ("低 (1-3次)", "#a8d4e8"),
            ("中 (4-6次)", "#5dade2"),
            ("高 (7-9次)", "#3498db"),
            ("很高 (10+次)", "#2980b9"),
        ]
        
        for label, color in intensity_labels:
            item_frame = ttk.Frame(legend_inner)
            item_frame.pack(side=tk.LEFT, padx=10)
            color_box = tk.Label(item_frame, bg=color, width=8, height=2, relief="solid", borderwidth=1)
            color_box.pack(side=tk.LEFT, padx=3)
            ttk.Label(item_frame, text=label, font=("", 9)).pack(side=tk.LEFT)
        
        # 特殊标记说明
        today_marker = ttk.Frame(legend_inner)
        today_marker.pack(side=tk.RIGHT)
        today_box = tk.Label(today_marker, bg="#f39c12", width=8, height=2, relief="solid", borderwidth=2)
        today_box.pack(side=tk.LEFT, padx=3)
        ttk.Label(today_marker, text="今天", font=("", 9)).pack(side=tk.LEFT)

    def _render_calendar(self, stats):
        """渲染日历"""
        year = self.cal_year.get()
        month = self.cal_month.get()
        
        # 更新月份标签
        self._cal_month_label.config(text=f"{year}年 {month}月")
        
        # 清除旧的日期
        for widget in self._cal_container.grid_slaves():
            if int(widget.grid_info()["row"]) > 0:
                widget.destroy()
        
        # 获取当月第一天和天数
        first_day = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        days_in_month = (next_month - first_day).days
        
        # 确定起始位置 (0=周一)
        start_col = first_day.weekday()
        
        # 获取每日活动数据
        daily = stats.get("daily", {})
        
        # 计算当月总活动次数
        total_activities = sum(daily.get(f"{year}-{month:02d}-{d:02d}", 0) for d in range(1, days_in_month + 1))
        
        # 渲染日期
        row = 1
        col = start_col
        
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            date_str = d.strftime("%Y-%m-%d")
            count = daily.get(date_str, 0)
            
            # 日期容器
            day_frame = tk.Frame(self._cal_container, bg="#ecf0f1", padx=4, pady=4)
            day_frame.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
            day_frame.bind("<Button-1>", lambda e, dt=d, cnt=count: self._on_calendar_click(dt, cnt))
            
            # 日期标签
            date_lbl = tk.Label(day_frame, text=str(day), font=("", 11, "bold"), bg="#ecf0f1")
            date_lbl.pack(anchor="n")
            
            # 活动指示器
            if count > 0:
                # 根据活动次数选择颜色
                if count <= 3:
                    color = "#a8d4e8"
                elif count <= 6:
                    color = "#5dade2"
                elif count <= 9:
                    color = "#3498db"
                else:
                    color = "#2980b9"
                
                # 活动数量标签
                info_lbl = tk.Label(day_frame, text=f"{count}次", 
                                    font=("", 9), fg="white", bg=color,
                                    padx=4, pady=1)
                info_lbl.pack(anchor="s")
                
                # 更新背景颜色
                day_frame.configure(bg=color)
                date_lbl.configure(bg=color, fg="white")
            else:
                # 无活动显示横线
                empty_lbl = tk.Label(day_frame, text="—", font=("", 10), fg="#bdc3c7", bg="#ecf0f1")
                empty_lbl.pack(anchor="s")
            
            # 今天高亮
            if d == date.today():
                day_frame.configure(bg="#f39c12", relief="solid", borderwidth=2)
                date_lbl.configure(bg="#f39c12", fg="white")
                # 移除活动指示器的白色
                for child in day_frame.winfo_children():
                    if child != date_lbl:
                        child.destroy()
            
            self._cal_days[date_str] = day_frame
            
            col += 1
            if col > 6:
                col = 0
                row += 1

    def _change_month(self, delta):
        """切换月份"""
        month = self.cal_month.get() + delta
        year = self.cal_year.get()
        
        if month > 12:
            month = 1
            year += 1
        elif month < 1:
            month = 12
            year -= 1
        
        self.cal_year.set(year)
        self.cal_month.set(month)
        
        # 重新渲染日历
        self._render_calendar(self._cal_current_stats)
    
    def _go_to_today(self, stats):
        """跳转到今天"""
        today = datetime.now()
        self.cal_year.set(today.year)
        self.cal_month.set(today.month)
        self._render_calendar(stats)
    
    def _on_calendar_click(self, date_obj, count):
        """点击日期时显示详情"""
        date_str = date_obj.strftime("%Y年%m月%d日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date_obj.weekday()]
        
        if count > 0:
            messagebox.showinfo("📅 当日详情", 
                               f"{date_str} ({weekday})\n\n"
                               f"学习活动次数: {count} 次")
        else:
            messagebox.showinfo("📅 当日详情", 
                               f"{date_str} ({weekday})\n\n"
                               f"该日暂无学习记录")

    def _build_log_stream(self, parent, entries, period="all"):
        """构建日志流Tab - 自适应布局"""
        # 根据时间范围筛选日志
        filtered_entries = self._filter_entries_by_period(entries, period)
        
        # 快捷笔记
        note_tb = ttk.Frame(parent)
        note_tb.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(note_tb, text="📌 快速笔记：", font=("", 10, "bold")).pack(side=tk.LEFT)
        note_var = tk.StringVar()
        note_entry = ttk.Entry(note_tb, textvariable=note_var, font=("", 9))
        note_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        def _add_log_note():
            text = note_var.get().strip()
            if text:
                self.wflogger.log_note(text)
                note_var.set("")
                self._show_workflow_log(period)

        note_entry.bind("<Return>", lambda e: _add_log_note())
        ttk.Button(note_tb, text="添加", command=_add_log_note).pack(side=tk.LEFT, padx=3)

        # 日志树容器
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("time", "type", "course", "lesson", "detail")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        tree.heading("time", text="时间")
        tree.heading("type", text="类型")
        tree.heading("course", text="课程")
        tree.heading("lesson", text="课时")
        tree.heading("detail", text="详情")

        # 设置列权重
        tree.column("time", width=120, stretch=tk.NO)
        tree.column("type", width=100, anchor="center", stretch=tk.NO)
        tree.column("course", width=150, stretch=tk.YES)
        tree.column("lesson", width=60, anchor="center", stretch=tk.NO)
        tree.column("detail", width=200, stretch=tk.YES)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 响应窗口大小变化
        def _on_tree_resize(event):
            width = tree_frame.winfo_width()
            # 动态调整列宽
            tree.column("course", width=int(width * 0.2))
            tree.column("detail", width=int(width * 0.4))

        tree_frame.bind("<Configure>", _on_tree_resize)

        type_icons = {
            "timer_start": "▶️", "timer_stop": "⏹️", "action": "⚡",
            "note": "📝", "blur": "👋", "focus_return": "👋",
            "lesson_complete": "✅",
        }

        for e in reversed(filtered_entries):
            ts = e.get("timestamp", "")
            etype = e.get("type", "")
            cid = e.get("course_id", "")
            ln = e.get("lesson_number", "")
            action = e.get("action", "")
            detail = e.get("detail", "")

            type_text = f"{type_icons.get(etype, '•')} {etype}"
            course_title = ""
            if cid:
                course = self.system.get_course_by_id(cid)
                course_title = course.get("course_title", cid)[:30] if course else cid[:30]

            if action:
                display_detail = f"{action}: {detail[:100]}" if detail else action
            else:
                display_detail = detail[:100] if detail else ""

            time_short = ts[11:19] if len(ts) >= 19 else ts

            tree.insert("", 0, values=(
                time_short, type_text, course_title,
                f"L{ln}" if ln else "",
                display_detail
            ))

        tree.tag_configure("note", foreground="#27ae60")
        tree.tag_configure("action", foreground="#2980b9")
        tree.tag_configure("blur", foreground="#e67e22")
        tree.tag_configure("lesson_complete", foreground="#8e44ad")

    def _filter_entries_by_period(self, entries, period):
        """根据时间周期筛选日志条目"""
        if period == "all":
            return entries
        
        today = datetime.now().date()
        start_date = end_date = None
        
        if period == "today":
            start_date = end_date = today.strftime("%Y-%m-%d")
        elif period == "yesterday":
            yesterday = today - timedelta(days=1)
            start_date = end_date = yesterday.strftime("%Y-%m-%d")
        elif period == "week":
            monday = today - timedelta(days=today.weekday())
            start_date = monday.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif period == "last_week":
            last_monday = today - timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + timedelta(days=6)
            start_date = last_monday.strftime("%Y-%m-%d")
            end_date = last_sunday.strftime("%Y-%m-%d")
        elif period == "month":
            first_day = today.replace(day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif period == "last_month":
            last_month = today.replace(day=1) - timedelta(days=1)
            first_day = last_month.replace(day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = last_month.strftime("%Y-%m-%d")
        elif period == "year":
            first_day = today.replace(month=1, day=1)
            start_date = first_day.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        
        if start_date and end_date:
            return [e for e in entries if start_date <= e.get("timestamp", "")[:10] <= end_date]
        
        return entries

    def _clear_workflow_log(self):
        """清空工作流日志"""
        if messagebox.askyesno("确认清空", "确定要清空所有工作日志吗？\n此操作不可撤销。"):
            self.wflogger.clear()
            self._show_workflow_log()

    def _confirm_reset(self, course_id):
        """确认重置"""
        if messagebox.askyesno("确认重置", f"确定要重置课程进度吗？\n此操作不可撤销。"):
            self.system.reset_course(course_id)
            self._refresh_overview()

    def _confirm_delete_course(self, course_id):
        """确认删除课程"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            return
        title = course.get("course_title", course_id)
        hours = course.get("total_hours", "?")
        n_lessons = len(course.get("lessons", []))
        msg = (f"确定要删除课程吗？\n\n"
               f"课程：{title}\n"
               f"课时：{hours}τ / {n_lessons}条\n\n"
               f"将同时删除：进度记录、资源索引、JSON数据\n"
               f"此操作不可撤销！")
        if messagebox.askyesno("⚠️ 确认删除课程", msg):
            self.system.remove_course(course_id)
            self._refresh_overview()

    def _show_duplicates(self):
        """检测并展示重复课程，支持选择性删除"""
        dupes = self.system.find_duplicates()
        if not dupes:
            messagebox.showinfo("检测完成", "未发现重复课程")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("🔍 重复课程检测")
        dlg.geometry("800x500")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"发现 {len(dupes)} 组重复课程",
                  font=("", 13, "bold"), foreground="#c0392b").pack(pady=(10, 5))

        cols = ("select", "title", "domain", "hours", "lessons", "source")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", height=18)
        tree.heading("select", text="删除?")
        tree.heading("title", text="课程标题")
        tree.heading("domain", text="域")
        tree.heading("hours", text="课时")
        tree.heading("lessons", text="条目")
        tree.heading("source", text="来源文件")
        tree.column("select", width=50, anchor="center")
        tree.column("title", width=280)
        tree.column("domain", width=80, anchor="center")
        tree.column("hours", width=60, anchor="center")
        tree.column("lessons", width=60, anchor="center")
        tree.column("source", width=150)

        ts = ttk.Scrollbar(dlg, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ts.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        ts.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        right = ttk.Frame(dlg, padding=8)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=5)

        row_map = {}
        for base, courses in dupes.items():
            for i, c in enumerate(courses):
                cid = c.get("note_id", c.get("course_title", ""))
                title = c.get("course_title", "")
                domain = c.get("domain", "UNKNOWN")
                hours = c.get("total_hours", "?")
                n_lessons = len(c.get("lessons", []))
                source = c.get("source_file", "")
                if source:
                    source = Path(source).name[:40]
                mark = "✅ 保留" if i == 0 else "🗑️ 删除"
                iid = tree.insert("", "end", values=(mark, title, DOMAIN_NAMES.get(domain, domain),
                                                      hours, n_lessons, source))
                row_map[iid] = (cid, i == 0)
                if i > 0:
                    tree.item(iid, tags=("dup",))
            tree.tag_configure("dup", foreground="#e74c3c")

        def _toggle_select():
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            cid, is_keep = row_map[iid]
            row_map[iid] = (cid, not is_keep)
            mark = "✅ 保留" if not is_keep else "🗑️ 删除"
            vals = list(tree.item(iid, "values"))
            vals[0] = mark
            tree.item(iid, values=vals, tags=("dup",) if not is_keep else ())

        def _delete_selected():
            to_delete = [cid for iid, (cid, is_keep) in row_map.items() if not is_keep]
            if not to_delete:
                messagebox.showinfo("提示", "未选择要删除的课程", parent=dlg)
                return
            if not messagebox.askyesno("确认", f"将删除 {len(to_delete)} 门课程，继续？", parent=dlg):
                return
            for cid in to_delete:
                self.system.remove_course(cid)
            dlg.destroy()
            self._refresh_all()

        ttk.Button(right, text="🔄 切换保留/删除", command=_toggle_select).pack(fill=tk.X, pady=(10, 5))
        ttk.Button(right, text="🗑️ 删除选中", command=_delete_selected).pack(fill=tk.X, pady=5)
        ttk.Button(right, text="❌ 取消", command=dlg.destroy).pack(fill=tk.X, pady=5)

        ttk.Label(right, text="点击课程行后\n点击切换按钮\n标记删除/保留",
                  font=("", 9), foreground="#7f8c8d").pack(pady=10)

    def _show_batch_delete(self):
        """批量选择删除课程"""
        dlg = tk.Toplevel(self.root)
        dlg.title("🗑️ 批量删除课程")
        dlg.geometry("700x500")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"选择要删除的课程（共 {len(self.system.courses)} 门）",
                  font=("", 13, "bold"), foreground="#2C3E50").pack(pady=(10, 5))

        cols = ("select", "title", "domain", "hours", "lessons")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", height=18)
        tree.heading("select", text="删除?")
        tree.heading("title", text="课程标题")
        tree.heading("domain", text="域")
        tree.heading("hours", text="课时")
        tree.heading("lessons", text="条目")
        tree.column("select", width=50, anchor="center")
        tree.column("title", width=320)
        tree.column("domain", width=100, anchor="center")
        tree.column("hours", width=60, anchor="center")
        tree.column("lessons", width=60, anchor="center")

        ts = ttk.Scrollbar(dlg, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ts.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        ts.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        right = ttk.Frame(dlg, padding=8)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=5)

        row_map = {}
        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "")
            domain = c.get("domain", "UNKNOWN")
            hours = c.get("total_hours", "?")
            n_lessons = len(c.get("lessons", []))
            iid = tree.insert("", "end", values=("☐", title, DOMAIN_NAMES.get(domain, domain),
                                                   hours, n_lessons))
            row_map[iid] = (cid, False)

        def _toggle():
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            cid, marked = row_map[iid]
            row_map[iid] = (cid, not marked)
            mark = "☑️" if not marked else "☐"
            vals = list(tree.item(iid, "values"))
            vals[0] = mark
            tree.item(iid, values=vals, tags=("del",) if not marked else ())

        tree.tag_configure("del", foreground="#e74c3c")

        def _delete():
            to_delete = [cid for iid, (cid, marked) in row_map.items() if marked]
            if not to_delete:
                messagebox.showinfo("提示", "未选择要删除的课程", parent=dlg)
                return
            if not messagebox.askyesno("⚠️ 确认", f"将删除 {len(to_delete)} 门课程及其所有数据，继续？", parent=dlg):
                return
            for cid in to_delete:
                self.system.remove_course(cid)
            dlg.destroy()
            self._refresh_all()

        ttk.Button(right, text="☑️ 切换选择", command=_toggle).pack(fill=tk.X, pady=(10, 5))
        ttk.Button(right, text="🗑️ 删除选中", command=_delete).pack(fill=tk.X, pady=5)
        ttk.Button(right, text="❌ 取消", command=dlg.destroy).pack(fill=tk.X, pady=5)

        ttk.Label(right, text="点击课程行后\n点击切换选择\n标记要删除的课程",
                  font=("", 9), foreground="#7f8c8d").pack(pady=10)

    def _show_review_reminder(self, course_id):
        """显示待复习课时列表，支持一键复习+自动打开笔记"""
        due = self.system.get_due_reviews(course_id)
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        if not due:
            messagebox.showinfo("复习提醒", "暂无待复习课时 🎉")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("🔄 循环复习提醒")
        dlg.geometry("600x450")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"📚 {course.get('course_title', '')} — 待复习课时",
                  font=("", 13, "bold"), foreground="#2C3E50").pack(pady=(10, 5))
        ttk.Label(dlg, text=f"工作量越大 → 复习间隔越短，共 {len(due)} 个课时待复习",
                  font=("", 9), foreground="#7F8C8D").pack(pady=(0, 5))

        cols = ("lesson", "title", "workload", "interval", "overdue")
        tree = ttk.Treeview(dlg, columns=cols, show="headings", height=14)
        tree.heading("lesson", text="课时")
        tree.heading("title", text="标题")
        tree.heading("workload", text="工作量")
        tree.heading("interval", text="间隔(天)")
        tree.heading("overdue", text="逾期(天)")
        tree.column("lesson", width=60, anchor="center")
        tree.column("title", width=250)
        tree.column("workload", width=80, anchor="center")
        tree.column("interval", width=80, anchor="center")
        tree.column("overdue", width=80, anchor="center")

        ts = ttk.Scrollbar(dlg, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ts.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=5)
        ts.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        right = ttk.Frame(dlg, padding=8)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=5)

        lesson_map = {}
        lessons = {l.get("lesson_number"): l for l in course.get("lessons", [])}
        for d in due:
            lnum = d["lesson_number"]
            linfo = lessons.get(lnum, {})
            title = linfo.get("lesson_title", f"课时 {lnum}")
            iid = tree.insert("", "end", values=(
                lnum, title, d["workload"], d["interval_days"], d["overdue_days"]))
            lesson_map[iid] = lnum
            if d["overdue_days"] > 3:
                tree.item(iid, tags=("urgent",))
            elif d["overdue_days"] > 0:
                tree.item(iid, tags=("due",))
        tree.tag_configure("urgent", foreground="#c0392b")
        tree.tag_configure("due", foreground="#e67e22")

        def _review_selected():
            sel = tree.selection()
            if not sel:
                return
            lnum = lesson_map[sel[0]]
            self.system.mark_review_done(course_id, lnum)
            path, _ = self.system.get_or_create_note(course_id, lnum)
            if path and path.exists():
                open_file(str(path))
            vals = list(tree.item(sel[0], "values"))
            tree.delete(sel[0])
            lesson_map.pop(sel[0], None)
            if tree.get_children():
                ch = tree.get_children()[0]
                tree.selection_set(ch)
            if not tree.get_children():
                dlg.destroy()
                messagebox.showinfo("复习完成", "所有待复习课时已处理 🎉")

        def _review_all():
            for iid in list(tree.get_children()):
                lnum = lesson_map[iid]
                self.system.mark_review_done(course_id, lnum)
            dlg.destroy()
            messagebox.showinfo("复习完成", f"已标记 {len(lesson_map)} 个课时复习完成")

        ttk.Button(right, text="📖 复习选中+打开笔记", command=_review_selected).pack(fill=tk.X, pady=(10, 5))
        ttk.Button(right, text="✅ 全部标记已复习", command=_review_all).pack(fill=tk.X, pady=5)
        ttk.Button(right, text="❌ 关闭", command=dlg.destroy).pack(fill=tk.X, pady=5)

        ttk.Label(right, text="复习选中课时将\n自动打开对应笔记\n并标记复习完成",
                  font=("", 9), foreground="#7f8c8d").pack(pady=10)

        if tree.get_children():
            tree.selection_set(tree.get_children()[0])

    def _refresh_overview(self):
        self._show_overview()


# ============================================================
# 入口
# ============================================================

    def _show_tree_editor(self):
        """Excel风格的Treeview课程管理编辑器"""
        self._clear_content()
        self._highlight_nav("manage")
        self.nav_title.config(text="📋 课程管理编辑器")

        main_paned = tk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL,
                                     sashrelief=tk.RAISED, sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_paned, width=300)
        main_paned.add(left_frame, width=320)

        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame)

        self._tree_editor_build_left(left_frame)
        self._tree_editor_build_right(right_frame)

    def _tree_editor_build_left(self, parent):
        """构建左侧：课程列表Treeview"""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(header, text="📚 课程列表", font=("", 12, "bold")).pack(side=tk.LEFT)
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="➕", width=3,
                   command=self._tree_editor_add_course).pack(side=tk.LEFT, padx=1)
        ttk.Button(btn_frame, text="🗑️", width=3,
                   command=self._tree_editor_delete_course).pack(side=tk.LEFT, padx=1)
        ttk.Button(btn_frame, text="🔄", width=3,
                   command=self._tree_editor_refresh_courses).pack(side=tk.LEFT, padx=1)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("domain", "lessons", "hours")
        self._course_tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings",
                                         height=25, selectmode="browse")
        self._course_tree.heading("#0", text="课程名称")
        self._course_tree.heading("domain", text="域")
        self._course_tree.heading("lessons", text="课时")
        self._course_tree.heading("hours", text="总课时")

        self._course_tree.column("#0", width=200)
        self._course_tree.column("domain", width=60, anchor="center")
        self._course_tree.column("lessons", width=50, anchor="center")
        self._course_tree.column("hours", width=60, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._course_tree.yview)
        self._course_tree.configure(yscrollcommand=vsb.set)
        self._course_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._course_tree.tag_configure("selected", background="#E3F2FD")
        self._course_tree.bind("<<TreeviewSelect>>", self._tree_editor_on_course_select)
        self._course_tree.bind("<Double-1>", lambda e: self._tree_editor_edit_course())

        self._tree_editor_refresh_courses()

    def _tree_editor_refresh_courses(self):
        """刷新课程列表"""
        for item in self._course_tree.get_children():
            self._course_tree.delete(item)

        for c in self.system.courses:
            cid = c.get("note_id", c.get("course_title", ""))
            title = c.get("course_title", "未知课程")
            domain = c.get("domain", "UNKNOWN")
            n_lessons = len(c.get("lessons", []))
            hours = c.get("total_hours", "?")

            color = DOMAIN_COLORS.get(domain, "#7f8c8d")
            self._course_tree.insert("", "end", iid=cid, text=title,
                                     values=(domain, n_lessons, hours),
                                     tags=("course",))
            self._course_tree.tag_bind(cid, "<<TreeviewSelect>>",
                                       lambda e, c=cid: self._tree_editor_on_course_select(e, c))

        if hasattr(self, '_course_tree') and self._course_tree.get_children():
            if not self._course_tree.selection():
                first = self._course_tree.get_children()[0]
                self._course_tree.selection_set(first)
                self._course_tree.focus(first)

    def _tree_editor_on_course_select(self, event, course_id=None):
        """课程选中事件"""
        if course_id is None:
            sel = self._course_tree.selection()
            if not sel:
                return
            course_id = sel[0]

        for item in self._course_tree.get_children():
            self._course_tree.item(item, tags=("course",))
        self._course_tree.item(course_id, tags=("selected", "course"))

        self._current_editor_course = course_id
        self._tree_editor_load_lessons(course_id)

    def _tree_editor_add_course(self):
        """添加新课程"""
        dlg = tk.Toplevel(self.root)
        dlg.title("➕ 新建课程")
        dlg.geometry("500x400")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="新建课程", font=("", 14, "bold")).pack(pady=10)

        form_frame = ttk.Frame(dlg, padding=15)
        form_frame.pack(fill=tk.BOTH, expand=True)

        fields = {}
        row = 0
        for label, key, default in [
            ("课程名称", "title", ""),
            ("学科域", "domain", "UNKNOWN"),
            ("总课时", "hours", ""),
            ("授课对象", "audience", ""),
            ("考核方式", "assessment", ""),
            ("课程定位", "positioning", ""),
        ]:
            ttk.Label(form_frame, text=f"{label}：").grid(row=row, column=0, sticky="e", pady=5)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(form_frame, textvariable=var, width=35)
            entry.grid(row=row, column=1, sticky="w", pady=5, padx=5)
            fields[key] = var
            row += 1

        ttk.Label(form_frame, text="先修课程：").grid(row=row, column=0, sticky="ne", pady=5)
        prereq_frame = ttk.Frame(form_frame)
        prereq_frame.grid(row=row, column=1, sticky="w", pady=5, padx=5)
        prereq_var = tk.StringVar()
        ttk.Entry(prereq_frame, textvariable=prereq_var, width=35).pack()
        ttk.Label(prereq_frame, text="多个用逗号分隔", font=("", 8), foreground="#888").pack()

        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)

        def _confirm():
            title = fields["title"].get().strip()
            if not title:
                messagebox.showwarning("警告", "课程名称不能为空", parent=dlg)
                return

            domain = fields["domain"].get().strip() or "UNKNOWN"
            hours_str = fields["hours"].get().strip()
            hours = int(hours_str) if hours_str.isdigit() else None

            prereqs = [p.strip() for p in prereq_var.get().split(",") if p.strip()]

            course = {
                "note_id": f"new_{hashlib.md5(title.encode()).hexdigest()[:16]}",
                "course_title": title,
                "total_hours": hours,
                "domain": domain,
                "prerequisites": prereqs,
                "positioning": fields["positioning"].get().strip(),
                "target_audience": fields["audience"].get().strip(),
                "assessment": fields["assessment"].get().strip(),
                "sections": [],
                "lessons": [],
                "references": [],
            }

            self.system.courses.append(course)
            key = course["note_id"]
            self.progress[key] = {
                "completed_lessons": [],
                "current_lesson": None,
                "started_at": None,
                "last_updated": None,
                "review_schedule": {},
            }
            self._save_progress()

            self._tree_editor_refresh_courses()
            self._course_tree.selection_set(key)
            self._course_tree.see(key)
            dlg.destroy()
            self._log(f"✅ 新建课程: 《{title}》[{domain}]")

        ttk.Button(btn_frame, text="✅ 创建", command=_confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)

    def _tree_editor_delete_course(self):
        """删除选中课程"""
        sel = self._course_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的课程")
            return

        course_id = sel[0]
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        title = course.get("course_title", "")
        n_lessons = len(course.get("lessons", []))

        if messagebox.askyesno("确认删除",
            f"确定要删除课程「{title}」吗？\n\n将同时删除：\n- {n_lessons} 个课时\n- 进度记录\n- 资源索引\n\n此操作不可撤销！"):
            self.system.remove_course(course_id)
            self._tree_editor_refresh_courses()
            if hasattr(self, '_lesson_tree'):
                for item in self._lesson_tree.get_children():
                    self._lesson_tree.delete(item)

    def _tree_editor_edit_course(self):
        """编辑选中课程基本信息"""
        sel = self._course_tree.selection()
        if not sel:
            return

        course_id = sel[0]
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("✏️ 编辑课程信息")
        dlg.geometry("500x450")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"编辑：{course.get('course_title', '')}",
                 font=("", 13, "bold")).pack(pady=10)

        form_frame = ttk.Frame(dlg, padding=15)
        form_frame.pack(fill=tk.BOTH, expand=True)

        fields = {}
        row = 0
        for label, key, value in [
            ("课程名称", "title", course.get("course_title", "")),
            ("学科域", "domain", course.get("domain", "UNKNOWN")),
            ("总课时", "hours", str(course.get("total_hours", ""))),
            ("授课对象", "audience", course.get("target_audience", "")),
            ("考核方式", "assessment", course.get("assessment", "")),
            ("课程定位", "positioning", course.get("positioning", "")),
        ]:
            ttk.Label(form_frame, text=f"{label}：").grid(row=row, column=0, sticky="e", pady=5)
            var = tk.StringVar(value=value)
            entry = ttk.Entry(form_frame, textvariable=var, width=35)
            entry.grid(row=row, column=1, sticky="w", pady=5, padx=5)
            fields[key] = var
            row += 1

        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)

        def _save():
            title = fields["title"].get().strip()
            if not title:
                messagebox.showwarning("警告", "课程名称不能为空", parent=dlg)
                return

            course["course_title"] = title
            course["domain"] = fields["domain"].get().strip() or "UNKNOWN"
            hours_str = fields["hours"].get().strip()
            course["total_hours"] = int(hours_str) if hours_str.isdigit() else None
            course["target_audience"] = fields["audience"].get().strip()
            course["assessment"] = fields["assessment"].get().strip()
            course["positioning"] = fields["positioning"].get().strip()

            for p in self.system.db_paths:
                data = load_json_safe(p)
                if not data:
                    continue
                for ci, c in enumerate(data.get("courses", [])):
                    if c.get("note_id") == course_id or c.get("course_title") == title:
                        data["courses"][ci] = course
                        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        break

            self._tree_editor_refresh_courses()
            self._course_tree.selection_set(course_id)
            dlg.destroy()
            self._log(f"✅ 更新课程: 《{title}》")

        ttk.Button(btn_frame, text="💾 保存", command=_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)

    def _tree_editor_build_right(self, parent):
        """构建右侧：课时编辑区域"""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 5))

        self._lesson_header_label = ttk.Label(header, text="选择左侧课程以编辑课时",
                                              font=("", 12, "bold"))
        self._lesson_header_label.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="➕ 添加课时", width=10,
                   command=self._tree_editor_add_lesson).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✏️ 编辑", width=8,
                   command=self._tree_editor_edit_lesson).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 删除", width=8,
                   command=self._tree_editor_delete_lesson).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⬆️ 上移", width=8,
                   command=lambda: self._tree_editor_move_lesson(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⬇️ 下移", width=8,
                   command=lambda: self._tree_editor_move_lesson(1)).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("num", "title", "section", "question", "hours", "status")
        self._lesson_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                         height=25, selectmode="browse")
        self._lesson_tree.heading("num", text="#")
        self._lesson_tree.heading("title", text="课时标题")
        self._lesson_tree.heading("section", text="所属Section")
        self._lesson_tree.heading("question", text="中心问题")
        self._lesson_tree.heading("hours", text="预计课时")
        self._lesson_tree.heading("status", text="状态")

        self._lesson_tree.column("num", width=50, anchor="center")
        self._lesson_tree.column("title", width=280)
        self._lesson_tree.column("section", width=100, anchor="center")
        self._lesson_tree.column("question", width=250)
        self._lesson_tree.column("hours", width=70, anchor="center")
        self._lesson_tree.column("status", width=60, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._lesson_tree.yview)
        self._lesson_tree.configure(yscrollcommand=vsb.set)
        self._lesson_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._lesson_tree.tag_configure("done", foreground="#27AE60")
        self._lesson_tree.tag_configure("pending", foreground="#000000")
        self._lesson_tree.bind("<Double-1>", lambda e: self._tree_editor_edit_lesson())

        hint = ttk.Label(parent, text="💡 双击行编辑课时 | 使用按钮增删改课程和课时",
                        font=("", 9), foreground="#888")
        hint.pack(pady=5)

    def _tree_editor_load_lessons(self, course_id):
        """加载课程课时到右侧Treeview"""
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        title = course.get("course_title", "")
        self._lesson_header_label.config(text=f"📖 {title} — 课时列表")

        for item in self._lesson_tree.get_children():
            self._lesson_tree.delete(item)

        lessons = course.get("lessons", [])
        completed = set(self.system.get_course_progress(course_id).get("completed_lessons", []))

        for idx, lesson in enumerate(lessons, 1):
            lnum = lesson.get("lesson_number", idx)
            ltitle = lesson.get("lesson_title", "")
            section = lesson.get("section", "")
            question = lesson.get("central_question", "")
            hours = lesson.get("estimated_hours", "")
            is_done = lnum in completed
            status = "✅ 完成" if is_done else "⬜ 未完成"

            tag = "done" if is_done else "pending"
            iid = str(lnum)
            # 确保iid不存在再插入（防止快速切换时的并发问题）
            try:
                if iid in self._lesson_tree.get_children():
                    self._lesson_tree.delete(iid)
                self._lesson_tree.insert("", "end", iid=iid,
                                         values=(lnum, ltitle, section, question, hours, status),
                                         tags=(tag,))
            except:
                pass

        info = f"共 {len(lessons)} 课时 | 已完成 {len(completed)} 个"
        self._lesson_header_label.config(text=f"📖 {title} — {info}")

    def _tree_editor_add_lesson(self):
        """添加新课时"""
        if not hasattr(self, '_current_editor_course') or not self._current_editor_course:
            messagebox.showinfo("提示", "请先在左侧选择课程")
            return

        course_id = self._current_editor_course
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        lessons = course.setdefault("lessons", [])
        next_num = (max((l.get("lesson_number", 0) for l in lessons), default=0)) + 1

        dlg = tk.Toplevel(self.root)
        dlg.title("➕ 添加课时")
        dlg.geometry("550x400")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"为《{course.get('course_title', '')}》添加课时",
                 font=("", 12, "bold")).pack(pady=10)

        form_frame = ttk.Frame(dlg, padding=15)
        form_frame.pack(fill=tk.BOTH, expand=True)

        fields = {}
        row = 0
        for label, key, default in [
            ("课时编号", "num", str(next_num)),
            ("课时标题", "title", ""),
            ("所属Section", "section", ""),
            ("中心问题", "question", ""),
            ("课时描述", "desc", ""),
            ("预计课时(小时)", "hours", "1"),
        ]:
            ttk.Label(form_frame, text=f"{label}：").grid(row=row, column=0, sticky="ne", pady=5)
            if key == "desc":
                text = tk.Text(form_frame, width=35, height=4, font=("", 10))
                text.insert("1.0", default)
                text.grid(row=row, column=1, sticky="w", pady=5, padx=5)
                fields[key] = text
            else:
                var = tk.StringVar(value=default)
                entry = ttk.Entry(form_frame, textvariable=var, width=35)
                entry.grid(row=row, column=1, sticky="w", pady=5, padx=5)
                fields[key] = var
            row += 1

        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)

        def _add_multiple():
            num_str = fields["num"].get().strip()
            try:
                start_num = int(num_str)
            except ValueError:
                messagebox.showwarning("警告", "课时编号必须是数字", parent=dlg)
                return

            title = fields["title"].get().strip()
            if not title:
                messagebox.showwarning("警告", "课时标题不能为空", parent=dlg)
                return

            section = fields["section"].get().strip()
            question = fields["question"].get().strip()
            desc = fields["desc"].get("1.0", tk.END).strip()
            hours_str = fields["hours"].get().strip()
            hours = float(hours_str) if hours_str.replace(".", "").isdigit() else 1.0

            new_lesson = {
                "lesson_number": start_num,
                "lesson_title": title,
                "section": section,
                "central_question": question,
                "description": desc,
                "estimated_hours": hours,
            }
            lessons.append(new_lesson)

            self._save_editor_course(course)
            self._tree_editor_load_lessons(course_id)
            dlg.destroy()
            self._log(f"✅ 添加课时: {title} (#{start_num})")

        ttk.Button(btn_frame, text="✅ 添加", command=_add_multiple).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)

    def _tree_editor_edit_lesson(self):
        """编辑选中课时"""
        sel = self._lesson_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要编辑的课时")
            return

        if not hasattr(self, '_current_editor_course') or not self._current_editor_course:
            return

        course_id = self._current_editor_course
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        lnum = int(sel[0])
        lessons = course.get("lessons", [])
        lesson = next((l for l in lessons if l.get("lesson_number") == lnum), None)

        if not lesson:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("✏️ 编辑课时")
        dlg.geometry("550x420")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"编辑课时 #{lnum}",
                 font=("", 12, "bold")).pack(pady=10)

        form_frame = ttk.Frame(dlg, padding=15)
        form_frame.pack(fill=tk.BOTH, expand=True)

        fields = {}
        row = 0
        for label, key, default in [
            ("课时编号", "num", str(lesson.get("lesson_number", ""))),
            ("课时标题", "title", lesson.get("lesson_title", "")),
            ("所属Section", "section", lesson.get("section", "")),
            ("中心问题", "question", lesson.get("central_question", "")),
            ("预计课时(小时)", "hours", str(lesson.get("estimated_hours", "1"))),
        ]:
            ttk.Label(form_frame, text=f"{label}：").grid(row=row, column=0, sticky="ne", pady=5)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(form_frame, textvariable=var, width=35)
            entry.grid(row=row, column=1, sticky="w", pady=5, padx=5)
            fields[key] = var
            row += 1

        ttk.Label(form_frame, text="课时描述：").grid(row=row, column=0, sticky="ne", pady=5)
        desc_text = tk.Text(form_frame, width=35, height=4, font=("", 10))
        desc_text.insert("1.0", lesson.get("description", ""))
        desc_text.grid(row=row, column=1, sticky="w", pady=5, padx=5)
        fields["desc"] = desc_text
        row += 1

        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)

        def _save():
            num_str = fields["num"].get().strip()
            try:
                new_num = int(num_str)
            except ValueError:
                messagebox.showwarning("警告", "课时编号必须是数字", parent=dlg)
                return

            title = fields["title"].get().strip()
            if not title:
                messagebox.showwarning("警告", "课时标题不能为空", parent=dlg)
                return

            lesson["lesson_number"] = new_num
            lesson["lesson_title"] = title
            lesson["section"] = fields["section"].get().strip()
            lesson["central_question"] = fields["question"].get().strip()
            lesson["estimated_hours"] = float(fields["hours"].get().strip() or "1")
            lesson["description"] = fields["desc"].get("1.0", tk.END).strip()

            self._save_editor_course(course)
            self._tree_editor_load_lessons(course_id)
            dlg.destroy()
            self._log(f"✅ 更新课时: {title} (#{new_num})")

        ttk.Button(btn_frame, text="💾 保存", command=_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)

    def _tree_editor_delete_lesson(self):
        """删除选中课时"""
        sel = self._lesson_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的课时")
            return

        if not hasattr(self, '_current_editor_course') or not self._current_editor_course:
            return

        course_id = self._current_editor_course
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        lnum = int(sel[0])
        lessons = course.get("lessons", [])
        lesson = next((l for l in lessons if l.get("lesson_number") == lnum), None)

        if not lesson:
            return

        title = lesson.get("lesson_title", "")
        if messagebox.askyesno("确认删除", f"确定要删除课时「{title}」(#{lnum})吗？\n\n此操作不可撤销！"):

            progress = self.system.get_course_progress(course_id)
            if lnum in progress.get("completed_lessons", []):
                progress["completed_lessons"].remove(lnum)

            course["lessons"] = [l for l in lessons if l.get("lesson_number") != lnum]

            self._save_editor_course(course)
            self._tree_editor_load_lessons(course_id)
            self._log(f"🗑️ 删除课时: {title} (#{lnum})")

    def _tree_editor_move_lesson(self, direction):
        """上下移动课时顺序"""
        sel = self._lesson_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要移动的课时")
            return

        if not hasattr(self, '_current_editor_course') or not self._current_editor_course:
            return

        course_id = self._current_editor_course
        course = self.system.get_course_by_id(course_id)
        if not course:
            return

        lessons = course.get("lessons", [])
        if not lessons:
            return

        lnum = int(sel[0])
        idx = next((i for i, l in enumerate(lessons) if l.get("lesson_number") == lnum), -1)

        if idx == -1:
            return

        new_idx = idx + direction
        if 0 <= new_idx < len(lessons):
            lessons[idx], lessons[new_idx] = lessons[new_idx], lessons[idx]

            for i, lesson in enumerate(lessons):
                lesson["lesson_number"] = i + 1

            self._save_editor_course(course)
            self._tree_editor_load_lessons(course_id)

            new_iid = str(lessons[new_idx]["lesson_number"])
            self._lesson_tree.selection_set(new_iid)
            self._lesson_tree.see(new_iid)

    def _save_editor_course(self, course):
        """保存编辑后的课程到JSON文件"""
        for p in self.system.db_paths:
            data = load_json_safe(p)
            if not data:
                continue
            for ci, c in enumerate(data.get("courses", [])):
                if c.get("note_id") == course.get("note_id"):
                    data["courses"][ci] = course
                    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    return

    # ========== 任务看板模块 ==========
    
    def _show_task_board(self):
        """显示任务看板"""
        self._clear_content()
        self._highlight_nav("taskboard")
        self.nav_title.config(text="任务看板")
        
        # 先初始化日历相关变量
        self._calendar_current = datetime.now().date()
        self._calendar_selected_date = None
        
        # 主布局：左看板 + 右日历
        main_paned = tk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL,
                                     sashrelief=tk.RAISED, sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左侧：看板区域
        kanban_frame = ttk.Frame(main_paned, padding=2)
        main_paned.add(kanban_frame, width=800)
        
        # 右侧：日历区域
        calendar_frame = ttk.Frame(main_paned, padding=2)
        main_paned.add(calendar_frame, width=350)
        
        # 构建看板和日历
        self._build_task_kanban(kanban_frame)
        self._build_task_calendar(calendar_frame)
    
    def _build_task_kanban(self, parent):
        """构建任务看板界面"""
        # 顶部工具栏
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Button(toolbar, text="➕ 新建任务", command=self._add_new_task).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        
        # 看板容器：四宫格布局（2x2）
        self._kanban_columns = {}
        self._kanban_expanded = {"待办": True, "进行中": True, "已完成": False, "已归档": False}
        self._kanban_container = tk.Frame(parent, bg="#ecf0f1")
        self._kanban_container.pack(fill=tk.BOTH, expand=True)
        
        # 配置网格布局
        for i in range(2):
            self._kanban_container.grid_rowconfigure(i, weight=1)
            self._kanban_container.grid_columnconfigure(0, weight=1)
            self._kanban_container.grid_columnconfigure(1, weight=1)
        
        # 创建四个状态列（2x2 四宫格）
        # 第一行：待办（0,0）、进行中（0,1）
        # 第二行：已完成（1,0）、已归档（1,1）
        grid_positions = [
            ("待办", 0, 0),
            ("进行中", 0, 1),
            ("已完成", 1, 0),
            ("已归档", 1, 1)
        ]
        
        for status, row, col in grid_positions:
            col_frame = ttk.LabelFrame(self._kanban_container, text="")
            col_frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            
            # 可折叠头部
            header_frame = ttk.Frame(col_frame)
            header_frame.pack(fill=tk.X, pady=2)
            
            # 展开/收起按钮
            toggle_btn = ttk.Button(header_frame, text="▼", width=3)
            toggle_btn.pack(side=tk.LEFT, padx=4)
            
            # 标题
            ttk.Label(header_frame, text=f"{status}", font=("", 11, "bold")).pack(side=tk.LEFT, padx=4)
            
            # 任务计数
            count_label = ttk.Label(header_frame, text="(0)", foreground="#7f8c8d")
            count_label.pack(side=tk.LEFT)
            
            # 内容区域
            content_frame = ttk.Frame(col_frame)
            content_frame.pack(fill=tk.BOTH, expand=True)
            
            # 任务列表容器（可折叠）
            tasks_container = ttk.Frame(content_frame)
            tasks_container.pack(fill=tk.BOTH, expand=True)
            
            # 任务列表
            tasks_list_frame = tk.Canvas(tasks_container, bg="#ffffff")
            tasks_scrollbar = ttk.Scrollbar(tasks_container, orient="vertical", command=tasks_list_frame.yview)
            tasks_scroll_frame = ttk.Frame(tasks_list_frame)
            
            tasks_scroll_frame.bind("<Configure>", lambda e, c=tasks_list_frame: c.configure(scrollregion=c.bbox("all")))
            tasks_list_frame.create_window((0, 0), window=tasks_scroll_frame, anchor="nw", width=300)
            tasks_list_frame.configure(yscrollcommand=tasks_scrollbar.set)
            
            tasks_list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tasks_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 保存引用
            self._kanban_columns[status] = {
                "toggle_btn": toggle_btn,
                "count_label": count_label,
                "tasks_container": tasks_container,
                "tasks_frame": tasks_scroll_frame
            }
            
            # 绑定 toggle 按钮
            toggle_btn.config(command=lambda s=status: self._toggle_kanban_column(s))
        
        self._refresh_task_kanban()
    
    def _build_task_calendar(self, parent):
        """构建日历控件"""
        # 变量已经在_show_task_board中初始化
        
        # 创建一个PanedWindow来分割日历和时间表
        right_paned = tk.PanedWindow(parent, orient=tk.VERTICAL,
                                      sashrelief=tk.RAISED, sashwidth=4)
        right_paned.pack(fill=tk.BOTH, expand=True)
        
        # 日历部分
        calendar_container = ttk.Frame(right_paned)
        right_paned.add(calendar_container, height=300)
        
        # 日历标题栏
        title_frame = ttk.Frame(calendar_container)
        title_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Button(title_frame, text="◀", width=3, command=lambda: self._nav_calendar(-1)).pack(side=tk.LEFT)
        self._calendar_title = ttk.Label(title_frame, text="", font=("", 12, "bold"))
        self._calendar_title.pack(side=tk.LEFT, expand=True)
        ttk.Button(title_frame, text="▶", width=3, command=lambda: self._nav_calendar(1)).pack(side=tk.LEFT)
        
        # 日历网格
        self._calendar_frame = ttk.Frame(calendar_container)
        self._calendar_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置网格列宽度自适应
        for col in range(7):
            self._calendar_frame.grid_columnconfigure(col, weight=1)
        for row in range(7):
            self._calendar_frame.grid_rowconfigure(row, weight=1)
        
        # 星期头
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        for i, day in enumerate(weekdays):
            lbl = ttk.Label(self._calendar_frame, text=day, font=("", 9, "bold"), 
                          background="#3498db", foreground="white",
                          padding=(10, 8))
            lbl.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
        
        # 日期网格
        self._calendar_cells = {}
        for row in range(1, 7):
            for col in range(7):
                cell = tk.Canvas(self._calendar_frame, bg="#ffffff", 
                                 highlightthickness=0)
                cell.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
                cell.bind("<Button-1>", lambda e, r=row, c=col: self._select_calendar_date(r, c))
                self._calendar_cells[(row, col)] = cell
        
        # 底部：今日按钮
        ttk.Button(calendar_container, text="返回今天", command=lambda: self._go_to_today()).pack(pady=8)
        
        # 绑定窗口大小变化事件，用于重新绘制日历内容
        self._calendar_frame.bind("<Configure>", self._on_calendar_resize)
        
        # 时间表部分
        timeline_container = ttk.Frame(right_paned)
        right_paned.add(timeline_container, height=400)
        
        # 时间表标题
        self._timeline_title = ttk.Label(timeline_container, text="当日时间表", font=("", 11, "bold"))
        self._timeline_title.pack(fill=tk.X, pady=(10, 5))
        
        # 构建时间表
        self._build_timeline(timeline_container)
        
        self._refresh_calendar()
    
    def _nav_calendar(self, delta):
        """日历导航"""
        try:
            if delta < 0:
                # 上个月
                if self._calendar_current.month == 1:
                    self._calendar_current = self._calendar_current.replace(year=self._calendar_current.year-1, month=12)
                else:
                    self._calendar_current = self._calendar_current.replace(month=self._calendar_current.month-1)
            else:
                # 下个月
                if self._calendar_current.month == 12:
                    self._calendar_current = self._calendar_current.replace(year=self._calendar_current.year+1, month=1)
                else:
                    self._calendar_current = self._calendar_current.replace(month=self._calendar_current.month+1)
            
            self._refresh_calendar()
        except:
            pass
    
    def _go_to_today(self):
        """返回今天"""
        try:
            self._calendar_current = datetime.now().date()
            self._refresh_calendar()
        except:
            pass
    
    def _on_calendar_resize(self, event):
        """处理日历窗口大小变化，重新绘制日历内容"""
        try:
            self._refresh_calendar()
        except:
            pass
    
    def _refresh_calendar(self):
        """刷新日历显示"""
        try:
            # 检查相关属性是否还存在
            if not hasattr(self, '_calendar_title') or not hasattr(self, '_calendar_cells'):
                return
                
            # 更新标题
            year = self._calendar_current.year
            month = self._calendar_current.month
            self._calendar_title.config(text=f"{year}年{month}月")
            
            # 获取本月第一天和天数
            first_day = self._calendar_current.replace(day=1)
            if month == 12:
                next_month = first_day.replace(year=year+1, month=1)
            else:
                next_month = first_day.replace(month=month+1)
            days_in_month = (next_month - first_day).days
            
            # 计算第一天的星期 (0=周一)
            first_weekday = first_day.weekday()
            
            # 有任务的日期
            dates_with_tasks = self.task_board_mgr.get_dates_with_tasks()
            today = datetime.now().date()
            
            # 清除并重新填充日期
            for (row, col), cell in self._calendar_cells.items():
                try:
                    cell.delete("all")
                except:
                    continue
            
            day = 1
            for row in range(1, 7):
                for col in range(7):
                    try:
                        cell = self._calendar_cells[(row, col)]
                        
                        # 获取当前单元格的实际尺寸
                        cell.update()
                        cell_width = cell.winfo_width()
                        cell_height = cell.winfo_height()
                        
                        # 如果尺寸为0，使用默认值
                        if cell_width <= 1:
                            cell_width = 50
                        if cell_height <= 1:
                            cell_height = 40
                    except:
                        continue
                    
                    # 计算当前格子的日期
                    day_num = (row-1)*7 + col - first_weekday
                    
                    if day_num < 0 or day_num >= days_in_month:
                        # 空白格子
                        try:
                            cell.config(bg="#ecf0f1")
                        except:
                            pass
                        continue
                    
                    current_day = day_num + 1
                    date_str = f"{year}-{month:02d}-{current_day:02d}"
                    
                    # 确定颜色
                    bg = "#ffffff"
                    fg = "#333333"
                    
                    # 今天高亮
                    if (year, month, current_day) == (today.year, today.month, today.day):
                        bg = "#3498db"
                        fg = "#ffffff"
                    # 周末
                    elif col >= 5:
                        bg = "#f8f9fa"
                    
                    # 如果选中
                    if self._calendar_selected_date == date_str:
                        bg = "#95a5a6"
                        fg = "#ffffff"
                    
                    try:
                        cell.config(bg=bg)
                        
                        # 计算居中位置
                        center_x = cell_width // 2
                        center_y = cell_height // 2
                        
                        # 根据单元格大小调整字体大小
                        font_size = min(10, cell_width // 5)
                        
                        # 绘制日期（居中）
                        cell.create_text(center_x, center_y, text=str(current_day), fill=fg, 
                                       font=("", font_size, "normal" if bg == "#ffffff" else "bold"))
                        
                        # 有任务标记（根据尺寸调整位置）
                        if date_str in dates_with_tasks:
                            dot_size = min(6, cell_width // 8)
                            dot_x = cell_width - dot_size - 4
                            dot_y = cell_height - dot_size - 4
                            cell.create_oval(dot_x, dot_y, dot_x + dot_size, dot_y + dot_size, 
                                             fill="#e74c3c", outline="")
                        
                        # 保存日期信息到cell
                        cell.date_str = date_str
                        cell.day_num = current_day
                    except:
                        pass
        except:
            pass
    
    def _select_calendar_date(self, row, col):
        """选择日历日期"""
        try:
            cell = self._calendar_cells.get((row, col))
            if hasattr(cell, "date_str"):
                if self._calendar_selected_date == cell.date_str:
                    # 取消选择
                    self._calendar_selected_date = None
                else:
                    self._calendar_selected_date = cell.date_str
                
                self._refresh_calendar()
                self._refresh_task_kanban()
                self._refresh_timeline()
        except:
            pass
    
    def _build_timeline(self, parent):
        """构建时间表组件"""
        # 时间表容器
        self._timeline_container = ttk.Frame(parent)
        self._timeline_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建带滚动条的画布
        self._timeline_canvas = tk.Canvas(self._timeline_container, bg="#e8eef7")
        timeline_scrollbar = ttk.Scrollbar(self._timeline_container, orient="vertical", 
                                          command=self._timeline_canvas.yview)
        self._timeline_canvas.configure(yscrollcommand=timeline_scrollbar.set)
        
        self._timeline_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        timeline_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 内部框架
        self._timeline_inner = ttk.Frame(self._timeline_canvas, style="Timeline.TFrame")
        self._timeline_canvas.create_window((0, 0), window=self._timeline_inner, anchor="nw", tags="timeline_inner")
        
        # 配置大小变化
        self._timeline_inner.bind("<Configure>", self._on_timeline_configure)
        self._timeline_canvas.bind("<Configure>", self._on_timeline_canvas_configure)
        
        # 刷新时间表
        self._refresh_timeline()
    
    def _on_timeline_configure(self, event):
        """处理内部框架配置变化"""
        self._timeline_canvas.configure(scrollregion=self._timeline_canvas.bbox("all"))
    
    def _on_timeline_canvas_configure(self, event):
        """处理画布配置变化"""
        canvas_width = event.width
        self._timeline_canvas.itemconfig("timeline_inner", width=canvas_width)
    
    def _time_to_minutes(self, time_str):
        """将 HH:MM 格式转换为分钟数"""
        if not time_str:
            return 0
        try:
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
        except:
            return 0
    
    def _minutes_to_time(self, minutes):
        """将分钟数转换为 HH:MM 格式"""
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    def _refresh_timeline(self):
        """刷新时间表显示"""
        try:
            # 检查相关属性是否存在
            if not hasattr(self, '_timeline_title') or not hasattr(self, '_timeline_inner'):
                return
                
            # 获取选中的日期，如果没有选中则使用今天
            date_str = self._calendar_selected_date
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            # 更新时间表标题
            try:
                self._timeline_title.config(text=f"📅 {date_str} 时间表")
            except:
                pass
            
            # 清空现有内容
            try:
                for widget in self._timeline_inner.winfo_children():
                    widget.destroy()
            except:
                pass
            
            # 获取当天的任务
            tasks = self.task_board_mgr.get_tasks_by_date(date_str)
            
            # 从 6:00 到 24:00，每小时一个时间段
            start_hour = 6
            end_hour = 24
            
            # 创建时间轴网格
            for hour in range(start_hour, end_hour):
                try:
                    # 时间槽框架
                    hour_frame = tk.Frame(self._timeline_inner, bg="white")
                    hour_frame.pack(fill=tk.X, pady=2)
                    
                    # 时间标签
                    time_label = tk.Label(hour_frame, text=f"{hour:02d}:00", 
                                         width=6, font=("Segoe UI", 10, "bold"), 
                                         bg="#3498db", fg="white", padx=10, pady=8)
                    time_label.pack(side=tk.LEFT, padx=(0, 10))
                    
                    # 时间槽区域
                    slot_frame = tk.Frame(hour_frame, bg="#ffffff", 
                                       relief="solid", bd=1, height=50)
                    slot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    slot_frame.pack_propagate(False)
                    
                    # 绑定点击事件
                    minutes = (hour - start_hour) * 60
                    slot_frame.bind("<Button-1>", lambda e, d=date_str, m=minutes: self._on_slot_click(d, m))
                    
                    # 保存槽信息
                    slot_frame.date_str = date_str
                    slot_frame.start_hour = hour
                except:
                    continue
            
            # 渲染任务
            for task in tasks:
                try:
                    self._render_task_on_timeline(task)
                except:
                    continue
            
            # 自动滚动到当前时间（只在显示今天时才滚动）
            try:
                if date_str == datetime.now().strftime("%Y-%m-%d"):
                    self._scroll_timeline_to_current_time()
            except:
                pass
        except:
            pass
    
    def _scroll_timeline_to_current_time(self):
        """滚动时间表到当前时间，使当前时间行对齐中轴"""
        try:
            if not hasattr(self, '_timeline_canvas'):
                return
                
            now = datetime.now()
            current_hour = now.hour
            start_hour = 6  # 时间表从6点开始
            
            # 获取所有时间槽
            hour_frames = self._timeline_inner.winfo_children()
            if not hour_frames:
                return
            
            # 计算目标行索引
            target_index = max(0, min(len(hour_frames) - 1, current_hour - start_hour))
            
            # 更新界面后滚动
            self.root.update_idletasks()
            
            # 获取Canvas和滚动区域信息
            scrollregion = self._timeline_canvas.bbox("all")
            if not scrollregion:
                return
                
            total_height = scrollregion[3] - scrollregion[1]
            canvas_height = self._timeline_canvas.winfo_height()
            
            if total_height <= 0 or canvas_height <= 0:
                return
                
            # 获取目标框架的位置
            target_frame = hour_frames[target_index]
            target_y = target_frame.winfo_y()
            
            # 计算滚动位置，使目标行位于视图中轴
            # 滚动比例 = (目标位置 - 视图高度/2) / 总内容高度
            scroll_y = max(0.0, min(1.0, (target_y - canvas_height / 2) / max(1, total_height)))
            
            # 执行滚动
            self._timeline_canvas.yview_moveto(scroll_y)
        except:
            pass
    
    def _render_task_on_timeline(self, task):
        """在时间表上渲染任务"""
        start_time = task.get("start_time", "09:00")
        start_minutes = self._time_to_minutes(start_time)
        duration = task.get("duration", 60)
        start_hour = start_minutes // 60
        
        # 查找对应的小时槽
        target_slot = None
        for hour_frame in self._timeline_inner.winfo_children():
            for child in hour_frame.winfo_children():
                if isinstance(child, tk.Frame) and hasattr(child, 'start_hour'):
                    if child.start_hour == start_hour:
                        target_slot = child
                        break
            if target_slot:
                break
        
        if target_slot:
            # 清空槽中现有内容
            for widget in target_slot.winfo_children():
                widget.destroy()
            
            # 颜色
            bg_color = self._get_priority_color(task.get("priority", "中"))
            
            # 任务框架
            task_frame = tk.Frame(target_slot, bg=bg_color, relief="raised", bd=0)
            task_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            
            # 任务标题
            title_label = tk.Label(task_frame, text=task.get("title", "未命名任务"), 
                                bg=bg_color, fg="white", 
                                font=("Segoe UI", 9, "bold"), anchor="w")
            title_label.pack(fill=tk.X, padx=8, pady=(4, 2))
            
            # 任务时间和描述
            end_time = self._minutes_to_time(start_minutes + duration)
            desc_text = f"{start_time} - {end_time}"
            if task.get("description"):
                desc_text += f" | {task.get('description')[:30]}"
            
            desc_label = tk.Label(task_frame, text=desc_text, 
                               bg=bg_color, fg="#ecf0f1", 
                               font=("Segoe UI", 8), anchor="w")
            desc_label.pack(fill=tk.X, padx=8, pady=(0, 4))
            
            # 绑定点击事件
            task_frame.bind("<Button-1>", lambda e, t=task: self._edit_task_time(t))
            title_label.bind("<Button-1>", lambda e, t=task: self._edit_task_time(t))
            desc_label.bind("<Button-1>", lambda e, t=task: self._edit_task_time(t))
    
    def _get_priority_color(self, priority):
        """获取优先级对应的颜色"""
        colors = {
            "高": "#e74c3c",
            "中": "#3498db",
            "低": "#27ae60"
        }
        return colors.get(priority, "#3498db")
    
    def _on_slot_click(self, date_str, minutes):
        """点击时间槽，添加新任务"""
        start_hour = 6
        start_time = self._minutes_to_time(start_hour * 60 + minutes)
        self._add_task_with_time(date_str, start_time)
    
    def _add_task_with_time(self, date_str, start_time):
        """添加带时间的任务"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加新任务")
        dialog.geometry("400x300")
        
        ttk.Label(dialog, text="任务标题:").pack(pady=(10, 5))
        title_entry = ttk.Entry(dialog, width=40)
        title_entry.pack(pady=(0, 10))
        
        ttk.Label(dialog, text="描述:").pack(pady=(0, 5))
        desc_text = tk.Text(dialog, width=40, height=4)
        desc_text.pack(pady=(0, 10))
        
        ttk.Label(dialog, text=f"日期: {date_str}").pack(pady=(0, 5))
        
        time_frame = ttk.Frame(dialog)
        time_frame.pack(pady=(0, 10))
        
        ttk.Label(time_frame, text="开始时间:").pack(side=tk.LEFT, padx=5)
        start_hour, start_min = map(int, start_time.split(':'))
        hour_var = tk.StringVar(value=str(start_hour))
        min_var = tk.StringVar(value=str(start_min))
        
        hour_spin = ttk.Spinbox(time_frame, from_=0, to=23, textvariable=hour_var, width=3)
        hour_spin.pack(side=tk.LEFT)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        min_spin = ttk.Spinbox(time_frame, from_=0, to=59, increment=5, textvariable=min_var, width=3)
        min_spin.pack(side=tk.LEFT)
        
        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(pady=(0, 10))
        ttk.Label(duration_frame, text="持续时间(分钟):").pack(side=tk.LEFT, padx=5)
        duration_var = tk.StringVar(value="60")
        duration_spin = ttk.Spinbox(duration_frame, from_=15, to=480, increment=15, 
                                   textvariable=duration_var, width=5)
        duration_spin.pack(side=tk.LEFT)
        
        priority_frame = ttk.Frame(dialog)
        priority_frame.pack(pady=(0, 10))
        ttk.Label(priority_frame, text="优先级:").pack(side=tk.LEFT, padx=5)
        priority_var = tk.StringVar(value="中")
        ttk.Radiobutton(priority_frame, text="高", variable=priority_var, value="高").pack(side=tk.LEFT)
        ttk.Radiobutton(priority_frame, text="中", variable=priority_var, value="中").pack(side=tk.LEFT)
        ttk.Radiobutton(priority_frame, text="低", variable=priority_var, value="低").pack(side=tk.LEFT)
        
        def save_task():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("警告", "请输入任务标题")
                return
            
            desc = desc_text.get("1.0", tk.END).strip()
            h = hour_var.get().zfill(2)
            m = min_var.get().zfill(2)
            start = f"{h}:{m}"
            duration = int(duration_var.get())
            
            self.task_board_mgr.add_task(
                title=title,
                description=desc,
                due_date=date_str,
                priority=priority_var.get(),
                status="待办",
                start_time=start,
                duration=duration
            )
            dialog.destroy()
            self._refresh_task_kanban()
            self._refresh_timeline()
            self._refresh_calendar()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=save_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _edit_task_time(self, task):
        """编辑任务时间"""
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑任务时间")
        dialog.geometry("400x300")
        
        ttk.Label(dialog, text=f"任务: {task.get('title')}").pack(pady=(10, 10))
        
        time_frame = ttk.Frame(dialog)
        time_frame.pack(pady=(0, 10))
        
        ttk.Label(time_frame, text="开始时间:").pack(side=tk.LEFT, padx=5)
        start_time = task.get("start_time", "09:00")
        start_hour, start_min = map(int, start_time.split(':'))
        hour_var = tk.StringVar(value=str(start_hour))
        min_var = tk.StringVar(value=str(start_min))
        
        hour_spin = ttk.Spinbox(time_frame, from_=0, to=23, textvariable=hour_var, width=3)
        hour_spin.pack(side=tk.LEFT)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        min_spin = ttk.Spinbox(time_frame, from_=0, to=59, increment=5, textvariable=min_var, width=3)
        min_spin.pack(side=tk.LEFT)
        
        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(pady=(0, 10))
        ttk.Label(duration_frame, text="持续时间(分钟):").pack(side=tk.LEFT, padx=5)
        duration_var = tk.StringVar(value=str(task.get("duration", 60)))
        duration_spin = ttk.Spinbox(duration_frame, from_=15, to=480, increment=15, 
                                   textvariable=duration_var, width=5)
        duration_spin.pack(side=tk.LEFT)
        
        def save_changes():
            h = hour_var.get().zfill(2)
            m = min_var.get().zfill(2)
            new_start = f"{h}:{m}"
            new_duration = int(duration_var.get())
            
            self.task_board_mgr.update_task(
                task["id"],
                start_time=new_start,
                duration=new_duration
            )
            dialog.destroy()
            self._refresh_task_kanban()
            self._refresh_timeline()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=save_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _toggle_kanban_column(self, status):
        """切换看板列的展开/收起"""
        self._kanban_expanded[status] = not self._kanban_expanded[status]
        self._refresh_task_kanban()
    
    def _refresh_task_kanban(self):
        """刷新看板任务"""
        try:
            # 检查相关属性是否存在
            if not hasattr(self, '_kanban_columns') or not hasattr(self, '_kanban_container'):
                return
                
            today = datetime.now().strftime("%Y-%m-%d")
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            # 获取所有任务（总是显示所有任务）
            all_tasks = self.task_board_mgr.get_all_tasks()
            
            # 检查并自动转移到达开始时间的待办任务
            today_date = datetime.now().date()
            for task in all_tasks:
                if task["status"] == "待办" and task.get("due_date") == today:
                    # 获取任务开始时间
                    start_time = task.get("start_time", "00:00")
                    try:
                        start_hour, start_min = map(int, start_time.split(':'))
                        # 检查是否到达或超过开始时间
                        if current_hour > start_hour or (current_hour == start_hour and current_minute >= start_min):
                            self.task_board_mgr.update_task(task["id"], status="进行中")
                    except:
                        pass
            
            # 重新获取更新后的任务列表
            all_tasks = self.task_board_mgr.get_all_tasks()
            
            # 日期筛选（如果选中了日期）
            if self._calendar_selected_date:
                all_tasks = [t for t in all_tasks if t.get("due_date") == self._calendar_selected_date]
            
            # 按状态分类
            tasks_by_status = {s: [] for s in TaskBoardManager.TASK_STATUS}
            for task in all_tasks:
                tasks_by_status[task["status"]].append(task)
            
            # 重新配置行高度（展开/收起）
            # 行 0：待办和进行中 - 总是展开
            # 行 1：已完成和已归档 - 根据展开状态调整高度
            # 检查第二行是否有展开的栏目
            row1_expanded = self._kanban_expanded["已完成"] or self._kanban_expanded["已归档"]
            
            # 重新配置行高度
            try:
                self._kanban_container.grid_rowconfigure(0, weight=1)  # 第一行总是有权重
                self._kanban_container.grid_rowconfigure(1, weight=1 if row1_expanded else 0)
            except:
                pass
            
            # 处理各列
            for status in TaskBoardManager.TASK_STATUS:
                try:
                    col = self._kanban_columns[status]
                    tasks = tasks_by_status[status]
                    
                    # 更新计数
                    col["count_label"].config(text=f"({len(tasks)})")
                    
                    # 更新展开/收起按钮
                    col["toggle_btn"].config(text="▼" if self._kanban_expanded[status] else "▶")
                    
                    # 清空现有任务
                    for widget in col["tasks_frame"].winfo_children():
                        widget.destroy()
                    
                    # 根据展开状态处理显示
                    if self._kanban_expanded[status]:
                        col["tasks_container"].pack(fill=tk.BOTH, expand=True)
                        
                        if status == "待办":
                            # 待办列：分当日任务和全任务
                            today_tasks = []
                            other_tasks = []
                            
                            for task in tasks:
                                if task.get("due_date") == today:
                                    today_tasks.append(task)
                                else:
                                    other_tasks.append(task)
                            
                            # 当日任务分组
                            if today_tasks:
                                separator = ttk.Label(col["tasks_frame"], text="═════════ 当日任务 ═════════", 
                                                    foreground="#27ae60", font=("", 9, "bold"), background="#d5f4e6")
                                separator.pack(fill=tk.X, pady=(2, 4), padx=2)
                                
                                for task in today_tasks:
                                    self._add_task_card(col["tasks_frame"], task)
                            
                            # 全任务（其他任务）
                            if other_tasks or (today_tasks and other_tasks):
                                if today_tasks:
                                    separator = ttk.Label(col["tasks_frame"], text="═════════ 全部任务 ═════════", 
                                                        foreground="#95a5a6", font=("", 9, "bold"), background="#ecf0f1")
                                    separator.pack(fill=tk.X, pady=(4, 4), padx=2)
                                
                                for task in other_tasks:
                                    self._add_task_card(col["tasks_frame"], task)
                        else:
                            # 其他列：直接显示所有任务
                            for task in tasks:
                                self._add_task_card(col["tasks_frame"], task)
                    else:
                        # 收起状态：隐藏内容
                        col["tasks_container"].pack_forget()
                except:
                    continue
        except:
            pass
    
    def _add_task_card(self, parent, task):
        """添加任务卡片"""
        # 任务卡片
        priority_colors = {"高": "#e74c3c", "中": "#f39c12", "低": "#27ae60"}
        priority_color = priority_colors.get(task["priority"], "#95a5a6")
        
        card = tk.Frame(parent, bg="#ffffff", bd=1, relief=tk.RAISED, padx=6, pady=6)
        card.pack(fill=tk.X, pady=4, padx=4)
        
        # 优先级指示
        tk.Frame(card, bg=priority_color, width=4, height=40).pack(side=tk.LEFT, padx=(0, 6))
        
        # 内容区域
        content = tk.Frame(card, bg="#ffffff")
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(content, text=task["title"], font=("", 9, "bold"), 
               background="#ffffff").pack(anchor="w")
        
        # 截止日期（如果有）
        if task.get("due_date"):
            ttk.Label(content, text=f"📅 {task['due_date']}", font=("", 8), 
                   foreground="#7f8c8d", background="#ffffff").pack(anchor="w")
        
        # 按钮区域
        btn_frame = tk.Frame(content, bg="#ffffff")
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        
        ttk.Button(btn_frame, text="✏️", width=2, 
                  command=lambda t=task: self._edit_task(t)).pack(side=tk.LEFT, padx=1)
        
        ttk.Button(btn_frame, text="🗑️", width=2,
                  command=lambda t=task: self._delete_task(t)).pack(side=tk.LEFT, padx=1)
        
        # 状态转换按钮
        if task["status"] in ["待办", "进行中"]:
            next_status = "进行中" if task["status"] == "待办" else "已完成"
            ttk.Button(btn_frame, text=f"→{next_status}",
                      command=lambda t=task, ns=next_status: self._move_task(t, ns)).pack(side=tk.RIGHT, padx=1)
        elif task["status"] == "已完成":
            ttk.Button(btn_frame, text="→已归档",
                      command=lambda t=task: self._move_task(t, "已归档")).pack(side=tk.RIGHT, padx=1)
    
    def _move_task(self, task, new_status):
        """移动任务到新状态"""
        self.task_board_mgr.update_task(task["id"], status=new_status)
        self._refresh_task_kanban()
    
    def _add_new_task(self):
        """添加新任务"""
        dlg = tk.Toplevel(self.root)
        dlg.title("新建任务")
        dlg.geometry("400x520")
        
        fields = {}
        
        # 表单区域
        form = ttk.Frame(dlg, padding=15)
        form.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(form, text="任务标题：").pack(anchor="w")
        title_var = tk.StringVar()
        fields["title"] = ttk.Entry(form, textvariable=title_var, width=50)
        fields["title"].pack(fill=tk.X, pady=(2, 8))
        
        ttk.Label(form, text="任务描述：").pack(anchor="w")
        fields["desc"] = tk.Text(form, height=5, width=50)
        fields["desc"].pack(fill=tk.BOTH, expand=True, pady=(2, 8))
        
        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row1, text="截止日期：").pack(side=tk.LEFT)
        date_var = tk.StringVar()
        if self._calendar_selected_date:
            date_var.set(self._calendar_selected_date)
        else:
            date_var.set(datetime.now().strftime("%Y-%m-%d"))
        fields["date"] = ttk.Entry(row1, textvariable=date_var, width=12)
        fields["date"].pack(side=tk.LEFT, padx=(4, 8))
        
        ttk.Label(row1, text="优先级：").pack(side=tk.LEFT)
        priority_var = tk.StringVar(value="中")
        fields["priority"] = ttk.Combobox(row1, textvariable=priority_var, 
                                       values=TaskBoardManager.TASK_PRIORITIES, 
                                       state="readonly", width=6)
        fields["priority"].pack(side=tk.LEFT, padx=4)
        
        # 时间字段 - 默认当前时间
        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row2, text="开始时间：").pack(side=tk.LEFT)
        now = datetime.now()
        hour_var = tk.StringVar(value=str(now.hour))
        min_var = tk.StringVar(value=str(now.minute))
        ttk.Spinbox(row2, from_=0, to=23, textvariable=hour_var, width=3).pack(side=tk.LEFT)
        ttk.Label(row2, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(row2, from_=0, to=59, increment=5, textvariable=min_var, width=3).pack(side=tk.LEFT, padx=(0, 8))
        
        ttk.Label(row2, text="持续时间(分)：").pack(side=tk.LEFT)
        duration_var = tk.StringVar(value="60")
        ttk.Spinbox(row2, from_=15, to=480, increment=15, textvariable=duration_var, width=5).pack(side=tk.LEFT)
        
        # 循环任务字段
        row3 = ttk.Frame(form)
        row3.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row3, text="循环模式：").pack(side=tk.LEFT)
        recurrence_var = tk.StringVar(value="不循环")
        fields["recurrence"] = ttk.Combobox(row3, textvariable=recurrence_var, 
                                          values=TaskBoardManager.RECURRENCE_TYPES, 
                                          state="readonly", width=8)
        fields["recurrence"].pack(side=tk.LEFT, padx=(4, 8))
        
        ttk.Label(row3, text="结束日期：").pack(side=tk.LEFT)
        recurrence_end_var = tk.StringVar()
        fields["recurrence_end"] = ttk.Entry(row3, textvariable=recurrence_end_var, width=12)
        fields["recurrence_end"].pack(side=tk.LEFT)
        
        # 按钮
        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)
        
        def _save():
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning("警告", "任务标题不能为空", parent=dlg)
                return
            
            h = hour_var.get().zfill(2)
            m = min_var.get().zfill(2)
            start_time = f"{h}:{m}"
            
            self.task_board_mgr.add_task(
                title=title,
                description=fields["desc"].get("1.0", tk.END).strip(),
                due_date=date_var.get() or None,
                priority=priority_var.get(),
                status="待办",
                start_time=start_time,
                duration=int(duration_var.get()),
                recurrence=recurrence_var.get(),
                recurrence_end=recurrence_end_var.get() or None
            )
            
            self._refresh_task_kanban()
            self._refresh_calendar()
            self._refresh_timeline()
            dlg.destroy()
        
        ttk.Button(btn_frame, text="💾 保存", command=_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)
    
    def _edit_task(self, task):
        """编辑任务"""
        dlg = tk.Toplevel(self.root)
        dlg.title("编辑任务")
        dlg.geometry("400x550")
        
        fields = {}
        
        # 表单区域
        form = ttk.Frame(dlg, padding=15)
        form.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(form, text="任务标题：").pack(anchor="w")
        title_var = tk.StringVar(value=task["title"])
        fields["title"] = ttk.Entry(form, textvariable=title_var, width=50)
        fields["title"].pack(fill=tk.X, pady=(2, 8))
        
        ttk.Label(form, text="任务描述：").pack(anchor="w")
        fields["desc"] = tk.Text(form, height=5, width=50)
        fields["desc"].insert("1.0", task.get("description", ""))
        fields["desc"].pack(fill=tk.BOTH, expand=True, pady=(2, 8))
        
        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row1, text="截止日期：").pack(side=tk.LEFT)
        date_var = tk.StringVar(value=task.get("due_date", ""))
        fields["date"] = ttk.Entry(row1, textvariable=date_var, width=12)
        fields["date"].pack(side=tk.LEFT, padx=(4, 8))
        
        ttk.Label(row1, text="优先级：").pack(side=tk.LEFT)
        priority_var = tk.StringVar(value=task.get("priority", "中"))
        fields["priority"] = ttk.Combobox(row1, textvariable=priority_var, 
                                       values=TaskBoardManager.TASK_PRIORITIES, 
                                       state="readonly", width=6)
        fields["priority"].pack(side=tk.LEFT, padx=4)
        
        # 时间字段
        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row2, text="开始时间：").pack(side=tk.LEFT)
        start_time = task.get("start_time", "09:00")
        start_hour, start_min = map(int, start_time.split(':'))
        hour_var = tk.StringVar(value=str(start_hour))
        min_var = tk.StringVar(value=str(start_min))
        ttk.Spinbox(row2, from_=0, to=23, textvariable=hour_var, width=3).pack(side=tk.LEFT)
        ttk.Label(row2, text=":").pack(side=tk.LEFT)
        ttk.Spinbox(row2, from_=0, to=59, increment=5, textvariable=min_var, width=3).pack(side=tk.LEFT, padx=(0, 8))
        
        ttk.Label(row2, text="持续时间(分)：").pack(side=tk.LEFT)
        duration_var = tk.StringVar(value=str(task.get("duration", 60)))
        ttk.Spinbox(row2, from_=15, to=480, increment=15, textvariable=duration_var, width=5).pack(side=tk.LEFT)
        
        # 循环任务字段
        row3 = ttk.Frame(form)
        row3.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row3, text="循环模式：").pack(side=tk.LEFT)
        recurrence_var = tk.StringVar(value=task.get("recurrence", "不循环"))
        fields["recurrence"] = ttk.Combobox(row3, textvariable=recurrence_var, 
                                          values=TaskBoardManager.RECURRENCE_TYPES, 
                                          state="readonly", width=8)
        fields["recurrence"].pack(side=tk.LEFT, padx=(4, 8))
        
        ttk.Label(row3, text="结束日期：").pack(side=tk.LEFT)
        recurrence_end_var = tk.StringVar(value=task.get("recurrence_end", ""))
        fields["recurrence_end"] = ttk.Entry(row3, textvariable=recurrence_end_var, width=12)
        fields["recurrence_end"].pack(side=tk.LEFT)
        
        row4 = ttk.Frame(form)
        row4.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row4, text="状态：").pack(side=tk.LEFT)
        status_var = tk.StringVar(value=task["status"])
        fields["status"] = ttk.Combobox(row4, textvariable=status_var, 
                                      values=TaskBoardManager.TASK_STATUS, 
                                      state="readonly", width=10)
        fields["status"].pack(side=tk.LEFT, padx=4)
        
        # 按钮
        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)
        
        def _save():
            title = title_var.get().strip()
            if not title:
                messagebox.showwarning("警告", "任务标题不能为空", parent=dlg)
                return
            
            h = hour_var.get().zfill(2)
            m = min_var.get().zfill(2)
            new_start_time = f"{h}:{m}"
            
            self.task_board_mgr.update_task(
                task["id"],
                title=title,
                description=fields["desc"].get("1.0", tk.END).strip(),
                due_date=date_var.get() or None,
                priority=priority_var.get(),
                status=status_var.get(),
                start_time=new_start_time,
                duration=int(duration_var.get()),
                recurrence=recurrence_var.get(),
                recurrence_end=recurrence_end_var.get() or None
            )
            
            self._refresh_task_kanban()
            self._refresh_calendar()
            self._refresh_timeline()
            dlg.destroy()
        
        ttk.Button(btn_frame, text="💾 保存", command=_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="❌ 取消", command=dlg.destroy).pack(side=tk.LEFT)
    
    def _delete_task(self, task):
        """删除任务"""
        if messagebox.askyesno("确认删除", f"确定要删除任务 '{task['title']}'？"):
            self.task_board_mgr.delete_task(task["id"])
            self._refresh_task_kanban()
            self._refresh_calendar()
            self._refresh_timeline()


    # ============ 网络搜索界面 ============

    def _show_search_page(self):
        """显示网络搜索界面"""
        self._clear_content()
        self._highlight_nav("search")
        self.nav_title.config(text="🔍 网络搜索 & 书签管理")

        # 主分割窗口：左书签，右文件管理
        main_paned = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左侧：书签区域（20%）
        left_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(left_frame, weight=2)

        # 右侧：文件和笔记管理（80%）
        self._search_right_frame = ttk.Frame(main_paned, padding=5)
        main_paned.add(self._search_right_frame, weight=8)

        # 构建书签区域
        self._build_bookmark_section(left_frame)
        
        # 初始化右栏为空白
        self._clear_search_right()
        
        # 记录当前选中的书签
        self._current_selected_bookmark = None

    def _build_bookmark_section(self, parent):
        """构建书签管理区域"""
        # 标题栏
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="📚 学术网站书签", font=("", 12, "bold")).pack(side=tk.LEFT)
        
        ttk.Button(header_frame, text="➕ 添加书签", command=self._add_bookmark_dialog).pack(side=tk.RIGHT, padx=5)
        ttk.Button(header_frame, text="📥 从浏览器导入", command=self._import_bookmarks_from_browser).pack(side=tk.RIGHT, padx=5)

        # 搜索框
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(search_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=(0, 5))
        self._bookmark_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self._bookmark_search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self._refresh_bookmarks())

        # 分类标签
        category_frame = ttk.Frame(parent)
        category_frame.pack(fill=tk.X, pady=(0, 10))
        self._bookmark_category_var = tk.StringVar(value="all")
        
        categories = [
            ("全部", "all"),
            ("预印本", "preprint"),
            ("学术搜索", "search"),
            ("期刊", "journal"),
            ("数据库", "database"),
            ("工具", "tool")
        ]
        for text, val in categories:
            ttk.Radiobutton(category_frame, text=text, variable=self._bookmark_category_var, 
                           value=val, command=self._refresh_bookmarks).pack(side=tk.LEFT, padx=5)

        # 书签卡片容器（带滚动）
        bookmark_container = ttk.Frame(parent)
        bookmark_container.pack(fill=tk.BOTH, expand=True)
        
        self._bookmark_canvas = tk.Canvas(bookmark_container, bg="#ecf0f1")
        bookmark_scrollbar = ttk.Scrollbar(bookmark_container, orient="vertical", 
                                          command=self._bookmark_canvas.yview)
        self._bookmark_canvas.configure(yscrollcommand=bookmark_scrollbar.set)
        
        self._bookmark_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bookmark_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._bookmark_inner = ttk.Frame(self._bookmark_canvas)
        self._bookmark_canvas.create_window((0, 0), window=self._bookmark_inner, anchor="nw", tags="bookmark_inner")
        
        self._bookmark_inner.bind("<Configure>", lambda e: self._bookmark_canvas.configure(scrollregion=self._bookmark_canvas.bbox("all")))
        
        # 修复布局问题：确保内联Frame能够正确响应宽度变化
        def on_canvas_configure(event):
            self._bookmark_canvas.itemconfig("bookmark_inner", width=event.width)
        self._bookmark_canvas.bind("<Configure>", on_canvas_configure)
        
        # 绑定鼠标滚轮滚动事件（只绑定到Canvas，非全局）
        def on_mousewheel(event):
            # Windows系统使用
            self._bookmark_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"  # 阻止事件继续传播
        self._bookmark_canvas.bind("<MouseWheel>", on_mousewheel)
        self._bookmark_inner.bind("<MouseWheel>", on_mousewheel)
        
        def on_mousewheel_linux(event):
            # Linux系统使用
            if event.num == 4:
                self._bookmark_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._bookmark_canvas.yview_scroll(1, "units")
            return "break"
        self._bookmark_canvas.bind("<Button-4>", on_mousewheel_linux)
        self._bookmark_canvas.bind("<Button-5>", on_mousewheel_linux)
        self._bookmark_inner.bind("<Button-4>", on_mousewheel_linux)
        self._bookmark_inner.bind("<Button-5>", on_mousewheel_linux)

        # 刷新书签
        self._refresh_bookmarks()

    def _get_default_bookmarks(self):
        """获取默认预印本网站书签"""
        return [
            {"name": "arXiv", "url": "https://arxiv.org", "category": "preprint", "icon": "📄", "color": "#b33939", "id": "arxiv", "children": []},
            {"name": "bioRxiv", "url": "https://www.biorxiv.org", "category": "preprint", "icon": "🧬", "color": "#218c74", "id": "biorxiv", "children": []},
            {"name": "medRxiv", "url": "https://www.medrxiv.org", "category": "preprint", "icon": "💊", "color": "#227093", "id": "medrxiv", "children": []},
            {"name": "SSRN", "url": "https://www.ssrn.com", "category": "preprint", "icon": "📊", "color": "#cd6133", "id": "ssrn", "children": []},
            {"name": "Research Square", "url": "https://www.researchsquare.com", "category": "preprint", "icon": "🔬", "color": "#474787", "id": "researchsquare", "children": []},
            
            {"name": "Google Scholar", "url": "https://scholar.google.com", "category": "search", "icon": "🔍", "color": "#3498db", "id": "googlescholar", "children": []},
            {"name": "Semantic Scholar", "url": "https://www.semanticscholar.org", "category": "search", "icon": "🔎", "color": "#2ecc71", "id": "semanticscholar", "children": []},
            {"name": "Microsoft Academic", "url": "https://academic.microsoft.com", "category": "search", "icon": "📚", "color": "#9b59b6", "id": "msacademic", "children": []},
            {"name": "CNKI", "url": "https://www.cnki.net", "category": "search", "icon": "🇨🇳", "color": "#e74c3c", "id": "cnki", "children": []},
            {"name": "Web of Science", "url": "https://webofscience.com", "category": "search", "icon": "🌐", "color": "#f39c12", "id": "webofscience", "children": []},
            
            {"name": "Nature", "url": "https://www.nature.com", "category": "journal", "icon": "🌿", "color": "#1abc9c", "id": "nature", "children": []},
            {"name": "Science", "url": "https://www.science.org", "category": "journal", "icon": "🔬", "color": "#e67e22", "id": "science", "children": []},
            {"name": "Cell", "url": "https://www.cell.com", "category": "journal", "icon": "🧫", "color": "#c0392b", "id": "cell", "children": []},
            {"name": "IEEE Xplore", "url": "https://ieeexplore.ieee.org", "category": "journal", "icon": "⚡", "color": "#2980b9", "id": "ieee", "children": []},
            
            {"name": "GitHub", "url": "https://github.com", "category": "tool", "icon": "💻", "color": "#333333", "id": "github", "children": []},
            {"name": "GitLab", "url": "https://gitlab.com", "category": "tool", "icon": "🔧", "color": "#fca326", "id": "gitlab", "children": []},
            {"name": "Overleaf", "url": "https://www.overleaf.com", "category": "tool", "icon": "✏️", "color": "#46a046", "id": "overleaf", "children": []},
            {"name": "Zotero", "url": "https://www.zotero.org", "category": "tool", "icon": "📖", "color": "#cc2a36", "id": "zotero", "children": []},
            {"name": "Mendeley", "url": "https://www.mendeley.com", "category": "tool", "icon": "📑", "color": "#a3472e", "id": "mendeley", "children": []},
        ]

    def _load_bookmarks(self):
        """加载书签（从文件或默认）"""
        bookmark_file = BASE / "bookmarks.json"
        if bookmark_file.exists():
            try:
                bookmarks = json.loads(bookmark_file.read_text(encoding="utf-8"))
                # 为旧书签添加子书签字段和ID
                import uuid
                for bm in bookmarks:
                    if "children" not in bm:
                        bm["children"] = []
                    if "id" not in bm:
                        # 为没有ID的旧书签生成ID
                        name = bm.get("name", "unknown")
                        clean_name = self._sanitize_filename(name.lower().replace(" ", "_"))
                        bm["id"] = clean_name + "_" + str(uuid.uuid4())[:8]
                return bookmarks
            except:
                pass
        # 返回默认书签
        bookmarks = self._get_default_bookmarks()
        self._save_bookmarks(bookmarks)
        return bookmarks

    def _save_bookmarks(self, bookmarks):
        """保存书签到文件"""
        bookmark_file = BASE / "bookmarks.json"
        bookmark_file.write_text(json.dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_bookmarks(self):
        """刷新书签显示"""
        # 清空现有内容
        for widget in self._bookmark_inner.winfo_children():
            widget.destroy()
        
        bookmarks = self._load_bookmarks()
        search_text = self._bookmark_search_var.get().lower() if hasattr(self, '_bookmark_search_var') else ""
        category = self._bookmark_category_var.get() if hasattr(self, '_bookmark_category_var') else "all"
        
        # 过滤
        filtered = []
        for bm in bookmarks:
            # 分类过滤
            if category != "all":
                bm_category = bm.get("category", "")
                if bm_category != category:
                    continue
            
            # 搜索文本过滤（更智能的搜索）
            if search_text:
                bm_name = bm.get("name", "").lower()
                bm_url = bm.get("url", "").lower()
                bm_tags = [tag.lower() for tag in bm.get("tags", [])]
                
                # 检查是否匹配任意字段
                match_found = False
                if search_text in bm_name:
                    match_found = True
                elif search_text in bm_url:
                    match_found = True
                else:
                    for tag in bm_tags:
                        if search_text in tag:
                            match_found = True
                            break
                
                if not match_found:
                    continue
            
            filtered.append(bm)
        
        # 显示网格布局
        row, col = 0, 0
        max_cols = 3
        
        # 先配置所有列的权重，确保均衡分布
        for c in range(max_cols):
            self._bookmark_inner.grid_columnconfigure(c, weight=1, uniform="equal")
        
        for bm in filtered:
            # 创建卡片
            card = tk.Frame(self._bookmark_inner, bg="white", relief="raised", bd=2, padx=10, pady=10)
            card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            
            # 配置行权重
            self._bookmark_inner.grid_rowconfigure(row, weight=1)
            
            # 图标和名称
            header_frame = tk.Frame(card, bg="white")
            header_frame.pack(fill=tk.X)
            
            icon_label = tk.Label(header_frame, text=bm.get("icon", "🌐"), font=("", 16), bg="white")
            icon_label.pack(side=tk.LEFT, padx=(0, 10))
            
            name_label = tk.Label(header_frame, text=bm.get("name", "Untitled"), 
                                 font=("", 10, "bold"), bg="white", fg=bm.get("color", "#333"))
            name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # URL
            url_label = tk.Label(card, text=bm.get("url", "")[:40] + ("..." if len(bm.get("url", "")) > 40 else ""),
                                font=("", 8), bg="white", fg="#7f8c8d", anchor="w")
            url_label.pack(fill=tk.X, pady=(5, 0))
            
            # 按钮
            btn_frame = tk.Frame(card, bg="white")
            btn_frame.pack(fill=tk.X, pady=(10, 0))
            
            tk.Button(btn_frame, text="🌐打开", bg=bm.get("color", "#3498db"), fg="white", relief="flat",
                     command=lambda u=bm.get("url"): self._open_url(u)).pack(side=tk.LEFT, padx=(0, 5))
            tk.Button(btn_frame, text="切换", bg="#34495e", fg="white", 
                     relief="flat", command=lambda b=bm: self._select_bookmark_for_panel(b)).pack(side=tk.LEFT, padx=(0, 5))
            tk.Button(btn_frame, text="✏️", bg="#f1c40f", fg="white", relief="flat", width=3,
                     command=lambda b=bm: self._edit_bookmark_dialog(b)).pack(side=tk.LEFT, padx=2)
            tk.Button(btn_frame, text="🗑️", bg="#e74c3c", fg="white", relief="flat", width=3,
                     command=lambda b=bm: self._delete_bookmark(b)).pack(side=tk.RIGHT)
            
            # 卡片点击选中（更新右栏）
            card.bind("<Button-1>", lambda e, b=bm: self._select_bookmark_for_panel(b))
            icon_label.bind("<Button-1>", lambda e, b=bm: self._select_bookmark_for_panel(b))
            name_label.bind("<Button-1>", lambda e, b=bm: self._select_bookmark_for_panel(b))
            
            # 更新行列
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        if not filtered:
            ttk.Label(self._bookmark_inner, text="暂无书签\n\n点击添加按钮创建", 
                     font=("", 11), foreground="#95a5a6").grid(row=0, column=0, pady=40)

    def _add_bookmark_dialog(self):
        """添加书弹框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("添加书签")
        dlg.geometry("500x400")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="名称:").pack(pady=(15, 5))
        name_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=name_var, width=50).pack()

        ttk.Label(dlg, text="URL:").pack(pady=(10, 5))
        url_var = tk.StringVar()
        url_entry = ttk.Entry(dlg, textvariable=url_var, width=50)
        url_entry.pack()
        
        # 尝试从剪贴板获取
        try:
            clip = self.root.clipboard_get().strip()
            if _detect_urls(clip):
                url_var.set(clip)
                name_var.set(_extract_title_from_url(clip) or "")
        except:
            pass

        ttk.Label(dlg, text="分类:").pack(pady=(10, 5))
        category_var = tk.StringVar(value="preprint")
        cat_frame = ttk.Frame(dlg)
        cat_frame.pack()
        categories = [("预印本", "preprint"), ("学术搜索", "search"), ("期刊", "journal"), ("数据库", "database"), ("工具", "tool")]
        for text, val in categories:
            ttk.Radiobutton(cat_frame, text=text, variable=category_var, value=val).pack(side=tk.LEFT, padx=5)

        ttk.Label(dlg, text="图标 (emoji):").pack(pady=(10, 5))
        icon_var = tk.StringVar(value="🌐")
        ttk.Entry(dlg, textvariable=icon_var, width=10).pack()

        def save():
            name = name_var.get().strip()
            url = url_var.get().strip()
            if not name or not url:
                messagebox.showwarning("警告", "请填写名称和URL", parent=dlg)
                return
            
            # 生成书签ID（先清理非法字符）
            import uuid
            clean_name = self._sanitize_filename(name.lower().replace(" ", "_"))
            bookmark_id = clean_name + "_" + str(uuid.uuid4())[:8]
            
            bookmarks = self._load_bookmarks()
            bookmarks.append({
                "name": name,
                "url": url,
                "category": category_var.get(),
                "icon": icon_var.get() or "🌐",
                "color": "#3498db",
                "id": bookmark_id,
                "children": []
            })
            self._save_bookmarks(bookmarks)
            self._refresh_bookmarks()
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 从剪贴板粘贴", 
                  command=lambda: self._paste_clipboard_to_entry(url_entry, name_var)).pack(side=tk.LEFT, padx=5)

    def _edit_bookmark_dialog(self, bookmark):
        """编辑书弹框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("编辑书签")
        dlg.geometry("500x400")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="名称:").pack(pady=(15, 5))
        name_var = tk.StringVar(value=bookmark.get("name", ""))
        ttk.Entry(dlg, textvariable=name_var, width=50).pack()

        ttk.Label(dlg, text="URL:").pack(pady=(10, 5))
        url_var = tk.StringVar(value=bookmark.get("url", ""))
        ttk.Entry(dlg, textvariable=url_var, width=50).pack()

        ttk.Label(dlg, text="分类:").pack(pady=(10, 5))
        category_var = tk.StringVar(value=bookmark.get("category", "preprint"))
        cat_frame = ttk.Frame(dlg)
        cat_frame.pack()
        categories = [("预印本", "preprint"), ("学术搜索", "search"), ("期刊", "journal"), ("数据库", "database"), ("工具", "tool")]
        for text, val in categories:
            ttk.Radiobutton(cat_frame, text=text, variable=category_var, value=val).pack(side=tk.LEFT, padx=5)

        ttk.Label(dlg, text="图标 (emoji):").pack(pady=(10, 5))
        icon_var = tk.StringVar(value=bookmark.get("icon", "🌐"))
        ttk.Entry(dlg, textvariable=icon_var, width=10).pack()

        def save():
            name = name_var.get().strip()
            url = url_var.get().strip()
            if not name or not url:
                messagebox.showwarning("警告", "请填写名称和URL", parent=dlg)
                return
            
            bookmarks = self._load_bookmarks()
            for i, bm in enumerate(bookmarks):
                if bm.get("id") == bookmark.get("id") or bm.get("url") == bookmark.get("url"):
                    # 保留原有ID和children
                    bookmarks[i] = {
                        "name": name,
                        "url": url,
                        "category": category_var.get(),
                        "icon": icon_var.get() or "🌐",
                        "color": bookmark.get("color", "#3498db"),
                        "id": bm.get("id", bookmark.get("id")),
                        "children": bm.get("children", [])
                    }
                    break
            self._save_bookmarks(bookmarks)
            self._refresh_bookmarks()
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    def _delete_bookmark(self, bookmark):
        """删除书签"""
        if not messagebox.askyesno("确认删除", f"确定要删除书签 '{bookmark.get('name')}' 吗？"):
            return
        bookmarks = self._load_bookmarks()
        bookmarks = [bm for bm in bookmarks if bm.get("url") != bookmark.get("url")]
        self._save_bookmarks(bookmarks)
        self._refresh_bookmarks()

    def _import_bookmarks_from_browser(self):
        """从浏览器导入书签"""
        # 尝试找到浏览器书签文件位置
        # 支持 Chrome 和 Edge
        possible_paths = []
        
        if platform.system() == "Windows":
            app_data = os.environ.get("LOCALAPPDATA", "")
            possible_paths.extend([
                os.path.join(app_data, "Google", "Chrome", "User Data", "Default", "Bookmarks"),
                os.path.join(app_data, "Microsoft", "Edge", "User Data", "Default", "Bookmarks"),
            ])
        elif platform.system() == "Darwin":
            home = os.path.expanduser("~")
            possible_paths.extend([
                os.path.join(home, "Library", "Application Support", "Google", "Chrome", "Default", "Bookmarks"),
                os.path.join(home, "Library", "Application Support", "Microsoft Edge", "Default", "Bookmarks"),
            ])
        else:
            home = os.path.expanduser("~")
            possible_paths.extend([
                os.path.join(home, ".config", "google-chrome", "Default", "Bookmarks"),
                os.path.join(home, ".config", "chromium", "Default", "Bookmarks"),
            ])
        
        # 让用户选择书签文件
        file_path = filedialog.askopenfilename(
            title="选择浏览器书签文件",
            filetypes=[("所有文件", "*.*"), ("JSON", "*.json")]
        )
        
        if not file_path:
            # 尝试自动查找
            for path in possible_paths:
                if os.path.exists(path):
                    file_path = path
                    break
            
            if not file_path:
                messagebox.showinfo("提示", "未找到浏览器书签文件，请手动选择", parent=self.root)
                return
        
        try:
            # 解析 Chrome/Edge 书签格式
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            
            imported = []
            
            def extract_bookmarks(nodes):
                for node in nodes:
                    if node.get("type") == "url":
                        imported.append({
                            "name": node.get("name", ""),
                            "url": node.get("url", ""),
                            "category": "search",
                            "icon": "🌐",
                            "color": "#3498db"
                        })
                    elif node.get("type") == "folder":
                        extract_bookmarks(node.get("children", []))
            
            roots = data.get("roots", {})
            for root_key in ["bookmark_bar", "other_bookmarks", "synced"]:
                if root_key in roots:
                    extract_bookmarks(roots[root_key].get("children", []))
            
            if imported:
                # 让用户选择要导入的书签
                self._select_bookmarks_to_import(imported)
            else:
                messagebox.showinfo("提示", "未找到可导入的书签", parent=self.root)
        
        except Exception as e:
            messagebox.showerror("错误", f"导入书签失败: {str(e)}", parent=self.root)

    def _select_bookmarks_to_import(self, imported_bookmarks):
        """选择要导入的书签"""
        dlg = tk.Toplevel(self.root)
        dlg.title("选择要导入的书签")
        dlg.geometry("700x500")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"找到 {len(imported_bookmarks)} 个书签，请选择要导入的:", font=("", 10)).pack(pady=10, anchor="w", padx=10)

        # 滚动列表
        tree_frame = ttk.Frame(dlg)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(tree_frame, columns=("name", "url"), show="headings", selectmode="extended")
        tree.heading("name", text="名称")
        tree.heading("url", text="URL")
        tree.column("name", width=200)
        tree.column("url", width=400)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 添加数据
        for i, bm in enumerate(imported_bookmarks):
            tree.insert("", tk.END, values=(bm.get("name", ""), bm.get("url", "")), tags=(i,))
            tree.selection_set(tree.get_children())  # 默认全选

        def do_import():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("警告", "请选择要导入的书签", parent=dlg)
                return
            
            bookmarks = self._load_bookmarks()
            existing_urls = set(b.get("url") for b in bookmarks)
            
            imported_count = 0
            for item in selected:
                idx = int(tree.item(item, "tags")[0])
                bm = imported_bookmarks[idx]
                if bm.get("url") not in existing_urls:
                    bookmarks.append(bm)
                    imported_count += 1
            
            self._save_bookmarks(bookmarks)
            self._refresh_bookmarks()
            messagebox.showinfo("成功", f"成功导入 {imported_count} 个书签", parent=dlg)
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="导入选中", command=do_import).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    def _build_file_manager_section(self, parent):
        """构建文件管理区域"""
        # 创建 Notebook
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: 下载文件夹
        download_tab = ttk.Frame(notebook, padding=10)
        notebook.add(download_tab, text="📥 下载文件夹")
        self._build_download_folder_tab(download_tab)

        # Tab 2: 笔记文件夹
        notes_tab = ttk.Frame(notebook, padding=10)
        notebook.add(notes_tab, text="📝 笔记文件夹")
        self._build_notes_folder_tab(notes_tab)

        # Tab 3: 快速笔记
        quick_note_tab = ttk.Frame(notebook, padding=10)
        notebook.add(quick_note_tab, text="✏️ 快速笔记")
        self._build_quick_note_tab(quick_note_tab)

    def _build_download_folder_tab(self, parent):
        """构建下载文件夹管理Tab"""
        downloads_dir = BASE / "downloads"
        downloads_dir.mkdir(exist_ok=True)

        # 标题和按钮
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text=f"📂 {downloads_dir}", font=("", 10)).pack(side=tk.LEFT)
        ttk.Button(header_frame, text="📂 打开文件夹", command=lambda: open_file(str(downloads_dir))).pack(side=tk.RIGHT)

        # 文件列表
        self._download_file_list = self._build_file_list(parent, downloads_dir)

    def _build_notes_folder_tab(self, parent):
        """构建笔记文件夹管理Tab"""
        notes_dir = BASE / "Notes"
        notes_dir.mkdir(exist_ok=True)

        # 标题和按钮
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text=f"📂 {notes_dir}", font=("", 10)).pack(side=tk.LEFT)
        ttk.Button(header_frame, text="📂 打开文件夹", command=lambda: open_file(str(notes_dir))).pack(side=tk.RIGHT)
        ttk.Button(header_frame, text="➕ 新建笔记", command=lambda: self._create_new_note(notes_dir)).pack(side=tk.RIGHT, padx=5)

        # 文件列表
        self._notes_file_list = self._build_file_list(parent, notes_dir, is_notes=True)

    def _build_file_list(self, parent, directory, is_notes=False):
        """构建文件列表组件"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(container, columns=("name", "size", "modified"), show="headings", selectmode="browse")
        tree.heading("name", text="文件")
        tree.heading("size", text="大小")
        tree.heading("modified", text="修改时间")
        tree.column("name", width=300)
        tree.column("size", width=100)
        tree.column("modified", width=150)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 刷新文件列表
        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            
            files = sorted(directory.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            for f in files:
                if f.is_file():
                    stat = f.stat()
                    size = f"{stat.st_size / 1024:.1f} KB" if stat.st_size > 1024 else f"{stat.st_size} B"
                    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    tree.insert("", tk.END, values=(f.name, size, modified))

        # 双击打开
        def on_double_click(event):
            selection = tree.selection()
            if selection:
                filename = tree.item(selection[0], "values")[0]
                filepath = directory / filename
                if is_notes and filename.endswith(('.md', '.txt')):
                    self._edit_note_file(filepath)
                else:
                    open_file(str(filepath))

        tree.bind("<Double-1>", on_double_click)

        # 右键菜单
        menu = tk.Menu(tree, tearoff=0)
        menu.add_command(label="打开", command=lambda: on_double_click(None))
        menu.add_separator()
        menu.add_command(label="删除", command=lambda: self._delete_selected_file(tree, directory))
        
        tree.bind("<Button-3>", lambda e: menu.post(e.x_root, e.y_root))

        refresh()

        # 添加刷新按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="🔄 刷新列表", command=refresh).pack(side=tk.LEFT)

        return tree, refresh

    def _delete_selected_file(self, tree, directory):
        """删除选中的文件"""
        selection = tree.selection()
        if not selection:
            return
        
        filename = tree.item(selection[0], "values")[0]
        if messagebox.askyesno("确认删除", f"确定要删除 '{filename}' 吗？"):
            filepath = directory / filename
            filepath.unlink(missing_ok=True)
            if hasattr(self, '_download_file_list'):
                self._download_file_list[1]()
            if hasattr(self, '_notes_file_list'):
                self._notes_file_list[1]()

    def _create_new_note(self, notes_dir):
        """创建新笔记"""
        name = simpledialog.askstring("新笔记", "请输入笔记名称:", parent=self.root)
        if not name:
            return
        
        if not name.endswith('.md'):
            name += '.md'
        
        filepath = notes_dir / name
        filepath.write_text(f"# {name.replace('.md', '')}\n\n", encoding="utf-8")
        self._edit_note_file(filepath)
        if hasattr(self, '_notes_file_list'):
            self._notes_file_list[1]()

    def _edit_note_file(self, filepath):
        """编辑笔记文件"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"编辑笔记: {filepath.name}")
        dlg.geometry("800x600")
        dlg.transient(self.root)

        # 工具栏
        toolbar = ttk.Frame(dlg)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(toolbar, text="💾 保存", command=lambda: save_note()).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="📋 剪切", command=lambda: text.event_generate("<<Cut>>")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📋 复制", command=lambda: text.event_generate("<<Copy>>")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📋 粘贴", command=lambda: text.event_generate("<<Paste>>")).pack(side=tk.LEFT, padx=2)

        # 文本编辑区
        text_frame = ttk.Frame(dlg)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 11))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 加载文件内容
        if filepath.exists():
            text.insert("1.0", filepath.read_text(encoding="utf-8"))

        def save_note():
            content = text.get("1.0", tk.END)
            filepath.write_text(content, encoding="utf-8")
            if hasattr(self, '_notes_file_list'):
                self._notes_file_list[1]()

        dlg.protocol("WM_DELETE_WINDOW", lambda: (save_note(), dlg.destroy()))

    def _build_quick_note_tab(self, parent):
        """构建快速笔记Tab"""
        ttk.Label(parent, text="💡 快速笔记（自动保存）", font=("", 11, "bold")).pack(anchor="w", pady=(0, 10))

        # 文本编辑区
        text = tk.Text(parent, wrap=tk.WORD, font=("Consolas", 11))
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 加载快速笔记
        quick_note_file = BASE / "quick_note.md"
        if quick_note_file.exists():
            text.insert("1.0", quick_note_file.read_text(encoding="utf-8"))

        # 自动保存
        def auto_save():
            content = text.get("1.0", tk.END)
            quick_note_file.write_text(content, encoding="utf-8")
            parent.after(5000, auto_save)  # 每5秒自动保存

        auto_save()

        # 清空按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="🗑️ 清空", command=lambda: text.delete("1.0", tk.END)).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="💾 立即保存", command=lambda: quick_note_file.write_text(text.get("1.0", tk.END), encoding="utf-8")).pack(side=tk.LEFT, padx=5)

    def _show_bookmark_detail(self, bookmark):
        """显示书签详情页面"""
        self._clear_content()
        self._highlight_nav("search")
        
        bookmark_id = bookmark.get("id", bookmark.get("name", "unknown").lower().replace(" ", "_"))
        self._current_bookmark_id = bookmark_id
        self.nav_title.config(text=f"{bookmark.get('icon', '🌐')} {bookmark.get('name', '书签')}")
        
        color = bookmark.get("color", "#3498db")
        
        # 顶部信息
        top = ttk.Frame(self.content_frame)
        top.pack(fill=tk.X, pady=5)
        
        ttk.Button(top, text="← 返回书签", command=self._show_search_page).pack(side=tk.LEFT, padx=5)
        
        info_frame = ttk.Frame(top)
        info_frame.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(info_frame, text=f"{bookmark.get('icon', '🌐')} {bookmark.get('name', '书签')}", style="Title.TLabel").pack(anchor="w")
        ttk.Label(info_frame, text=f"[{bookmark.get('category', 'uncategorized')}]  |  {bookmark.get('url', '')}", style="Sub.TLabel").pack(anchor="w")
        
        ttk.Button(top, text="🌐 打开网站", command=lambda u=bookmark.get("url"): self._open_url(u)).pack(side=tk.RIGHT, padx=5)
        
        # 创建书签的独立文件夹
        bookmark_dir = BASE / "bookmarks" / bookmark_id
        bookmark_dir.mkdir(parents=True, exist_ok=True)
        
        # 标签页
        notebook = ttk.Notebook(self.content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Tab 1: 下载文件夹
        downloads_tab = ttk.Frame(notebook, padding=10)
        notebook.add(downloads_tab, text="📥 下载文件夹")
        self._build_bookmark_downloads_tab(downloads_tab, bookmark_dir)
        
        # Tab 2: 笔记文件夹
        notes_tab = ttk.Frame(notebook, padding=10)
        notebook.add(notes_tab, text="📝 笔记文件夹")
        self._build_bookmark_notes_tab(notes_tab, bookmark_dir)
        
        # Tab 3: 快速笔记
        quick_tab = ttk.Frame(notebook, padding=10)
        notebook.add(quick_tab, text="✏️ 快速笔记")
        self._build_bookmark_quick_note_tab(quick_tab, bookmark_dir, bookmark)
        
        # Tab 4: 书签信息
        info_tab = ttk.Frame(notebook, padding=10)
        notebook.add(info_tab, text="ℹ️ 信息")
        self._build_bookmark_info_tab(info_tab, bookmark)

    def _build_bookmark_downloads_tab(self, parent, bookmark_dir):
        """构建书签下载文件夹Tab（参考执行模式资源管理）"""
        downloads_dir = bookmark_dir / "downloads"
        downloads_dir.mkdir(exist_ok=True)
        
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text=f"📂 {downloads_dir}", font=("", 11)).pack(side=tk.LEFT)
        ttk.Button(header, text="📂 打开文件夹", command=lambda: open_file(str(downloads_dir))).pack(side=tk.RIGHT)
        
        # 文件列表
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        cols = ("name", "size", "modified")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=20, selectmode="extended")
        tree.heading("name", text="文件名")
        tree.heading("size", text="大小")
        tree.heading("modified", text="修改时间")
        
        tree.column("name", width=400)
        tree.column("size", width=100)
        tree.column("modified", width=150)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            files = sorted(downloads_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            for f in files:
                if f.is_file():
                    stat = f.stat()
                    size_str = f"{stat.st_size / 1024:.1f} KB" if stat.st_size > 1024 else f"{stat.st_size} B"
                    modified_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    tree.insert("", tk.END, values=(f.name, size_str, modified_str))
        
        def on_double_click(event):
            selection = tree.selection()
            if selection:
                filename = tree.item(selection[0], "values")[0]
                filepath = downloads_dir / filename
                open_file(str(filepath))
        
        tree.bind("<Double-1>", on_double_click)
        refresh()
        
        # 按钮区（可滚动）
        btn_frame = self._scrollable_button_bar(parent)
        
        ttk.Button(btn_frame, text="🔄 刷新", command=refresh).pack(side=tk.LEFT, padx=2)
        
        # 保存链接
        def save_link():
            dlg = tk.Toplevel(self.root)
            dlg.title("保存链接")
            dlg.geometry("500x300")
            dlg.transient(self.root)
            dlg.grab_set()
            
            ttk.Label(dlg, text="名称：").pack(pady=(15, 5))
            name_var = tk.StringVar()
            name_entry = ttk.Entry(dlg, textvariable=name_var, width=50)
            name_entry.pack()
            
            ttk.Label(dlg, text="URL：").pack(pady=(10, 5))
            url_var = tk.StringVar()
            url_entry = ttk.Entry(dlg, textvariable=url_var, width=50)
            url_entry.pack()
            
            # 尝试从剪贴板获取
            try:
                clip = self.root.clipboard_get().strip()
                if _detect_urls(clip):
                    url_var.set(clip)
                    name_var.set(_extract_title_from_url(clip) or "")
            except:
                pass
            
            name_entry.focus()
            
            def save():
                name = name_var.get().strip()
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("提示", "请填写URL", parent=dlg)
                    return
                if not name:
                    name = _extract_title_from_url(url) or url[:30]
                
                # 创建.url文件（Windows快捷方式）
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                url_file = downloads_dir / f"{safe_name}.url"
                
                # 避免文件名冲突
                counter = 1
                while url_file.exists():
                    url_file = downloads_dir / f"{safe_name}_{counter}.url"
                    counter += 1
                
                # 写入.url文件格式
                content = f"""[InternetShortcut]
URL={url}
"""
                url_file.write_text(content, encoding="utf-8")
                
                messagebox.showinfo("成功", f"链接已保存：{url_file.name}", parent=dlg)
                dlg.destroy()
                refresh()
            
            ttk.Button(dlg, text="保存", command=save).pack(pady=10)
        
        ttk.Button(btn_frame, text="🌐 保存链接", command=save_link).pack(side=tk.LEFT, padx=2)
        
        # 智能粘贴URL
        def smart_paste_urls():
            try:
                clip = self.root.clipboard_get().strip()
            except Exception:
                messagebox.showinfo("提示", "剪贴板为空")
                return
            
            urls = _detect_urls(clip)
            if not urls:
                messagebox.showinfo("提示", "剪贴板中没有找到URL")
                return
            
            # 确认导入
            confirm = messagebox.askyesno("确认", f"找到 {len(urls)} 个URL，是否保存到文件夹？")
            if not confirm:
                return
            
            saved = 0
            for url in urls:
                name = _extract_title_from_url(url) or url[:30]
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                url_file = downloads_dir / f"{safe_name}.url"
                
                # 避免文件名冲突
                counter = 1
                while url_file.exists():
                    url_file = downloads_dir / f"{safe_name}_{counter}.url"
                    counter += 1
                
                content = f"""[InternetShortcut]
URL={url}
"""
                url_file.write_text(content, encoding="utf-8")
                saved += 1
            
            messagebox.showinfo("完成", f"已保存 {saved} 个链接", parent=self.root)
            refresh()
        
        ttk.Button(btn_frame, text="📋 智能粘贴URL", command=smart_paste_urls).pack(side=tk.LEFT, padx=2)
        
        # 批量导入（参考执行模式）
        def batch_import_files():
            choice = messagebox.askyesno("选择导入方式", 
                                        "是：选择文件夹（递归扫描）\n否：直接选择文件")
            
            if choice:  # 文件夹模式
                import_dir = filedialog.askdirectory(
                    title=f"选择包含资源的目录（递归扫描）"
                )
                if not import_dir:
                    return
                
                exts = {
                    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
                    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
                    '.zip', '.rar', '.epub', '.mobi', '.mp3', '.flac', '.wav',
                    '.rmd', '.md', '.py', '.ipynb'
                }
                import_path = Path(import_dir)
                files = []
                total_scanned = 0
                
                for f in import_path.rglob("*"):
                    total_scanned += 1
                    if f.is_file() and f.suffix.lower() in exts:
                        if not f.name.startswith('.') and not f.name.startswith('~'):
                            files.append(f)
                
                if not files:
                    messagebox.showinfo("提示", f"扫描了 {total_scanned} 个文件，\n该目录下没有可导入的资源文件")
                    return
                
                self._log(f"📂 递归扫描 {import_path}：找到 {len(files)} 个文件")
                messagebox.showinfo("扫描结果", 
                                   f"📂 目录：{import_path.name}\n"
                                   f"📄 共扫描：{total_scanned} 个文件\n"
                                   f"✅ 找到：{len(files)} 个可导入文件")
                
                # 复制文件
                added = 0
                skipped = 0
                for f in files:
                    dest_path = downloads_dir / f.name
                    if not dest_path.exists():
                        import shutil
                        shutil.copy2(f, dest_path)
                        added += 1
                    else:
                        skipped += 1
                
                msg = f"已添加 {added} 个文件"
                if skipped:
                    msg += f"，跳过 {skipped} 个（已存在）"
                messagebox.showinfo("批量导入完成", msg)
                
            else:  # 文件模式
                files = filedialog.askopenfilenames(
                    title="批量选择文件",
                    filetypes=[
                        ("文档/PDF", "*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                        ("视频", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv"),
                        ("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp"),
                        ("所有文件", "*.*")
                    ]
                )
                if not files:
                    return
                
                added = 0
                skipped = 0
                for f_str in files:
                    f = Path(f_str)
                    dest_path = downloads_dir / f.name
                    if not dest_path.exists():
                        import shutil
                        shutil.copy2(f, dest_path)
                        added += 1
                    else:
                        skipped += 1
                
                msg = f"已添加 {added} 个文件"
                if skipped:
                    msg += f"，跳过 {skipped} 个（已存在）"
                messagebox.showinfo("批量导入完成", msg)
            
            refresh()
        
        ttk.Button(btn_frame, text="📁 批量导入", command=batch_import_files).pack(side=tk.LEFT, padx=2)
        
        def delete_file():
            selection = tree.selection()
            if not selection:
                return
            
            if len(selection) > 1:
                if not messagebox.askyesno("确认删除", f"确定要删除选中的 {len(selection)} 个文件吗？"):
                    return
                for sel in selection:
                    filename = tree.item(sel, "values")[0]
                    filepath = downloads_dir / filename
                    filepath.unlink(missing_ok=True)
            else:
                filename = tree.item(selection[0], "values")[0]
                if messagebox.askyesno("确认删除", f"确定要删除文件 '{filename}' 吗？"):
                    filepath = downloads_dir / filename
                    filepath.unlink(missing_ok=True)
            
            refresh()
        
        ttk.Button(btn_frame, text="🗑️ 删除", command=delete_file).pack(side=tk.LEFT, padx=2)

    def _build_bookmark_notes_tab(self, parent, bookmark_dir):
        """构建书签笔记文件夹Tab（使用Rmd格式）"""
        notes_dir = bookmark_dir / "notes"
        notes_dir.mkdir(exist_ok=True)
        
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text=f"📂 {notes_dir}", font=("", 11)).pack(side=tk.LEFT)
        ttk.Button(header, text="📂 打开文件夹", command=lambda: open_file(str(notes_dir))).pack(side=tk.RIGHT)
        
        def create_note():
            name = simpledialog.askstring("新建笔记", "请输入笔记名称:", parent=self.root)
            if not name:
                return
            if not name.endswith('.Rmd') and not name.endswith('.rmd'):
                name += '.Rmd'
            filepath = notes_dir / name
            # Rmd文件头部
            yaml_header = f"""---
title: "{name.replace('.Rmd', '').replace('.rmd', '')}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
output: html_document
---

# {name.replace('.Rmd', '').replace('.rmd', '')}

"""
            filepath.write_text(yaml_header, encoding="utf-8")
            self._edit_rmd_file(filepath, bookmark_dir)
            refresh()
        
        ttk.Button(header, text="➕ 新建笔记(Rmd)", command=create_note).pack(side=tk.RIGHT, padx=5)
        
        # 文件列表
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        cols = ("name", "size", "modified")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=20, selectmode="extended")
        tree.heading("name", text="文件名")
        tree.heading("size", text="大小")
        tree.heading("modified", text="修改时间")
        
        tree.column("name", width=400)
        tree.column("size", width=100)
        tree.column("modified", width=150)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            files = sorted(notes_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            for f in files:
                if f.is_file():
                    stat = f.stat()
                    size_str = f"{stat.st_size / 1024:.1f} KB" if stat.st_size > 1024 else f"{stat.st_size} B"
                    modified_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    tree.insert("", tk.END, values=(f.name, size_str, modified_str))
        
        def on_double_click(event):
            selection = tree.selection()
            if selection:
                filename = tree.item(selection[0], "values")[0]
                filepath = notes_dir / filename
                self._edit_rmd_file(filepath, bookmark_dir)
                refresh()
        
        tree.bind("<Double-1>", on_double_click)
        refresh()
        
        # 按钮区（可滚动）
        btn_frame = self._scrollable_button_bar(parent)
        
        ttk.Button(btn_frame, text="🔄 刷新", command=refresh).pack(side=tk.LEFT, padx=2)
        
        # 批量导入（参考执行模式）
        def batch_import_notes():
            choice = messagebox.askyesno("选择导入方式", 
                                        "是：选择文件夹（递归扫描）\n否：直接选择文件")
            
            if choice:  # 文件夹模式
                import_dir = filedialog.askdirectory(
                    title=f"选择包含笔记的目录（递归扫描）"
                )
                if not import_dir:
                    return
                
                exts = {'.rmd', '.Rmd', '.md', '.markdown', '.txt'}
                import_path = Path(import_dir)
                files = []
                total_scanned = 0
                
                for f in import_path.rglob("*"):
                    total_scanned += 1
                    if f.is_file() and f.suffix.lower() in exts:
                        if not f.name.startswith('.') and not f.name.startswith('~'):
                            files.append(f)
                
                if not files:
                    messagebox.showinfo("提示", f"扫描了 {total_scanned} 个文件，\n该目录下没有可导入的笔记文件")
                    return
                
                self._log(f"📂 递归扫描 {import_path}：找到 {len(files)} 个笔记文件")
                messagebox.showinfo("扫描结果", 
                                   f"📂 目录：{import_path.name}\n"
                                   f"📄 共扫描：{total_scanned} 个文件\n"
                                   f"✅ 找到：{len(files)} 个可导入笔记文件")
                
                # 复制文件
                added = 0
                skipped = 0
                for f in files:
                    dest_path = notes_dir / f.name
                    if not dest_path.exists():
                        import shutil
                        shutil.copy2(f, dest_path)
                        added += 1
                    else:
                        skipped += 1
                
                msg = f"已添加 {added} 个文件"
                if skipped:
                    msg += f"，跳过 {skipped} 个（已存在）"
                messagebox.showinfo("批量导入完成", msg)
                
            else:  # 文件模式
                files = filedialog.askopenfilenames(
                    title="批量选择笔记文件",
                    filetypes=[
                        ("Rmarkdown", "*.Rmd *.rmd"),
                        ("Markdown", "*.md *.markdown"),
                        ("文本文件", "*.txt"),
                        ("所有文件", "*.*")
                    ]
                )
                if not files:
                    return
                
                added = 0
                skipped = 0
                for f_str in files:
                    f = Path(f_str)
                    dest_path = notes_dir / f.name
                    if not dest_path.exists():
                        import shutil
                        shutil.copy2(f, dest_path)
                        added += 1
                    else:
                        skipped += 1
                
                msg = f"已添加 {added} 个文件"
                if skipped:
                    msg += f"，跳过 {skipped} 个（已存在）"
                messagebox.showinfo("批量导入完成", msg)
            
            refresh()
        
        ttk.Button(btn_frame, text="📁 批量导入", command=batch_import_notes).pack(side=tk.LEFT, padx=2)
        
        def delete_file():
            selection = tree.selection()
            if not selection:
                return
            
            if len(selection) > 1:
                if not messagebox.askyesno("确认删除", f"确定要删除选中的 {len(selection)} 个文件吗？"):
                    return
                for sel in selection:
                    filename = tree.item(sel, "values")[0]
                    filepath = notes_dir / filename
                    filepath.unlink(missing_ok=True)
            else:
                filename = tree.item(selection[0], "values")[0]
                if messagebox.askyesno("确认删除", f"确定要删除文件 '{filename}' 吗？"):
                    filepath = notes_dir / filename
                    filepath.unlink(missing_ok=True)
            
            refresh()
        
        ttk.Button(btn_frame, text="🗑️ 删除", command=delete_file).pack(side=tk.LEFT, padx=2)

    def _build_bookmark_quick_note_tab(self, parent, bookmark_dir, bookmark):
        """构建书签快速笔记Tab（使用Rmd格式和完整编辑器）"""
        quick_note_file = bookmark_dir / "quick_note.Rmd"
        if not quick_note_file.exists():
            # 创建默认的Rmd文件
            yaml_header = f"""---
title: "快速笔记 - {bookmark.get('name', '')}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
output: html_document
---

# 快速笔记

"""
            quick_note_file.write_text(yaml_header, encoding="utf-8")
        
        # 使用完整的Rmd编辑器
        self._build_inline_rmd_editor(parent, quick_note_file, bookmark_dir)

    def _build_bookmark_info_tab(self, parent, bookmark):
        """构建书签信息Tab"""
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(info_frame, text="📋 书签信息", font=("", 12, "bold")).pack(anchor="w", pady=(0, 15))
        
        info = [
            ("名称", bookmark.get("name", "")),
            ("URL", bookmark.get("url", "")),
            ("分类", bookmark.get("category", "")),
            ("图标", bookmark.get("icon", "")),
            ("ID", bookmark.get("id", "")),
        ]
        
        for label, value in info:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=f"{label}:", width=10).pack(side=tk.LEFT)
            ttk.Label(row, text=value).pack(side=tk.LEFT)
        
        ttk.Separator(info_frame, orient="horizontal").pack(fill=tk.X, pady=15)
        
        ttk.Label(info_frame, text="⚡ 快捷操作", font=("", 12, "bold")).pack(anchor="w", pady=(0, 15))
        
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="🌐 打开网站", command=lambda u=bookmark.get("url"): self._open_url(u)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="✏️ 编辑书签", command=lambda: self._edit_bookmark_dialog(bookmark)).pack(side=tk.LEFT, padx=5)

    def _build_sub_bookmarks_tab(self, parent, parent_bookmark):
        """构建子书签管理Tab"""
        # 标题
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="📑 链接列表", font=("", 12, "bold")).pack(side=tk.LEFT)
        
        # 子书签列表区域
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 子书签Treeview
        tree = ttk.Treeview(list_frame, columns=("name", "url"), show="headings", selectmode="browse")
        tree.heading("name", text="名称")
        tree.heading("url", text="URL")
        tree.column("name", width=200)
        tree.column("url", width=400)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 刷新函数
        def refresh_sub_bookmarks():
            for item in tree.get_children():
                tree.delete(item)
            
            # 获取当前书签的子书签
            bookmarks = self._load_bookmarks()
            current_bm = None
            for bm in bookmarks:
                if bm.get("id") == parent_bookmark.get("id"):
                    current_bm = bm
                    break
            
            if current_bm:
                children = current_bm.get("children", [])
                for child in children:
                    tree.insert("", tk.END, values=(child.get("name", ""), child.get("url", "")))
        
        # 双击打开子书签
        def on_double_click(event):
            selection = tree.selection()
            if selection:
                item = selection[0]
                url = tree.item(item, "values")[1]
                if url:
                    self._open_url(url)
        
        tree.bind("<Double-1>", on_double_click)
        
        # 按钮区域
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 1. 添加子书签
        def add_sub_bookmark():
            dlg = tk.Toplevel(self.root)
            dlg.title("添加链接")
            dlg.geometry("500x300")
            dlg.transient(self.root)
            dlg.grab_set()
            
            ttk.Label(dlg, text="名称:").pack(pady=(15, 5))
            name_var = tk.StringVar()
            name_entry = ttk.Entry(dlg, textvariable=name_var, width=50)
            name_entry.pack()
            
            ttk.Label(dlg, text="URL:").pack(pady=(10, 5))
            url_var = tk.StringVar()
            url_entry = ttk.Entry(dlg, textvariable=url_var, width=50)
            url_entry.pack()
            
            # 尝试从剪贴板获取
            try:
                clip = self.root.clipboard_get().strip()
                if _detect_urls(clip):
                    url_var.set(clip)
                    name_var.set(_extract_title_from_url(clip) or "")
            except:
                pass
            
            name_entry.focus()
            
            def save():
                name = name_var.get().strip()
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("提示", "请填写URL", parent=dlg)
                    return
                if not name:
                    name = _extract_title_from_url(url) or url[:30]
                
                # 添加到父书签的子列表
                bookmarks = self._load_bookmarks()
                for bm in bookmarks:
                    if bm.get("id") == parent_bookmark.get("id"):
                        if "children" not in bm:
                            bm["children"] = []
                        import uuid
                        bm["children"].append({
                            "name": name,
                            "url": url,
                            "id": f"sub_{uuid.uuid4().hex[:8]}",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        break
                self._save_bookmarks(bookmarks)
                refresh_sub_bookmarks()
                dlg.destroy()
            
            btn_frame2 = ttk.Frame(dlg)
            btn_frame2.pack(pady=20)
            ttk.Button(btn_frame2, text="保存", command=save).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame2, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="➕ 添加书签", command=add_sub_bookmark).pack(side=tk.LEFT, padx=2)
        
        # 2. 保存链接（类似下载文件夹Tab的功能）
        def save_link_dialog():
            dlg = tk.Toplevel(self.root)
            dlg.title("保存链接")
            dlg.geometry("500x300")
            dlg.transient(self.root)
            dlg.grab_set()
            
            ttk.Label(dlg, text="名称:").pack(pady=(15, 5))
            name_var = tk.StringVar()
            name_entry = ttk.Entry(dlg, textvariable=name_var, width=50)
            name_entry.pack()
            
            ttk.Label(dlg, text="URL:").pack(pady=(10, 5))
            url_var = tk.StringVar()
            url_entry = ttk.Entry(dlg, textvariable=url_var, width=50)
            url_entry.pack()
            
            # 尝试从剪贴板获取
            try:
                clip = self.root.clipboard_get().strip()
                if _detect_urls(clip):
                    url_var.set(clip)
                    name_var.set(_extract_title_from_url(clip) or "")
            except:
                pass
            
            name_entry.focus()
            
            def save():
                name = name_var.get().strip()
                url = url_var.get().strip()
                if not url:
                    messagebox.showwarning("提示", "请填写URL", parent=dlg)
                    return
                if not name:
                    name = _extract_title_from_url(url) or url[:30]
                
                # 添加到父书签的子列表
                bookmarks = self._load_bookmarks()
                for bm in bookmarks:
                    if bm.get("id") == parent_bookmark.get("id"):
                        if "children" not in bm:
                            bm["children"] = []
                        import uuid
                        bm["children"].append({
                            "name": name,
                            "url": url,
                            "id": f"sub_{uuid.uuid4().hex[:8]}",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        break
                self._save_bookmarks(bookmarks)
                refresh_sub_bookmarks()
                dlg.destroy()
            
            btn_frame2 = ttk.Frame(dlg)
            btn_frame2.pack(pady=20)
            ttk.Button(btn_frame2, text="保存", command=save).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame2, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="🌐 保存链接", command=save_link_dialog).pack(side=tk.LEFT, padx=2)
        
        # 3. 智能粘贴URL
        def smart_paste_urls():
            try:
                clip = self.root.clipboard_get().strip()
            except Exception:
                messagebox.showinfo("提示", "剪贴板为空")
                return
            
            urls = _detect_urls(clip)
            if not urls:
                messagebox.showinfo("提示", "剪贴板中没有找到URL")
                return
            
            # 确认导入
            confirm = messagebox.askyesno("确认", f"找到 {len(urls)} 个URL，是否保存为子书签？")
            if not confirm:
                return
            
            saved = 0
            bookmarks = self._load_bookmarks()
            for bm in bookmarks:
                if bm.get("id") == parent_bookmark.get("id"):
                    if "children" not in bm:
                        bm["children"] = []
                    
                    for url in urls:
                        name = _extract_title_from_url(url) or url[:30]
                        import uuid
                        bm["children"].append({
                            "name": name,
                            "url": url,
                            "id": f"sub_{uuid.uuid4().hex[:8]}",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        saved += 1
                    break
            
            self._save_bookmarks(bookmarks)
            messagebox.showinfo("完成", f"已保存 {saved} 个链接", parent=self.root)
            refresh_sub_bookmarks()
        
        ttk.Button(btn_frame, text="📋 智能粘贴URL", command=smart_paste_urls).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # 4. 删除子书签
        def delete_sub_bookmark():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("提示", "请选择要删除的子书签")
                return
            
            if not messagebox.askyesno("确认删除", "确定要删除选中的子书签吗？"):
                return
            
            item = selection[0]
            url_to_delete = tree.item(item, "values")[1]
            
            # 从父书签中删除
            bookmarks = self._load_bookmarks()
            for bm in bookmarks:
                if bm.get("id") == parent_bookmark.get("id"):
                    if "children" in bm:
                        bm["children"] = [c for c in bm["children"] if c.get("url") != url_to_delete]
                    break
            
            self._save_bookmarks(bookmarks)
            refresh_sub_bookmarks()
        
        ttk.Button(btn_frame, text="🗑️ 删除", command=delete_sub_bookmark).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # 5. 刷新列表
        ttk.Button(btn_frame, text="🔄 刷新", command=refresh_sub_bookmarks).pack(side=tk.LEFT, padx=2)
        
        # 初始加载
        refresh_sub_bookmarks()

    def _clear_search_right(self):
        """清空右栏内容，显示完整的书签管理界面"""
        for widget in self._search_right_frame.winfo_children():
            widget.destroy()
        
        # 主容器
        main_container = ttk.Frame(self._search_right_frame, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(main_container, text="📚 书签管理中心", 
                 font=("", 14, "bold")).pack(pady=(0, 15))
        
        # 快速操作按钮区
        quick_ops = ttk.Frame(main_container)
        quick_ops.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Button(quick_ops, text="➕ 添加书签", 
                  command=self._add_bookmark_dialog, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_ops, text="📥 从浏览器导入", 
                  command=self._import_bookmarks_from_browser, width=18).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(quick_ops, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # 统计信息
        bookmarks = self._load_bookmarks()
        stats_text = f"📊 当前共 {len(bookmarks)} 个书签"
        ttk.Label(quick_ops, text=stats_text, 
                 font=("", 10), foreground="#7f8c8d").pack(side=tk.LEFT, padx=10)
        
        ttk.Separator(main_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 分类统计和提示
        info_frame = ttk.Frame(main_container)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # 显示分类统计
        categories = {
            "preprint": "预印本",
            "search": "学术搜索", 
            "journal": "期刊",
            "database": "数据库",
            "tool": "工具"
        }
        
        cat_count = {}
        for bm in bookmarks:
            cat = bm.get("category", "other")
            cat_count[cat] = cat_count.get(cat, 0) + 1
        
        ttk.Label(info_frame, text="📂 书签分类统计:", font=("", 11, "bold")).pack(anchor="w", pady=(10, 5))
        
        cat_list = ttk.Frame(info_frame)
        cat_list.pack(fill=tk.X, anchor="w")
        
        for cat_key, cat_name in categories.items():
            count = cat_count.get(cat_key, 0)
            ttk.Label(cat_list, text=f"  • {cat_name}: {count} 个", 
                     font=("", 10)).pack(anchor="w")
        
        ttk.Separator(info_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        
        # 使用提示
        tips_frame = ttk.LabelFrame(info_frame, text="💡 使用提示", padding=10)
        tips_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        tips = [
            "1. 从左侧选择一个书签，可进入该书签的专用文件夹",
            "2. 每个书签有独立的下载和笔记文件夹",
            "3. 可从浏览器导入现有的书签",
            "4. 点击书签卡片上的 '🌐打开' 快速访问网站"
        ]
        
        for tip in tips:
            ttk.Label(tips_frame, text=tip, font=("", 10), 
                     foreground="#7f8c8d").pack(anchor="w", pady=3)

    def _select_bookmark_for_panel(self, bookmark):
        """选中书签并在右栏显示"""
        self._current_selected_bookmark = bookmark
        self._refresh_search_right(bookmark)

    def _sanitize_filename(self, filename):
        """清理文件名，移除非法字符"""
        import re
        # Windows文件系统非法字符: \ / : * ? " < > |
        invalid_chars = r'[\\/:*?"<>|]'
        # 替换非法字符为下划线
        sanitized = re.sub(invalid_chars, '_', filename)
        # 限制长度，防止文件名过长
        sanitized = sanitized[:200]
        # 去除首尾空格和点
        sanitized = sanitized.strip(' .')
        # 如果为空，使用默认名称
        if not sanitized:
            sanitized = "unknown_bookmark"
        return sanitized
    
    def _refresh_search_right(self, bookmark):
        """刷新右栏显示选中书签的内容"""
        self._clear_search_right()
        
        # 优先使用书签的ID，如果没有则使用清理后的名称
        bookmark_id = bookmark.get("id")
        if not bookmark_id:
            # 使用清理后的名称作为ID
            name = bookmark.get("name", "unknown")
            bookmark_id = self._sanitize_filename(name.lower().replace(" ", "_"))
        
        # 创建书签的独立文件夹
        bookmark_dir = BASE / "bookmarks" / bookmark_id
        bookmark_dir.mkdir(parents=True, exist_ok=True)
        
        # 标签页
        notebook = ttk.Notebook(self._search_right_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: 子书签管理（新增）
        sub_children_tab = ttk.Frame(notebook, padding=10)
        notebook.add(sub_children_tab, text="📑 书签")
        self._build_sub_bookmarks_tab(sub_children_tab, bookmark)
        
        # Tab 2: 下载文件夹
        downloads_tab = ttk.Frame(notebook, padding=10)
        notebook.add(downloads_tab, text="📥 下载文件夹")
        self._build_bookmark_downloads_tab(downloads_tab, bookmark_dir)
        
        # Tab 3: 笔记文件夹
        notes_tab = ttk.Frame(notebook, padding=10)
        notebook.add(notes_tab, text="📝 笔记文件夹")
        self._build_bookmark_notes_tab(notes_tab, bookmark_dir)
        
        # Tab 4: 快速笔记
        quick_tab = ttk.Frame(notebook, padding=10)
        notebook.add(quick_tab, text="✏️ 快速笔记")
        self._build_bookmark_quick_note_tab(quick_tab, bookmark_dir, bookmark)
        
        # Tab 5: 书签信息
        info_tab = ttk.Frame(notebook, padding=10)
        notebook.add(info_tab, text="ℹ️ 信息")
        self._build_bookmark_info_tab(info_tab, bookmark)


    def _edit_rmd_file(self, filepath, bookmark_dir):
        """编辑Rmd文件（完整编辑器对话框）"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"编辑笔记: {filepath.name}")
        dlg.geometry("1000x700")
        dlg.transient(self.root)
        dlg.grab_set()
        
        # 使用完整的内联编辑器
        self._build_inline_rmd_editor(dlg, filepath, bookmark_dir)
        
        # 关闭按钮
        ttk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=10)
    
    def _build_inline_rmd_editor(self, parent, note_file, bookmark_dir):
        """构建内联Rmd编辑器（复制执行模式笔记编辑器功能）"""
        self._current_rmd_file = note_file
        self._rmd_bookmark_dir = bookmark_dir
        
        # 标题
        ttk.Label(parent, text=f"📝 编辑: {note_file.name}", 
                 font=("", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # 工具栏（可滚动）
        toolbar = self._scrollable_button_bar(parent)
        
        def save_rmd():
            content = self._rmd_editor.get("1.0", tk.END)
            note_file.write_text(content, encoding="utf-8")
            self._rmd_status_label.config(text=f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}", 
                                          foreground="#27ae60")
            self._rmd_auto_saving = False
        
        ttk.Button(toolbar, text="💾 保存", command=save_rmd).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # 预览/编辑模式切换
        self._rmd_preview_mode = tk.BooleanVar(value=True)
        
        def toggle_mode():
            current_content = self._rmd_editor.get("1.0", tk.END + "-1c")
            if self._rmd_preview_mode.get():
                # 从预览模式切换到完整模式
                try:
                    full_content = note_file.read_text(encoding="utf-8")
                    cleaned_content = self._clean_note_content(full_content)
                    if current_content.strip() and current_content.strip() != cleaned_content.strip():
                        yaml_end = full_content.find('\n---\n', 4)
                        if yaml_end != -1:
                            header = full_content[:yaml_end + 5]
                            new_content = header + current_content
                            note_file.write_text(new_content, encoding="utf-8")
                        else:
                            note_file.write_text(current_content, encoding="utf-8")
                except:
                    note_file.write_text(current_content, encoding="utf-8")
            else:
                # 从完整模式切换到预览模式
                note_file.write_text(current_content, encoding="utf-8")
            
            self._rmd_preview_mode.set(not self._rmd_preview_mode.get())
            self._refresh_rmd_editor(note_file)
        
        ttk.Button(toolbar, text="👁️ 预览模式", command=toggle_mode).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # 插图功能
        def insert_image():
            img_path = filedialog.askopenfilename(
                title="选择图片",
                filetypes=[
                    ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp"),
                    ("所有文件", "*.*")
                ]
            )
            if img_path:
                img_file = Path(img_path)
                # 复制到images文件夹
                images_dir = bookmark_dir / "images"
                images_dir.mkdir(exist_ok=True)
                dest_path = images_dir / img_file.name
                import shutil
                shutil.copy2(img_file, dest_path)
                # 插入Markdown标签
                insert_text = f"![{img_file.name}]({dest_path.relative_to(bookmark_dir)})\n"
                self._rmd_editor.insert(tk.INSERT, insert_text)
        
        ttk.Button(toolbar, text="🖼️ 插图", command=insert_image).pack(side=tk.LEFT, padx=2)
        
        # 插入代码块
        def insert_code():
            code_template = """```{r}

```
"""
            self._rmd_editor.insert(tk.INSERT, code_template)
        
        ttk.Button(toolbar, text="💻 代码", command=insert_code).pack(side=tk.LEFT, padx=2)
        
        # 插入LaTeX公式
        def insert_math():
            math_template = "$$\n\n$$"
            self._rmd_editor.insert(tk.INSERT, math_template)
        
        ttk.Button(toolbar, text="📐 公式", command=insert_math).pack(side=tk.LEFT, padx=2)
        
        # 插入链接
        def insert_link():
            link_template = "[链接文本](URL)"
            self._rmd_editor.insert(tk.INSERT, link_template)
        
        ttk.Button(toolbar, text="📋 链接", command=insert_link).pack(side=tk.LEFT, padx=2)
        
        # 插入表格
        def insert_table():
            table_template = """| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 内容 | 内容 | 内容 |
"""
            self._rmd_editor.insert(tk.INSERT, table_template)
        
        ttk.Button(toolbar, text="📊 表格", command=insert_table).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        
        # 环境模板
        def insert_definition():
            env_template = """::: {.definition}
名称: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="📌 定义", command=insert_definition).pack(side=tk.LEFT, padx=2)
        
        def insert_theorem():
            env_template = """::: {.theorem}
名称: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="📜 定理", command=insert_theorem).pack(side=tk.LEFT, padx=2)
        
        def insert_corollary():
            env_template = """::: {.corollary}
名称: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="💡 推论", command=insert_corollary).pack(side=tk.LEFT, padx=2)
        
        def insert_example():
            env_template = """::: {.example}
示例: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="🎯 例子", command=insert_example).pack(side=tk.LEFT, padx=2)
        
        def insert_problem():
            env_template = """::: {.problem}
问题: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="❓ 问题", command=insert_problem).pack(side=tk.LEFT, padx=2)
        
        def insert_solution():
            env_template = """::: {.solution}
解答: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="✅ 解答", command=insert_solution).pack(side=tk.LEFT, padx=2)
        
        def insert_remark():
            env_template = """::: {.remark}
备注: 

内容:
:::
"""
            self._rmd_editor.insert(tk.INSERT, env_template)
        
        ttk.Button(toolbar, text="📝 注解", command=insert_remark).pack(side=tk.LEFT, padx=2)
        
        # 编辑器区域
        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self._rmd_editor = tk.Text(editor_frame, wrap=tk.WORD, font=("Consolas", 10),
                                   undo=True, maxundo=50,
                                   insertbackground="#2c3e50", selectbackground="#3498db",
                                   selectforeground="white", relief="flat", bg="#FAFAFA",
                                   padx=8, pady=6)
        editor_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self._rmd_editor.yview)
        self._rmd_editor.configure(yscrollcommand=editor_scroll.set)
        self._rmd_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        editor_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 语法高亮
        self._rmd_editor.tag_configure("yaml_delim", foreground="#7f8c8d", font=("Consolas", 10, "bold"))
        self._rmd_editor.tag_configure("yaml_key", foreground="#8e44ad")
        self._rmd_editor.tag_configure("yaml_val", foreground="#2980b9")
        self._rmd_editor.tag_configure("heading", foreground="#2c3e50", font=("Consolas", 11, "bold"))
        self._rmd_editor.tag_configure("heading2", foreground="#34495e", font=("Consolas", 10, "bold"))
        self._rmd_editor.tag_configure("code_block", foreground="#27ae60", font=("Consolas", 10))
        self._rmd_editor.tag_configure("code_delim", foreground="#95a5a6", font=("Consolas", 10, "bold"))
        self._rmd_editor.tag_configure("math_block", foreground="#c0392b", font=("Consolas", 10))
        self._rmd_editor.tag_configure("bold", foreground="#2c3e50", font=("Consolas", 10, "bold"))
        self._rmd_editor.tag_configure("italic", foreground="#7f8c8d")
        self._rmd_editor.tag_configure("link", foreground="#2980b9", underline=True)
        self._rmd_editor.tag_configure("image_ref", foreground="#e67e22")
        self._rmd_editor.tag_configure("blockquote", foreground="#7f8c8d", font=("Consolas", 10, "italic"))
        self._rmd_editor.tag_configure("list_item", foreground="#8e44ad")
        
        # 加载内容
        self._refresh_rmd_editor(note_file)
        
        # 状态条
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._rmd_status_label = ttk.Label(status_frame, text=f"📄 {note_file.name}", 
                                           font=("", 8), foreground="#95a5a6")
        self._rmd_status_label.pack(side=tk.LEFT)
        
        ttk.Label(status_frame, text="自动保存 | Ctrl+S 手动保存", 
                 font=("", 8), foreground="#bdc3c7").pack(side=tk.RIGHT)
        
        # 自动保存设置
        self._rmd_auto_saving = False
        self._rmd_auto_save_timer = None
        
        def on_modified(event=None):
            if not self._rmd_auto_saving:
                self._rmd_status_label.config(text="📝 已修改...", foreground="#f39c12")
                self._rmd_auto_saving = True
            if self._rmd_auto_save_timer:
                parent.after_cancel(self._rmd_auto_save_timer)
            self._rmd_auto_save_timer = parent.after(5000, save_rmd)
        
        self._rmd_editor.bind("<<Modified>>", on_modified)
        self._rmd_editor.bind("<Control-s>", lambda e: save_rmd())
        self._rmd_editor.bind("<FocusOut>", lambda e: save_rmd())
        
        # 快捷键绑定
        def wrap_with_bold():
            try:
                sel_text = self._rmd_editor.get(tk.SEL_FIRST, tk.SEL_LAST)
                self._rmd_editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self._rmd_editor.insert(tk.INSERT, f"**{sel_text}**")
            except:
                self._rmd_editor.insert(tk.INSERT, "****")
                self._rmd_editor.mark_set(tk.INSERT, "insert-2c")
        
        self._rmd_editor.bind("<Control-b>", lambda e: wrap_with_bold())
        
        def wrap_with_italic():
            try:
                sel_text = self._rmd_editor.get(tk.SEL_FIRST, tk.SEL_LAST)
                self._rmd_editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self._rmd_editor.insert(tk.INSERT, f"*{sel_text}*")
            except:
                self._rmd_editor.insert(tk.INSERT, "**")
                self._rmd_editor.mark_set(tk.INSERT, "insert-1c")
        
        self._rmd_editor.bind("<Control-i>", lambda e: wrap_with_italic())
    
    def _refresh_rmd_editor(self, note_file):
        """刷新Rmd编辑器显示"""
        if hasattr(self, '_rmd_editor') and self._rmd_editor.winfo_exists():
            self._rmd_editor.delete("1.0", tk.END)
            content = note_file.read_text(encoding="utf-8")
            
            if self._rmd_preview_mode.get():
                # 预览模式显示清理后的内容
                display_content = self._clean_note_content(content)
                self._rmd_editor.insert("1.0", display_content)
            else:
                # 完整模式显示所有内容
                self._rmd_editor.insert("1.0", content)
            
            self._apply_rmd_syntax_highlighting()
    
    def _apply_rmd_syntax_highlighting(self):
        """应用Rmd语法高亮"""
        if not hasattr(self, '_rmd_editor') or not self._rmd_editor.winfo_exists():
            return
        
        editor = self._rmd_editor
        content = editor.get("1.0", tk.END)
        lines = content.split('\n')
        in_yaml = False
        yaml_done = False
        in_code = False
        
        # 清除现有标签
        for tag in ("yaml_delim", "yaml_key", "yaml_val", "heading", "heading2",
                    "code_block", "code_delim", "math_block", "bold", "italic",
                    "link", "image_ref", "blockquote", "list_item"):
            editor.tag_remove(tag, "1.0", tk.END)
        
        for i, line in enumerate(lines):
            li = i + 1
            stripped = line.strip()
            
            if not yaml_done and stripped == '---':
                editor.tag_add("yaml_delim", f"{li}.0", f"{li}.end")
                if in_yaml:
                    yaml_done = True
                    in_yaml = False
                else:
                    in_yaml = True
                continue
            
            if in_yaml:
                import re
                match = re.match(r'^(\s*[\w_-]+)(\s*:\s*)(.*)', line)
                if match:
                    editor.tag_add("yaml_key", f"{li}.0", f"{li}.{match.end(1)}")
                    if match.group(3).strip():
                        editor.tag_add("yaml_val", f"{li}.{match.start(3)}", f"{li}.end")
                continue
            
            if stripped.startswith('```'):
                editor.tag_add("code_delim", f"{li}.0", f"{li}.end")
                if in_code:
                    in_code = False
                    # 标记整个代码块
                    if hasattr(self, '_rmd_code_start') and self._rmd_code_start:
                        editor.tag_add("code_block", f"{self._rmd_code_start}.0", f"{li}.end")
                        self._rmd_code_start = None
                else:
                    in_code = True
                    self._rmd_code_start = li
                continue
            
            if in_code:
                continue
            
            if stripped.startswith('$$'):
                editor.tag_add("math_block", f"{li}.0", f"{li}.end")
                continue
            
            if stripped.startswith('# '):
                editor.tag_add("heading", f"{li}.0", f"{li}.end")
            elif stripped.startswith('## '):
                editor.tag_add("heading2", f"{li}.0", f"{li}.end")
            
            # 标记引用
            if stripped.startswith('>'):
                editor.tag_add("blockquote", f"{li}.0", f"{li}.end")
            
            # 标记列表项
            if stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('+ '):
                editor.tag_add("list_item", f"{li}.0", f"{li}.end")
            
            # 标记粗体和斜体
            import re
            # 粗体 **...**
            for match in re.finditer(r'\*\*(.*?)\*\*', line):
                editor.tag_add("bold", f"{li}.{match.start()}", f"{li}.{match.end()}")
            
            # 斜体 *...*
            for match in re.finditer(r'\*(.*?)\*', line):
                # 排除粗体
                if len(match.group(1)) > 0 and not (line[max(0, match.start()-2):match.start()] == '**' or line[match.end():match.end()+2] == '**'):
                    editor.tag_add("italic", f"{li}.{match.start()}", f"{li}.{match.end()}")
            
            # 链接 [text](url)
            for match in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', line):
                editor.tag_add("link", f"{li}.{match.start()}", f"{li}.{match.end()}")
            
            # 图片 ![text](url)
            for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', line):
                editor.tag_add("image_ref", f"{li}.{match.start()}", f"{li}.{match.end()}")

    # ============ 项目管理界面 ============

    def _show_projects_page(self):
        """显示项目管理界面"""
        self._clear_content()
        self._highlight_nav("projects")
        self.nav_title.config(text="📁 项目管理")

        # 主布局
        main_frame = ttk.Frame(self.content_frame)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧：项目列表
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        left_frame.config(width=300)

        # 项目列表标题
        list_header = ttk.Frame(left_frame)
        list_header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(list_header, text="项目列表", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(list_header, text="➕ 新建", command=self._create_project_dialog).pack(side=tk.RIGHT)

        # 项目列表
        self._projects_tree = ttk.Treeview(left_frame, columns=("name", "status"), show="headings", selectmode="browse")
        self._projects_tree.heading("name", text="项目名称")
        self._projects_tree.heading("status", text="状态")
        self._projects_tree.column("name", width=200)
        self._projects_tree.column("status", width=80)

        proj_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._projects_tree.yview)
        self._projects_tree.configure(yscrollcommand=proj_scroll.set)

        self._projects_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        proj_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._projects_tree.bind("<<TreeviewSelect>>", self._on_project_select)

        # 右侧：项目详情
        self._project_detail_frame = ttk.Frame(main_frame)
        self._project_detail_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 初始刷新
        self._refresh_projects_list()
        # 默认选中第一个项目
        items = self._projects_tree.get_children()
        if items:
            self._projects_tree.selection_set(items[0])
            self._on_project_select(None)
        else:
            self._clear_project_detail()

    def _refresh_projects_list(self):
        """刷新项目列表"""
        for item in self._projects_tree.get_children():
            self._projects_tree.delete(item)

        projects = self.project_mgr.get_all_projects()
        for proj in projects:
            status_text = {
                "active": "🟢 活动",
                "completed": "✅ 完成",
                "archived": "📦 归档"
            }.get(proj.get("status", "active"), "活动")
            self._projects_tree.insert("", tk.END, values=(proj["name"], status_text), tags=(proj["id"],))

    def _clear_project_detail(self):
        """清空项目详情"""
        for widget in self._project_detail_frame.winfo_children():
            widget.destroy()
        ttk.Label(self._project_detail_frame, text="请从左侧选择一个项目", font=("", 12), foreground="#95a5a6").pack(expand=True)

    def _on_project_select(self, event):
        """选中项目时显示详情"""
        selection = self._projects_tree.selection()
        if not selection:
            self._clear_project_detail()
            return

        item = selection[0]
        proj_id = self._projects_tree.item(item, "tags")[0]
        proj = self.project_mgr.get_project_by_id(proj_id)
        if proj:
            self._show_project_detail(proj)

    def _show_project_detail(self, project):
        """显示项目详情"""
        for widget in self._project_detail_frame.winfo_children():
            widget.destroy()

        # 项目信息区
        info_frame = ttk.LabelFrame(self._project_detail_frame, text="项目信息", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        # 基本信息
        ttk.Label(info_frame, text=f"📂 {project['name']}", font=("", 14, "bold")).pack(anchor="w")
        ttk.Label(info_frame, text=f"📍 位置: {project['folder_path']}", foreground="#7f8c8d").pack(anchor="w", pady=5)
        if project.get("description"):
            ttk.Label(info_frame, text=f"📝 {project['description']}", foreground="#7f8c8d").pack(anchor="w", pady=5)

        # 创建时间
        created = datetime.fromisoformat(project["created_at"]) if project.get("created_at") else None
        if created:
            ttk.Label(info_frame, text=f"🕐 创建于: {created.strftime('%Y-%m-%d %H:%M')}").pack(anchor="w")

        # 标签
        if project.get("tags"):
            tag_frame = ttk.Frame(info_frame)
            tag_frame.pack(fill=tk.X, pady=5)
            ttk.Label(tag_frame, text="🏷️ 标签: ").pack(side=tk.LEFT)
            for tag in project["tags"]:
                ttk.Label(tag_frame, text=f"[{tag}]", background="#ecf0f1", padding=3).pack(side=tk.LEFT, padx=2)

        # 操作按钮
        btn_frame = ttk.Frame(self._project_detail_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_frame, text="📂 打开文件夹", command=lambda: open_file(project["folder_path"])).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✏️ 编辑", command=lambda: self._edit_project_dialog(project)).pack(side=tk.LEFT, padx=2)
        
        status_btn = ttk.Button(btn_frame, text="📦 归档", command=lambda: self._archive_project(project))
        status_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(btn_frame, text="🗑️ 删除", command=lambda: self._delete_project_dialog(project)).pack(side=tk.LEFT, padx=2)

        # 项目文件浏览器
        files_frame = ttk.LabelFrame(self._project_detail_frame, text="项目文件", padding=10)
        files_frame.pack(fill=tk.BOTH, expand=True)

        self._build_project_file_browser(files_frame, project)

    def _edit_project_file(self, file_path, project):
        """编辑项目文件 - 支持多种格式"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"编辑 - {file_path.name}")
        dlg.geometry("900x700")
        dlg.transient(self.root)
        dlg.grab_set()
        
        ext = file_path.suffix.lower()
        
        if ext in [".md", ".rmd", ".txt", ".tex", ".html", ".css", ".js", ".py", ".r"]:
            # 使用类似Rmd的编辑器
            self._build_project_file_editor(dlg, file_path, project)
        else:
            # 其他类型用系统默认打开
            open_file(str(file_path))
            dlg.destroy()
    
    def _build_project_file_editor(self, parent, file_path, project):
        """构建项目文件编辑器"""
        self._current_proj_edit_file = file_path
        
        # 标题
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Label(header, text=f"📝 编辑: {file_path.name}", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text=f"项目: {project['name']}", font=("", 9), foreground="#7f8c8d").pack(side=tk.RIGHT)
        
        # 编辑器区域
        edit_frame = ttk.Frame(parent)
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        editor = tk.Text(edit_frame, wrap="word", font=("Consolas", 11))
        scroll = ttk.Scrollbar(edit_frame, orient=tk.VERTICAL, command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 加载文件内容
        try:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                editor.insert("1.0", content)
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")
        
        # 状态栏
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        status_label = ttk.Label(status_frame, text="就绪", foreground="#27ae60")
        status_label.pack(side=tk.LEFT)
        
        # 保存函数
        def save_file():
            try:
                content = editor.get("1.0", tk.END)
                file_path.write_text(content, encoding="utf-8")
                status_label.config(text=f"✅ 已保存 {datetime.now().strftime('%H:%M:%S')}", foreground="#27ae60")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")
                status_label.config(text=f"❌ 保存失败", foreground="#e74c3c")
        
        # 按钮栏
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="💾 保存", command=save_file).pack(side=tk.LEFT, padx=2)
        ttk.Separator(btn_frame, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10)
        
        # 根据文件类型添加辅助按钮
        ext = file_path.suffix.lower()
        if ext in [".rmd", ".md"]:
            # 添加预览按钮
            def preview():
                save_file()
                if ext == ".rmd":
                    # Rmd预览
                    import subprocess
                    try:
                        subprocess.Popen(["Rscript", "-e", f"rmarkdown::render('{file_path}')"], 
                                        cwd=str(file_path.parent))
                        html_path = file_path.with_suffix(".html")
                        if html_path.exists():
                            open_file(str(html_path))
                    except:
                        messagebox.showinfo("提示", "请确保已安装R和rmarkdown包")
                else:
                    open_file(str(file_path))
            
            ttk.Button(btn_frame, text="👁️ 预览", command=preview).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(btn_frame, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10)
        ttk.Button(btn_frame, text="📂 在文件夹中打开", command=lambda: open_file(str(file_path.parent))).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="关闭", command=parent.destroy).pack(side=tk.RIGHT)

    def _build_project_file_browser(self, parent, project):
        """构建项目文件浏览器（支持子文件夹、创建文件、编辑）"""
        folder_path = Path(project["folder_path"])
        self._current_proj_folder = folder_path
        self._current_project = project

        # 文件列表容器（上方）
        list_container = ttk.Frame(parent)
        list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # 文件列表
        tree = ttk.Treeview(list_container, columns=("name", "type", "modified"), show="tree headings")
        tree.heading("#0", text="名称")
        tree.heading("name", text="文件名")
        tree.heading("type", text="类型")
        tree.heading("modified", text="修改时间")
        tree.column("#0", width=200, stretch=True)
        tree.column("name", width=0, stretch=False)  # 隐藏，因为名称在#0列
        tree.column("type", width=100)
        tree.column("modified", width=150)

        scroll = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 递归填充目录
        def populate_tree(parent_node, current_path):
            if not current_path.exists():
                return
            
            items = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                if item.name.startswith('.'):
                    continue
                
                stat = item.stat()
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                
                if item.is_dir():
                    # 文件夹
                    node_id = tree.insert(parent_node, tk.END, text=f"📁 {item.name}", values=("", "文件夹", modified), open=False)
                    # 预填充一个占位符，使文件夹可展开
                    tree.insert(node_id, tk.END, text="")
                else:
                    # 文件
                    ext = item.suffix[1:].upper() if item.suffix else "文件"
                    tree.insert(parent_node, tk.END, text=f"📄 {item.name}", values=("", ext, modified))

        # 展开文件夹时加载内容
        def on_open_node(event):
            item_id = tree.focus()
            if not item_id:
                return
            
            # 获取节点的完整路径
            def get_full_path(node):
                parts = []
                current_node = node
                while current_node:
                    text = tree.item(current_node, "text")
                    # 只处理非空的文本（根节点是空字符串，不要加入）
                    if text and text.strip():
                        name = text[2:] if text.startswith(("📁", "📄")) else text
                        parts.insert(0, name)
                    current_node = tree.parent(current_node)
                # 直接用所有收集到的部分构建路径
                return folder_path.joinpath(*parts)

            current_path = get_full_path(item_id)
            
            # 检查是否有占位符子节点
            children = tree.get_children(item_id)
            if len(children) == 1 and tree.item(children[0], "text") == "":
                # 删除占位符，加载实际内容
                tree.delete(children[0])
                populate_tree(item_id, current_path)

        tree.bind("<<TreeviewOpen>>", on_open_node)

        # 初始化按钮变量 - 后面会赋值
        selected_edit_btn = None
        selected_delete_btn = None

        # 获取选中文件路径
        def get_selected_path():
            sel = tree.selection()
            if not sel:
                return None
            
            item_id = sel[0]
            
            def get_full_path(node):
                parts = []
                current_node = node
                while current_node:
                    text = tree.item(current_node, "text")
                    # 只处理非空的文本（根节点是空字符串，不要加入）
                    if text and text.strip():
                        name = text[2:] if text.startswith(("📁", "📄")) else text
                        parts.insert(0, name)
                    current_node = tree.parent(current_node)
                # 直接用所有收集到的部分构建路径
                return folder_path.joinpath(*parts)
            
            return get_full_path(item_id)

        # 选择变化事件 - 更新按钮状态
        def on_select(event):
            # 获取当前选中的项
            sel = tree.selection()
            if sel:
                # 先从Treeview的显示信息判断类型（更可靠）
                item_id = sel[0]
                item_text = tree.item(item_id, "text")
                is_folder = item_text.startswith("📁")
                is_file = item_text.startswith("📄")
                
                # 更新按钮状态
                if selected_edit_btn and selected_delete_btn:
                    if is_folder:
                        # 是文件夹 - 禁用编辑，启用删除
                        selected_edit_btn.state(['disabled'])
                        selected_delete_btn.state(['!disabled'])
                    elif is_file:
                        # 是文件 - 启用编辑和删除
                        selected_edit_btn.state(['!disabled'])
                        selected_delete_btn.state(['!disabled'])
                    else:
                        # 其他情况
                        selected_edit_btn.state(['disabled'])
                        selected_delete_btn.state(['disabled'])
            else:
                # 没有选中
                if selected_edit_btn and selected_delete_btn:
                    selected_edit_btn.state(['disabled'])
                    selected_delete_btn.state(['disabled'])

        # 双击打开文件或文件夹
        def on_double_click(event):
            full_path = get_selected_path()
            if not full_path:
                return
            
            if full_path.is_dir():
                # 切换展开/折叠
                item_id = tree.selection()[0]
                if tree.item(item_id, "open"):
                    tree.item(item_id, open=False)
                else:
                    tree.item(item_id, open=True)
            else:
                # 检查是否是可编辑文件类型，是则用内置编辑器，否则用系统默认
                ext = full_path.suffix.lower()
                if ext in [".md", ".rmd", ".py", ".r", ".txt", ".tex", ".html", ".css", ".js"]:
                    self._edit_project_file(full_path, project)
                else:
                    open_file(str(full_path))

        tree.bind("<Double-1>", on_double_click)

        # 刷新文件列表
        def refresh_files():
            for item in tree.get_children():
                tree.delete(item)
            populate_tree("", folder_path)

        refresh_files()

        # 创建新文件
        def create_new_file():
            # 先确定在哪里创建 - 如果选中文件夹则在该文件夹创建，否则在根目录
            selected_path = get_selected_path()
            target_dir = folder_path
            
            if selected_path and selected_path.is_dir():
                target_dir = selected_path
            elif selected_path and selected_path.is_file():
                target_dir = selected_path.parent
            
            # 弹出对话框选择文件类型
            dlg = tk.Toplevel(self.root)
            dlg.title("新建文件")
            dlg.geometry("400x450")
            dlg.transient(self.root)
            dlg.grab_set()
            
            ttk.Label(dlg, text="选择文件类型:", font=("", 11, "bold")).pack(pady=(15, 10))
            
            # 文件类型按钮
            type_frame = ttk.Frame(dlg)
            type_frame.pack(fill=tk.X, padx=20)
            
            file_type_var = tk.StringVar(value="md")
            
            types = [
                ("📝 Markdown (.md)", "md"),
                ("📊 R Notebook (.Rmd)", "Rmd"),
                ("💻 Python (.py)", "py"),
                ("📈 R Script (.R)", "R"),
                ("📄 文本文件 (.txt)", "txt"),
                ("📘 LaTeX (.tex)", "tex"),
                ("🌐 HTML (.html)", "html"),
                ("🎨 CSS (.css)", "css"),
                ("⚡ JavaScript (.js)", "js")
            ]
            
            for text, ext in types:
                rb = ttk.Radiobutton(type_frame, text=text, variable=file_type_var, value=ext)
                rb.pack(anchor="w", pady=3)
            
            ttk.Label(dlg, text="文件名:", font=("", 10)).pack(pady=(15, 5))
            name_var = tk.StringVar(value="未命名")
            name_entry = ttk.Entry(dlg, textvariable=name_var, width=40)
            name_entry.pack()
            name_entry.select_range(0, tk.END)
            name_entry.focus_set()
            
            def do_create():
                name = name_var.get().strip()
                if not name:
                    messagebox.showwarning("提示", "请输入文件名", parent=dlg)
                    return
                
                ext = file_type_var.get()
                if not name.lower().endswith(f".{ext.lower()}"):
                    name = f"{name}.{ext}"
                
                file_path = target_dir / name
                
                if file_path.exists():
                    if not messagebox.askyesno("文件存在", f"{name} 已存在，是否覆盖?", parent=dlg):
                        return
                
                try:
                    # 根据类型创建内容
                    if ext == "md":
                        content = f"# {name}\n\n"
                    elif ext == "Rmd":
                        content = f'''---
title: "{name}"
output: html_document
---

```r
# 代码开始

```
'''
                    elif ext == "py":
                        content = f'"""\n项目: {project["name"]}\n文件: {name}\n"""\n\n'
                    elif ext == "R":
                        content = f'## 项目: {project["name"]} | 文件: {name}\n\n'
                    elif ext == "tex":
                        content = f'''\\documentclass{{article}}
\\title{{{name}}}
\\begin{{document}}
\\maketitle

\\end{{document}}
'''
                    elif ext == "html":
                        content = f'''<!DOCTYPE html>
<html>
<head>
    <title>{name}</title>
</head>
<body>

</body>
</html>
'''
                    elif ext == "css":
                        content = f"/* {name} */\n\n"
                    elif ext == "js":
                        content = f"// {name}\n\n"
                    else:
                        content = f"// {name}\n\n"
                    
                    file_path.write_text(content, encoding="utf-8")
                    refresh_files()
                    dlg.destroy()
                    
                    # 自动打开编辑
                    self._edit_project_file(file_path, project)
                    
                except Exception as e:
                    messagebox.showerror("错误", f"创建文件失败: {e}", parent=dlg)
            
            btn_frame = ttk.Frame(dlg)
            btn_frame.pack(pady=20)
            ttk.Button(btn_frame, text="创建", command=do_create).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        # 创建新文件夹
        def create_new_folder():
            selected_path = get_selected_path()
            target_dir = folder_path
            
            if selected_path and selected_path.is_dir():
                target_dir = selected_path
            elif selected_path and selected_path.is_file():
                target_dir = selected_path.parent
            
            from tkinter import simpledialog
            name = simpledialog.askstring("新建文件夹", "输入文件夹名:", initialvalue="新建文件夹")
            if not name:
                return
            
            try:
                folder_to_create = target_dir / name
                folder_to_create.mkdir(parents=True, exist_ok=True)
                refresh_files()
            except Exception as e:
                messagebox.showerror("错误", f"创建文件夹失败: {e}")

        # 编辑选中文件
        def edit_selected_file():
            # 先从Treeview判断类型（更可靠）
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请选择一个文件进行编辑")
                return
            item_id = sel[0]
            item_text = tree.item(item_id, "text")
            if not item_text.startswith("📄"):
                messagebox.showinfo("提示", "请选择一个文件进行编辑")
                return
            # 获取路径并打开编辑
            full_path = get_selected_path()
            if full_path:
                self._edit_project_file(full_path, project)

        # 删除选中项
        def delete_selected():
            # 先从Treeview判断类型（更可靠）
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请选择要删除的文件或文件夹")
                return
            item_id = sel[0]
            item_text = tree.item(item_id, "text")
            is_folder = item_text.startswith("📁")
            is_file = item_text.startswith("📄")
            if not is_folder and not is_file:
                messagebox.showinfo("提示", "请选择要删除的文件或文件夹")
                return
            # 获取路径
            full_path = get_selected_path()
            if not full_path:
                return
            
            msg = f"确定要删除「{full_path.name}」吗？"
            if is_folder:
                msg += "\n\n⚠️ 这是一个文件夹，将删除其下所有内容！"
            
            if messagebox.askyesno("确认删除", msg):
                try:
                    if is_folder:
                        import shutil
                        shutil.rmtree(full_path)
                    else:
                        full_path.unlink()
                    refresh_files()
                except Exception as e:
                    messagebox.showerror("错误", f"删除失败: {e}")

        # 操作按钮（下方）
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="📄 新建文件", command=create_new_file).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="📁 新建文件夹", command=create_new_folder).pack(side=tk.LEFT, padx=5)
        # 保存按钮引用以便后面控制状态
        selected_edit_btn = ttk.Button(btn_frame, text="✏️ 编辑", command=edit_selected_file)
        selected_edit_btn.pack(side=tk.LEFT, padx=5)
        selected_delete_btn = ttk.Button(btn_frame, text="🗑️ 删除", command=delete_selected)
        selected_delete_btn.pack(side=tk.LEFT, padx=5)
        ttk.Separator(btn_frame, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10)
        ttk.Button(btn_frame, text="🔄 刷新", command=refresh_files).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="📂 打开根文件夹", command=lambda: open_file(str(folder_path))).pack(side=tk.LEFT, padx=5)
        
        # 绑定选择事件并设置初始按钮状态
        tree.bind("<<TreeviewSelect>>", on_select)
        # 初始状态 - 禁用编辑和删除按钮
        selected_edit_btn.state(['disabled'])
        selected_delete_btn.state(['disabled'])

    def _create_project_dialog(self):
        """创建新项目对话框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("创建新项目")
        dlg.geometry("500x450")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="项目名称:").pack(pady=(15, 5))
        name_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=name_var, width=50).pack()

        ttk.Label(dlg, text="项目描述:").pack(pady=(10, 5))
        desc_text = tk.Text(dlg, height=4, width=50)
        desc_text.pack()

        ttk.Label(dlg, text="项目文件夹:").pack(pady=(10, 5))
        folder_var = tk.StringVar(value=str(BASE / "projects"))
        folder_frame = ttk.Frame(dlg)
        folder_frame.pack(fill=tk.X, padx=25)
        ttk.Entry(folder_frame, textvariable=folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_folder():
            folder = filedialog.askdirectory(title="选择项目文件夹")
            if folder:
                folder_var.set(folder)
                # 自动用文件夹名作为项目名
                if not name_var.get().strip():
                    folder_path = Path(folder)
                    name_var.set(folder_path.name)
        ttk.Button(folder_frame, text="浏览...", command=browse_folder).pack(side=tk.LEFT, padx=5)

        ttk.Label(dlg, text="标签 (逗号分隔):").pack(pady=(10, 5))
        tags_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=tags_var, width=50).pack()

        def create():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入项目名称", parent=dlg)
                return
            
            folder = folder_var.get().strip()
            if not folder:
                messagebox.showwarning("提示", "请选择项目文件夹", parent=dlg)
                return

            tags = [t.strip() for t in tags_var.get().split(',') if t.strip()]
            description = desc_text.get("1.0", tk.END).strip()

            try:
                proj = self.project_mgr.create_project(name, description, folder, tags)
                messagebox.showinfo("成功", f"项目 '{name}' 创建成功！", parent=dlg)
                self._refresh_projects_list()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"创建项目失败: {str(e)}", parent=dlg)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="创建", command=create).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    def _edit_project_dialog(self, project):
        """编辑项目对话框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("编辑项目")
        dlg.geometry("500x400")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="项目名称:").pack(pady=(15, 5))
        name_var = tk.StringVar(value=project["name"])
        ttk.Entry(dlg, textvariable=name_var, width=50).pack()

        ttk.Label(dlg, text="项目描述:").pack(pady=(10, 5))
        desc_text = tk.Text(dlg, height=4, width=50)
        desc_text.insert("1.0", project.get("description", ""))
        desc_text.pack()

        ttk.Label(dlg, text="标签 (逗号分隔):").pack(pady=(10, 5))
        tags_var = tk.StringVar(value=", ".join(project.get("tags", [])))
        ttk.Entry(dlg, textvariable=tags_var, width=50).pack()

        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入项目名称", parent=dlg)
                return

            tags = [t.strip() for t in tags_var.get().split(',') if t.strip()]
            description = desc_text.get("1.0", tk.END).strip()

            self.project_mgr.update_project(project["id"], name=name, description=description, tags=tags)
            messagebox.showinfo("成功", "项目更新成功！", parent=dlg)
            self._refresh_projects_list()
            self._show_project_detail(self.project_mgr.get_project_by_id(project["id"]))
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    def _archive_project(self, project):
        """归档/取消归档项目"""
        new_status = "archived" if project.get("status") == "active" else "active"
        action_text = "归档" if new_status == "archived" else "取消归档"
        
        if messagebox.askyesno("确认", f"确定要{action_text}项目 '{project['name']}' 吗？"):
            self.project_mgr.update_project(project["id"], status=new_status)
            self._refresh_projects_list()
            self._show_project_detail(self.project_mgr.get_project_by_id(project["id"]))

    def _delete_project_dialog(self, project):
        """删除项目对话框"""
        dlg = tk.Toplevel(self.root)
        dlg.title("删除项目")
        dlg.geometry("400x200")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"确定要删除项目 '{project['name']}' 吗？", font=("", 11)).pack(pady=20)

        delete_folder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dlg, text="同时删除项目文件夹", variable=delete_folder_var).pack()

        def delete():
            self.project_mgr.delete_project(project["id"], delete_folder=delete_folder_var.get())
            messagebox.showinfo("成功", "项目已删除", parent=dlg)
            self._refresh_projects_list()
            self._clear_project_detail()
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="删除", command=delete, style="Complete.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    # ============ 文本分析 ============
    def _show_research_analysis(self):
        """显示科研分析页面"""
        self._clear_content()
        self._highlight_nav("analyze")
        self.nav_title.config(text="🔬 科研文本分析")

        # 导入分析模块
        try:
            from research_analyzer import ResearchAnalyzer, LiteratureNoteBuilder
            self.research_analyzer = ResearchAnalyzer(BASE)
            self.note_builder = LiteratureNoteBuilder(self.research_analyzer)
        except ImportError:
            self.research_analyzer = None
            self.note_builder = None

        # 主布局
        main_frame = ttk.Frame(self.content_frame)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部：标题和说明
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(header_frame, text="🔬 科研文本分析工具", font=("", 14, "bold")).pack(side=tk.LEFT)
        ttk.Label(header_frame, text="  文本分析、关键词提取、文献笔记生成", font=("", 10), foreground="#7f8c8d").pack(side=tk.LEFT)

        # 分割窗口
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：文本输入区
        left_frame = ttk.Frame(paned, padding=10)
        paned.add(left_frame, weight=5)

        ttk.Label(left_frame, text="📝 输入/粘贴文本", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))

        # 文本输入框
        text_frame = ttk.Frame(left_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self._research_text = tk.Text(text_frame, wrap="word", font=("Consolas", 11))
        text_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._research_text.yview)
        self._research_text.configure(yscrollcommand=text_scroll.set)

        self._research_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 操作按钮
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="📥 从文件导入", command=self._import_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📋 粘贴", command=self._paste_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Separator(btn_frame, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10)
        ttk.Button(btn_frame, text="🔍 分析", command=self._analyze_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📝 生成笔记", command=self._generate_literature_note).pack(side=tk.LEFT, padx=2)

        # 右侧：分析结果区
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=5)

        ttk.Label(right_frame, text="📊 分析结果", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))

        # 结果显示区（Notebook标签页）
        self._research_notebook = ttk.Notebook(right_frame)
        self._research_notebook.pack(fill=tk.BOTH, expand=True)

        # 关键词标签页
        keywords_frame = ttk.Frame(self._research_notebook, padding=10)
        self._research_notebook.add(keywords_frame, text="🔑 关键词")
        
        self._keywords_text = tk.Text(keywords_frame, wrap="word", font=("Consolas", 11))
        keywords_scroll = ttk.Scrollbar(keywords_frame, orient=tk.VERTICAL, command=self._keywords_text.yview)
        self._keywords_text.configure(yscrollcommand=keywords_scroll.set)
        self._keywords_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        keywords_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 结构分析标签页
        structure_frame = ttk.Frame(self._research_notebook, padding=10)
        self._research_notebook.add(structure_frame, text="📋 结构分析")
        
        self._structure_text = tk.Text(structure_frame, wrap="word", font=("Consolas", 11))
        structure_scroll = ttk.Scrollbar(structure_frame, orient=tk.VERTICAL, command=self._structure_text.yview)
        self._structure_text.configure(yscrollcommand=structure_scroll.set)
        self._structure_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        structure_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 参考文献标签页
        refs_frame = ttk.Frame(self._research_notebook, padding=10)
        self._research_notebook.add(refs_frame, text="📚 参考文献")
        
        self._refs_text = tk.Text(refs_frame, wrap="word", font=("Consolas", 11))
        refs_scroll = ttk.Scrollbar(refs_frame, orient=tk.VERTICAL, command=self._refs_text.yview)
        self._refs_text.configure(yscrollcommand=refs_scroll.set)
        self._refs_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        refs_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 存储当前加载的文件路径
        self._current_paper_file = None
        
        # 更新标题和说明
        self.nav_title.config(text="🔬 文本分析")
        
        # 显示支持的格式
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="🔬 WS2 科研文本分析工具", font=("", 14, "bold")).pack(side=tk.LEFT)
        
        format_info = "支持: PDF, DOCX, TXT, MD, HTML, TeX"
        if self.research_analyzer:
            available = self.research_analyzer.paper_reader.available_formats
            available_list = [k for k, v in available.items() if v]
            if available_list:
                format_info = "已安装: " + ", ".join([ext[1:].upper() for ext in sorted(available_list)])
        
        ttk.Label(header_frame, text=f"  {format_info}", font=("", 10), 
                 foreground="#7f8c8d").pack(side=tk.LEFT)
        
        # 文件信息栏
        info_frame = ttk.LabelFrame(main_frame, text="📄 文件信息", padding=8)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self._paper_info_label = ttk.Label(info_frame, text="尚未加载任何论文文件")
        self._paper_info_label.pack(anchor="w")
        
        # 更新左侧区域标题
        ttk.Label(left_frame, text="📝 论文内容", font=("", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        # 添加概览标签页
        overview_frame = ttk.Frame(self._research_notebook, padding=10)
        self._research_notebook.insert(0, overview_frame, text="📋 概览")
        
        self._overview_text = tk.Text(overview_frame, wrap="word", font=("Consolas", 11))
        overview_scroll = ttk.Scrollbar(overview_frame, orient=tk.VERTICAL, command=self._overview_text.yview)
        self._overview_text.configure(yscrollcommand=overview_scroll.set)
        self._overview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        overview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 更新按钮
        # 清空原按钮
        for widget in btn_frame.winfo_children():
            widget.destroy()
        
        # 构建文件过滤器
        file_types = [("所有支持的文件", "*.pdf *.docx *.txt *.md *.html *.htm *.tex")]
        if self.research_analyzer:
            for ext, name in self.research_analyzer.paper_reader.SUPPORTED_FORMATS.items():
                file_types.append((name, f"*{ext}"))
        file_types.append(("所有文件", "*.*"))
        self._paper_file_types = file_types
        
        ttk.Button(btn_frame, text="📂 导入论文", command=self._import_paper_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📋 粘贴", command=self._paste_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🧹 清空", command=self._clear_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Separator(btn_frame, orient="vertical").pack(side=tk.LEFT, fill="y", padx=10)
        ttk.Button(btn_frame, text="🔍 分析", command=self._analyze_research_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📝 生成笔记", command=self._generate_literature_note).pack(side=tk.LEFT, padx=2)
        
        # 初始化欢迎文本
        welcome_text = """╔═══════════════════════════════════════════════════════════╗
║          欢迎使用 WS2 科研文本分析工具                          ║
╠═══════════════════════════════════════════════════════════╣
║  支持的文件格式:                                        ║
║    • PDF 文档 (.pdf)                                      ║
║    • Word 文档 (.docx)                                     ║
║    • 纯文本文件 (.txt)                                      ║
║    • Markdown (.md)                                        ║
║    • HTML 网页 (.html/.htm)                                ║
║    • LaTeX 源码 (.tex)                                     ║
║                                                            ║
║  功能:                                                    ║
║    • 关键词自动提取                                          ║
║    • 论文结构分析                                            ║
║    • 参考文献识别                                            ║
║    • 文献笔记生成                                            ║
╚═══════════════════════════════════════════════════════════╝

请点击「导入论文」按钮选择文件，或直接粘贴文本内容。
"""
        self._research_text.delete(1.0, tk.END)
        self._research_text.insert(1.0, welcome_text)
    
    def _import_paper_file(self):
        """导入论文文件"""
        if not self.research_analyzer:
            messagebox.showerror("错误", "科研分析模块未加载")
            return
        
        file_path = filedialog.askopenfilename(
            title="选择论文文件",
            filetypes=self._paper_file_types
        )
        
        if file_path:
            try:
                text, format_name = self.research_analyzer.load_paper(file_path)
                
                if text is None:
                    messagebox.showerror("错误", f"加载文件失败: {format_name}")
                    return
                
                # 显示文本
                self._research_text.delete(1.0, tk.END)
                self._research_text.insert(1.0, text)
                
                # 存储文件路径
                self._current_paper_file = file_path
                
                # 更新信息显示
                file_name = Path(file_path).name
                file_size = Path(file_path).stat().st_size
                size_str = f"{file_size:,} 字节" if file_size < 1024*1024 else f"{file_size/1024/1024:.1f} MB"
                
                info_text = f"📄 文件: {file_name} | 📋 格式: {format_name} | 📏 大小: {size_str}"
                self._paper_info_label.config(text=info_text)
                
                messagebox.showinfo("成功", f"成功导入 {format_name}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入文件时出错: {str(e)}")
    
    def _clear_research_text(self):
        """清空文本"""
        self._research_text.delete(1.0, tk.END)
        self._current_paper_file = None
        self._paper_info_label.config(text="尚未加载任何论文文件")
    
    def _paste_research_text(self):
        """从剪贴板粘贴文本"""
        try:
            content = self.root.clipboard_get()
            self._research_text.delete(1.0, tk.END)
            self._research_text.insert(1.0, content)
            self._current_paper_file = None
            self._paper_info_label.config(text="从剪贴板粘贴的内容")
        except Exception as e:
            messagebox.showwarning("提示", "剪贴板为空或无法读取")
    
    def _import_research_text(self):
        """从文件导入文本（兼容旧版本）"""
        self._import_paper_file()

    def _analyze_research_text(self):
        """分析科研文本"""
        if not self.research_analyzer:
            messagebox.showerror("错误", "科研分析模块未加载")
            return

        text = self._research_text.get(1.0, tk.END).strip()
        if not text or len(text) < 50:
            messagebox.showwarning("提示", "请先导入论文或输入足够的文本内容")
            return

        try:
            # 概览分析
            overview = "📊 论文分析概览\n" + "="*60 + "\n\n"
            
            # 尝试提取标题
            title = self.research_analyzer.extract_title(text)
            if title:
                overview += f"📌 推测标题: {title}\n\n"
            
            # 尝试提取作者
            authors = self.research_analyzer.extract_authors(text)
            if authors:
                overview += f"👥 作者: {'; '.join(authors[:5])}"
                if len(authors) > 5:
                    overview += f" 等 {len(authors)} 人"
                overview += "\n\n"
            
            # 提取摘要
            abstract = self.research_analyzer.extract_abstract(text)
            if abstract:
                overview += f"📝 摘要预览:\n{abstract[:500]}"
                if len(abstract) > 500:
                    overview += "..."
                overview += "\n\n"
            
            # 基本统计
            structure = self.research_analyzer.analyze_paper_structure(text)
            overview += f"📈 统计信息:\n"
            overview += f"   • 总字数: {structure.get('word_count', 0):,} 字\n"
            overview += f"   • 字符数: {structure.get('char_count', 0):,} 字符\n\n"
            
            self._overview_text.delete(1.0, tk.END)
            self._overview_text.insert(1.0, overview)

            # 关键词分析
            keywords = self.research_analyzer.extract_keywords(text, 30)
            self._keywords_text.delete(1.0, tk.END)
            self._keywords_text.insert(1.0, "🔑 关键词词频统计\n" + "="*60 + "\n\n")
            if keywords:
                max_count = max(k[1] for k in keywords)
                for word, count in keywords:
                    # 生成条形图
                    bar_length = int(40 * count / max_count)
                    bar = "█" * bar_length
                    self._keywords_text.insert(tk.END, f"  {word:<20} {count:>3}  {bar}\n")
            else:
                self._keywords_text.insert(tk.END, "  未能提取到关键词\n")

            # 结构分析
            structure = self.research_analyzer.analyze_paper_structure(text)
            self._structure_text.delete(1.0, tk.END)
            self._structure_text.insert(1.0, "🏗️ 论文结构分析\n" + "="*60 + "\n\n")
            
            structure_items = [
                ('标题', 'has_title'),
                ('摘要', 'has_abstract'),
                ('关键词', 'has_keywords'),
                ('引言', 'has_introduction'),
                ('方法', 'has_methods'),
                ('结果', 'has_results'),
                ('讨论', 'has_discussion'),
                ('结论', 'has_conclusion'),
                ('参考文献', 'has_references'),
                ('图表', 'has_figures'),
                ('表格', 'has_tables'),
            ]
            
            for label, key in structure_items:
                status = "✅" if structure.get(key, False) else "❌"
                self._structure_text.insert(tk.END, f"  {status} {label}\n")
            
            self._structure_text.insert(tk.END, "\n" + "-"*60 + "\n")
            self._structure_text.insert(tk.END, f"\n📈 字数: {structure.get('word_count', 0):,} 字\n")
            self._structure_text.insert(tk.END, f"📏 字符数: {structure.get('char_count', 0):,} 字符\n")

            # 参考文献
            refs = self.research_analyzer.extract_references(text)
            self._refs_text.delete(1.0, tk.END)
            self._refs_text.insert(1.0, "📚 参考文献\n" + "="*60 + "\n\n")
            if refs:
                for i, ref in enumerate(refs, 1):
                    self._refs_text.insert(tk.END, f"  [{i}] {ref}\n\n")
            else:
                self._refs_text.insert(tk.END, "  未能识别到参考文献\n")

            # 切换到概览页面
            self._research_notebook.select(0)

        except Exception as e:
            messagebox.showerror("错误", f"分析失败: {e}")

    def _generate_literature_note(self):
        """生成文献笔记"""
        if not self.note_builder:
            messagebox.showerror("错误", "笔记生成模块未加载")
            return

        text = self._research_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先导入论文或输入文本内容")
            return

        # 询问信息对话框
        note_dlg = tk.Toplevel(self.root)
        note_dlg.title("📝 生成文献笔记")
        note_dlg.geometry("500x400")
        note_dlg.transient(self.root)
        note_dlg.grab_set()

        ttk.Label(note_dlg, text="文献标题 (可选，自动提取):").pack(pady=(15, 5))
        title_var = tk.StringVar()
        title_entry = ttk.Entry(note_dlg, textvariable=title_var, width=50)
        title_entry.pack()

        ttk.Label(note_dlg, text="作者 (可选，自动提取):").pack(pady=(10, 5))
        author_var = tk.StringVar()
        author_entry = ttk.Entry(note_dlg, textvariable=author_var, width=50)
        author_entry.pack()

        ttk.Separator(note_dlg, orient="horizontal").pack(fill="x", pady=15)

        ttk.Label(note_dlg, text="输出格式:").pack()
        format_var = tk.StringVar(value="rmd")
        format_frame = ttk.Frame(note_dlg)
        format_frame.pack(pady=5)
        ttk.Radiobutton(format_frame, text="R Markdown (.Rmd)", variable=format_var, value="rmd").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="Markdown (.md)", variable=format_var, value="md").pack(side="left", padx=10)

        def generate_and_save():
            title = title_var.get().strip()
            author = author_var.get().strip()
            
            try:
                note_content = self.note_builder.create_literature_note(
                    title, text, author, 
                    source_file=self._current_paper_file
                )

                # 保存文件
                default_ext = ".Rmd" if format_var.get() == "rmd" else ".md"
                save_path = filedialog.asksaveasfilename(
                    title="保存文献笔记",
                    defaultextension=default_ext,
                    filetypes=[
                        ("R Markdown", "*.Rmd"),
                        ("Markdown", "*.md"),
                        ("所有文件", "*.*")
                    ],
                    initialdir=str(BASE / "Notes")
                )

                if save_path:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(note_content)
                    messagebox.showinfo("成功", f"文献笔记已保存到:\n{save_path}")
                    note_dlg.destroy()

            except Exception as e:
                messagebox.showerror("错误", f"生成笔记失败: {e}")

        btn_frame = ttk.Frame(note_dlg)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="生成并保存", command=generate_and_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=note_dlg.destroy).pack(side="left", padx=5)

    def _show_visualization(self):
        """显示可视化分析界面"""
        self._clear_content()
        self._highlight_nav("visualize")
        self.nav_title.config(text="可视化分析")
        self._update_overall_label()
        
        if self._visualizer:
            # 使用集成的可视化器
            self._visualizer.create_integrated_ui(self.content_frame)
        else:
            # 如果没有加载可视化器，显示备用界面
            header = ttk.Label(self.content_frame, 
                            text="🌌 WS2 可视化分析中心",
                            font=("", 20, "bold"))
            header.pack(pady=(20, 10))
            
            msg = ttk.Label(self.content_frame, 
                          text="⚠️ 可视化模块未加载\n\n"
                               "请确保以下文件存在：\n"
                               "- ws2_visualization.py\n\n"
                               "如需使用高级可视化功能，请安装依赖库：\n"
                               "pip install matplotlib plotly networkx",
                          justify=tk.CENTER)
            msg.pack(pady=20)
            
            # 添加快速启动按钮
            btn_frame = ttk.Frame(self.content_frame)
            btn_frame.pack(pady=20)
            
            def try_load_visualizer():
                try:
                    from ws2_visualization import create_visualizer
                    self._visualizer = create_visualizer(BASE)
                    self._visualizer.initialize(course_system=self.system,
                                              workflow_logger=self.wflogger)
                    self._show_visualization()
                except ImportError as e:
                    messagebox.showerror("错误", f"加载可视化模块失败: {e}")
            
            ttk.Button(btn_frame, text="🔄 重新加载模块", 
                     command=try_load_visualizer).pack(side=tk.LEFT, padx=5)
    
    def _show_web_crawler(self):
        """显示网络爬虫界面"""
        self._clear_content()
        self._highlight_nav("crawler")
        self.nav_title.config(text="🌐 网络爬虫")
        self._update_overall_label()
        
        try:
            from ws2_web_crawler import WebCrawlerUI
            self._web_crawler_ui = WebCrawlerUI(self.content_frame, BASE)
            self._web_crawler_ui.frame.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            header = ttk.Label(self.content_frame, 
                            text="🌐 WS2 网络爬虫系统",
                            font=("", 20, "bold"))
            header.pack(pady=(20, 10))
            
            msg = ttk.Label(self.content_frame, 
                          text=f"⚠️ 爬虫模块加载失败\n\n"
                               f"错误: {e}\n\n"
                               "请确保以下文件存在：\n"
                               "- ws2_web_crawler.py\n"
                               "- WebAnalyze II/ 目录\n\n"
                               "如需使用爬虫功能，请安装依赖库：\n"
                               "pip install aiohttp beautifulsoup4 lxml requests python-dateutil",
                          justify=tk.CENTER)
            msg.pack(pady=20)
            
            btn_frame = ttk.Frame(self.content_frame)
            btn_frame.pack(pady=20)
            
            def try_load_crawler():
                try:
                    from ws2_web_crawler import WebCrawlerUI
                    self._web_crawler_ui = WebCrawlerUI(self.content_frame, BASE)
                    self._show_web_crawler()
                except Exception as e2:
                    messagebox.showerror("错误", f"加载爬虫模块失败: {e2}")
            
            ttk.Button(btn_frame, text="🔄 重新加载模块", 
                     command=try_load_crawler).pack(side=tk.LEFT, padx=5)
    
    def _show_synergy_hub(self):
        """显示研究交流中心界面"""
        self._clear_content()
        self._highlight_nav("synergy")
        self.nav_title.config(text="🔗 研究交流中心")
        self._update_overall_label()
        
        main_container = ttk.Frame(self.content_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 顶部：快速操作区域
        quick_frame = ttk.Frame(main_container)
        quick_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 打开独立助手按钮
        def open_assistant():
            try:
                sys.path.insert(0, str(BASE))
                from mcp.agent_assistant import AgentAssistantWindow
                assistant_window = AgentAssistantWindow(
                    self.root,
                    BASE,
                    self.system,
                    self.project_mgr,
                    self.task_board_mgr
                )
                assistant_window.show()
            except Exception as e:
                messagebox.showerror("错误", f"启动独立助手失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 打开配置按钮
        def open_config():
            try:
                sys.path.insert(0, str(BASE))
                from mcp.config_ui import show_enhanced_config_dialog
                show_enhanced_config_dialog(self.root)
            except Exception as e:
                messagebox.showerror("错误", f"打开配置界面失败: {e}")
                import traceback
                traceback.print_exc()
        
        ttk.Button(quick_frame, text="🤖 打开AI助手", 
                  command=open_assistant, style="Accent.TButton", width=20).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(quick_frame, text="⚙️ 配置助手", 
                  command=open_config, width=20).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(quick_frame, 
                text="💡 提示：也可以点击导航栏左侧的「🤖」按钮随时打开",
                foreground="gray").pack(side=tk.LEFT, padx=10)
        
        # 创建Notebook - 标签页切换
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # 标签页1：三模块联动
        synergy_frame = ttk.Frame(notebook, padding=15)
        notebook.add(synergy_frame, text="🔗 三模块联动")
        
        try:
            from ws2_synergy_ui import SynergyHubUI
            self._synergy_ui = SynergyHubUI(synergy_frame, BASE, self)
            self._synergy_ui.frame.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            msg = ttk.Label(synergy_frame, 
                          text=f"⚠️ 联动模块加载失败\n\n"
                               f"错误: {e}\n\n"
                               "请确保以下文件存在：\n"
                               "- ws2_synergy.py\n"
                               "- ws2_synergy_ui.py\n\n"
                               "三大模块：\n"
                               "1. 科研分析 (🔬) - 论文和文献处理\n"
                               "2. 网络研探 (🔍) - 学术网站和资源发现\n"
                               "3. 网络爬虫 (🌐) - 网页和GitHub项目爬取\n\n"
                               "联动功能：\n"
                               "- 数据共享 - 各模块可直接访问共享数据\n"
                               "- 工作流 - 从一个模块跳转到另一个继续处理\n"
                               "- 统一管理 - 集中查看和管理所有数据",
                          justify=tk.CENTER)
            msg.pack(pady=20)
            
            btn_frame = ttk.Frame(synergy_frame)
            btn_frame.pack(pady=10)
            
            def try_load_synergy():
                try:
                    from ws2_synergy_ui import SynergyHubUI
                    self._synergy_ui = SynergyHubUI(synergy_frame, BASE, self)
                except Exception as e2:
                    messagebox.showerror("错误", f"加载联动模块失败: {e2}")
            
            ttk.Button(btn_frame, text="🔄 重新加载", 
                      command=try_load_synergy).pack(side=tk.LEFT, padx=5)
        
        # 标签页2：书签/RSS管理器
        bookmark_frame = ttk.Frame(notebook, padding=15)
        notebook.add(bookmark_frame, text="🔖 书签与RSS订阅")
        
        try:
            from ws2_bookmark_manager import BookmarkManagerWindow
            self._bookmark_window = BookmarkManagerWindow(bookmark_frame, BASE, self.project_mgr, embedded=True)
        except Exception as e:
            msg = ttk.Label(bookmark_frame, 
                          text=f"⚠️ 书签管理器加载失败\n\n"
                               f"错误: {e}\n\n"
                               "功能说明：\n"
                               "• 自动爬取书签网页内容\n"
                               "• 支持RSS订阅解析\n"
                               "• 一键汇总网址和资源信息\n"
                               "• 用于AI分析和项目创建",
                          justify=tk.CENTER)
            msg.pack(pady=20)
            
            btn_frame = ttk.Frame(bookmark_frame)
            btn_frame.pack(pady=10)
            
            def try_load_bookmark():
                try:
                    from ws2_bookmark_manager import BookmarkManagerWindow
                    self._bookmark_window = BookmarkManagerWindow(bookmark_frame, BASE, self.project_mgr, embedded=True)
                except Exception as e2:
                    messagebox.showerror("错误", f"加载书签管理器失败: {e2}")
            
            ttk.Button(btn_frame, text="🔄 重新加载", 
                      command=try_load_bookmark).pack(side=tk.LEFT, padx=5)


def main():
    default_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "courses_structured.json")

    json_path = sys.argv[1] if len(sys.argv) > 1 else default_json

    if not os.path.exists(json_path):
        print(f"❌ 找不到数据文件: {json_path}")
        print(f"用法: python {sys.argv[0]} <courses_structured.json>")
        sys.exit(1)

    print(f"📂 加载数据: {json_path}")
    system = CourseSystem(json_path)
    print(f"✅ 已加载 {len(system.courses)} 门课程")

    root = tk.Tk()
    app = CourseTrackerApp(root, system)
    root.mainloop()


if __name__ == "__main__":
    main()
