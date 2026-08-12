"""
LLM Manager — 从 ~/.ts2/agent_config/providers.json 读取 LLM 设置
供 SaberSystem 决策生成使用，避免硬编码环境变量
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AGENT_CONFIG_DIR = Path.home() / '.ts2' / 'agent_config'
_PROVIDERS_FILE = _AGENT_CONFIG_DIR / 'providers.json'


def _load_providers() -> list[dict[str, Any]]:
    try:
        if _PROVIDERS_FILE.exists():
            return json.loads(_PROVIDERS_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning(f"读取 providers.json 失败: {e}")
    return []


def get_best_provider() -> dict[str, Any] | None:
    """从 providers.json 找到优先级最高（priority 最小）且 enabled 的 provider"""
    providers = _load_providers()
    enabled = [p for p in providers if p.get('enabled', False)]
    if not enabled:
        logger.warning("没有启用的 LLM provider")
        return None
    enabled.sort(key=lambda p: p.get('priority', 99))
    best = enabled[0]
    logger.info(f"选中 LLM provider: {best.get('name', best.get('provider', 'unknown'))} (priority {best.get('priority')})")
    return best


_SABER_LLM_CACHE: dict[str, Any] | None = None


def get_model_selector():
    """延迟导入 ModelSelector，避免循环依赖。"""
    from ...model_selector import get_model_selector as _gs
    return _gs()


def get_llm_config_selector() -> dict[str, Any] | None:
    """fixed 模式返回固定 provider 配置；否则返回 None（走 get_best_provider）。"""
    try:
        sel = get_model_selector()
    except Exception:
        return None
    if sel.get_mode() != "fixed":
        return None
    key = sel.get_default_model()
    if not key:
        return None
    name, _, model = key.partition("/")
    if not model:
        return None
    providers = [p for p in _load_providers() if p.get("enabled", True)]
    exact_name = [p for p in providers if p.get("name") == name]
    provider_model = [
        p for p in providers
        if p.get("provider") == name and p.get("model") == model
    ]
    if not provider_model:
        provider_model = [p for p in providers if p.get("provider") == name]
    if not provider_model:
        provider_model = [p for p in providers if p.get("model") == model]
    candidates = exact_name or provider_model
    candidates.sort(key=lambda p: (p.get("priority", 99), p.get("name", "")))
    if candidates:
        p = candidates[0]
        return {
            "api_key": p.get("api_key", ""),
            "base_url": p.get("base_url", ""),
            "model": model,
            "temperature": p.get("temperature", 0.7),
            "max_tokens": p.get("max_tokens", 4096),
        }
    return None


def get_llm_config(use_selector: bool = True) -> dict[str, Any]:
    """获取 LLM 配置（api_key, base_url, model, temperature, max_tokens）"""
    global _SABER_LLM_CACHE
    if _SABER_LLM_CACHE is not None:
        return _SABER_LLM_CACHE
    if use_selector:
        fixed = get_llm_config_selector()
        if fixed is not None:
            _SABER_LLM_CACHE = fixed
            return fixed

    provider = get_best_provider()
    if provider is None:
        cfg = {
            'api_key': os.environ.get('OPENAI_API_KEY', ''),
            'base_url': os.environ.get('OPENAI_BASE_URL', ''),
            'model': os.environ.get('SABER_LLM_MODEL', 'gpt-4o-mini'),
            'temperature': 0.7,
            'max_tokens': 4096,
        }
        _SABER_LLM_CACHE = cfg
        return cfg

    cfg = {
        'api_key': provider.get('api_key', ''),
        'base_url': provider.get('base_url', ''),
        'model': provider.get('model', 'gpt-4o-mini'),
        'temperature': provider.get('temperature', 0.7),
        'max_tokens': provider.get('max_tokens', 4096),
    }
    _SABER_LLM_CACHE = cfg
    return cfg


def clear_cache():
    global _SABER_LLM_CACHE
    _SABER_LLM_CACHE = None


def get_openai_client():
    """创建 OpenAI 客户端（基于配置中最优 provider）"""
    cfg = get_llm_config()
    api_key = cfg['api_key']
    base_url = cfg['base_url']
    if not api_key:
        logger.warning("LLM 未配置 api_key")
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url or None)
    except ImportError:
        logger.warning("openai package not installed")
        return None
