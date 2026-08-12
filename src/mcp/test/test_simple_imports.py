#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的导入和初始化测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("测试 1: 基础导入...")
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    print("  ✅ tkinter 导入成功")
except Exception as e:
    print(f"  ❌ tkinter 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 2: tools 导入...")
try:
    from tools import get_tools
    print("  ✅ tools 导入成功")
except Exception as e:
    print(f"  ❌ tools 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 3: config 导入...")
try:
    from config import get_config_manager
    print("  ✅ config 导入成功")
except Exception as e:
    print(f"  ❌ config 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 4: 实例化 get_tools...")
try:
    tools = get_tools()
    print(f"  ✅ 成功获取 {len(tools)} 个工具")
    print(f"  工具列表: {[t.name for t in tools[:10]]}...")
except Exception as e:
    print(f"  ❌ get_tools() 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 5: 新工具类实例化...")
try:
    from tools import CLITool, ConfigTool, SkillTool, RAGTool, SandboxTool, MCPClientTool
    
    cli = CLITool(base_dir=".")
    print(f"  ✅ CLITool OK: {cli.name}")
    
    cfg = ConfigTool(base_dir=".")
    print(f"  ✅ ConfigTool OK: {cfg.name}")
    
    sk = SkillTool(base_dir=".")
    print(f"  ✅ SkillTool OK: {sk.name}")
    
    rag = RAGTool(base_dir=".")
    print(f"  ✅ RAGTool OK: {rag.name}")
    
    sandbox = SandboxTool(base_dir=".")
    print(f"  ✅ SandboxTool OK: {sandbox.name}")
    
    mcp = MCPClientTool(base_dir=".")
    print(f"  ✅ MCPClientTool OK: {mcp.name}")
    
except Exception as e:
    print(f"  ❌ 工具实例化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试 6: config_ui 基础导入...")
try:
    import config_ui
    print("  ✅ config_ui 导入成功")
except Exception as e:
    print(f"  ❌ config_ui 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("测试完成！")
