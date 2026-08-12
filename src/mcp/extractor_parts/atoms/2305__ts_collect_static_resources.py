# 原子：_ts_collect_static_resources（原 interface_chain_extractor.py 第 2305 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _ts_collect_static_resources(file: Path, text: str, rel: str) -> list:
    items = []
    for m in _STATIC_FILE_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(StaticResourceItem(file=rel, line=line, path=m.group(0)[:120],
                                        kind="express_static", context="static_mount"))
    for m in _IO_PATH_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        items.append(StaticResourceItem(file=rel, line=line, path=m.group(1)[:120],
                                        kind="io_path", context="file_read_write"))
    for m in _PATH_LITERAL_RE.finditer(text):
        path = m.group(1)
        line = text[:m.start()].count("\n") + 1
        ext = Path(path).suffix.lower().lstrip(".")
        kind_map = {"html": "template", "htm": "template", "jinja2": "template", "jinja": "template",
                    "css": "css", "js": "js", "png": "image", "jpg": "image",
                    "jpeg": "image", "gif": "image", "svg": "image", "ico": "image",
                    "woff": "font", "woff2": "font", "ttf": "font", "eot": "font"}
        kind = kind_map.get(ext, "other")
        items.append(StaticResourceItem(file=rel, line=line, path=path[:120],
                                        kind=kind, context="path_literal"))
    return items
