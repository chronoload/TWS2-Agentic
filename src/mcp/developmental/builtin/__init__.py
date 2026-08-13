"""内置原子工具集合

从 reptilian 重新导出基准工具，并提供符号信道等内置实现。
"""
from mcp.developmental.reptilian import (
    EchoFunction,
    SaturateFunction,
    LambdaFunction,
)
from mcp.developmental.builtin.symbol_channel import SymbolChannelFunction
from mcp.developmental.builtin.web_agent import WebAgentFunction

__all__ = [
    "EchoFunction",
    "SaturateFunction",
    "LambdaFunction",
    "SymbolChannelFunction",
    "WebAgentFunction",
]
