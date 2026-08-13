"""opencode 配置单向导入：auth.json + opencode.json → TS2 providers.json。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# opencode provider id → TS2 ProviderType.value
PROVIDER_ID_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "google": "gemini",
    "gemini": "gemini",
    "ollama": "ollama",
    "groq": "groq",
    "mistral": "mistral",
    "azure": "custom",
    "mimo": "mimo",
    "custom": "custom",
}


def _opencode_dir() -> Optional[Path]:
    cfg = Path.home() / ".config" / "opencode"
    if cfg.exists():
        return cfg
    xdg = Path.home() / ".config" / "opencode"
    return xdg if xdg.exists() else None


def discover_opencode_config() -> Dict[str, Any]:
    d = _opencode_dir()
    if not d:
        return {"found": False, "auth_path": None, "config_path": None, "dir": None}
    auth_path = d / "auth.json"
    cfg_path = d / "opencode.json"
    return {
        "found": auth_path.exists() or cfg_path.exists(),
        "auth_path": str(auth_path) if auth_path.exists() else None,
        "config_path": str(cfg_path) if cfg_path.exists() else None,
        "dir": str(d),
    }


def parse_opencode_auth(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取 auth.json 失败: {e}")
        return {}
    out: Dict[str, Any] = {}
    for pid, entry in data.items():
        if isinstance(entry, dict) and entry.get("type") == "api" and entry.get("key"):
            out[pid] = {"type": "api", "key": entry["key"]}
    return out


def import_opencode_config() -> Dict[str, Any]:
    """将 opencode auth.json（+ opencode.json 的 baseURL/model）导入 TS2 providers.json。"""
    from .config import get_config_manager
    from .llm import ProviderConfig, ProviderType

    discovered = discover_opencode_config()
    if not discovered["found"]:
        return {"imported": 0, "skipped": 0, "providers": [], "error": "未找到 opencode 配置目录"}

    manager = get_config_manager()

    # opencode.json: baseURL / models 补充信息
    json_info: Dict[str, Dict[str, Any]] = {}
    if discovered["config_path"]:
        try:
            cfg_data = json.loads(Path(discovered["config_path"]).read_text(encoding="utf-8"))
            for pid, block in (cfg_data.get("provider") or {}).items():
                opts = block.get("options") or {}
                models = list((block.get("models") or {}).keys())
                json_info[pid] = {"base_url": opts.get("baseURL"), "models": models}
        except Exception as e:
            logger.warning(f"解析 opencode.json 失败: {e}")

    auth = parse_opencode_auth(Path(discovered["auth_path"])) if discovered["auth_path"] else {}

    imported, skipped, names = 0, 0, []
    for pid, entry in auth.items():
        ts2_provider = PROVIDER_ID_MAP.get(pid, "custom")
        model = (json_info.get(pid, {}).get("models") or ["gpt-4o-mini"])[0]
        base_url = json_info.get(pid, {}).get("base_url")
        existing_names = {c.name for c in manager.provider_configs}
        base_name = f"opencode-{pid}"
        name = base_name
        n = 2
        while name in existing_names:
            name = f"{base_name}-{n}"
            n += 1
        try:
            cfg = ProviderConfig(
                provider=ProviderType(ts2_provider),
                api_key=entry["key"],
                base_url=base_url,
                model=model,
                enabled=True,
                priority=len(manager.provider_configs),
                name=name,
            )
            manager.add_provider_config(cfg)
            imported += 1
            names.append(name)
        except Exception as e:
            skipped += 1
            logger.warning(f"导入 {pid} 失败: {e}")

    logger.info(f"opencode 导入完成: 新增 {imported} 个 provider, 跳过 {skipped}")
    return {"imported": imported, "skipped": skipped, "providers": names}
