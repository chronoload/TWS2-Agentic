#!/usr/bin/env python3
"""
TS2 MCP Agent 启动脚本
用于快速启动 MCP Agent 界面
"""
import sys
import tkinter as tk
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    print("="*60)
    print("TS2 MCP Agent System")
    print("="*60)
    print()
    
    try:
        from mcp.agent_assistant import AgentAssistantWindow
        print("✓ MCP Agent UI 加载成功")
        print()
        
        root = tk.Tk()
        root.withdraw()
        
        base_path = Path(__file__).parent / "src"
        app = AgentAssistantWindow(
            parent=root,
            base_path=str(base_path)
        )
        print("✓ 应用窗口创建成功")
        print()
        print("启动Agent界面...")
        app.window.protocol("WM_DELETE_WINDOW", lambda: _cleanup_and_exit(root))
        app.window.bind("<Destroy>", lambda e: _cleanup_and_exit(root))
        root.mainloop()
        
    except KeyboardInterrupt:
        print("\n\n用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def _cleanup_and_exit(root):
    try:
        root.quit()
        root.destroy()
    except:
        pass
    sys.exit(0)

if __name__ == "__main__":
    main()
