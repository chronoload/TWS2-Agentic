# 原子：_ts_collect_env_vars（原 interface_chain_extractor.py 第 2083 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _ts_collect_env_vars(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _ENV_VAR_JS_RE.finditer(text):
        name = m.group(1) or m.group(2)
        line = text[:m.start()].count("\n") + 1
        items.append(EnvVarItem(file=rel, line=line, name=name, default="",
                                context="process.env"))
    return items
