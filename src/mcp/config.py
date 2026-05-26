#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 和 Skill 配置管理系统
支持 API 密钥管理、Skill 配置和动态加载
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
import logging

logger = logging.getLogger(__name__)

# 子 Agent 配置
@dataclass
class SubAgentConfig:
    role: str
    name: str
    enabled: bool = True
    model: str = ""
    max_turns: int = 10
    system_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

# 导入新的提供商类型（从 llm 模块）
try:
    from .llm import ProviderType, ProviderConfig, DEFAULT_MODEL_INFOS, PROVIDER_DISPLAY_NAMES, PROVIDER_DEFAULT_BASE_URL, PROVIDER_DEFAULT_MODELS
    HAS_PROVIDERS = True
except ImportError:
    HAS_PROVIDERS = False


@dataclass
class APIConfig:
    """API 配置（保持向后兼容）"""
    name: str
    provider: str  # openai, claude, anthropic, custom
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 60
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 新增：优先级

    def to_provider_config(self) -> 'ProviderConfig':
        """转换为新的 ProviderConfig 格式"""
        if HAS_PROVIDERS:
            # 尝试映射旧的 provider 字符串到新的 ProviderType
            provider_map = {
                "openai": ProviderType.OPENAI,
                "claude": ProviderType.ANTHROPIC,
                "anthropic": ProviderType.ANTHROPIC,
                "deepseek": ProviderType.DEEPSEEK,
                "qwen": ProviderType.QWEN,
                "ollama": ProviderType.OLLAMA,
                "mimo": ProviderType.MIMO,
                "custom": ProviderType.CUSTOM,
                "simulator": ProviderType.SIMULATOR,
            }
            provider_type = provider_map.get(self.provider.lower(), ProviderType.CUSTOM)
            return ProviderConfig(
                provider=provider_type,
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model or "gpt-4o-mini",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                enabled=self.enabled,
                priority=self.priority,
                name=self.name,
            )
        raise ImportError("llm_providers 模块不可用")


@dataclass
class SkillConfig:
    """Skill 配置"""
    name: str
    description: str
    type: str  # builtin, custom, plugin
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    handler_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolConfig:
    """Tool 配置"""
    name: str
    description: str
    category: str  # builtin, ws2, hub, rag, sandbox, mcp_client
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path(__file__).parent.parent / "agent_config"
        self.config_dir.mkdir(exist_ok=True)

        self.api_configs_file = self.config_dir / "apis.json"
        self.skills_config_file = self.config_dir / "skills.json"
        self.tools_config_file = self.config_dir / "tools.json"  # 新增工具配置文件
        self.settings_file = self.config_dir / "settings.json"
        # 新的提供商配置文件
        self.providers_config_file = self.config_dir / "providers.json"
        # 子 Agent 配置文件
        self.sub_agents_config_file = self.config_dir / "sub_agents.json"

        self.api_configs: Dict[str, APIConfig] = {}
        self.provider_configs: List['ProviderConfig'] = []  # 新的提供商配置
        self.skill_configs: Dict[str, SkillConfig] = {}
        self.tool_configs: Dict[str, ToolConfig] = {}  # 新增工具配置字典
        self.settings: Dict[str, Any] = {}
        self.sub_agent_configs: List['SubAgentConfig'] = []

        self._load_all()

    def _load_all(self):
        """加载所有配置"""
        self._load_api_configs()
        self._load_provider_configs()  # 新增
        self._load_sub_agent_configs()
        self._load_skill_configs()
        self._load_tool_configs()  # 新增工具配置加载
        self._load_settings()
        self._init_defaults()

    def _load_sub_agent_configs(self):
        """加载子 Agent 配置"""
        if self.sub_agents_config_file.exists():
            try:
                data = json.loads(self.sub_agents_config_file.read_text("utf-8"))
                for item in data:
                    self.sub_agent_configs.append(SubAgentConfig(**item))
            except Exception as e:
                logger.warning(f"加载子 Agent 配置失败: {e}")

    def _save_sub_agent_configs(self):
        """保存子 Agent 配置"""
        data = [asdict(cfg) for cfg in self.sub_agent_configs]
        self.sub_agents_config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def get_sub_agent_config(self, name: str) -> Optional['SubAgentConfig']:
        """获取指定子 Agent 的配置"""
        for cfg in self.sub_agent_configs:
            if cfg.name == name:
                return cfg
        return None

    def get_sub_agent_configs(self) -> List['SubAgentConfig']:
        """获取所有子 Agent 配置"""
        return self.sub_agent_configs.copy()

    def update_sub_agent_config(self, name: str, **kwargs) -> bool:
        """更新子 Agent 配置"""
        for cfg in self.sub_agent_configs:
            if cfg.name == name:
                for key, value in kwargs.items():
                    if hasattr(cfg, key):
                        setattr(cfg, key, value)
                self._save_sub_agent_configs()
                return True
        return False

    def add_sub_agent_config(self, config: 'SubAgentConfig') -> bool:
        """添加子 Agent 配置"""
        # 移除同名配置
        self.sub_agent_configs = [c for c in self.sub_agent_configs if c.name != config.name]
        self.sub_agent_configs.append(config)
        self._save_sub_agent_configs()
        return True

    def _init_defaults(self):
        """初始化默认配置"""
        if not self.api_configs and not self.provider_configs:
            # 添加默认的模拟 API（旧格式）
            self.add_api_config(APIConfig(
                name="simulator",
                provider="custom",
                api_key="demo_key_123",
                model="simulator",
                enabled=True
            ))

        if HAS_PROVIDERS and not self.provider_configs:
            # 添加默认的提供商配置（新格式）
            self._add_default_provider_configs()

        # 自动检测环境变量中的 API Key，补充缺失的提供商
        if HAS_PROVIDERS and self.provider_configs:
            self._auto_add_env_providers()

        if not self.sub_agent_configs:
            # 添加默认子 Agent 配置
            default_sub_agents = [
                SubAgentConfig(
                    role="coder",
                    name="coder",
                    enabled=True,
                    model="",
                    max_turns=15,
                    system_prompt="你是一名专业的编程助手。你的任务是编写、调试、重构代码，解决编程问题。请给出清晰、可执行的解决方案。",
                ),
                SubAgentConfig(
                    role="task",
                    name="task",
                    enabled=True,
                    model="",
                    max_turns=10,
                    system_prompt="你是一名任务执行助手。你的任务是完成用户指定的具体任务，一步一步执行，并给出完整的结果。",
                ),
                SubAgentConfig(
                    role="research",
                    name="research",
                    enabled=True,
                    model="",
                    max_turns=8,
                    system_prompt="你是一名研究助手。你的任务是搜索信息、分析资料、总结内容，帮助用户深入了解特定主题。",
                ),
                SubAgentConfig(
                    role="review",
                    name="review",
                    enabled=True,
                    model="",
                    max_turns=5,
                    system_prompt="你是一名代码审查专家。你的任务是审查代码质量、安全性、最佳实践，并给出建设性的改进建议。",
                ),
            ]
            for cfg in default_sub_agents:
                self.add_sub_agent_config(cfg)

        if not self.skill_configs:
            # 添加默认 Skills
            default_skills = [
                SkillConfig(
                    name="read_file",
                    description="读取文件内容",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="write_file",
                    description="写入文件内容",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="list_directory",
                    description="列出目录内容",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="web_search",
                    description="网络搜索",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="calculate",
                    description="数学计算",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="analyze_paper",
                    description="分析科研论文",
                    type="builtin",
                    enabled=True
                ),
                SkillConfig(
                    name="crawl_website",
                    description="爬取网站内容",
                    type="builtin",
                    enabled=False
                ),
                SkillConfig(
                    name="github_search",
                    description="搜索 GitHub 项目",
                    type="builtin",
                    enabled=False
                )
            ]
            for skill in default_skills:
                self.add_skill_config(skill)

    def _load_api_configs(self):
        """加载 API 配置"""
        if self.api_configs_file.exists():
            try:
                data = json.loads(self.api_configs_file.read_text("utf-8"))
                for item in data:
                    self.api_configs[item["name"]] = APIConfig(**item)
            except Exception as e:
                logger.warning(f"加载 API 配置失败: {e}")

    def _load_provider_configs(self):
        """加载新的提供商配置"""
        if not HAS_PROVIDERS:
            return
        if self.providers_config_file.exists():
            try:
                data = json.loads(self.providers_config_file.read_text("utf-8"))
                for item in data:
                    # 将字符串 provider 转换为 ProviderType
                    if "provider" in item and isinstance(item["provider"], str):
                        try:
                            item["provider"] = ProviderType(item["provider"])
                        except ValueError:
                            item["provider"] = ProviderType.CUSTOM
                    self.provider_configs.append(ProviderConfig(**item))
            except Exception as e:
                logger.warning(f"加载提供商配置失败: {e}")

    def _add_default_provider_configs(self):
        """添加默认的提供商配置"""
        if not HAS_PROVIDERS:
            return
        default_providers = [
            ProviderConfig(
                provider=ProviderType.SIMULATOR,
                name="simulator",
                model="simulator",
                enabled=True,
                priority=0,
            ),
            ProviderConfig(
                provider=ProviderType.OPENAI,
                name="openai-gpt4o-mini",
                model="gpt-4o-mini",
                base_url="https://api.openai.com/v1",
                enabled=False,
                priority=1,
            ),
            ProviderConfig(
                provider=ProviderType.DEEPSEEK,
                name="deepseek-chat",
                model="deepseek-chat",
                base_url="https://api.deepseek.com",
                enabled=False,
                priority=2,
            ),
            ProviderConfig(
                provider=ProviderType.QWEN,
                name="qwen-plus",
                model="qwen-plus",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                enabled=False,
                priority=3,
            ),
            ProviderConfig(
                provider=ProviderType.MIMO,
                name="mimo-v2.5-pro",
                model="mimo-v2.5-pro",
                base_url="https://api.xiaomimimo.com/v1",
                api_key=os.environ.get("MIMO_API_KEY", ""),
                enabled=bool(os.environ.get("MIMO_API_KEY")),
                priority=4,
                thinking_enabled=True,
            ),
        ]
        for provider in default_providers:
            self.add_provider_config(provider)

    def _auto_add_env_providers(self):
        """自动检测环境变量中的 API Key，补充缺失的提供商配置"""
        if not HAS_PROVIDERS:
            return

        _ENV_ALIASES = {
            ProviderType.QWEN: ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
            ProviderType.QWEN_CODE: ["QWEN_CODE_API_KEY", "DASHSCOPE_API_KEY"],
            ProviderType.DOUBAO: ["DOUBAO_API_KEY", "VOLCENGINE_API_KEY"],
            ProviderType.GEMINI: ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            ProviderType.CLAUDE_CODE: ["CLAUDE_CODE_API_KEY", "ANTHROPIC_API_KEY"],
            ProviderType.LM_STUDIO: [],
            ProviderType.OLLAMA: [],
            ProviderType.SIMULATOR: [],
            ProviderType.LITELLM: [],
            ProviderType.CUSTOM: [],
            ProviderType.DIFY: [],
            ProviderType.HICAP: [],
        }

        _REASONING_MODELS = {
            ProviderType.MIMO,
            ProviderType.DEEPSEEK,
            ProviderType.OPENAI,
        }

        existing_providers = {cfg.provider for cfg in self.provider_configs}

        for provider_type in ProviderType:
            if provider_type in existing_providers:
                continue
            if provider_type in (ProviderType.SIMULATOR, ProviderType.CUSTOM, ProviderType.LITELLM):
                continue

            env_names = _ENV_ALIASES.get(provider_type)
            if env_names is None:
                env_names = [f"{provider_type.value.upper().replace('-', '_')}_API_KEY"]

            api_key = ""
            matched_env = ""
            for env_name in env_names:
                val = os.environ.get(env_name, "")
                if val:
                    api_key = val
                    matched_env = env_name
                    break

            if not api_key:
                if provider_type in (ProviderType.OLLAMA, ProviderType.LM_STUDIO):
                    base_url = PROVIDER_DEFAULT_BASE_URL.get(provider_type, "")
                    models = PROVIDER_DEFAULT_MODELS.get(provider_type, [])
                    if base_url and models:
                        display_name = PROVIDER_DISPLAY_NAMES.get(provider_type, provider_type.value)
                        cfg = ProviderConfig(
                            provider=provider_type,
                            name=f"{display_name} 配置",
                            api_key="local",
                            base_url=base_url,
                            model=models[0],
                            enabled=True,
                            priority=len(self.provider_configs),
                        )
                        self.add_provider_config(cfg)
                        logger.info(f"自动添加本地提供商: {display_name}")
                continue

            base_url = PROVIDER_DEFAULT_BASE_URL.get(provider_type, "")
            models = PROVIDER_DEFAULT_MODELS.get(provider_type, [])
            if not models:
                continue

            model = models[0]
            thinking = provider_type in _REASONING_MODELS
            from .llm import DEFAULT_MODEL_INFOS
            model_info = DEFAULT_MODEL_INFOS.get(model)
            if model_info and model_info.is_reasoning_model:
                thinking = True
            else:
                thinking = False

            display_name = PROVIDER_DISPLAY_NAMES.get(provider_type, provider_type.value)
            cfg = ProviderConfig(
                provider=provider_type,
                name=f"{display_name} 配置",
                api_key=api_key,
                base_url=base_url,
                model=model,
                enabled=True,
                priority=len(self.provider_configs),
                thinking_enabled=True if thinking else None,
            )
            self.add_provider_config(cfg)
            logger.info(f"自动添加提供商: {display_name} (from {matched_env})")

    def _save_provider_configs(self):
        """保存提供商配置"""
        if not HAS_PROVIDERS:
            return
        data = []
        for config in self.provider_configs:
            d = asdict(config)
            # 将 ProviderType 转换为字符串
            d["provider"] = d["provider"].value if hasattr(d["provider"], "value") else str(d["provider"])
            data.append(d)
        self.providers_config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_skill_configs(self):
        """加载 Skill 配置"""
        if self.skills_config_file.exists():
            try:
                data = json.loads(self.skills_config_file.read_text("utf-8"))
                for item in data:
                    self.skill_configs[item["name"]] = SkillConfig(**item)
            except Exception as e:
                logger.warning(f"加载 Skill 配置失败: {e}")

    def _load_tool_configs(self):
        """加载 Tool 配置"""
        if self.tools_config_file.exists():
            try:
                data = json.loads(self.tools_config_file.read_text("utf-8"))
                for item in data:
                    self.tool_configs[item["name"]] = ToolConfig(**item)
            except Exception as e:
                logger.warning(f"加载 Tool 配置失败: {e}")

    def _load_settings(self):
        """加载通用设置"""
        if self.settings_file.exists():
            try:
                self.settings = json.loads(self.settings_file.read_text("utf-8"))
            except Exception as e:
                logger.warning(f"加载设置失败: {e}")

    def _save_api_configs(self):
        """保存 API 配置"""
        data = [asdict(config) for config in self.api_configs.values()]
        self.api_configs_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_skill_configs(self):
        """保存 Skill 配置"""
        data = [asdict(config) for config in self.skill_configs.values()]
        self.skills_config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_tool_configs(self):
        """保存 Tool 配置"""
        data = [asdict(config) for config in self.tool_configs.values()]
        self.tools_config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_settings(self):
        """保存通用设置"""
        self.settings_file.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    # 提供商配置管理（新增）
    def add_provider_config(self, config: 'ProviderConfig') -> bool:
        """添加提供商配置"""
        # 检查是否已存在同名配置
        for i, existing in enumerate(self.provider_configs):
            if existing.name == config.name:
                self.provider_configs[i] = config
                self._save_provider_configs()
                return True
        self.provider_configs.append(config)
        self._save_provider_configs()
        return True

    def update_provider_config(self, name: str, **kwargs) -> bool:
        """更新提供商配置"""
        for config in self.provider_configs:
            if config.name == name:
                for key, value in kwargs.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                self._save_provider_configs()
                return True
        return False

    def remove_provider_config(self, name: str) -> bool:
        """删除提供商配置"""
        original_len = len(self.provider_configs)
        self.provider_configs = [c for c in self.provider_configs if c.name != name]
        if len(self.provider_configs) < original_len:
            self._save_provider_configs()
            return True
        return False

    def get_provider_config(self, name: str) -> Optional['ProviderConfig']:
        """获取提供商配置"""
        for config in self.provider_configs:
            if config.name == name:
                return config
        return None

    def get_enabled_providers(self) -> List['ProviderConfig']:
        """获取所有启用的提供商配置"""
        return [config for config in self.provider_configs if config.enabled]

    def get_all_provider_configs(self) -> List['ProviderConfig']:
        """获取所有提供商配置"""
        return self.provider_configs

    def get_provider_configs_for_manager(self) -> List['ProviderConfig']:
        """获取用于 MultiProviderManager 的配置，同时兼容旧的 APIConfig"""
        configs = []
        # 优先使用新的提供商配置
        if self.provider_configs:
            for cfg in self.provider_configs:
                # 自动从环境变量补充 API Key（如果配置中为空）
                if not cfg.api_key and HAS_PROVIDERS:
                    env_key = f"{cfg.provider.value.upper().replace('-', '_')}_API_KEY"
                    env_val = os.environ.get(env_key, "")
                    if env_val:
                        cfg.api_key = env_val
                        if not cfg.enabled:
                            cfg.enabled = True
                configs.append(cfg)
        # 如果没有新配置，尝试将旧的 APIConfig 转换
        elif self.api_configs:
            for api_config in self.api_configs.values():
                try:
                    provider_config = api_config.to_provider_config()
                    configs.append(provider_config)
                except Exception as e:
                    logger.warning(f"转换 APIConfig 失败: {e}")
        return configs

    # API 配置管理
    def add_api_config(self, config: APIConfig) -> bool:
        """添加 API 配置"""
        self.api_configs[config.name] = config
        self._save_api_configs()
        return True

    def update_api_config(self, name: str, **kwargs) -> bool:
        """更新 API 配置"""
        if name in self.api_configs:
            for key, value in kwargs.items():
                if hasattr(self.api_configs[name], key):
                    setattr(self.api_configs[name], key, value)
            self._save_api_configs()
            return True
        return False

    def remove_api_config(self, name: str) -> bool:
        """删除 API 配置"""
        if name in self.api_configs:
            del self.api_configs[name]
            self._save_api_configs()
            return True
        return False

    def get_api_config(self, name: str) -> Optional[APIConfig]:
        """获取 API 配置"""
        return self.api_configs.get(name)

    def get_enabled_apis(self) -> List[APIConfig]:
        """获取所有启用的 API 配置"""
        return [config for config in self.api_configs.values() if config.enabled]

    # Skill 配置管理
    def add_skill_config(self, config: SkillConfig) -> bool:
        """添加 Skill 配置"""
        self.skill_configs[config.name] = config
        self._save_skill_configs()
        return True

    def update_skill_config(self, name: str, **kwargs) -> bool:
        """更新 Skill 配置"""
        if name in self.skill_configs:
            for key, value in kwargs.items():
                if hasattr(self.skill_configs[name], key):
                    setattr(self.skill_configs[name], key, value)
            self._save_skill_configs()
            return True
        return False

    def remove_skill_config(self, name: str) -> bool:
        """删除 Skill 配置"""
        if name in self.skill_configs:
            del self.skill_configs[name]
            self._save_skill_configs()
            return True
        return False

    def get_skill_config(self, name: str) -> Optional[SkillConfig]:
        """获取 Skill 配置"""
        return self.skill_configs.get(name)

    def get_enabled_skills(self) -> List[SkillConfig]:
        """获取所有启用的 Skill 配置"""
        return [config for config in self.skill_configs.values() if config.enabled]

    # Tool 配置管理
    def add_tool_config(self, config: ToolConfig) -> bool:
        """添加 Tool 配置"""
        self.tool_configs[config.name] = config
        self._save_tool_configs()
        return True

    def update_tool_config(self, name: str, **kwargs) -> bool:
        """更新 Tool 配置"""
        if name in self.tool_configs:
            for key, value in kwargs.items():
                if hasattr(self.tool_configs[name], key):
                    setattr(self.tool_configs[name], key, value)
            self._save_tool_configs()
            return True
        return False

    def remove_tool_config(self, name: str) -> bool:
        """删除 Tool 配置"""
        if name in self.tool_configs:
            del self.tool_configs[name]
            self._save_tool_configs()
            return True
        return False

    def get_tool_config(self, name: str) -> Optional[ToolConfig]:
        """获取 Tool 配置"""
        return self.tool_configs.get(name)

    def get_enabled_tools(self) -> List[ToolConfig]:
        """获取所有启用的 Tool 配置"""
        return [config for config in self.tool_configs.values() if config.enabled]

    def init_default_tool_configs(self, tools_list: List[Any]) -> None:
        """初始化默认工具配置（从工具列表）"""
        for tool in tools_list:
            if tool.name not in self.tool_configs:
                cfg = ToolConfig(
                    name=tool.name,
                    description=tool.description,
                    category="builtin",  # 默认分类
                    enabled=True
                )
                self.add_tool_config(cfg)

    # 设置管理
    def set_setting(self, key: str, value: Any):
        """设置配置项"""
        self.settings[key] = value
        self._save_settings()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.settings.get(key, default)

    # 导入/导出
    def export_config(self, export_path: Path):
        """导出全部配置"""
        data = {
            "apis": [asdict(c) for c in self.api_configs.values()],
            "skills": [asdict(c) for c in self.skill_configs.values()],
            "tools": [asdict(c) for c in self.tool_configs.values()],
            "settings": self.settings
        }
        export_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_config(self, import_path: Path):
        """导入配置"""
        data = json.loads(import_path.read_text("utf-8"))
        if "apis" in data:
            for item in data["apis"]:
                self.api_configs[item["name"]] = APIConfig(**item)
        if "skills" in data:
            for item in data["skills"]:
                self.skill_configs[item["name"]] = SkillConfig(**item)
        if "tools" in data:
            for item in data["tools"]:
                self.tool_configs[item["name"]] = ToolConfig(**item)
        if "settings" in data:
            self.settings = data["settings"]
        self._save_api_configs()
        self._save_skill_configs()
        self._save_tool_configs()
        self._save_settings()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
