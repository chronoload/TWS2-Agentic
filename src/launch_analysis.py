#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2世界地图式分析系统 - 启动器
集成到TS2主系统中
"""

import sys
from pathlib import Path

# 添加当前目录到路径
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

def launch_standalone():
    """独立启动分析系统"""
    import tkinter as tk
    from world_map_analyzer import WS2AnalysisGUI
    
    root = tk.Tk()
    app = WS2AnalysisGUI(root, BASE_DIR)
    root.mainloop()

if __name__ == "__main__":
    print("🚀 启动WS2世界地图式分析系统...")
    launch_standalone()
