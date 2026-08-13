# 原子：detect_drift（原 interface_chain_extractor.py 第 1074 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def detect_drift(endpoints: list[Endpoint], models: list[RequestModel],
                 client: list[ClientMethod]) -> list[Drift]:
    drifts: list[Drift] = []
    ep_by_path: dict = {}
    for ep in endpoints:
        ep_by_path.setdefault(ep.method + " " + _normalize_path(ep.path), ep)

    model_by_name = {m.name: m for m in models}

    for cm in client:
        if not cm.endpoint:
            continue
        key = cm.http_method + " " + _normalize_path(cm.endpoint)
        ep = ep_by_path.get(key)
        if ep is None:
            # 允许 method 不匹配时再看路径是否存在
            alt = [v for k, v in ep_by_path.items() if k.split(" ", 1)[1] == _normalize_path(cm.endpoint)]
            ep = alt[0] if alt else None
        if ep is None:
            drifts.append(Drift(kind="endpoint_missing", client=cm.name, endpoint=cm.endpoint,
                                detail="前端调用但后端未找到对应端点（注意：可能位于其他路由/构建产物）"))
            continue

        # 比对 payload 键 ↔ 请求模型字段
        if ep.request_model and cm.payload_keys:
            rm = model_by_name.get(ep.request_model.split(".")[-1])
            if rm:
                model_fields = {f.name for f in rm.fields}
                extra = [k for k in cm.payload_keys if k not in model_fields and k not in ("__dummy__",)]
                required_missing = [f.name for f in rm.fields if f.required and f.name not in cm.payload_keys]
                if extra:
                    drifts.append(Drift(kind="extra_payload_key", client=cm.name, endpoint=cm.endpoint,
                                        detail=f"前端多传字段 {extra}，后端模型 {rm.name} 不含"))
                if required_missing:
                    drifts.append(Drift(kind="missing_required", client=cm.name, endpoint=cm.endpoint,
                                        detail=f"前端缺少必填字段 {required_missing}（模型 {rm.name}）"))
    return drifts
