# 原子：_reflect_regex_patterns（原 interface_chain_extractor.py 第 3981 行）
# 逻辑组：doc_reflect · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _reflect_regex_patterns() -> list:
    """反射提取扫描相关的全局正则模式变量。"""
    import inspect as _inspect
    patterns = []
    module = sys.modules[__name__]
    regex_vars = [
        "_HARDCODE_KEYWORDS", "_HARDCODE_URL_RE", "_HARDCODE_PORT_RE", "_HARDCODE_PATH_RE",
        "_ENV_VAR_JS_RE", "_STATIC_FILE_RE", "_IO_PATH_RE", "_PATH_LITERAL_RE",
    ]
    for name in regex_vars:
        val = getattr(module, name, None)
        if isinstance(val, re.Pattern):
            patterns.append((name, val.pattern))
    return patterns
