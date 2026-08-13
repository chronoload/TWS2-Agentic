"""requirement.commands：需求管理的结构化命令（add/list/update/delete/export/scan/align）。

命令函数返回 (code, lines)（与 plan/log/project 同一约定，由 CLI 层打印）。
每次变更自动刷新双轨产物（db 权威 → json/csv/md），语言环境无关。
"""
from __future__ import annotations
from pathlib import Path

from .db import RequirementStore, VALID_KINDS, VALID_STATUS
from . import align as align_mod

# 默认需求文档目录（相对项目根探测，仅取存在的）
DEFAULT_REQ_DIRS = (".opencode/sdd", "openspec", ".superpowers/sdd")
# 默认代码扫描 glob（相对项目根，递归跳过依赖目录；可经 --code 精确指定）
DEFAULT_CODE_GLOBS = ("**/*.py", "**/*.js")


def _check_kind(kind: str) -> str | None:
    if kind not in VALID_KINDS:
        return (f"[requirement] 非法类型 '{kind}'，可选: {', '.join(VALID_KINDS)}")
    return None


def _check_status(status: str) -> str | None:
    if status not in VALID_STATUS:
        return f"[requirement] 非法状态 '{status}'，可选: {', '.join(VALID_STATUS)}"
    return None


def _probe(root: Path, subdirs: tuple) -> list:
    """从项目根探测存在的需求文档目录。"""
    return [root / d for d in subdirs if (root / d).is_dir()]


def _resolve_index(index: str, store: RequirementStore) -> str:
    return index or (str(store.index_json) if store.index_json else "")


def cmd_add(store: RequirementStore, kind: str, name: str,
            detail: str = "", source: str = "cli") -> tuple:
    err = _check_kind(kind)
    if err:
        return 1, [err]
    rid = store.add(kind=kind, name=name, detail=detail, source=source)
    return 0, [f"[requirement] added id={rid} kind={kind} name={name}",
               "  artifacts → REQUIREMENTS.md / requirements.json / requirements.csv / requirements.db"]


def cmd_list(store: RequirementStore, kind: str = "", status: str = "") -> tuple:
    if kind:
        err = _check_kind(kind)
        if err:
            return 1, [err]
    if status:
        err = _check_status(status)
        if err:
            return 1, [err]
    rows = store.list(kind=kind, status=status)
    if not rows:
        return 0, ["[requirement] 无需求条目（先 python -m macdev requirement add）"]
    out = [f"{'id':<4} {'kind':<10} {'status':<8} name / detail",
           "---- ---------- -------- --------------------"]
    for r in rows:
        out.append(f"{r[0]:<4} {r[1]:<10} {r[5]:<8} {r[2]}  — {r[3][:80]}")
    return 0, out


def cmd_update(store: RequirementStore, rid: int, **fields) -> tuple:
    if "kind" in fields and fields["kind"]:
        err = _check_kind(fields["kind"])
        if err:
            return 1, [err]
    if "status" in fields and fields["status"]:
        err = _check_status(fields["status"])
        if err:
            return 1, [err]
    n = store.update(rid, **fields)
    if not n:
        return 1, [f"[requirement] id={rid} 不存在或无可更新字段"]
    return 0, [f"[requirement] updated id={rid} 更新 {n} 行（双轨产物已同步）"]


def cmd_delete(store: RequirementStore, rid: int) -> tuple:
    n = store.delete(rid)
    if not n:
        return 1, [f"[requirement] id={rid} 不存在"]
    return 0, [f"[requirement] deleted id={rid}（双轨产物已同步）"]


def cmd_export(store: RequirementStore, fmt: str = "md") -> tuple:
    if fmt == "all":
        artifacts = store.refresh()
        return 0, ["[requirement] 双轨产物已同步", *[f"  → {p}" for p in artifacts]]
    # 单格式导出：缺省全量刷新（任何单一导出都不会让四件套失配）
    store.refresh()
    if fmt == "md":
        return 0, [f"[requirement] exported → {store.out_dir / 'REQUIREMENTS.md'}"]
    if fmt == "json":
        return 0, [f"[requirement] exported → {store.out_dir / 'requirements.json'}"]
    if fmt == "csv":
        return 0, [f"[requirement] exported → {store.out_dir / 'requirements.csv'}"]
    return 1, [f"[requirement] 非法格式 '{fmt}'，可选: md/json/csv/all"]


def cmd_align(store: RequirementStore, index: str = "", root: str = "",
              exclude: str = "") -> tuple:
    """结构化 DB 需求 → 代码/端点对齐，回写 missing 状态，落盘对齐四件套。"""
    items = store.all_items()
    if not items:
        return 1, ["[requirement] 需求库为空（先 add）"]
    # 默认代码根 = 项目根（cwd）；产物目录是输出地，不是代码所在处
    root_path = Path(root) if root else Path.cwd()
    idx = _resolve_index(index, store)
    endpoints = align_mod.load_endpoints(idx)
    ex = tuple(e.strip() for e in exclude.split(",") if e.strip())
    code_index = align_mod.build_code_index(root_path, list(DEFAULT_CODE_GLOBS), exclude=ex)
    res = align_mod.align(items, code_index, endpoints)

    # 回写未找到 → missing（不覆盖人工标定的 done）
    conn = store.connect()
    cur = conn.cursor()
    for a in res["alignment"]:
        if not a["found"] and a.get("req_id"):
            cur.execute("UPDATE requirements SET status='missing' "
                        "WHERE id=? AND status!='done'", (a["req_id"],))
    conn.commit()
    conn.close()
    store.refresh()  # 状态回写后同步双轨

    artifacts = store.write_alignment(res, [store.db])
    lines = [f"[requirement] align 需求={len(res['alignment'])} 未找到={len(res['not_found'])} "
             f"端点缺失={len(res['missing_paths'])} 前缀={len(res['prefix_matches'])}"]
    for a in res["not_found"][:10]:
        lines.append(f"  ⚠ [not_found] {a['kind']} `{a['name']}` @ {a['source']}:{a['line']}")
    for p in res["missing_paths"][:10]:
        lines.append(f"  ⚠ [missing] {p}")
    lines.append("  artifacts → " + " / ".join(str(p) for p in artifacts))
    return 0, lines


def cmd_scan(store: RequirementStore, req_dirs: str = "", root: str = "",
             code: str = "", index: str = "", exclude: str = "") -> tuple:
    """扫描需求文档目录，提取声明并做对齐（对应原 requirement_align 主流程）。"""
    # 默认根 = 项目根（cwd）：需求文档与代码都在项目根下，产物落在 out_dir
    root_path = Path(root) if root else Path.cwd()
    dirs = [Path(d) for d in req_dirs.split(",") if d] if req_dirs \
        else _probe(root_path, DEFAULT_REQ_DIRS)
    if not dirs:
        return 1, ["[requirement] 未找到需求文档目录（--req-dirs 指定，或在项目下建 .opencode/sdd 等）"]
    globs = [g for g in code.split(",") if g] if code else list(DEFAULT_CODE_GLOBS)
    idx = _resolve_index(index, store)
    endpoints = align_mod.load_endpoints(idx)
    items = align_mod.scan_dirs(dirs, root_path)
    ex = tuple(e.strip() for e in exclude.split(",") if e.strip())
    code_index = align_mod.build_code_index(root_path, globs, exclude=ex)
    res = align_mod.align(items, code_index, endpoints)

    artifacts = store.write_alignment(res, dirs)
    lines = [f"[requirement] scan 声明={len(res['alignment'])} 未找到={len(res['not_found'])} "
             f"端点缺失={len(res['missing_paths'])} 实现未声明={len(res['extra_paths'])}"]
    for a in res["not_found"][:10]:
        lines.append(f"  ⚠ [not_found] {a['kind']} `{a['name']}` @ {a['source']}:{a['line']}")
    for p in res["missing_paths"][:10]:
        lines.append(f"  ⚠ [missing] {p}")
    lines.append("  artifacts → " + " / ".join(str(p) for p in artifacts))
    return 0, lines
