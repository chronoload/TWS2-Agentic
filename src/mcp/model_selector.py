"""统一模型选择门面：会话级 > 全局固定 > 路由 fallback。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_RUNTIME: Dict[str, Any] = {
    "mode": "route",
    "default_model": None,
    "catalog": {},
    "session_overrides": {},
}


def _runtime_path() -> Path:
    return Path.home() / ".ts2" / "agent_config" / "model_runtime.json"


class ModelSelector:
    """模型选择门面。resolve() 按 会话级覆盖 > 全局默认固定 > 路由 fallback 取模型。"""

    def __init__(self, runtime_path: Optional[Path] = None):
        self.runtime_path = Path(runtime_path) if runtime_path else _runtime_path()
        self.mode: str = "route"
        self.default_model: Optional[str] = None
        self.catalog: Dict[str, list] = {}
        self.session_overrides: Dict[str, str] = {}
        self._load()

    # ── runtime 持久化 ──
    def _load(self) -> None:
        if not self.runtime_path.exists():
            self.save()
            return
        try:
            data = json.loads(self.runtime_path.read_text(encoding="utf-8"))
            self.mode = data.get("mode", "route")
            self.default_model = data.get("default_model")
            self.catalog = data.get("catalog", {})
            self.session_overrides = data.get("session_overrides", {})
        except Exception as e:
            logger.warning(f"加载 model_runtime.json 失败: {e}")

    def save(self) -> None:
        self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "mode": self.mode,
            "default_model": self.default_model,
            "catalog": self.catalog,
            "session_overrides": self.session_overrides,
        }
        self.runtime_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── mode / default ──
    def get_mode(self) -> str:
        return self.mode

    def set_mode(self, mode: str) -> None:
        if mode not in ("route", "fixed"):
            raise ValueError(f"无效 mode: {mode}")
        self.mode = mode
        self.save()

    def get_default_model(self) -> Optional[str]:
        return self.default_model

    def set_default_model(self, model_key: str) -> None:
        self.default_model = model_key
        self.save()

    # ── session 覆盖 ──
    def get_session_model(self, session_id: str) -> Optional[str]:
        return self.session_overrides.get(session_id)

    def set_session_model(self, session_id: str, model_key: str) -> None:
        self.session_overrides[session_id] = model_key
        self.save()

    def clear_session_model(self, session_id: str) -> None:
        self.session_overrides.pop(session_id, None)
        self.save()

    # ── 三层 resolve ──
    def resolve_key(self, model_key: Optional[str] = None, session_id: Optional[str] = None) -> Optional[str]:
        if model_key:
            return model_key
        if session_id and session_id in self.session_overrides:
            return self.session_overrides[session_id]
        if self.mode == "fixed" and self.default_model:
            return self.default_model
        if self.mode == "fixed":
            raise ValueError("fixed 模式下必须设置 default_model")
        return None  # route 模式 → MultiProviderManager fallback

    def resolve(self, model_key: Optional[str] = None, session_id: Optional[str] = None):
        """返回 LLM provider 客户端；route 模式返回 MultiProviderManager.get_provider()。"""
        key = self.resolve_key(model_key=model_key, session_id=session_id)
        if key:
            return _provider_from_key(key)
        from .config import get_config_manager
        from .llm import MultiProviderManager
        configs = get_config_manager().get_provider_configs_for_manager()
        if not configs:
            return None
        manager = MultiProviderManager(configs)
        return manager.get_provider()

    def chat(self, messages, tools=None, on_token=None, session_id=None):
        """直接聊天：fixed/显式 key 不 fallback；route 走 fallback。"""
        key = self.resolve_key(session_id=session_id)
        if key:
            provider = _provider_from_key(key)
            if not provider:
                return None
            return provider.chat(messages, tools, on_token)
        from .config import get_config_manager
        from .llm import MultiProviderManager
        configs = get_config_manager().get_provider_configs_for_manager()
        manager = MultiProviderManager(configs)
        return manager.chat_with_fallback(messages, tools=tools, on_token=on_token)

    # ── catalog ──
    def refresh_catalog(self, provider_value: Optional[str] = None) -> dict:
        """调用 provider 模型列表接口拉取模型并写回 catalog。返回 {provider_value: {ok, models, error}}。"""
        results: Dict[str, dict] = {}
        configs = [
            cfg for cfg in _get_manager().get_provider_configs_for_manager()
            if getattr(cfg, "enabled", True)
        ]
        if provider_value:
            configs = [cfg for cfg in configs if cfg.provider.value == provider_value]

        grouped: Dict[str, List] = {}
        for cfg in configs:
            grouped.setdefault(cfg.provider.value, []).append(cfg)

        for pv, candidates in grouped.items():
            candidates.sort(key=lambda cfg: (getattr(cfg, "priority", 0), getattr(cfg, "name", "")))
            last_error = None
            for cfg in candidates:
                try:
                    models = _list_provider_models(cfg)
                    entries = []
                    for info in models:
                        entries.append({
                            "model_id": info.name,
                            "context_window": getattr(info, "context_window", 0),
                            "max_tokens": getattr(info, "max_tokens", 0),
                            "is_reasoning": getattr(info, "is_reasoning_model", False),
                            "supports_image": getattr(info, "supports_image_input", False),
                            "supports_video": getattr(info, "supports_video_input", False),
                            "supports_tools": getattr(info, "supports_tools", True),
                            "pricing_input": getattr(info, "pricing_input", 0.0),
                            "pricing_output": getattr(info, "pricing_output", 0.0),
                        })
                    self.catalog[pv] = entries
                    results[pv] = {"ok": True, "count": len(entries), "models": entries}
                    logger.info(f"刷新模型目录 {pv}: {len(entries)} 个模型")
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(f"刷新模型目录 {pv} 失败 ({getattr(cfg, 'name', pv)}): {e}")
            else:
                results[pv] = {"ok": False, "error": str(last_error)}
        self.save()
        return results

    def get_catalog(self) -> List[dict]:
        from .llm import DEFAULT_MODEL_INFOS, PROVIDER_DEFAULT_MODELS
        from .model_catalog import is_local_base_url  # 本地 base_url 无 key 也纳入（对齐 spec v2）

        active_configs = [
            cfg for cfg in _get_manager().get_provider_configs_for_manager()
            if getattr(cfg, "enabled", True) and (
                bool(str(getattr(cfg, "api_key", "")).strip())
                or is_local_base_url(getattr(cfg, "base_url", "") or "")
            )
        ]
        active_providers = {cfg.provider.value for cfg in active_configs}
        merged: Dict[tuple[str, str], dict] = {}
        for cfg in active_configs:
            provider_value = cfg.provider.value
            model_names = list(PROVIDER_DEFAULT_MODELS.get(cfg.provider, []))
            if cfg.model and cfg.model not in model_names:
                model_names.append(cfg.model)
            for model_name in model_names:
                info = DEFAULT_MODEL_INFOS.get(model_name)
                merged[(provider_value, model_name)] = {
                    "model_id": model_name,
                    "context_window": getattr(info, "context_window", 8192),
                    "max_tokens": getattr(info, "max_tokens", 4096),
                    "is_reasoning": getattr(info, "is_reasoning_model", False),
                    "supports_image": getattr(info, "supports_image_input", False),
                    "supports_video": getattr(info, "supports_video_input", False),
                    "supports_tools": getattr(info, "supports_tools", True),
                    "pricing_input": getattr(info, "pricing_input", 0.0),
                    "pricing_output": getattr(info, "pricing_output", 0.0),
                    "provider": provider_value,
                    "source": "builtin",
                }

        for pv, entries in self.catalog.items():
            if pv not in active_providers:
                continue
            for e in entries:
                row = dict(e, provider=pv, source="dynamic")
                merged[(pv, row.get("model_id", ""))] = row
        return [merged[key] for key in sorted(merged)]

    def get_status(self, session_id: Optional[str] = None) -> dict:
        return {
            "mode": self.mode,
            "default_model": self.default_model,
            "session_model": self.session_overrides.get(session_id) if session_id else None,
            "catalog_providers": sorted(self.catalog.keys()),
            "catalog": self.get_catalog(),
        }


def _get_manager():
    from .config import get_config_manager
    return get_config_manager()


def _list_provider_models(config) -> List:
    """同步拉取 provider 的模型列表并返回 ModelInfo 列表（OpenAI 兼容 /v1/models、Ollama /api/tags）。"""
    import urllib.request, urllib.error
    import json as _json

    from .llm import ModelInfo, ProviderType, PROVIDER_DEFAULT_BASE_URL

    base_url = config.base_url or PROVIDER_DEFAULT_BASE_URL.get(config.provider, "")
    if not base_url:
        if config.provider == ProviderType.SIMULATOR:
            return []
        raise ValueError(f"提供商 {config.provider.value} 未配置模型目录 endpoint")
    base_url = base_url.rstrip("/")

    def _do_fetch(url: str, headers: dict = None) -> Optional[dict]:
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return _json.loads(resp.read().decode())
        except Exception:
            return None

    try:
        if config.provider == ProviderType.OLLAMA:
            url = f"{base_url}/api/tags"
            data = _do_fetch(url)
            if data is None:
                raise ConnectionError(f"无法访问 {url}")
            out = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if name:
                    out.append(ModelInfo(name=name, provider=config.provider, context_window=8192, max_tokens=config.max_tokens))
            return out
        if config.provider == ProviderType.OPENROUTER:
            url = "https://openrouter.ai/api/v1/models"
        else:
            url = f"{base_url}/models"
        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        data = _do_fetch(url, headers)
        if data is None:
            raise ConnectionError(f"无法访问 {url}")
        out = []
        for m in data.get("data", []):
            mid = m.get("id") or m.get("name") or ""
            if not mid:
                continue
            ctx = m.get("context_window", 0) or m.get("context_length", 0) or 8192
            out.append(ModelInfo(
                name=mid, provider=config.provider,
                context_window=int(ctx), max_tokens=min(config.max_tokens, int(ctx)),
            ))
        return out
    except Exception as e:
        logger.warning(f"拉取模型列表失败 ({config.provider}): {e}")
        raise


def _provider_from_key(model_key: str):
    """按 'name/model' 或 'provider.value/model' 解析出 provider 配置并构造客户端。"""
    name, _, model = model_key.partition("/")
    if not model:
        return None
    from .config import get_config_manager
    from .llm import ProviderType, LLM, LiteLLM
    configs = [
        cfg for cfg in get_config_manager().get_provider_configs_for_manager()
        if getattr(cfg, "enabled", True)
    ]
    exact_name = [cfg for cfg in configs if cfg.name == name]
    provider_matches = [
        cfg for cfg in configs
        if cfg.provider.value == name and cfg.model == model
    ]
    if not provider_matches:
        provider_matches = [cfg for cfg in configs if cfg.provider.value == name]
    if not provider_matches:
        provider_matches = [cfg for cfg in configs if cfg.model == model]
    candidates = exact_name or provider_matches
    candidates.sort(key=lambda cfg: (getattr(cfg, "priority", 0), cfg.name))
    for cfg in candidates:
        if cfg.provider == ProviderType.SIMULATOR:
            from .llm import SimulatorLLM
            return SimulatorLLM()
        if cfg.provider == ProviderType.LITELLM:
            return LiteLLM(model, cfg.api_key, cfg.base_url)
        llm = LLM(model, cfg.api_key, cfg.base_url,
                  temperature=cfg.temperature, max_tokens=cfg.max_tokens, timeout=cfg.timeout)
        llm.config.provider = cfg.provider
        llm.config.thinking_enabled = cfg.thinking_enabled
        if cfg.provider == ProviderType.MIMO:
            llm._init_client()
        return llm
    logger.warning(f"未找到 provider 配置: {name}")
    return None


_selector: Optional[ModelSelector] = None


def get_model_selector() -> ModelSelector:
    global _selector
    if _selector is None:
        _selector = ModelSelector()
    return _selector
