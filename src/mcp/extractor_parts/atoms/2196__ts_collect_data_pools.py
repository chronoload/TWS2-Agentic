# 原子：_ts_collect_data_pools（原 interface_chain_extractor.py 第 2196 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _ts_collect_data_pools(file: Path, text: str, rel: str) -> list:
    items = []
    for pat_name, pat in [
        ("cache", re.compile(r'(?:const|let|var)\s+(\w*[Cc]ache\w*)\s*=')),
        ("pool", re.compile(r'(?:const|let|var)\s+(\w*[Pp]ool\w*)\s*=')),
        ("store", re.compile(r'(?:const|let|var)\s+(\w*[Ss]tore\w*)\s*=')),
        ("agent_pool", re.compile(r'(?:const|let|var)\s+(\w*[Aa]gent[Pp]ool\w*)\s*=')),
        ("model_cache", re.compile(r'(?:const|let|var)\s+(\w*[Mm]odel[Cc]ache\w*)\s*=')),
        ("vector_store", re.compile(r'(?:const|let|var)\s+(\w*[Vv]ector[Ss]tore\w*)\s*=')),
        ("singleton", re.compile(r'(?:const|let|var)\s+(\w*[Ss]ingleton\w*)\s*=')),
    ]:
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            items.append(DataPoolItem(file=rel, line=line, name=m.group(1),
                                      kind=pat_name, size_hint="",
                                      context="variable_init"))
    return items
