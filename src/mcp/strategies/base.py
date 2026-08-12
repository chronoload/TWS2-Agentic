"""依赖链特化生成策略基类（策略模式）。

子类覆盖语义表 / resolve_type_file / collect_builtin_transforms 即为新的特化生成策略。
默认空实现：不携带任何项目语义，类型解析退化为 import 反查，链路仍可读（unknown/builtin 叶子）。
"""
from __future__ import annotations


class ChainStrategy:
    """依赖链特化生成策略（默认空实现）。"""

    name = "base"

    # 类型名 → 源文件相对路径（import 反查失败时的兜底）
    known_type_files: dict = {}
    # 已知 helper 函数 → 返回类型（跨文件变量流简化）
    helper_return_types: dict = {}
    # 局部变量别名 → 类型（如 cp = mw.checkpointer）
    type_aliases: dict = {}
    # 已知函数形参 → 类型提示（方法调用归属：store.get → SessionStore.get）
    param_type_hints: dict = {}

    def resolve_type_file(self, type_name: str, import_map: dict) -> str:
        """类型名 → 源文件相对路径（known_type_files 兜底 + import 反查）。"""
        if type_name in self.known_type_files:
            return self.known_type_files[type_name]
        if type_name in import_map:
            return import_map[type_name].replace(".", "/") + ".py"
        return ""

    def collect_builtin_transforms(self) -> list:
        """收集内置变换名（agent 特化，默认空）。"""
        return []
