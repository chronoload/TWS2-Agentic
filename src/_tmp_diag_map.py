# -*- coding: utf-8 -*-
"""临时诊断：复现 macdev dev map 的 no such table: files"""
import sys, os, sqlite3, traceback
sys.path.insert(0, r'C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev\src')

out = r'C:/Users/qu/Desktop/deepseek-harness'
print('out_dir exists:', os.path.isdir(out), flush=True)
db = os.path.join(out, 'dir_tree.db')
print('db exists:', os.path.exists(db), 'size:', os.path.getsize(db) if os.path.exists(db) else '-', flush=True)

# 先独立测试 sqlite 建表流程
conn = sqlite3.connect(db)
c = conn.cursor()
try:
    c.execute("DROP TABLE IF EXISTS files")
    c.execute("CREATE TABLE files(rel TEXT, lines INT, size INT)")
    c.execute("INSERT INTO files VALUES (?,?,?)", ('a.py', 1, 10))
    conn.commit()
    print('sqlite 建表+插入 OK', flush=True)
    c.execute("SELECT count(*) FROM files")
    print('rows:', c.fetchone()[0], flush=True)
except Exception:
    traceback.print_exc()
finally:
    conn.close()

# 再跑完整 cmd_map
from mcp.macdev.dev.commands import cmd_map
try:
    code, lines = cmd_map(target='C:/Users/qu/Desktop/deepseek-harness', out=out, depth=3, exclude='')
    print('RESULT code=', code, flush=True)
    for l in lines:
        print(l, flush=True)
except Exception:
    traceback.print_exc()
