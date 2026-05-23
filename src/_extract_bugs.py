import json

# 提取 course_tracker.py 中的关键函数
with open("course_tracker.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# get_domain_stats at line 919
sections = {
    "get_domain_stats_919": (918, 960),
    "get_next_lesson_841": (840, 870),
    "complete_lesson_864": (863, 920),
    "create_project_292": (291, 330),
}

result = {}
for name, (start, end) in sections.items():
    result[name] = "".join(lines[start:end])

with open("_extracted_sections.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("Done! Sections:", list(result.keys()))
for name, content in result.items():
    print(f"\n=== {name} ===")
    print(content[:500])
