# -*- coding: utf-8 -*-
"""移除 TS2_dev 中异常的 .git 条目（worktree 残留）"""
import os
import shutil

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.git')
print('exists:', os.path.exists(p))
print('isfile:', os.path.isfile(p))
print('isdir:', os.path.isdir(p))
if os.path.isdir(p):
    shutil.rmtree(p)
elif os.path.isfile(p):
    os.remove(p)
print('after:', os.path.exists(p))
