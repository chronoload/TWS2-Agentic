#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查课程数据中的 domain 问题"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from course_tracker import CourseSystem

def check_domain_issues():
    """检查课程数据中的 domain 字段问题"""
    print("=== 检查课程数据中的 domain 问题 ===\n")
    
    system = CourseSystem()
    
    issues = []
    for idx, course in enumerate(system.courses):
        cid = course.get("note_id", course.get("course_title", f"课程{idx}"))
        title = course.get("course_title", "未知课程")
        domain = course.get("domain")
        
        # 检查 domain 是否存在
        if domain is None or domain == "":
            issues.append(f"❌ [{cid}] {title} - domain 字段缺失")
        elif domain == "UNKNOWN":
            issues.append(f"⚠️ [{cid}] {title} - domain 为 UNKNOWN")
        else:
            print(f"✅ [{cid}] {title} - domain: {domain}")
    
    if issues:
        print("\n=== 发现问题 ===")
        for issue in issues:
            print(issue)
    else:
        print("\n✅ 所有课程都有有效的 domain")

def check_execution_data():
    """检查执行模式所需的数据"""
    print("\n=== 检查执行模式数据 ===")
    
    system = CourseSystem()
    
    for course in system.courses[:3]:  # 检查前3门课程
        cid = course.get("note_id", course.get("course_title", "未知"))
        title = course.get("course_title", "未知课程")
        
        print(f"\n课程: {title}")
        print(f"  note_id: {cid}")
        
        # 检查课时数据
        lessons = course.get("lessons", [])
        print(f"  课时数: {len(lessons)}")
        
        if lessons:
            # 检查第一个课时
            first_lesson = lessons[0]
            required_fields = ["lesson_number", "lesson_title"]
            missing_fields = [f for f in required_fields if f not in first_lesson]
            if missing_fields:
                print(f"  ⚠️ 第一课时缺少字段: {missing_fields}")
            else:
                print(f"  ✅ 第一课时: {first_lesson['lesson_number']} - {first_lesson['lesson_title']}")
        
        # 检查进度数据
        progress = system.get_course_progress(cid)
        completed = progress.get("completed_lessons", [])
        print(f"  已完成课时: {len(completed)}")
        
        # 检查下一个课时
        next_lesson = system.get_next_lesson(cid)
        if next_lesson:
            print(f"  下一课时: {next_lesson.get('lesson_number')} - {next_lesson.get('lesson_title')}")
        else:
            print(f"  ⚠️ 没有下一个课时（可能已完成）")

if __name__ == "__main__":
    check_domain_issues()
    check_execution_data()
