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

from ..event_stream import emit as _emit_event

try:
    from ..skill_system import Skill, SkillCategory, SecurityScanner, ScanResult, Curator, SkillStatus
    from ..skill_system import filter_tools_by_skill_allowed_tools
    HAS_SKILL_SYSTEM = True
except ImportError:
    HAS_SKILL_SYSTEM = False


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
        self._skill_directory = Path(__file__).parent.parent / "custom_skills"
        self._skill_directory.mkdir(exist_ok=True)

        self._security_scanner = SecurityScanner() if HAS_SKILL_SYSTEM else None
        self._curator = None
        if HAS_SKILL_SYSTEM:
            try:
                skills_dir = Path(__file__).parent.parent / "skills"
                self._curator = Curator(skills_dir)
            except Exception as e:
                logger.warning(f"Curator初始化失败: {e}")

        # B 类硬编码技能（hello_world/calculate）已迁移至 mcp/tools.py 工具体系
        # （calculate 即 CalculateTool）；本注册表只面向 A 类文本技能（SKILL.md）。

    def register_skill(self, skill: SkillDefinition):
        """注册技能"""
        self._skills[skill.name] = skill
        logger.debug(f"Registered skill: {skill.name}")
        _emit_event("skill.registry.changed", {"action": "register", "name": skill.name})

    def unregister_skill(self, name: str):
        """取消注册技能"""
        if name in self._skills:
            del self._skills[name]
            logger.debug(f"Unregistered skill: {name}")
            _emit_event("skill.registry.changed", {"action": "unregister", "name": name})

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
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False

        if self._security_scanner:
            try:
                scan_result = self._security_scanner.scan_content(
                    file_path.read_text(encoding="utf-8", errors="ignore"),
                    name=file_path.name,
                )
                if not scan_result.passed:
                    logger.warning(f"Skill安全扫描未通过: {file_path.name}")
                    for finding in scan_result.findings:
                        if finding.severity.value == "critical":
                            logger.error(f"  CRITICAL: {finding.message} (L{finding.line_number})")
                    return False
            except Exception as e:
                logger.warning(f"Skill安全扫描异常: {e}")
        
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

    def create_custom_skill(
        self, name: str, description: str, parameters: List[SkillParameter],
        code: str, category: str = "custom", version: str = "1.0.0",
        tags: List[str] = None,
    ) -> Optional[SkillDefinition]:
        """创建自定义技能（B 类脚本式：动态生成 skill_xxx Python 文件并加载）。"""
        skill_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
{description}
"""

def skill_{name}(**kwargs):
    """{description}"""
    try:
        {code}
    except Exception as e:
        return f"错误: {{str(e)}}"

SKILL_NAME = "{name}"
SKILL_DESCRIPTION = "{description}"
SKILL_VERSION = "{version}"
SKILL_CATEGORY = "{category}"
SKILL_TAGS = {tags or []}
'''
        skill_dir = Path(__file__).resolve().parent.parent / "custom_skills"
        skill_dir.mkdir(exist_ok=True)
        skill_file = skill_dir / f"{name}.py"
        skill_file.write_text(skill_code, encoding="utf-8")
        if not self.load_skill_from_file(skill_file):
            logger.error(f"自定义技能加载失败: {name}")
            return None
        return self.get_skill(name)

    def import_skill(self, import_path: Path) -> Optional[SkillDefinition]:
        """从 JSON 文件导入技能定义（仅元数据，无执行代码）。"""
        try:
            if not import_path.exists():
                logger.error(f"导入文件不存在: {import_path}")
                return None
            data = json.loads(import_path.read_text(encoding="utf-8"))
            parameters = [SkillParameter(
                name=p.get("name", ""), type=p.get("type", "str"),
                description=p.get("description", ""), required=p.get("required", True),
                default=p.get("default"), enum=p.get("enum"))
                for p in data.get("parameters", [])]
            skill = SkillDefinition(
                name=data.get("name", ""), description=data.get("description", ""),
                parameters=parameters, category=data.get("category", "custom"),
                version=data.get("version", "1.0.0"), tags=data.get("tags", []),
                handler=None)
            self.register_skill(skill)
            logger.info(f"已导入技能: {skill.name}")
            return skill
        except Exception as e:
            logger.error(f"导入技能失败: {e}")
            return None

    def export_skill(self, name: str, export_path: Path) -> bool:
        skill = self.get_skill(name)
        if not skill:
            logger.error(f"Skill not found: {name}")
            return False
        try:
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

    def scan_skill_dir(self, skill_dir: Path) -> Optional[Any]:
        if not HAS_SKILL_SYSTEM:
            return None
        try:
            skill = Skill.from_skill_md(skill_dir)
            if skill and self._security_scanner:
                scan_result = self._security_scanner.scan_skill(skill_dir)
                return scan_result
        except Exception as e:
            logger.error(f"Skill扫描失败: {e}")
        return None

    def run_curator(self) -> List[Any]:
        if self._curator:
            return self._curator.maybe_run_curator()
        return []

    def record_skill_access(self, skill_name: str):
        if self._curator:
            self._curator.record_access(skill_name)

    def filter_tools(self, tools: List[Dict[str, Any]], active_skills: List[str] = None) -> List[Dict[str, Any]]:
        if not HAS_SKILL_SYSTEM or not active_skills:
            return tools
        skill_objs = [self._skills.get(s) for s in active_skills if s in self._skills]
        return filter_tools_by_skill_allowed_tools(tools, skill_objs)


# 全局注册表
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
