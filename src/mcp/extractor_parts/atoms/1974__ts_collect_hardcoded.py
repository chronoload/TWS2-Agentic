# 原子：_ts_collect_hardcoded（原 interface_chain_extractor.py 第 1974 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _ts_collect_hardcoded(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _HARDCODE_URL_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(HardcodedItem(file=rel, line=line, kind="url",
                                   value=m.group(0)[:120], context="url_literal"))
    for m in _HARDCODE_PORT_RE.finditer(text):
        port = m.group(1)
        line = text[:m.start()].count("\n") + 1
        items.append(HardcodedItem(file=rel, line=line, kind="port",
                                   value=port, context="port_literal"))
    for m in _HARDCODE_PATH_RE.finditer(text):
        p = m.group(1)
        line = text[:m.start()].count("\n") + 1
        if len(p) > 3:
            items.append(HardcodedItem(file=rel, line=line, kind="path",
                                       value=p[:120], context="path_literal"))
    for kw in _HARDCODE_KEYWORDS.finditer(text):
        line = text[:kw.start()].count("\n") + 1
        val_match = re.search(rf'{kw.group(0)}["\']?\s*[:=]\s*["\']([^"\']{{4,}})["\']', text[kw.start():kw.start()+100])
        if val_match:
            items.append(HardcodedItem(file=rel, line=line, kind="secret",
                                       value=val_match.group(1)[:120], context=kw.group(0)))
        else:
            items.append(HardcodedItem(file=rel, line=line, kind="key",
                                       value=kw.group(0), context="keyword_literal"))
    return items
