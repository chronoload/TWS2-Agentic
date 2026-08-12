# 原子：scan_env_vars（原 interface_chain_extractor.py 第 2093 行）
# 逻辑组：scan · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def scan_env_vars(root: Path, files: list, exclude: tuple = _SCAN_DEFAULT_EXCLUDE) -> list:
    items = []
    seen = set()
    for f in files:
        fp = Path(f)
        if not fp.is_file():
            continue
        if any(part in exclude for part in fp.parts):
            continue
        rel = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if fp.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(fp))
            except SyntaxError:
                continue
            for item in _py_collect_env_vars(fp, tree, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        elif fp.suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts"):
            for item in _ts_collect_env_vars(fp, text, rel):
                key = (item.file, item.line, item.name)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
    return items
