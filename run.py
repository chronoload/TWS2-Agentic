#!/usr/bin/env python3
"""
TS2 课程教学管理系统 - 启动脚本
"""
import sys
import os
from pathlib import Path

# 添加src到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# 导入并启动主程序
from course_tracker import main

if __name__ == "__main__":
    main()
