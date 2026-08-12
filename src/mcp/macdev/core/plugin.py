"""core.plugin：统一插件抽象接口（Plugin ABC）+ 自动发现。

哲学（自演化 / 插件平级）：macdev 的一切能力——审查（audit.strategy）、
修复（patch.generator）、展示、扫描……都是**同一种插件**：继承 Plugin 抽象接口，
声明 namespace + name，被 `Registry.discover()` 扫描捕捉后按名装配。
新增能力 = 新增一个 Plugin 子类（一个文件），内核零改动。

PluginMeta 在类定义时自动登记到全局注册表（不 import 即不发现）；
抽象基类本身 namespace/name 为空，不会被登记。
"""
from __future__ import annotations
from abc import ABCMeta


class PluginMeta(ABCMeta):
    """自动登记所有 Plugin 子类（按 namespace/name 去重）。
    用 getattr 取继承属性：子类只声明 name，namespace 继承自父类即被登记；
    抽象基类本身 name 为空，不会被登记。"""
    registry: dict = {}

    def __new__(mcls, name, bases, ns):
        cls = super().__new__(mcls, name, bases, ns)
        namespace = getattr(cls, "namespace", "")
        pname = getattr(cls, "name", "")
        if namespace and pname:
            mcls.registry[f"{namespace}:{pname}"] = cls
        return cls


class Plugin(metaclass=PluginMeta):
    """能力插件抽象接口：namespace + name 唯一标识，按名装配。"""
    namespace: str = ""   # audit.strategy / patch.generator / report.renderer ...
    name: str = ""        # base / ts2 / insert_set_after_clear ...
    description: str = ""

    @classmethod
    def qualified_name(cls) -> str:
        return f"{cls.namespace}/{cls.name}"


def scan_plugins(namespace: str = "") -> list:
    """扫描已导入模块中登记的插件类（可按命名空间过滤）。"""
    out = []
    for key, cls in PluginMeta.registry.items():
        if namespace and cls.namespace != namespace:
            continue
        out.append(cls)
    return out
