#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 新增工具功能测试脚本
测试 RAGTool, SandboxTool, MCPClientTool, ConfigTool, SkillTool
"""

import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试所有模块导入"""
    print("=" * 60)
    print("测试 1: 模块导入")
    print("=" * 60)
    
    try:
        # 测试 tools 模块
        from tools import (
            get_tools, 
            CLITool, 
            ConfigTool, 
            SkillTool,
            RAGTool,
            SandboxTool,
            MCPClientTool
        )
        print("✅ tools 模块导入成功")
        
        # 测试新工具类
        print(f"  - CLITool: {CLITool}")
        print(f"  - ConfigTool: {ConfigTool}")
        print(f"  - SkillTool: {SkillTool}")
        print(f"  - RAGTool: {RAGTool}")
        print(f"  - SandboxTool: {SandboxTool}")
        print(f"  - MCPClientTool: {MCPClientTool}")
        
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False


def test_tool_instances():
    """测试工具实例化"""
    print("\n" + "=" * 60)
    print("测试 2: 工具实例化")
    print("=" * 60)
    
    try:
        from tools import (
            CLITool, 
            ConfigTool, 
            SkillTool,
            RAGTool,
            SandboxTool,
            MCPClientTool
        )
        
        # 测试所有新工具的实例化
        cli_tool = CLITool(base_dir=".")
        print(f"✅ CLITool 实例化成功: {cli_tool.name}")
        
        config_tool = ConfigTool(base_dir=".")
        print(f"✅ ConfigTool 实例化成功: {config_tool.name}")
        
        skill_tool = SkillTool(base_dir=".")
        print(f"✅ SkillTool 实例化成功: {skill_tool.name}")
        
        rag_tool = RAGTool(base_dir=".")
        print(f"✅ RAGTool 实例化成功: {rag_tool.name}")
        
        sandbox_tool = SandboxTool(base_dir=".")
        print(f"✅ SandboxTool 实例化成功: {sandbox_tool.name}")
        
        mcp_tool = MCPClientTool(base_dir=".")
        print(f"✅ MCPClientTool 实例化成功: {mcp_tool.name}")
        
        return True
    except Exception as e:
        print(f"❌ 工具实例化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_tools():
    """测试 get_tools 函数"""
    print("\n" + "=" * 60)
    print("测试 3: get_tools() 函数")
    print("=" * 60)
    
    try:
        from tools import get_tools
        
        tools = get_tools()
        print(f"✅ get_tools() 返回 {len(tools)} 个工具")
        
        # 统计新工具
        new_tools = [
            "cli_execute",
            "config_manage", 
            "skill_manager",
            "rag_retrieval",
            "sandbox_execute",
            "mcp_client"
        ]
        
        tool_names = [t.name for t in tools]
        for tool_name in new_tools:
            if tool_name in tool_names:
                print(f"  ✅ {tool_name}")
            else:
                print(f"  ❌ {tool_name} 未找到")
        
        return True
    except Exception as e:
        print(f"❌ get_tools() 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_tool():
    """测试 RAGTool"""
    print("\n" + "=" * 60)
    print("测试 4: RAGTool 功能")
    print("=" * 60)
    
    try:
        from tools import RAGTool
        
        rag_tool = RAGTool(base_dir=".")
        
        # 测试 get_count
        print("测试 get_count...")
        result = rag_tool.execute_structured("get_count")
        print(f"  {result.message[:100]}")
        
        # 测试 list_documents
        print("\n测试 list_documents...")
        result = rag_tool.execute_structured("list_documents")
        print(f"  {result.message[:100]}")
        
        print("✅ RAGTool 功能正常")
        return True
    except Exception as e:
        print(f"❌ RAGTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_tool():
    """测试 ConfigTool"""
    print("\n" + "=" * 60)
    print("测试 5: ConfigTool 功能")
    print("=" * 60)
    
    try:
        from tools import ConfigTool
        
        config_tool = ConfigTool(base_dir=".")
        
        # 测试 list_providers
        print("测试 list_providers...")
        result = config_tool.execute_structured("list_providers")
        print(f"  {result.message[:150]}")
        
        # 测试 list_skills
        print("\n测试 list_skills...")
        result = config_tool.execute_structured("list_skills")
        print(f"  {result.message[:150]}")
        
        # 测试 get_settings
        print("\n测试 get_settings...")
        result = config_tool.execute_structured("get_settings")
        print(f"  {result.message[:150]}")
        
        print("✅ ConfigTool 功能正常")
        return True
    except Exception as e:
        print(f"❌ ConfigTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_skill_tool():
    """测试 SkillTool"""
    print("\n" + "=" * 60)
    print("测试 6: SkillTool 功能")
    print("=" * 60)
    
    try:
        from tools import SkillTool
        
        skill_tool = SkillTool(base_dir=".")
        
        # 测试 list
        print("测试 list...")
        result = skill_tool.execute_structured("list")
        lines = result.message.split('\n')
        print(f"  启用技能数量: {len([l for l in lines if '✅' in l])}")
        print(f"  禁用技能数量: {len([l for l in lines if '❌' in l])}")
        
        print("✅ SkillTool 功能正常")
        return True
    except Exception as e:
        print(f"❌ SkillTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sandbox_tool():
    """测试 SandboxTool"""
    print("\n" + "=" * 60)
    print("测试 7: SandboxTool 功能")
    print("=" * 60)
    
    try:
        from tools import SandboxTool
        
        sandbox_tool = SandboxTool(base_dir=".")
        
        # 测试简单命令
        print("测试简单命令执行...")
        result = sandbox_tool.execute_structured("echo test")
        print(f"  {result.message[:200]}")
        
        print("✅ SandboxTool 功能正常")
        return True
    except Exception as e:
        print(f"❌ SandboxTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mcp_client_tool():
    """测试 MCPClientTool"""
    print("\n" + "=" * 60)
    print("测试 8: MCPClientTool 功能")
    print("=" * 60)
    
    try:
        from tools import MCPClientTool
        
        mcp_tool = MCPClientTool(base_dir=".")
        
        # 测试 get_status
        print("测试 get_status...")
        result = mcp_tool.execute_structured("get_status")
        print(f"  {result.message[:150]}")
        
        # 测试 list_tools
        print("\n测试 list_tools...")
        result = mcp_tool.execute_structured("list_tools")
        print(f"  {result.message[:150]}")
        
        print("✅ MCPClientTool 功能正常")
        return True
    except Exception as e:
        print(f"❌ MCPClientTool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cli_tool():
    """测试 CLITool"""
    print("\n" + "=" * 60)
    print("测试 9: CLITool 功能")
    print("=" * 60)
    
    try:
        from tools import CLITool
        
        cli_tool = CLITool(base_dir=".")
        
        # 测试简单命令
        print("测试简单命令执行...")
        result = cli_tool.execute_structured("echo Hello from CLI")
        print(f"  {result.message[:200]}")
        
        print("✅ CLITool 功能正常")
        return True
    except Exception as e:
        print(f"❌ CLITool 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 MCP 新增工具功能测试套件")
    print("=" * 60)
    
    tests = [
        ("模块导入", test_imports),
        ("工具实例化", test_tool_instances),
        ("get_tools()", test_get_tools),
        ("RAGTool", test_rag_tool),
        ("ConfigTool", test_config_tool),
        ("SkillTool", test_skill_tool),
        ("SandboxTool", test_sandbox_tool),
        ("MCPClientTool", test_mcp_client_tool),
        ("CLITool", test_cli_tool),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} 测试崩溃: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 打印测试总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
