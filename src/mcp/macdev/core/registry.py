"""Registry 工厂：按 (namespace, name) 注册/装配类，能力按名创建。"""
from __future__ import annotations
from typing import Any, Type


class Registry:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Type]] = {}

    def register(self, namespace: str, name: str, cls: Type) -> None:
        self._store.setdefault(namespace, {})[name] = cls

    def discover(self, namespace: str = "") -> "Registry":
        """扫描捕捉已导入模块中的 Plugin 子类并装配（插件平级哲学）。
        新增能力 = 新增 Plugin 子类；import 它即被本方法自动登记。"""
        from .plugin import PluginMeta
        for key, cls in PluginMeta.registry.items():
            if namespace and cls.namespace != namespace:
                continue
            self.register(cls.namespace, cls.name, cls)
        return self

    def namespaces(self) -> list[str]:
        return sorted(self._store)

    def names(self, namespace: str) -> list[str]:
        return sorted(self._store.get(namespace, {}))

    def create(self, namespace: str, name: str, **opts: Any) -> Any:
        cls = self._store.get(namespace, {}).get(name)
        if cls is None:
            raise KeyError(f"未注册: {namespace}/{name}（可用 {self.names(namespace)}）")
        return cls(**opts)
