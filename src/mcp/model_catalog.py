"""模型目录动态化：每日 /v1/models 查询 + base_url 归组 + TTL 缓存（spec id=11）。

设计（langdriven 函数管道 + TTL 缓存门面）：
- query_models(base_url, api_key)    纯函数：GET {base_url}/models → List[str]（模型 id）
- group_by_base_url(configs)         纯函数：按 catalog_base_url 去重归组，同 base_url 只查一次
- ModelCatalogService                TTL 缓存门面：get_or_query(base_url, api_key) 命中缓存即返回，
                                     过期/未缓存则查询并刷新（后台任务由 app 层驱动）

凭据规则（spec v2）：本地 base_url（localhost/127.0.0.1/局域网）无 api_key 也查询；
远程 base_url 无 key → 跳过（由调用方 group 过滤决定）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── 本地地址判定：本地服务 /v1/models 无需认证 ────────────────────
def is_local_base_url(base_url: str) -> bool:
    """判定 base_url 是否指向本机/局域网（无 key 也可查询）。"""
    if not base_url:
        return False
    lowered = base_url.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered or "0.0.0.0" in lowered:
        return True
    # 局域网私有网段（10.x / 172.16-31.x / 192.168.x）
    import re
    m = re.search(r"//([^/:]+)", lowered)
    if not m:
        return False
    host = m.group(1)
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    return False


# ── 纯函数 1：查询 /v1/models ─────────────────────────────────────
# Cloudflare 等 CDN 会按 UA 拦截 Python-urllib 默认签名（Error 1010）——
# 用浏览器兼容 UA 让 opencode.ai 等站点放行。
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def query_models(base_url: str, api_key: Optional[str] = None,
                 timeout: float = 10.0, return_error: bool = False,
                 with_meta: bool = False):
    """GET {base_url}/models 解析 data[].id → 模型 id 列表。

    base_url 允许带 /v1 或裸地址，统一拼接 rstrip('/') + '/models'。
    本地无 key 直连；远程无 key 由调用方提前过滤（这里仍可调但通常不触发）。
    return_error=True 时返回 (models, error_msg)；False 时仅返回 models（兼容旧调用）。
    with_meta=True 时额外返回 {model_id: {context_window, max_tokens}}（能力真实化，供回填）。
    失败不再静默：error 记录 HTTP 状态/网络原因，供调用方写 CacheEntry.error。
    """
    if not base_url:
        if with_meta:
            return ([] if not return_error else ([], {}, "base_url 为空"))
        return ([] if not return_error else ([], "base_url 为空"))
    url = base_url.rstrip("/")
    if not url.endswith("/models"):
        url += "/models"
    req = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": _BROWSER_UA,
    })
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    error_msg = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_msg = f"HTTP {e.code}"
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
            if body:
                error_msg += f": {body}"
        except Exception:
            pass
        logger.warning(f"query_models HTTP 失败 {url}: {error_msg}")
        if with_meta:
            return ([] if not return_error else ([], {}, error_msg))
        return ([] if not return_error else ([], error_msg))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.warning(f"query_models 失败 {url}: {error_msg}")
        if with_meta:
            return ([] if not return_error else ([], {}, error_msg))
        return ([] if not return_error else ([], error_msg))
    models = []
    meta: Dict[str, Dict[str, Any]] = {}
    for item in data.get("data") or []:
        mid = item.get("id") if isinstance(item, dict) else None
        if mid:
            mid = str(mid)
            models.append(mid)
            try:
                ctx = int(item.get("context_window") or item.get("context_length") or 8192)
            except (TypeError, ValueError):
                ctx = 8192
            meta[mid] = {"context_window": ctx, "max_tokens": ctx}
    if return_error:
        return (models, meta, "") if with_meta else (models, "")
    return (models, meta) if with_meta else models


# ── 纯函数 2：按 base_url 归组 ────────────────────────────────────
def group_by_base_url(configs: List[Any]) -> List[Dict[str, Any]]:
    """按 catalog_base_url（默认=base_url）去重归组。

    每组取第一个非空 api_key（同 base_url 的多配置共享一次查询）；
    远程 base_url 无 key → 跳过；本地 base_url 无 key → 保留（include_keyless）。
    返回 [{"base_url", "api_key", "names": [配置名...]}]。
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for c in configs:
        if not getattr(c, "enabled", True):
            continue
        base_url = getattr(c, "catalog_base_url", None) or getattr(c, "base_url", None)
        if not base_url:
            continue
        api_key = getattr(c, "api_key", None) or None
        if not api_key and not is_local_base_url(base_url):
            continue  # 远程无 key → 跳过（避免无凭据请求失败）
        g = groups.setdefault(base_url, {"base_url": base_url, "api_key": None, "names": []})
        if api_key and not g["api_key"]:
            g["api_key"] = api_key
        g["names"].append(getattr(c, "name", base_url))
    return list(groups.values())


# ── TTL 缓存门面 ──────────────────────────────────────────────────
@dataclass
class CatalogEntry:
    base_url: str
    models: List[str]
    fetched_at: float
    error: Optional[str] = None
    capabilities: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class ModelCatalogService:
    """模型目录缓存门面。ensure_refresh() 由 app 启动后台任务驱动。

    TTL 过期 → 重查；查询失败 → 保留旧缓存（降级不阻塞），无缓存则返回 []。
    """

    def __init__(self, ttl_seconds: float = 86400, timeout_seconds: float = 10.0,
                 max_concurrent: int = 4):
        self._entries: Dict[str, CatalogEntry] = {}
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._max_concurrent = max_concurrent
        self._lock = threading.RLock()

    # -- 设置（app/UI 可调）--
    def set_ttl(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds

    def set_timeout(self, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds

    def get_ttl(self) -> float:
        return self._ttl

    # -- 核心 --
    def get_or_query(self, base_url: str, api_key: Optional[str] = None,
                     force: bool = False) -> List[str]:
        """取模型列表：缓存命中（未过期）直接返回；否则查询并写缓存。

        查询失败（query_models 返回 error）→ 保留旧缓存（降级不阻塞），
        无旧缓存则写入 error 标记的空条目，供前端展示失败原因。
        """
        now = time.time()
        with self._lock:
            entry = self._entries.get(base_url)
            if entry and not force and (now - entry.fetched_at) < self._ttl:
                return list(entry.models)
        # 过期/无缓存 → 查询（锁外，避免长时间阻塞其他 base_url）
        models, meta, error_msg = query_models(base_url, api_key, timeout=self._timeout,
                                               return_error=True, with_meta=True)
        with self._lock:
            old = self._entries.get(base_url)
            if error_msg:
                # 失败：保留旧缓存（若有），仅更新 error 与失败时间戳
                if old:
                    old.error = error_msg
                    old.fetched_at = time.time()  # 记录失败时刻，避免频繁重试风暴
                    return list(old.models)
                self._entries[base_url] = CatalogEntry(
                    base_url=base_url, models=[], fetched_at=time.time(),
                    error=error_msg, capabilities=meta)
                return []
            self._entries[base_url] = CatalogEntry(
                base_url=base_url, models=models, fetched_at=time.time(),
                error=None, capabilities=meta)
        return models

    def refresh_all(self, groups: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """按归组刷新全部（app 启动后台任务调用）。返回 base_url → models。"""
        result: Dict[str, List[str]] = {}
        for g in groups:
            models = self.get_or_query(g["base_url"], g.get("api_key"), force=True)
            result[g["base_url"]] = models
            logger.info(f"[model_catalog] {g['base_url']} → {len(models)} 模型")
        return result

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """导出缓存快照（供 GET /api/models / model_runtime.json 持久化）。"""
        with self._lock:
            return {
                url: {
                    "models": list(e.models),
                    "fetched_at": e.fetched_at,
                    "error": e.error,
                    "capabilities": dict(e.capabilities),
                }
                for url, e in self._entries.items()
            }

    def load_snapshot(self, snap: Dict[str, Dict[str, Any]]) -> None:
        """从持久化快照恢复（启动时避免首次无缓存）。"""
        with self._lock:
            for url, e in (snap or {}).items():
                self._entries[url] = CatalogEntry(
                    base_url=url, models=list(e.get("models") or []),
                    fetched_at=e.get("fetched_at", 0.0), error=e.get("error"),
                    capabilities=e.get("capabilities") or {})
