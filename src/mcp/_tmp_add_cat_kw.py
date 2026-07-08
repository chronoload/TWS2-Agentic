import re

file_path = r'C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\ws2_tools.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

mapping = {
    'ws2_get_overview': ('ws2_stats', '["ws2", "overview", "统计", "总览", "进度"]'),
    'ws2_get_domain_stats': ('ws2_stats', '["ws2", "overview", "统计", "总览", "进度"]'),
    'ws2_list_domains': ('ws2_stats', '["ws2", "overview", "统计", "总览", "进度"]'),
    'ws2_get_progress_by_domain': ('ws2_stats', '["ws2", "overview", "统计", "总览", "进度"]'),
    'ws2_list_courses': ('ws2_course', '["ws2", "course", "课程", "搜索"]'),
    'ws2_search_courses': ('ws2_course', '["ws2", "course", "课程", "搜索"]'),
    'ws2_get_course_detail': ('ws2_course', '["ws2", "course", "课程", "搜索"]'),
    'ws2_create_course': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_remove_course': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_update_course_info': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_add_lesson': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_update_lesson': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_remove_lesson': ('ws2_course_edit', '["ws2", "course", "课程", "编辑", "修改"]'),
    'ws2_mark_lesson_complete': ('ws2_progress', '["ws2", "progress", "进度", "复习", "完成"]'),
    'ws2_get_next_lesson': ('ws2_progress', '["ws2", "progress", "进度", "复习", "完成"]'),
    'ws2_get_course_progress': ('ws2_progress', '["ws2", "progress", "进度", "复习", "完成"]'),
    'ws2_get_review_schedule': ('ws2_progress', '["ws2", "progress", "进度", "复习", "完成"]'),
    'ws2_mark_review_done': ('ws2_progress', '["ws2", "progress", "进度", "复习", "完成"]'),
    'ws2_get_resources': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_add_bookmark': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_list_bookmarks': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_search_bookmarks': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_list_bookmark_categories': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_delete_bookmark': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_update_bookmark': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_add_resource': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_remove_resource': ('ws2_resource', '["ws2", "resource", "资源", "书签", "bookmark"]'),
    'ws2_list_notes': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_read_note': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_write_note': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_delete_note': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_search_notes': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_open_course_note': ('ws2_note', '["ws2", "note", "笔记", "记录"]'),
    'ws2_list_rmd': ('ws2_rmd', '["ws2", "rmd", "rmarkdown", "knit"]'),
    'ws2_knit_rmd': ('ws2_rmd', '["ws2", "rmd", "rmarkdown", "knit"]'),
    'ws2_knit_and_open_rmd': ('ws2_rmd', '["ws2", "rmd", "rmarkdown", "knit"]'),
    'ws2_list_projects': ('ws2_project', '["ws2", "project", "项目", "任务"]'),
    'ws2_create_project': ('ws2_project', '["ws2", "project", "项目", "任务"]'),
    'ws2_list_tasks': ('ws2_project', '["ws2", "project", "项目", "任务"]'),
    'ws2_add_task': ('ws2_project', '["ws2", "project", "项目", "任务"]'),
    'ws2_update_task': ('ws2_project', '["ws2", "project", "项目", "任务"]'),
    'ws2_rag_add_file': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_add_directory': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_add_text': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_search': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_get_context': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_get_stats': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_rag_clear': ('ws2_rag', '["ws2", "rag", "检索", "知识库"]'),
    'ws2_list_automation_tasks': ('ws2_automation', '["ws2", "automation", "自动化", "定时任务"]'),
    'ws2_create_automation_task': ('ws2_automation', '["ws2", "automation", "自动化", "定时任务"]'),
    'ws2_toggle_automation_task': ('ws2_automation', '["ws2", "automation", "自动化", "定时任务"]'),
    'ws2_run_automation_task': ('ws2_automation', '["ws2", "automation", "自动化", "定时任务"]'),
    'ws2_get_course_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_add_course_to_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_get_current_course': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_get_next_course': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_get_current_week_info': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_list_timetables': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_create_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_update_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_set_active_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_delete_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_update_course_slot': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_delete_course_slot': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_set_semester_dates': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_batch_add_courses': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_clear_timetable': ('ws2_timetable', '["ws2", "timetable", "课表", "时间表", "学期"]'),
    'ws2_load_course_json': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_list_courses_from_file': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_get_course_details_from_file': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_create_new_course': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_delete_course_from_file': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_list_lessons': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_get_lesson_details': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_delete_lesson': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_update_lesson_field': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_read_json_section': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_update_json_section': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_validate_course_json': ('ws2_json', '["ws2", "json", "文件", "编辑"]'),
    'ws2_scholar_search': ('ws2_scholar', '["ws2", "scholar", "学术", "论文", "搜索"]'),
    'ws2_scholar_get_by_doi': ('ws2_scholar', '["ws2", "scholar", "学术", "论文", "搜索"]'),
    'ws2_scholar_search_gene': ('ws2_scholar', '["ws2", "scholar", "学术", "论文", "搜索"]'),
    'ws2_scholar_search_protein': ('ws2_scholar', '["ws2", "scholar", "学术", "论文", "搜索"]'),
    'ws2_parse_text_links': ('ws2_hub', '["ws2", "hub", "链接", "导入"]'),
    'ws2_import_links_to_hub': ('ws2_hub', '["ws2", "hub", "链接", "导入"]'),
    'ws2_reload_all_sources': ('ws2_system', '["ws2", "system", "系统", "管理"]'),
    'ws2_add_db_path': ('ws2_system', '["ws2", "system", "系统", "管理"]'),
    'ws2_get_db_paths': ('ws2_system', '["ws2", "system", "系统", "管理"]'),
    'ws2_find_duplicates': ('ws2_system', '["ws2", "system", "系统", "管理"]'),
    'ws2_get_lesson_notes': ('ws2_course', '["ws2", "course", "课程"]'),
    'ws2_get_course_remaining_time': ('ws2_course', '["ws2", "course", "课程"]'),
    'ws2_open_resource': ('ws2_course', '["ws2", "course", "课程"]'),
}

count = 0
warnings = []
for tool_name, (cat, kw) in mapping.items():
    pattern = f'    name = "{tool_name}"\n'
    replacement = f'    name = "{tool_name}"\n    category = "{cat}"\n    keywords = {kw}\n'
    if pattern in content:
        content = content.replace(pattern, replacement, 1)
        count += 1
    else:
        warnings.append(f'WARNING: pattern not found for {tool_name}')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully updated {count} tool classes out of {len(mapping)} mappings.')
for w in warnings:
    print(w)
