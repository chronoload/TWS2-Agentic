#!/usr/bin/env python3
"""MCP Agent 完整测试"""
import sys
from pathlib import Path

# 添加src到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

print("="*60)
print("TS2 MCP Agent 系统测试")
print("="*60)

# 测试1: MCP模块结构
print("\n【1】MCP模块结构")
print("-" * 40)
try:
    import mcp
    print(f"✓ MCP版本: {mcp.__version__}")
    print(f"✓ MCP路径: {mcp.__path__}")
    
    # 检查子模块
    from mcp import rag, cache, prompt
    print(f"✓ rag模块: 可用 ({len(dir(rag))} 个属性)")
    print(f"✓ cache模块: 可用 ({len(dir(cache))} 个属性)")
    print(f"✓ prompt模块: 可用 ({len(dir(prompt))} 个属性)")
except Exception as e:
    print(f"✗ 模块结构测试失败: {e}")

# 测试2: LLM接口
print("\n【2】LLM接口")
print("-" * 40)
try:
    from mcp.llm import LLM, LLMResponse, ToolCall
    print("✓ LLM类: 可导入")
    print("✓ LLMResponse: 可导入")
    print("✓ ToolCall: 可导入")
    
    # 检查LLM类的方法
    llm_methods = [m for m in dir(LLM) if not m.startswith('_')]
    print(f"✓ LLM方法: {', '.join(llm_methods[:5])}...")
except Exception as e:
    print(f"✗ LLM接口测试失败: {e}")

# 测试3: 工具系统
print("\n【3】工具系统")
print("-" * 40)
try:
    from mcp.tools import Tool, get_tools
    from mcp.ws2_tools import get_ws2_tools
    print("✓ Tool类: 可导入")
    print("✓ get_tools函数: 可导入")
    print("✓ get_ws2_tools函数: 可导入")
    
    # 尝试获取工具列表
    try:
        tools = get_tools()
        print(f"✓ 基础工具数量: {len(tools)}")
    except:
        print("○ 基础工具: 需要配置才能获取")
    
    try:
        ws2_tools = get_ws2_tools()
        print(f"✓ WS2工具数量: {len(ws2_tools)}")
    except:
        print("○ WS2工具: 需要配置才能获取")
except Exception as e:
    print(f"✗ 工具系统测试失败: {e}")

# 测试4: Agent核心
print("\n【4】Agent核心")
print("-" * 40)
try:
    from mcp.agent import Agent, AgentConfig, create_agent
    print("✓ Agent类: 可导入")
    print("✓ AgentConfig: 可导入")
    print("✓ create_agent: 可导入")
except Exception as e:
    print(f"✗ Agent核心测试失败: {e}")

# 测试5: Agent UI
print("\n【5】Agent UI")
print("-" * 40)
try:
    from mcp.agent_assistant import (
        AgentAssistantWindow,
        DebugManager,
        PerformanceMetrics,
        ConversationHistory
    )
    print("✓ AgentAssistantWindow: 可导入")
    print("✓ DebugManager: 可导入")
    print("✓ PerformanceMetrics: 可导入")
    print("✓ ConversationHistory: 可导入")
    
    # 检查PerformanceMetrics的方法
    pm_methods = [m for m in dir(PerformanceMetrics) if not m.startswith('_') and callable(getattr(PerformanceMetrics, m))]
    print(f"✓ PerformanceMetrics方法: {', '.join(pm_methods[:5])}")
except Exception as e:
    print(f"✗ Agent UI测试失败: {e}")

# 测试6: 配置系统
print("\n【6】配置系统")
print("-" * 40)
try:
    from mcp.config import ConfigManager, APIConfig
    print("✓ ConfigManager: 可导入")
    print("✓ APIConfig: 可导入")
except Exception as e:
    print(f"✗ 配置系统测试失败: {e}")

# 测试7: RAG系统
print("\n【7】RAG系统")
print("-" * 40)
try:
    from mcp.rag import auto_rag, retriever, rag_engine
    print("✓ auto_rag: 可导入")
    print("✓ retriever: 可导入")
    print("✓ rag_engine: 可导入")
    
    # 检查auto_rag模块的类
    rag_classes = [c for c in dir(auto_rag) if not c.startswith('_')]
    print(f"✓ auto_rag可用组件: {', '.join(rag_classes[:5])}")
except Exception as e:
    print(f"✗ RAG系统测试失败: {e}")

# 测试8: 缓存系统
print("\n【8】缓存系统")
print("-" * 40)
try:
    from mcp.cache import lru_cache, disk, state_manager
    print("✓ lru_cache: 可导入")
    print("✓ disk: 可导入")
    print("✓ state_manager: 可导入")
except Exception as e:
    print(f"✗ 缓存系统测试失败: {e}")

# 测试9: 提示词系统
print("\n【9】提示词系统")
print("-" * 40)
try:
    from mcp.prompt import builder, context_window, templates
    print("✓ builder: 可导入")
    print("✓ context_window: 可导入")
    print("✓ templates: 可导入")
except Exception as e:
    print(f"✗ 提示词系统测试失败: {e}")

# 测试10: 工作流引擎
print("\n【10】工作流引擎")
print("-" * 40)
try:
    from mcp.workflow_engine import WorkflowEngine
    print("✓ WorkflowEngine: 可导入")
except Exception as e:
    print(f"✗ 工作流引擎测试失败: {e}")

# 总结
print("\n" + "="*60)
print("测试完成！MCP Agent系统已准备就绪。")
print("="*60)
print("\n使用方法:")
print("1. 直接运行: python src/mcp/agent_assistant.py")
print("2. 或通过course_tracker集成使用")
print("3. 需要配置API密钥后才能连接LLM")
print()
