"""patch.apply：应用自演化补丁脚本（备份 + 幂等 + 按行号倒序写入避免错位）。"""
from __future__ import annotations
from pathlib import Path
from .model import load_patch


def apply_patch(patch_file: Path | str, root: Path, backup: bool = True) -> tuple:
    """应用单个补丁 → (ok, message, applied_ops)。"""
    p = load_patch(patch_file)
    target = root / p.file
    if not target.exists():
        return False, f"[patch] 目标文件不存在: {p.file}", 0
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 备份
    if backup:
        bak = target.with_suffix(target.suffix + ".bak.macdev")
        if not bak.exists():
            bak.write_text(text, encoding="utf-8")

    # 按行号倒序应用（insert/replace 避免行号错位）
    ops = sorted(p.operations, key=lambda o: int(o.get("line", 0)), reverse=True)
    applied = 0
    for op in ops:
        ln = int(op.get("line", 0))
        if op["op"] == "insert":
            if 1 <= ln <= len(lines) + 1:
                lines.insert(ln - 1, op["text"])
                applied += 1
        elif op["op"] == "replace":
            if 1 <= ln <= len(lines):
                # 幂等：已含 TODO(macdev) 不重复
                if "TODO(macdev)" not in lines[ln - 1]:
                    lines[ln - 1] = op["text"]
                    applied += 1
        # noop：跳过（仅标注元数据）

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, f"[patch] applied {applied} ops → {p.file}", applied


def apply_patches(patch_files: list, root: Path, backup: bool = True) -> tuple:
    """批量应用补丁 → (ok, [messages])"""
    ok_all = True
    messages = []
    for f in patch_files:
        ok, msg, _ = apply_patch(f, root, backup)
        messages.append(msg)
        ok_all = ok_all and ok
    return ok_all, messages
