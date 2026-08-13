# 原子：extract_client_methods（原 interface_chain_extractor.py 第 512 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_client_methods(js_path: Path) -> list[ClientMethod]:
    if not js_path.exists():
        return []
    text = js_path.read_text(encoding="utf-8")
    methods = []
    # 在 TS2Client class 内部（从 'class TS2Client' 到文件尾 / 下一个顶级 class）
    cls_match = re.search(r"class TS2Client\b", text)
    if not cls_match:
        return []
    cls_start = cls_match.end()
    # 找到类体的结束位置（粗略：下一个行首非缩进的 class/const/function）
    tail = text[cls_start:]
    end_match = re.search(r"\n(?=[A-Za-z_$][\w$]*\s*\()", tail)
    body = tail[: end_match.start()] if end_match else tail

    for m in re.finditer(r"\b(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{", body):
        name, raw_params = m.group(1), m.group(2)
        if name in ("constructor",):
            continue
        # 找方法体内的第一个 API 端点引用
        method_body_start = m.end()
        # 截取到下一个相同缩进的方法（简化：取 400 字符内）
        seg = body[method_body_start: method_body_start + 600]
        ep_match = re.search(r"['\"](/api/[^'\"\s]+)['\"]", seg)
        endpoint = ep_match.group(1) if ep_match else ""
        http_method = "POST"
        if re.search(r"\b(?:fetch|api_get)\(.*['\"]GET['\"]", seg) or (ep_match and re.match(r"GET", seg)):
            http_method = "GET"
        if "api_get(" in seg and ep_match and ep_match.start() < seg.find("api_get(") + 10:
            http_method = "GET"
        # 提取 payload 键：this.api('path', {...}) 里的对象字面量键
        payload_keys = []
        payload_m = re.search(r"this\.api\(\s*['\"][^'\"]+['\"]\s*,\s*\{([^}]*)\}", seg)
        if payload_m:
            payload_keys = re.findall(r"([A-Za-z_$][\w$]*)\s*:", payload_m.group(1))
        methods.append(ClientMethod(
            name=name,
            line=text[:cls_start].count("\n") + body[:m.start()].count("\n") + 2,
            endpoint=endpoint,
            http_method=http_method,
            payload_keys=payload_keys,
        ))
    return methods
