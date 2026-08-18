# -*- coding: utf-8 -*-
"""提取 deepseek-harness 开发方式摘要到本地文件"""
import json
import io
import os
from pathlib import Path

# 可配置路径，优先环境变量，回退到项目相对路径
DS_HARNESS_ROOT = Path(os.environ.get("DEEPSEEK_HARNESS_ROOT", r"C:\Users\qu\Desktop\deepseek-harness"))
DS_HARNESS_PROJECT = Path(os.environ.get("DS_HARNESS_PROJECT", Path(__file__).resolve().parents[1] / "ds-harness-project" / "dev" / "deepseek-harness"))
OUTPUT_FILE = Path(os.environ.get("DSH_EXTRACT_OUTPUT", Path(__file__).resolve().parent / "_dsh_extract.txt"))

buf = io.StringIO()

# 1) dir_tree.json stats
try:
    d = json.load(open(DS_HARNESS_PROJECT / "dir_tree.json", encoding='utf-8'))
    s = d['stats']
    buf.write('=== stats ===\n')
    buf.write('total_files: %d, total_lines: %d\n' % (s['total_files'], s['total_lines']))
    buf.write('--- kinds top 20 ---\n')
    for k, v in list(s['kinds'].items())[:20]:
        buf.write('  %r: %d\n' % (k, v))
    buf.write('--- modules top 30 ---\n')
    for k, v in list(s['modules'].items())[:30]:
        buf.write('  %r: %d\n' % (k, v))
    buf.write('--- stack clues ---\n')
    for x in s['stack_clues']:
        buf.write('  %s\n' % x)
    buf.write('--- top files 15 ---\n')
    for t in s['top_files'][:15]:
        buf.write('  %s (%d lines, %d KB)\n' % (t['rel'], t['lines'], t['size'] // 1024))
except Exception as e:
    buf.write('JSON ERROR: %r\n' % e)

# 2) AGENTS.md 全文
try:
    agents = open(DS_HARNESS_ROOT / "AGENTS.md", encoding='utf-8').read()
    buf.write('\n\n=== AGENTS.md (%d chars) ===\n' % len(agents))
    buf.write(agents)
except Exception as e:
    buf.write('AGENTS ERROR: %r\n' % e)

# 3) README.md
try:
    readme = open(DS_HARNESS_ROOT / "README.md", encoding='utf-8').read()
    buf.write('\n\n=== README.md (%d chars) ===\n' % len(readme))
    buf.write(readme)
except Exception as e:
    buf.write('README ERROR: %r\n' % e)

open(OUTPUT_FILE, 'w', encoding='utf-8').write(buf.getvalue())
print('written', len(buf.getvalue()), 'chars ->', OUTPUT_FILE)