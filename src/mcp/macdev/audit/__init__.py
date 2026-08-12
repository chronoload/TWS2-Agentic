"""audit 能力插件：静态审计 + 亲属追逐依赖链。入口 register(registry)。"""
from .task import AuditTask
from .strategy import ChainStrategy


def register(registry) -> None:
    registry.register("audit.strategy", "base", ChainStrategy)
