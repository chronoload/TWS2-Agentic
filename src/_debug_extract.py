# 提取 course_tracker.py 中的关键函数
with open("course_tracker.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# get_domain_stats at line 919
output = []
output.append("=== get_domain_stats (lines 919-960) ===")
for i, line in enumerate(lines[918:960], 919):
    output.append(f"{i}:{line}")

output.append("")
output.append("=== get_next_lesson (lines 841-870) ===")
for i, line in enumerate(lines[840:870], 841):
    output.append(f"{i}:{line}")

output.append("")
output.append("=== complete_lesson (lines 864-920) ===")
for i, line in enumerate(lines[863:920], 864):
    output.append(f"{i}:{line}")

output.append("")
output.append("=== create_project (lines 292-330) ===")
for i, line in enumerate(lines[291:330], 292):
    output.append(f"{i}:{line}")

result = "\n".join(output)
with open("_extracted_code.txt", "w", encoding="utf-8") as f:
    f.write(result)
print(f"Written {len(result)} characters")
print("Done!")
