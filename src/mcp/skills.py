#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 系统 - 技能管理和执行
支持内置技能、自定义技能和插件技能
"""

import inspect
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from pathlib import Path
import importlib.util
import sys

from .config import get_config_manager, SkillConfig

logger = logging.getLogger(__name__)


@dataclass
class SkillParameter:
    """Skill 参数定义"""
    name: str
    type: str  # str, int, float, bool, list, dict
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None


@dataclass
class SkillDefinition:
    """Skill 完整定义"""
    name: str
    description: str
    parameters: List[SkillParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    config: Optional[SkillConfig] = None


class SkillRegistry:
    """Skill 注册表"""

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}
        self._loaded_modules = set()
        self._config_manager = get_config_manager()
        self._load_builtin_skills()

    def _load_builtin_skills(self):
        """加载内置技能"""
        from .tools import (
            read_file, write_file, list_directory,
            analyze_paper, web_search, crawl_website,
            github_search, calculate, get_current_time
        )

        builtin_skills = [
            SkillDefinition(
                name="read_file",
                description="读取文件内容",
                parameters=[
                    SkillParameter("path", "str", "文件路径", required=True),
                    SkillParameter("encoding", "str", "文件编码", required=False, default="utf-8")
                ],
                handler=read_file
            ),
            SkillDefinition(
                name="write_file",
                description="写入文件内容",
                parameters=[
                    SkillParameter("path", "str", "文件路径", required=True),
                    SkillParameter("content", "str", "内容", required=True),
                    SkillParameter("encoding", "str", "编码", required=False, default="utf-8")
                ],
                handler=write_file
            ),
            SkillDefinition(
                name="list_directory",
                description="列出目录内容",
                parameters=[
                    SkillParameter("path", "str", "目录路径", required=True)
                ],
                handler=list_directory
            ),
            SkillDefinition(
                name="calculate",
                description="数学计算",
                parameters=[
                    SkillParameter("expression", "str", "数学表达式", required=True)
                ],
                handler=calculate
            ),
            SkillDefinition(
                name="get_current_time",
                description="获取当前时间",
                parameters=[],
                handler=get_current_time
            ),
            SkillDefinition(
                name="web_search",
                description="网络搜索",
                parameters=[
                    SkillParameter("query", "str", "搜索关键词", required=True),
                    SkillParameter("num_results", "int", "结果数量", required=False, default=10)
                ],
                handler=web_search
            ),
            SkillDefinition(
                name="analyze_paper",
                description="分析科研论文",
                parameters=[
                    SkillParameter("file_path", "str", "论文文件路径", required=True)
                ],
                handler=analyze_paper
            ),
            SkillDefinition(
                name="crawl_website",
                description="爬取网站内容",
                parameters=[
                    SkillParameter("url", "str", "网站URL", required=True)
                ],
                handler=crawl_website
            ),
            SkillDefinition(
                name="github_search",
                description="搜索 GitHub 项目",
                parameters=[
                    SkillParameter("query", "str", "搜索关键词", required=True)
                ],
                handler=github_search
            )
        ]

        for skill in builtin_skills:
            self.register_skill(skill)

    def register_skill(self, definition: SkillDefinition):
        """注册一个 Skill"""
        self._skills[definition.name] = definition
        logger.debug(f"注册 Skill: {definition.name}")

    def unregister_skill(self, name: str):
        """取消注册 Skill"""
        if name in self._skills:
            del self._skills[name]
            logger.debug(f"取消注册 Skill: {name}")

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """获取 Skill 定义"""
        return self._skills.get(name)

    def get_all_skills(self) -> List[SkillDefinition]:
        """获取所有 Skill 定义"""
        return list(self._skills.values())

    def get_enabled_skills(self) -> List[SkillDefinition]:
        """获取所有启用的 Skill"""
        enabled_names = [cfg.name for cfg in self._config_manager.get_enabled_skills()]
        return [skill for skill in self._skills.values() if skill.name in enabled_names]

    async def execute_skill(self, name: str, **kwargs) -> Any:
        """执行 Skill"""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' 未找到")

        # 检查是否启用
        config = self._config_manager.get_skill_config(name)
        if config and not config.enabled:
            raise ValueError(f"Skill '{name}' 已禁用")

        if not skill.handler:
            raise ValueError(f"Skill '{name}' 没有处理器")

        # 验证参数
        self._validate_parameters(skill, kwargs)

        # 执行
        if inspect.iscoroutinefunction(skill.handler):
            return await skill.handler(**kwargs)
        else:
            return skill.handler(**kwargs)

    def _validate_parameters(self, skill: SkillDefinition, params: Dict[str, Any]):
        """验证参数"""
        for param in skill.parameters:
            if param.required and param.name not in params:
                raise ValueError(f"参数 '{param.name}' 是必需的")

    def load_skill_from_file(self, file_path: Path):
        """从文件加载自定义 Skill"""
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        module_name = f"custom_skill_{file_path.stem}"
        if module_name in self._loaded_modules:
            logger.warning(f"模块已加载: {module_name}")
            return

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            self._loaded_modules.add(module_name)
            self._register_from_module(module, file_path)
            logger.info(f"从文件加载 Skill: {file_path}")

    def _register_from_module(self, module, file_path: Path):
        """从模块注册 Skill"""
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name.startswith("skill_"):
                skill_name = name[6:]  # 去掉 "skill_" 前缀
                doc = inspect.getdoc(obj) or f"自定义 Skill: {skill_name}"

                signature = inspect.signature(obj)
                params = []
                for param_name, param in signature.parameters.items():
                    param_type = "str"
                    if param.annotation != inspect.Parameter.empty:
                        param_type = param.annotation.__name__

                    default = None
                    required = True
                    if param.default != inspect.Parameter.empty:
                        default = param.default
                        required = False

                    params.append(SkillParameter(
                        name=param_name,
                        type=param_type,
                        description="",
                        required=required,
                        default=default
                    ))

                definition = SkillDefinition(
                    name=skill_name,
                    description=doc,
                    parameters=params,
                    handler=obj
                )
                self.register_skill(definition)

    def load_skill_directory(self, dir_path: Path):
        """从目录加载所有 Skill"""
        if not dir_path.exists():
            logger.warning(f"目录不存在: {dir_path}")
            return

        for py_file in dir_path.glob("*.py"):
            try:
                self.load_skill_from_file(py_file)
            except Exception as e:
                logger.error(f"加载 Skill 失败 {py_file}: {e}")


# 全局 Skill 注册表
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局 Skill 注册表"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
