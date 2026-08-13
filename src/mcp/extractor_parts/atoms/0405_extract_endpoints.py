# 原子：extract_endpoints（原 interface_chain_extractor.py 第 405 行）
# 逻辑组：parse · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def extract_endpoints(path: Path, decorator_names: tuple, endpoints: list, prefix: str = "",
                      loose: bool = False):
    """提取 FastAPI/APIRouter 端点。decorator_names: ('app.get', 'app.post', ...)
    prefix: 路由前缀（如 saber 的 '/api/saber'）
    loose=True：通用模式——decorator_names 传 HTTP 方法名（'get','post',…），
    只要装饰器是 `X.<method>('path')`（X 为任意对象）即提取，不限 app/router 变量名。"""
    if not path.exists():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if loose:
                    matched = dec.func.attr in decorator_names
                else:
                    qual = f"{dec.func.value.id}.{dec.func.attr}" if isinstance(dec.func.value, ast.Name) else ""
                    matched = qual in decorator_names
                if matched and dec.args:
                    path_expr = dec.args[0]
                    if isinstance(path_expr, ast.Constant) and isinstance(path_expr.value, str):
                        ep = Endpoint(
                            method=dec.func.attr.upper(),
                            path=prefix + path_expr.value,
                            func=node.name,
                            file=path.name,
                            line=dec.lineno,
                            doc=_get_doc(node.body),
                            response_keys=_collect_response_keys(node),
                        )
                        # 函数参数（跳过 self/cls/request）
                        for a in node.args.args:
                            if a.arg in ("self", "cls"):
                                continue
                            ep.params.append(a.arg)
                        # 请求模型：从类型注解中找 *Request
                        for a in node.args.args:
                            if a.annotation:
                                ann = _unparse(a.annotation)
                                if ann.endswith("Request") or "BaseModel" in ann:
                                    ep.request_model = ann
                        endpoints.append(ep)
