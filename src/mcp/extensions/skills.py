#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 技能扩展系统
技能现在作为 MCP 扩展的一部分，支持动态加载和管理
"""
import inspect
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
import importlib.util
import sys
import json

logger = logging.getLogger(__name__)


@dataclass
class SkillParameter:
    """技能参数定义"""
    name: str
    type: str = "str"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None


@dataclass
class SkillDefinition:
    """完整的技能定义"""
    name: str
    description: str
    parameters: List[SkillParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    category: str = "general"
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    enabled: bool = True


class SkillRegistry:
    """
    MCP 技能注册表
    管理所有已注册的技能，支持动态加载和执行
    """

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}
        self._loaded_modules = set()
        self._skill_directory = Path(__file__).parent.parent.parent / "custom_skills"
        self._skill_directory.mkdir(exist_ok=True)
        self._load_builtin_skills()

    def _load_builtin_skills(self):
        """加载内置技能"""
        # 基础示例技能
        self.register_skill(SkillDefinition(
            name="hello_world",
            description="向世界问好的简单技能",
            parameters=[
                SkillParameter(name="name", description="名字", default="World")
            ],
            category="example",
            handler=lambda **kwargs: f"Hello, {kwargs.get('name', 'World')}!"
        ))

        self.register_skill(SkillDefinition(
            name="calculate",
            description="简单的数学计算",
            parameters=[
                SkillParameter(name="expression", description="数学表达式", required=True)
            ],
            category="math",
            handler=self._calculate_handler
        ))

        logger.info("Loaded built-in skills")

    def _calculate_handler(self, **kwargs):
        """计算处理函数"""
        try:
            expression = kwargs.get('expression', '')
            # 安全的计算，只允许基本操作
            allowed_chars = set("0123456789+-*/(). ")
            if not all(c in allowed_chars for c in expression):
                return "错误：表达式包含不允许的字符"
            result = eval(expression, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"计算错误：{str(e)}"

    def register_skill(self, skill: SkillDefinition):
        """注册技能"""
        self._skills[skill.name] = skill
        logger.debug(f"Registered skill: {skill.name}")

    def unregister_skill(self, name: str):
        """取消注册技能"""
        if name in self._skills:
            del self._skills[name]
            logger.debug(f"Unregistered skill: {name}")

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """获取技能"""
        return self._skills.get(name)

    def list_skills(self, category: Optional[str] = None) -> List[SkillDefinition]:
        """列出所有技能"""
        if category:
            return [s for s in self._skills.values() if s.category == category]
        return list(self._skills.values())

    async def execute_skill(self, name: str, **kwargs) -> Any:
        """执行技能"""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill not found: {name}")
        
        if not skill.enabled:
            raise ValueError(f"Skill disabled: {name}")
        
        if not skill.handler:
            raise ValueError(f"Skill has no handler: {name}")
        
        # 验证参数
        for param in skill.parameters:
            if param.required and param.name not in kwargs:
                raise ValueError(f"Missing required parameter: {param.name}")
        
        # 执行
        if inspect.iscoroutinefunction(skill.handler):
            return await skill.handler(**kwargs)
        else:
            return skill.handler(**kwargs)

    def load_skill_from_file(self, file_path: Path) -> bool:
        """从文件加载技能"""
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False
        
        try:
            # 动态加载模块
            module_name = f"custom_skill_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                # 查找技能定义
                for name, obj in inspect.getmembers(module):
                    if name.startswith('skill_') and callable(obj):
                        skill_name = name[6:]
                        doc = inspect.getdoc(obj) or f"Custom skill: {skill_name}"
                        sig = inspect.signature(obj)
                        params = []
                        
                        for param_name, param in sig.parameters.items():
                            param_type = "str"
                            if param.annotation != inspect.Parameter.empty:
                                param_type = getattr(param.annotation, '__name__', 'str')
                            
                            has_default = param.default != inspect.Parameter.empty
                            params.append(SkillParameter(
                                name=param_name,
                                type=param_type,
                                required=not has_default,
                                default=param.default if has_default else None
                            ))
                        
                        skill = SkillDefinition(
                            name=skill_name,
                            description=doc,
                            parameters=params,
                            category="custom",
                            handler=obj
                        )
                        self.register_skill(skill)
                        logger.info(f"Loaded skill from file: {skill_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to load skill from file: {e}")
        return False

    def load_skill_directory(self, dir_path: Path):
        """从目录加载所有技能"""
        if not dir_path.exists():
            return
        
        for py_file in dir_path.glob("*.py"):
            try:
                self.load_skill_from_file(py_file)
            except Exception as e:
                logger.error(f"Failed to load skill from {py_file}: {e}")

    def export_skill(self, name: str, export_path: Path) -> bool:
        """导出技能到文件"""
        skill = self.get_skill(name)
        if not skill:
            logger.error(f"Skill not found: {name}")
            return False
        
        try:
            # 导出基本信息
            export_data = {
                'name': skill.name,
                'description': skill.description,
                'category': skill.category,
                'version': skill.version,
                'tags': skill.tags,
                'parameters': [
                    {
                        'name': p.name,
                        'type': p.type,
                        'description': p.description,
                        'required': p.required,
                        'default': p.default,
                        'enum': p.enum
                    }
                    for p in skill.parameters
                ]
            }
            
            export_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding='utf-8')
            logger.info(f"Exported skill: {name} -> {export_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export skill: {e}")
        return False


# 全局注册表
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
