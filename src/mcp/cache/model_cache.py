#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型缓存 — 参考 Cline modelInfoCache + OpenCode models 设计
提供商模型信息缓存，TTL=1小时，支持动态模型列表
"""

import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path

from .lru_cache import TTLCache, LRUCache
from .disk import get_disk_store

logger = logging.getLogger(__name__)

MODEL_CACHE_TTL = 3600.0
MODEL_INFO_CACHE_TTL = 86400.0


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str
    api_model: str = ""
    context_window: int = 128000
    default_max_tokens: int = 4096
    cost_per_1m_in: float = 0.0
    cost_per_1m_out: float = 0.0
    cost_per_1m_in_cached: float = 0.0
    can_reason: bool = False
    supports_attachments: bool = True
    supports_streaming: bool = True
    supports_tools: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# 预置模型 — 参考 OpenCode SupportedModels
PRESET_MODELS: Dict[str, ModelInfo] = {
    "gpt-4o": ModelInfo(
        id="gpt-4o", name="GPT-4o", provider="openai",
        api_model="gpt-4o", context_window=128000,
        cost_per_1m_in=2.5, cost_per_1m_out=10.0,
        cost_per_1m_in_cached=1.25, can_reason=True,
        tags=["production", "recommended"],
    ),
    "gpt-4o-mini": ModelInfo(
        id="gpt-4o-mini", name="GPT-4o Mini", provider="openai",
        api_model="gpt-4o-mini", context_window=128000,
        cost_per_1m_in=0.15, cost_per_1m_out=0.6,
        cost_per_1m_in_cached=0.075, can_reason=False,
        tags=["economy", "fast"],
    ),
    "gpt-4-turbo": ModelInfo(
        id="gpt-4-turbo", name="GPT-4 Turbo", provider="openai",
        api_model="gpt-4-turbo", context_window=128000,
        cost_per_1m_in=10.0, cost_per_1m_out=30.0,
        can_reason=False,
    ),
    "claude-4-sonnet": ModelInfo(
        id="claude-4-sonnet", name="Claude 4 Sonnet", provider="anthropic",
        api_model="claude-4-sonnet-20250514", context_window=200000,
        cost_per_1m_in=3.0, cost_per_1m_out=15.0,
        cost_per_1m_in_cached=3.75, can_reason=False,
        tags=["production", "recommended"],
    ),
    "claude-4-opus": ModelInfo(
        id="claude-4-opus", name="Claude 4 Opus", provider="anthropic",
        api_model="claude-opus-4-20250514", context_window=200000,
        cost_per_1m_in=15.0, cost_per_1m_out=75.0,
        cost_per_1m_in_cached=18.75, can_reason=True,
        tags=["production", "premium"],
    ),
    "deepseek-v3": ModelInfo(
        id="deepseek-v3", name="DeepSeek-V3", provider="deepseek",
        api_model="deepseek-chat", context_window=128000,
        cost_per_1m_in=0.27, cost_per_1m_out=1.1, can_reason=False,
        tags=["economy"],
    ),
    "deepseek-r1": ModelInfo(
        id="deepseek-r1", name="DeepSeek-R1", provider="deepseek",
        api_model="deepseek-reasoner", context_window=128000,
        cost_per_1m_in=0.55, cost_per_1m_out=2.19, can_reason=True,
        tags=["reasoning"],
    ),
    "qwen-max": ModelInfo(
        id="qwen-max", name="Qwen-Max", provider="qwen",
        api_model="qwen-max-latest", context_window=32768,
        cost_per_1m_in=2.0, cost_per_1m_out=6.0, can_reason=False,
    ),
    "qwen-plus": ModelInfo(
        id="qwen-plus", name="Qwen-Plus", provider="qwen",
        api_model="qwen-plus-latest", context_window=131072,
        cost_per_1m_in=0.5, cost_per_1m_out=2.0, can_reason=False,
    ),
    "ollama-default": ModelInfo(
        id="ollama-default", name="Ollama (本地)", provider="ollama",
        api_model="", context_window=8192,
        cost_per_1m_in=0.0, cost_per_1m_out=0.0, can_reason=False,
        tags=["local", "free"],
    ),
    "mimo-v2.5-pro": ModelInfo(
        id="mimo-v2.5-pro", name="MiMo V2.5 Pro", provider="mimo",
        api_model="mimo-v2.5-pro", context_window=131072,
        default_max_tokens=131072,
        cost_per_1m_in=2.0, cost_per_1m_out=10.0, can_reason=True,
        tags=["reasoning", "production"],
    ),
    "mimo-v2.5": ModelInfo(
        id="mimo-v2.5", name="MiMo V2.5", provider="mimo",
        api_model="mimo-v2.5", context_window=131072,
        default_max_tokens=32768,
        cost_per_1m_in=1.0, cost_per_1m_out=5.0, can_reason=True,
        tags=["reasoning"],
    ),
    "mimo-v2-flash": ModelInfo(
        id="mimo-v2-flash", name="MiMo V2 Flash", provider="mimo",
        api_model="mimo-v2-flash", context_window=131072,
        default_max_tokens=65536,
        cost_per_1m_in=0.1, cost_per_1m_out=0.5, can_reason=False,
        tags=["economy", "fast"],
    ),
    "mimo-v2-pro": ModelInfo(
        id="mimo-v2-pro", name="MiMo V2 Pro", provider="mimo",
        api_model="mimo-v2-pro", context_window=131072,
        default_max_tokens=131072,
        cost_per_1m_in=1.5, cost_per_1m_out=7.5, can_reason=True,
        tags=["reasoning"],
    ),
    "mimo-v2-omni": ModelInfo(
        id="mimo-v2-omni", name="MiMo V2 Omni", provider="mimo",
        api_model="mimo-v2-omni", context_window=131072,
        default_max_tokens=32768,
        cost_per_1m_in=1.0, cost_per_1m_out=5.0, can_reason=False,
        tags=["multimodal"],
    ),
}


class ProviderModelCache:
    """单提供商模型缓存 — 类似 Cline 的 modelInfoCache 每个提供商的条目"""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self._data: Optional[Dict[str, ModelInfo]] = None
        self._timestamp: float = 0.0
        self._ttl = MODEL_CACHE_TTL

    def get(self, model_id: str) -> Optional[ModelInfo]:
        if self._is_expired():
            self._data = None
            return None
        return self._data.get(model_id) if self._data else None

    def get_all(self) -> Optional[Dict[str, ModelInfo]]:
        if self._is_expired():
            self._data = None
            return None
        return self._data

    def set(self, models: Dict[str, ModelInfo]):
        self._data = models
        self._timestamp = time.time()

    def set_from_raw(self, raw_models: List[Dict], ttl: Optional[float] = None):
        models = {}
        for raw in raw_models:
            model_id = raw.get("id", "")
            if model_id:
                if isinstance(raw, ModelInfo):
                    models[model_id] = raw
                else:
                    models[model_id] = ModelInfo(
                        id=model_id,
                        name=raw.get("name", model_id),
                        provider=self.provider_name,
                        api_model=raw.get("api_model", raw.get("id", "")),
                        context_window=raw.get("context_window", 128000),
                        default_max_tokens=raw.get("default_max_tokens", 4096),
                        can_reason=raw.get("can_reason", False),
                    )
        self._data = models
        self._timestamp = time.time()
        if ttl is not None:
            self._ttl = ttl

    def _is_expired(self) -> bool:
        return time.time() - self._timestamp > self._ttl

    @property
    def valid(self) -> bool:
        return self._data is not None and not self._is_expired()


class ModelCache:
    """
    全局模型缓存 — 类似 Cline StateManager 的 modelInfoCache
    每个提供商有独立的 ProviderModelCache，TTL=1小时
    """

    def __init__(self):
        self._provider_caches: Dict[str, ProviderModelCache] = {}
        self._lr_cache = LRUCache(max_size=500)
        self._lock = __import__("threading").RLock()
        self._default_ttl = MODEL_CACHE_TTL

    def _get_provider_cache(self, provider: str) -> ProviderModelCache:
        if provider not in self._provider_caches:
            self._provider_caches[provider] = ProviderModelCache(provider)
        return self._provider_caches[provider]

    def get_models(self, provider: str) -> Optional[Dict[str, ModelInfo]]:
        return self._get_provider_cache(provider).get_all()

    def get_model(self, provider: str, model_id: str) -> Optional[ModelInfo]:
        cache_key = f"{provider}:{model_id}"
        cached = self._lr_cache.get(cache_key)
        if cached:
            return cached

        provider_cache = self._get_provider_cache(provider)
        model = provider_cache.get(model_id)
        if model:
            self._lr_cache.set(cache_key, model)
            return model

        preset = PRESET_MODELS.get(model_id)
        if preset and preset.provider == provider:
            self._lr_cache.set(cache_key, preset)
            return preset

        return None

    def set_models(self, provider: str, models: Dict[str, ModelInfo]):
        provider_cache = self._get_provider_cache(provider)
        provider_cache.set(models)
        for model_id, model in models.items():
            self._lr_cache.set(f"{provider}:{model_id}", model)

    def set_models_from_raw(self, provider: str, raw_models: List[Dict]):
        provider_cache = self._get_provider_cache(provider)
        provider_cache.set_from_raw(raw_models, self._default_ttl)

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """跨提供商查找模型信息"""
        preset = PRESET_MODELS.get(model_id)
        if preset:
            return preset

        cached = self._lr_cache.get(f"any:{model_id}")
        if cached:
            return cached

        for provider, pc in self._provider_caches.items():
            model = pc.get(model_id)
            if model:
                self._lr_cache.set(f"any:{model_id}", model)
                return model

        return None

    def get_context_window(self, model_id: str) -> int:
        info = self.get_model_info(model_id)
        return info.context_window if info else 128000

    def can_reason(self, model_id: str) -> bool:
        info = self.get_model_info(model_id)
        return info.can_reason if info else False

    def invalidate_provider(self, provider: str):
        if provider in self._provider_caches:
            del self._provider_caches[provider]
        prefix = f"{provider}:"
        keys_to_del = [k for k in self._lr_cache.keys() if k.startswith(prefix)]
        for k in keys_to_del:
            self._lr_cache.delete(k)

    def clear(self):
        self._provider_caches.clear()
        self._lr_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "providers": list(self._provider_caches.keys()),
            "provider_cache_sizes": {
                k: len(v._data) if v._data else 0
                for k, v in self._provider_caches.items()
            },
            "lr_cache_size": self._lr_cache.size,
            "preset_models": len(PRESET_MODELS),
        }

    def save_to_disk(self):
        disk = get_disk_store()
        data = {}
        for provider, pc in self._provider_caches.items():
            if pc.valid and pc._data:
                data[provider] = {
                    "timestamp": pc._timestamp,
                    "models": {k: v.to_dict() for k, v in pc._data.items()},
                }
        disk.model_cache_store.set_batch(data)

    def load_from_disk(self):
        disk = get_disk_store()
        data = disk.model_cache_store.all()
        for provider, cache_data in data.items():
            pc = self._get_provider_cache(provider)
            models = {}
            for model_id, model_dict in cache_data.get("models", {}).items():
                models[model_id] = ModelInfo.from_dict(model_dict)
            pc._data = models
            pc._timestamp = cache_data.get("timestamp", 0)


_model_cache: Optional[ModelCache] = None


def get_model_cache() -> ModelCache:
    global _model_cache
    if _model_cache is None:
        _model_cache = ModelCache()
    return _model_cache