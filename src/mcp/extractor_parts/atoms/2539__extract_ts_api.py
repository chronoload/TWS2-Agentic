# 原子：_extract_ts_api（原 interface_chain_extractor.py 第 2539 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _extract_ts_api(path: Path, endpoints: list) -> None:
    """JS/TS API 端点（Fastify/Express/Hono 风格）：router.get('/path', ...)"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    clean = _strip_comments(text)
    for m in _TS_HTTP_METHODS.finditer(clean):
        method, epath = m.group(1), m.group(2)
        if not epath.startswith("/"):
            continue
        endpoints.append(Endpoint(method=method.upper(), path=epath, func="",
                                  file=path.name,
                                  line=text[:m.start()].count("\n") + 1, doc=""))
