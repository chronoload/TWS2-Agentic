from __future__ import annotations
from ..core.plugin import Plugin


class ChainStrategy(Plugin):
    """ChainStrategy 基类（零语义）：类型解析语义表由外部子类化提供。
    继承 Plugin 抽象接口（namespace=audit.strategy），子类被 Registry.discover 扫描捕捉。"""
    namespace = "audit.strategy"
    name = "base"
    known_type_files: dict = {}
    helper_return_types: dict = {}
    type_aliases: dict = {}
    param_type_hints: dict = {}

    def resolve_type_file(self, type_name: str, import_map: dict) -> str:
        if type_name in self.known_type_files:
            return self.known_type_files[type_name]
        if type_name in import_map:
            return import_map[type_name].replace(".", "/") + ".py"
        return ""

    def collect_builtin_transforms(self) -> list:
        return []
