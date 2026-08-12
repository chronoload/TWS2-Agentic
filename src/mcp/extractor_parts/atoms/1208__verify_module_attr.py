# 原子：_verify_module_attr（原 interface_chain_extractor.py 第 1208 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _verify_module_attr(obj: str, attr: str) -> str:
    """尝试用运行时反射验证「模块级属性」是否真实存在。

    返回可展示的核查结论：
      - 模块可导入且属性存在      → 库内定义，正常
      - 模块可导入但属性不存在    → 疑似库 API 变更 / 运行时注入，需人工确认
      - 模块不可导入（非模块名）  → 对象类型未知（SDK 返回对象等），无法静态验证
    """
    try:
        mod = importlib.import_module(obj)
    except Exception:
        # 可能是带包名的模块（如 aiohttp.ClientResponse），逐级尝试
        for depth in range(max(1, obj.count(".")), -1, -1):
            head = ".".join(obj.split(".")[:depth])
            try:
                mod = importlib.import_module(head)
                break
            except Exception:
                mod = None
        if mod is None:
            return f"对象 `{obj}` 非可导入模块名（疑似 SDK 返回对象/动态实例），无法静态验证，需人工核对是否存在该参数"
    if hasattr(mod, attr):
        return f"模块 `{obj}` 中确实存在属性 `{attr}`（库内定义，正常）"
    return f"模块 `{obj}` 中不存在属性 `{attr}` —— 疑似库 API 变更或运行时注入（如 sys.frozen 由打包器注入），需人工确认"
