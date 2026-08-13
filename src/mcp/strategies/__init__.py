"""依赖链特化生成策略（策略模式 + 工厂）。

引擎 = 追踪（trace_chain/符号索引）+ 展示（text/mermaid/断裂索引），保持通用；
策略 = 类型解析语义表等特化信息。新增特化生成策略 = 在脚本目录加一个策略类并在本文件注册，
task 配置 "strategy": <name> 选择，extractor 无需改动。
"""
from .base import ChainStrategy
from .ts2 import Ts2ChainStrategy

_REGISTRY = {
    "base": ChainStrategy,
    "ts2": Ts2ChainStrategy,
}


def load_strategy(name: str = "base") -> ChainStrategy:
    """策略工厂：按名返回策略实例。"""
    cls = _REGISTRY.get(name or "base")
    if cls is None:
        raise KeyError(f"未知策略 '{name}'，可用: {sorted(_REGISTRY)}")
    return cls()
