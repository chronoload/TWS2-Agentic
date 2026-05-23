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

# 导入新的提供商类型（从 llm 模块）
try:
    from .llm import ProviderType, ProviderConfig, DEFAULT_MODEL_INFOS
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


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path(__file__).parent.parent / "agent_config"
        self.config_dir.mkdir(exist_ok=True)

        self.api_configs_file = self.config_dir / "apis.json"
        self.skills_config_file = self.config_dir / "skills.json"
        self.settings_file = self.config_dir / "settings.json"
        # 新的提供商配置文件
        self.providers_config_file = self.config_dir / "providers.json"

        self.api_configs: Dict[str, APIConfig] = {}
        self.provider_configs: List['ProviderConfig'] = []  # 新的提供商配置
        self.skill_configs: Dict[str, SkillConfig] = {}
        self.settings: Dict[str, Any] = {}

        self._load_all()

    def _load_all(self):
        """加载所有配置"""
        self._load_api_configs()
        self._load_provider_configs()  # 新增
        self._load_skill_configs()
        self._load_settings()
        self._init_defaults()

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
        ]
        for provider in default_providers:
            self.add_provider_config(provider)

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
            configs.extend(self.provider_configs)
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
        if "settings" in data:
            self.settings = data["settings"]
        self._save_api_configs()
        self._save_skill_configs()
        self._save_settings()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
