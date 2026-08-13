"""通用原子化拆分：任意 Python 源文件 → 每顶层 def/class 一个原子文件 + core.py。
用法：python macdev/scripts/split_atoms.py <src.py> <out_dir>
"""
from __future__ import annotations
import ast, json, re, sys
from pathlib import Path

HEADER = """# 原子：{name}（原 {src} 第 {line} 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations
"""
CORE_HEADER = """# 原子 core：顶层常量/import/模块头（原 {src}）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations
"""

def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", name) or "anon"

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: split_atoms.py <src.py> <out_dir>"); return 1
    src = Path(sys.argv[1]); out = Path(sys.argv[2])
    if not src.exists():
        print(f"[split] 源不存在: {src}"); return 1
    text = src.read_text(encoding="utf-8")
    tree = ast.parse(text)
    out.mkdir(parents=True, exist_ok=True)
    index, core_blocks, count = [], [], 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seg = ast.get_source_segment(text, node) or ""
            fname = f"{node.lineno:04d}_{_safe(node.name)}.py"
            (out / fname).write_text(
                HEADER.format(name=node.name, src=src.name, line=node.lineno) + "\n" + seg + "\n",
                encoding="utf-8")
            count += 1
            index.append({"name": node.name, "line": node.lineno, "file": fname})
        else:
            core_blocks.append(ast.get_source_segment(text, node) or "")
    (out / "core.py").write_text(CORE_HEADER.format(src=src.name) + "\n\n".join(core_blocks) + "\n",
                                 encoding="utf-8")
    (out / "index.json").write_text(json.dumps({"source": str(src), "atoms": index},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[split] {count} atoms + core.py → {out}"); return 0

if __name__ == "__main__":
    sys.exit(main())
