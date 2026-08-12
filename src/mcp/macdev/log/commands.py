"""log.commands：经验沉淀的结构化 CRUD（add/list/get/query/export/update/delete）。

命令函数返回 (code, lines)，由 CLI 层打印（与 plan 同一约定）。
"""
from __future__ import annotations

from .db import LogStore, CATEGORIES, CATEGORY_LABELS, SCOPES, SCOPE_LABELS


def _unescape(s: str) -> str:
    """把 shell 传入的字面 \\n / \\t 转成真实换行/制表。"""
    if not s:
        return s
    return s.replace("\\n", "\n").replace("\\t", "\t")


def _check_category(category: str) -> str | None:
    if category not in CATEGORIES:
        return (f"[log] 非法分类 '{category}'，可选: {', '.join(CATEGORIES)}"
                f"（{', '.join(CATEGORY_LABELS.values())}）")
    return None


def _check_scope(scope: str) -> str | None:
    if scope and scope not in SCOPES:
        return (f"[log] 非法 scope '{scope}'，可选: {', '.join(SCOPES)}"
                f"（{'/'.join(SCOPE_LABELS.values())}）")
    return None


def cmd_add(store: LogStore, title: str, category: str,
            body: str = "", tags: str = "", refs: str = "",
            file: str = "", scope: str = "project") -> tuple:
    err = _check_category(category)
    if err:
        return 1, [err]
    err = _check_scope(scope)
    if err:
        return 1, [err]
    if file:
        from pathlib import Path
        p = Path(file)
        if not p.exists():
            return 1, [f"[log] 文件不存在: {p}"]
        body = p.read_text(encoding="utf-8")
    body = _unescape(body)
    lid = store.add(category=category, title=title, body=body,
                    tags=tags, refs=refs, scope=scope)
    return 0, [f"[log] added id={lid} [{category}] {title} "
               f"（{SCOPE_LABELS.get(scope, scope)}经验）"]


def cmd_list(store: LogStore, category: str = "", tag: str = "",
             scope: str = "") -> tuple:
    if category:
        err = _check_category(category)
        if err:
            return 1, [err]
    err = _check_scope(scope)
    if err:
        return 1, [err]
    entries = store.list(category=category, tag=tag, scope=scope)
    if not entries:
        return 0, ["[log] 无记录（先 python -m macdev log add）"]
    out = [f"| id | 分类 | 归属 | 标题 | 标签 | 时间 |",
           "|----|------|------|------|------|------|"]
    for e in entries:
        out.append(f"| {e['id']} | {e['category']} | {SCOPE_LABELS.get(e['scope'], e['scope'])} | "
                   f"{e['title']} | {e['tags'] or '—'} | {e['created_at']} |")
    return 0, out


def cmd_get(store: LogStore, lid: int) -> tuple:
    e = store.get(lid)
    if not e:
        return 1, [f"[log] id={lid} 不存在"]
    out = [
        f"[{e['id']}] {e['title']}",
        f"分类: {e['category']}（{CATEGORY_LABELS.get(e['category'], '')}）"
        f" ｜ 归属: {SCOPE_LABELS.get(e['scope'], e['scope'])}经验"
        f" ｜ 标签: {e['tags'] or '—'} ｜ 时间: {e['created_at']}",
    ]
    if e["refs"]:
        out.append(f"引用: {e['refs']}")
    out.append("")
    out.append(e["body"] or "（无正文）")
    return 0, out


def cmd_query(store: LogStore, keyword: str, category: str = "",
              scope: str = "") -> tuple:
    if category:
        err = _check_category(category)
        if err:
            return 1, [err]
    err = _check_scope(scope)
    if err:
        return 1, [err]
    entries = store.query(keyword, category=category, scope=scope)
    if not entries:
        return 0, [f"[log] 无匹配 '{keyword}' 的记录"]
    out = [f"[log] 匹配 '{keyword}'：{len(entries)} 条", ""]
    for e in entries:
        out.append(f"### [{e['id']}] [{e['category']}] {e['title']}"
                   f"（{SCOPE_LABELS.get(e['scope'], e['scope'])}）— {e['created_at']}")
        if e["tags"]:
            out.append(f"标签: {e['tags']}")
        if e["body"]:
            first_line = e["body"].splitlines()[0] if e["body"].splitlines() else ""
            out.append(first_line[:120])
        out.append("")
    return 0, out


def cmd_export(store: LogStore, out: str = "", scope: str = "") -> tuple:
    err = _check_scope(scope)
    if err:
        return 1, [err]
    from pathlib import Path
    target = Path(out) if out else store.db.parent / "LOGS.md"
    path = store.export_md(target, scope=scope)
    return 0, [f"[log] exported → {path}"]


def cmd_delete(store: LogStore, lid: int) -> tuple:
    if store.delete(lid):
        return 0, [f"[log] deleted id={lid}"]
    return 1, [f"[log] id={lid} 不存在"]


def cmd_update(store: LogStore, lid: int, **fields) -> tuple:
    if "category" in fields and fields["category"]:
        err = _check_category(fields["category"])
        if err:
            return 1, [err]
    if "scope" in fields and fields["scope"]:
        err = _check_scope(fields["scope"])
        if err:
            return 1, [err]
    if "body" in fields and fields["body"]:
        fields["body"] = _unescape(fields["body"])
    if store.update(lid, **fields):
        return 0, [f"[log] updated id={lid}"]
    return 1, [f"[log] id={lid} 不存在或无可更新字段"]
