#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mathematica MCP 工具模块 - 为 TS2 Agent 提供数学计算能力
基于 WolframScript 实现，支持多种数学计算、符号计算、绘图等
"""

import os
import re
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

from .tools import Tool, ToolResult

logger = logging.getLogger(__name__)

WOLFRAMSCRIPT_PATH = None


def find_wolframscript() -> Optional[str]:
    """
    查找 wolframscript 可执行文件
    
    Returns:
        wolframscript 完整路径，或 None
    """
    global WOLFRAMSCRIPT_PATH
    if WOLFRAMSCRIPT_PATH:
        return WOLFRAMSCRIPT_PATH
    
    # 常见路径检查
    possible_paths = [
        "wolframscript",
        "wolframscript.exe",
        r"F:\Mathematica14.0\wolframscript.exe",
        r"F:\Mathematica14.0\SystemFiles\Kernel\wolframscript.exe",
        r"C:\Program Files\Wolfram Research\WolframScript\wolframscript.exe",
        r"C:\Program Files (x86)\Wolfram Research\WolframScript\wolframscript.exe",
    ]
    
    for path in possible_paths:
        try:
            result = subprocess.run(
                [path, "-code", "2+2"],
                capture_output=True,
                text=True,
                encoding='utf-8', errors='replace',
                timeout=10
            )
            if result.returncode == 0 and "4" in result.stdout:
                WOLFRAMSCRIPT_PATH = path
                logger.info(f"找到了 wolframscript: {path}")
                return path
        except Exception:
            continue
    
    return None


def run_wolfram_code(code: str, timeout: int = 60) -> Dict[str, Any]:
    """
    运行 Wolfram 代码
    
    Args:
        code: Wolfram 代码
        timeout: 超时时间（秒）
    
    Returns:
        包含结果的字典
    """
    wolframscript = find_wolframscript()
    if not wolframscript:
        return {
            "success": False,
            "error": "找不到 wolframscript，请确保已安装 Mathematica 或 Wolfram Engine"
        }
    
    try:
        # 直接运行代码
        result = subprocess.run(
            [wolframscript, "-code", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"执行失败: {stderr or stdout}"
            }
        
        # 解析输出
        if not stdout or stdout == "$Failed":
            return {
                "success": False,
                "error": "计算返回失败（$Failed）",
                "stdout": stdout,
                "stderr": stderr
            }
        
        return {
            "success": True,
            "result": stdout,
            "stdout": stdout,
            "stderr": stderr
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"执行超时（{timeout}秒）"
        }
    except Exception as e:
        logger.exception(f"运行 Wolfram 代码出错")
        return {
            "success": False,
            "error": f"异常: {str(e)}"
        }


class WolframCalculateTool(Tool):
    """
    Wolfram 计算工具 - 通用数学计算
    """
    name = "wolfram_calculate"
    category = "math"
    keywords = ["wolfram", "calculate", "计算", "数学"]
    description = """使用 Mathematica/Wolfram 进行数学计算，支持：
    - 数值计算（加减乘除、开方、三角函数等）
    - 符号计算（代数化简、因式分解、积分、微分等）
    - 线性代数（矩阵计算、特征值等）
    - 统计计算（概率分布、统计量）
    - 单位转换
    示例：
    - "2+2" -> 4
    - "Integrate[x^2,x]" -> x^3/3
    - "Factor[x^2-1]" -> (x-1)(x+1)
    """
    parameters = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "要计算的 Wolfram 表达式（必需）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["expression"],
    }
    
    def execute(self, expression: str, timeout: int = 60) -> str:
        result = run_wolfram_code(expression, timeout)
        if result["success"]:
            return f"✅ 计算结果:\n\n{result['result']}"
        else:
            return f"❌ 计算失败:\n\n{result['error']}"


class WolframSolveTool(Tool):
    """
    Wolfram 解方程工具
    """
    name = "wolfram_solve"
    description = """使用 Mathematica 解方程/不等式/方程组
    
    示例：
    - "x^2 - 4 == 0" -> x=2, x=-2
    - "x + y == 5 && x - y == 1" -> x=3, y=1
    """
    parameters = {
        "type": "object",
        "properties": {
            "equation": {"type": "string", "description": "方程/方程组/不等式（必需）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["equation"],
    }
    
    def execute(self, equation: str, timeout: int = 60) -> str:
        expr = f"Solve[{equation}]"
        result = run_wolfram_code(expr, timeout)
        if result["success"]:
            return f"✅ 解方程结果:\n\n{result['result']}"
        else:
            return f"❌ 解方程失败:\n\n{result['error']}"


class WolframIntegrateTool(Tool):
    """
    Wolfram 积分工具
    """
    name = "wolfram_integrate"
    category = "math"
    keywords = ["wolfram", "integrate", "积分"]
    description = """计算积分（不定积分/定积分）
    
    示例：
    - "x^2, x" -> ∫x²dx = x³/3
    - "x^2, x, 0, 1" -> ∫₀¹x²dx = 1/3
    """
    parameters = {
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "要积分的表达式（必需）"},
            "var": {"type": "string", "description": "积分变量（必需）"},
            "lower": {"type": "string", "description": "积分下限（可选，不定积分）"},
            "upper": {"type": "string", "description": "积分上限（可选，不定积分）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["expr", "var"],
    }
    
    def execute(self, expr: str, var: str, lower: Optional[str] = None, upper: Optional[str] = None, timeout: int = 60) -> str:
        if lower is not None and upper is not None:
            wolfram_expr = f"Integrate[{expr}, {{{var}, {lower}, {upper}}}]"
        else:
            wolfram_expr = f"Integrate[{expr}, {var}]"
        
        result = run_wolfram_code(wolfram_expr, timeout)
        if result["success"]:
            return f"✅ 积分结果:\n\n{result['result']}"
        else:
            return f"❌ 积分失败:\n\n{result['error']}"


class WolframDifferentiateTool(Tool):
    """
    Wolfram 微分工具
    """
    name = "wolfram_differentiate"
    category = "math"
    keywords = ["wolfram", "differentiate", "微分", "求导"]
    description = """计算导数
    
    示例：
    - "x^2, x" -> 2x
    - "x^2, x, 2" -> 二阶导数
    """
    parameters = {
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "要微分的表达式（必需）"},
            "var": {"type": "string", "description": "微分变量（必需）"},
            "order": {"type": "integer", "description": "导数阶数，默认 1", "default": 1},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["expr", "var"],
    }
    
    def execute(self, expr: str, var: str, order: int = 1, timeout: int = 60) -> str:
        wolfram_expr = f"D[{expr}, {{{var}, {order}}}]"
        result = run_wolfram_code(wolfram_expr, timeout)
        if result["success"]:
            return f"✅ 导数结果:\n\n{result['result']}"
        else:
            return f"❌ 求导失败:\n\n{result['error']}"


class WolframPlotTool(Tool):
    """
    Wolfram 绘图工具
    """
    name = "wolfram_plot"
    category = "math"
    keywords = ["wolfram", "plot", "绘图", "可视化"]
    description = """使用 Mathematica 绘制图形
    
    支持多种图形类型：Plot, Plot3D, ContourPlot, ListPlot 等
    示例：
    - "Sin[x]" -> 二维曲线图
    - "Sin[x + y]" -> 三维曲面图
    """
    parameters = {
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "要绘制的表达式（必需）"},
            "plot_type": {"type": "string", "description": "绘图类型：Plot, Plot3D, ContourPlot, ListPlot（默认 Plot）", "default": "Plot"},
            "xmin": {"type": "number", "description": "X轴下限（默认 -10）", "default": -10},
            "xmax": {"type": "number", "description": "X轴上限（默认 10）", "default": 10},
            "ymin": {"type": "number", "description": "Y轴下限（默认 -10，3D 图用）", "default": -10},
            "ymax": {"type": "number", "description": "Y轴上限（默认 10，3D 图用）", "default": 10},
            "save_path": {"type": "string", "description": "保存路径（可选，默认保存临时文件）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 120", "default": 120},
        },
        "required": ["expr"],
    }
    
    def execute(self, expr: str, plot_type: str = "Plot", 
                xmin: float = -10, xmax: float = 10, 
                ymin: float = -10, ymax: float = 10, 
                save_path: Optional[str] = None, timeout: int = 120) -> str:
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp_file.close()
            temp_path = temp_file.name
            
            if plot_type == "Plot":
                wolfram_expr = f'Export["{temp_path}", Plot[{expr}, {{x, {xmin}, {xmax}}}]]'
            elif plot_type == "Plot3D":
                wolfram_expr = f'Export["{temp_path}", Plot3D[{expr}, {{x, {xmin}, {xmax}}}, {{y, {ymin}, {ymax}}}]]'
            elif plot_type == "ContourPlot":
                wolfram_expr = f'Export["{temp_path}", ContourPlot[{expr}, {{x, {xmin}, {xmax}}}, {{y, {ymin}, {ymax}}}]]'
            elif plot_type == "ListPlot":
                wolfram_expr = f'Export["{temp_path}", ListPlot[{expr}]]'
            else:
                wolfram_expr = f'Export["{temp_path}", {plot_type}[{expr}, {{x, {xmin}, {xmax}}}]]'
            
            result = run_wolfram_code(wolfram_expr, timeout)
            
            if result["success"]:
                if save_path:
                    import shutil
                    shutil.copy(temp_path, save_path)
                    os.unlink(temp_path)
                    return f"✅ 绘图完成，已保存到: {save_path}"
                else:
                    return f"✅ 绘图完成，临时文件: {temp_path}\n（请打开查看图像）"
            else:
                os.unlink(temp_path)
                return f"❌ 绘图失败:\n\n{result['error']}"
        
        except Exception as e:
            logger.exception(f"绘图出错")
            return f"❌ 绘图异常: {str(e)}"


class WolframSimplifyTool(Tool):
    """
    Wolfram 简化工具
    """
    name = "wolfram_simplify"
    category = "math"
    keywords = ["wolfram", "simplify", "化简"]
    description = """简化数学表达式
    
    示例：
    - "(x^2-1)/(x-1)" -> x+1
    - "Expand[(x+y)^2]" -> x²+2xy+y²
    """
    parameters = {
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "要简化的表达式（必需）"},
            "method": {"type": "string", "description": "方法：Simplify（默认）/ FullSimplify / Expand / Factor", "default": "Simplify"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["expr"],
    }
    
    def execute(self, expr: str, method: str = "Simplify", timeout: int = 60) -> str:
        if method not in ["Simplify", "FullSimplify", "Expand", "Factor"]:
            method = "Simplify"
        
        wolfram_expr = f"{method}[{expr}]"
        result = run_wolfram_code(wolfram_expr, timeout)
        if result["success"]:
            return f"✅ 简化结果:\n\n{result['result']}"
        else:
            return f"❌ 简化失败:\n\n{result['error']}"


class WolframLinearAlgebraTool(Tool):
    """
    Wolfram 线性代数工具
    """
    name = "wolfram_linear_algebra"
    category = "math"
    keywords = ["wolfram", "linear", "algebra", "线性代数"]
    description = """线性代数计算：矩阵运算、行列式、特征值等
    
    操作类型：Inverse（逆矩阵）, Det（行列式）, Eigenvalues（特征值）, NullSpace, RowReduce
    """
    parameters = {
        "type": "object",
        "properties": {
            "matrix": {"type": "string", "description": "矩阵，用 Wolfram 格式：{{1,2},{3,4}}（必需）"},
            "operation": {"type": "string", "description": "操作：Inverse/Det/Eigenvalues/NullSpace/RowReduce（必需）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["matrix", "operation"],
    }
    
    def execute(self, matrix: str, operation: str = "Inverse", timeout: int = 60) -> str:
        wolfram_expr = f"{operation}[{matrix}]"
        result = run_wolfram_code(wolfram_expr, timeout)
        if result["success"]:
            return f"✅ {operation}结果:\n\n{result['result']}"
        else:
            return f"❌ 计算失败:\n\n{result['error']}"


class WolframStatisticsTool(Tool):
    """
    Wolfram 统计工具
    """
    name = "wolfram_statistics"
    category = "math"
    keywords = ["wolfram", "statistics", "统计"]
    description = """统计计算：分布、期望、方差、随机数等
    
    示例：
    - "NormalDistribution[0, 1], Mean" -> 0
    - "PoissonDistribution[5], Variance" -> 5
    """
    parameters = {
        "type": "object",
        "properties": {
            "distribution": {"type": "string", "description": "概率分布（例如 NormalDistribution[0,1]）（必需）"},
            "operation": {"type": "string", "description": "操作：Mean/Variance/CDF/PDF/RandomVariate（必需）"},
            "args": {"type": "string", "description": "额外参数（可选）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 60", "default": 60},
        },
        "required": ["distribution", "operation"],
    }
    
    def execute(self, distribution: str, operation: str, args: Optional[str] = None, timeout: int = 60) -> str:
        if args:
            wolfram_expr = f"{operation}[{distribution}, {args}]"
        else:
            wolfram_expr = f"{operation}[{distribution}]"
        
        result = run_wolfram_code(wolfram_expr, timeout)
        if result["success"]:
            return f"✅ {operation}结果:\n\n{result['result']}"
        else:
            return f"❌ 统计计算失败:\n\n{result['error']}"


class WolframQueryTool(Tool):
    """
    Wolfram 查询工具 - 直接运行任意 Wolfram 代码
    """
    name = "wolfram_query"
    category = "math"
    keywords = ["wolfram", "query", "查询"]
    description = """直接运行任意 Wolfram 代码（高级功能）
    
    警告：请确保代码安全，避免破坏性操作！
    """
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要运行的 Wolfram 代码（必需）"},
            "timeout": {"type": "integer", "description": "超时时间（秒），默认 120", "default": 120},
        },
        "required": ["code"],
    }
    
    def execute(self, code: str, timeout: int = 120) -> str:
        result = run_wolfram_code(code, timeout)
        if result["success"]:
            return f"✅ 执行结果:\n\n{result['result']}"
        else:
            return f"❌ 执行失败:\n\n{result['error']}"


# 工具注册表
WOLFRAM_TOOLS = [
    WolframCalculateTool,
    WolframSolveTool,
    WolframIntegrateTool,
    WolframDifferentiateTool,
    WolframSimplifyTool,
    WolframLinearAlgebraTool,
    WolframStatisticsTool,
    WolframPlotTool,
    WolframQueryTool,
]


def register_wolfram_tools() -> List[Tool]:
    """
    注册所有 Wolfram 工具
    
    Returns:
        工具实例列表
    """
    logger.info("正在注册 Wolfram 工具...")
    
    if not find_wolframscript():
        logger.warning("wolframscript 未找到，Wolfram 工具不可用")
        return []
    
    tools = []
    for tool_cls in WOLFRAM_TOOLS:
        try:
            tool = tool_cls()
            tools.append(tool)
            logger.info(f"注册工具: {tool.name}")
        except Exception as e:
            logger.exception(f"注册工具 {tool_cls.__name__} 失败")
    
    logger.info(f"Wolfram 工具注册完成，共 {len(tools)} 个工具")
    return tools


def get_wolfram_tool_schemas() -> List[Dict[str, Any]]:
    """
    获取所有 Wolfram 工具的 schema
    
    Returns:
        OpenAI 兼容的工具 schema 列表
    """
    tools = register_wolfram_tools()
    return [tool.schema() for tool in tools]


def check_wolfram_availability() -> Dict[str, Any]:
    """
    检查 Wolfram 是否可用
    
    Returns:
        状态信息
    """
    path = find_wolframscript()
    if not path:
        return {
            "available": False,
            "message": "wolframscript 未找到"
        }
    
    # 测试运行
    test_result = run_wolfram_code("2+2", timeout=10)
    if test_result["success"]:
        return {
            "available": True,
            "path": path,
            "test_result": test_result["result"]
        }
    else:
        return {
            "available": False,
            "path": path,
            "error": test_result["error"]
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("TS2 Mathematica MCP 工具 - 检查")
    print("=" * 60)
    
    check_result = check_wolfram_availability()
    print(f"\nWolfram 可用性: {'✅ 可用' if check_result['available'] else '❌ 不可用'}")
    if check_result['available']:
        print(f"路径: {check_result['path']}")
        print(f"测试: 2+2 = {check_result['test_result']}")
        
        print("\n可用工具:")
        schemas = get_wolfram_tool_schemas()
        for i, schema in enumerate(schemas, 1):
            tool_name = schema['function']['name']
            tool_desc = schema['function']['description'][:50]
            print(f"{i:2d}. {tool_name:30s} - {tool_desc}...")
    else:
        if 'path' in check_result:
            print(f"路径: {check_result['path']}")
        print(f"错误: {check_result.get('error', '未知')}")
    
    print("\n" + "=" * 60)
