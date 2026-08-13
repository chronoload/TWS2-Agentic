#!/usr/bin/env python3
"""
批量更新 Notes 目录下所有 Rmd 文件的 YAML template 路径
从 template/xxx 改为 ../template/xxx
"""

import os
import re
from pathlib import Path

NOTES_DIR = Path(r"c:\Users\qu\Desktop\物理科学与技术论题\TS2\Notes")

REPLACEMENTS = [
    (r'in_header:\s*template/preamble-book\.tex', 'in_header: ../template/preamble-book.tex'),
    (r'--lua-filter=template/env_mapping\.lua', '--lua-filter=../template/env_mapping.lua'),
]

def update_file(filepath):
    """更新单个文件的 template 路径"""
    try:
        content = filepath.read_text(encoding="utf-8")
        original = content
        changed = False

        for pattern, replacement in REPLACEMENTS:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                changed = True
                content = new_content

        if changed:
            filepath.write_text(content, encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"  ❌ 错误: {filepath.name}: {e}")
        return False

def main():
    rmd_files = list(NOTES_DIR.glob("**/*.Rmd"))
    print(f"🔍 扫描 Notes 目录: {NOTES_DIR}")
    print(f"📁 找到 {len(rmd_files)} 个 .Rmd 文件\n")

    updated = 0
    skipped = 0

    for rmd_file in sorted(rmd_files):
        if update_file(rmd_file):
            print(f"  ✅ 更新: {rmd_file.relative_to(NOTES_DIR)}")
            updated += 1
        else:
            skipped += 1

    print(f"\n📊 完成!")
    print(f"   更新: {updated} 个文件")
    print(f"   跳过: {skipped} 个文件")

if __name__ == "__main__":
    main()
