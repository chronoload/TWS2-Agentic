#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试执行模式显示问题"""

import sys
import traceback
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def test_execution_mode():
    """测试执行模式代码"""
    print("=== 调试执行模式 ===")
    
    try:
        # 测试导入
        print("1. 测试导入...")
        import tkinter as tk
        from tkinter import ttk
        print("   ✅ tkinter 导入成功")
        
        # 测试创建 PanedWindow
        print("\n2. 测试 PanedWindow 创建...")
        root = tk.Tk()
        root.withdraw()  # 不显示窗口
        
        # 测试 ttk.PanedWindow
        print("   测试 ttk.PanedWindow...")
        paned1 = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned1.pack(fill=tk.BOTH, expand=True)
        
        # 添加面板
        frame1 = ttk.Frame(paned1, width=650, height=400)
        frame1.pack_propagate(False)
        paned1.add(frame1, weight=3)
        
        frame2 = ttk.Frame(paned1, width=380, height=400)
        frame2.pack_propagate(False)
        paned1.add(frame2, weight=1)
        
        print("   ✅ ttk.PanedWindow 创建成功")
        
        # 测试 tk.PanedWindow
        print("\n   测试 tk.PanedWindow...")
        paned2 = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=4)
        paned2.pack(fill=tk.BOTH, expand=True)
        
        # 尝试使用 width 参数（这可能是问题所在）
        try:
            frame3 = ttk.Frame(paned2)
            paned2.add(frame3, width=650)
            print("   ✅ tk.PanedWindow width 参数成功")
        except Exception as e:
            print(f"   ❌ tk.PanedWindow width 参数失败: {e}")
        
        root.destroy()
        print("\n3. PanedWindow 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()

def test_course_tracker_import():
    """测试 course_tracker 导入"""
    print("\n=== 测试 CourseTrackerApp 导入 ===")
    try:
        from course_tracker import CourseTrackerApp, CourseSystem, load_json_safe
        
        # 测试创建系统
        print("1. 创建 CourseSystem...")
        system = CourseSystem()
        print("   ✅ CourseSystem 创建成功")
        
        # 检查是否有课程数据
        if system.courses:
            print(f"   已加载 {len(system.courses)} 门课程")
            for c in system.courses[:3]:
                print(f"     - {c.get('course_title', '未知')}")
        else:
            print("   ⚠️ 没有加载到课程数据")
        
        # 测试执行模式相关方法
        print("\n2. 测试执行模式方法...")
        methods = ['_show_execution_mode', '_render_current_lesson', '_complete_and_next']
        for method in methods:
            if hasattr(CourseTrackerApp, method):
                print(f"   ✅ {method} 方法存在")
            else:
                print(f"   ❌ {method} 方法不存在")
                
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_execution_mode()
    test_course_tracker_import()
