#!/usr/bin/env python3
"""测试TS2模块导入"""
import sys
from pathlib import Path

# 添加src到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

print("=== 测试导入 ===")

print("\n1. 测试 tex_to_utf8...")
try:
    from tex_to_utf8 import TeXToUTF8
    print("   OK: tex_to_utf8")
except Exception as e:
    print(f"   FAIL: tex_to_utf8 - {e}")

print("\n2. 测试 data_converter...")
try:
    from data_converter import convert_file
    print("   OK: data_converter")
except Exception as e:
    print(f"   FAIL: data_converter - {e}")

print("\n3. 测试 md_builder...")
try:
    from md_builder import parse_md_file, parse_md_directory
    print("   OK: md_builder")
except Exception as e:
    print(f"   FAIL: md_builder - {e}")

print("\n4. 测试 MCP 模块...")
try:
    import mcp
    print("   OK: mcp")
    print(f"   版本: {mcp.__version__}")
except Exception as e:
    print(f"   FAIL: mcp - {e}")

print("\n5. 测试 MCP llm...")
try:
    from mcp.llm import LLM
    print("   OK: mcp.llm")
except Exception as e:
    print(f"   FAIL: mcp.llm - {e}")

print("\n6. 测试 MCP tools...")
try:
    from mcp.tools import Tool, get_tools
    print("   OK: mcp.tools")
except Exception as e:
    print(f"   FAIL: mcp.tools - {e}")

print("\n7. 测试 MCP ws2_tools...")
try:
    from mcp.ws2_tools import get_ws2_tools
    print("   OK: mcp.ws2_tools")
except Exception as e:
    print(f"   FAIL: mcp.ws2_tools - {e}")

print("\n8. 测试 MCP agent...")
try:
    from mcp.agent import Agent
    print("   OK: mcp.agent")
except Exception as e:
    print(f"   FAIL: mcp.agent - {e}")

print("\n9. 测试 MCP agent_assistant...")
try:
    from mcp.agent_assistant import AgentAssistantWindow, DebugManager, PerformanceMetrics
    print("   OK: mcp.agent_assistant")
    print("   类: AgentAssistantWindow, DebugManager, PerformanceMetrics")
except Exception as e:
    print(f"   FAIL: mcp.agent_assistant - {e}")

print("\n10. 测试 course_tracker...")
try:
    from course_tracker import main
    print("   OK: course_tracker")
except Exception as e:
    print(f"   FAIL: course_tracker - {e}")

print("\n11. 测试 MCP 子模块...")
try:
    from mcp.rag import auto_rag
    print("   OK: mcp.rag")
except Exception as e:
    print(f"   FAIL: mcp.rag - {e}")

try:
    from mcp.cache import lru_cache
    print("   OK: mcp.cache")
except Exception as e:
    print(f"   FAIL: mcp.cache - {e}")

try:
    from mcp.prompt import builder
    print("   OK: mcp.prompt")
except Exception as e:
    print(f"   FAIL: mcp.prompt - {e}")

print("\n=== 测试完成 ===")
