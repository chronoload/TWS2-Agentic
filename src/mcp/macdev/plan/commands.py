"""plan.commands：Plan 数据结构化 CRUD（create/list/update/delete/task/step）。
从 plan_cli 原子重组；命令函数返回输出行列表（list[str]），由 CLI 层打印。
"""
from __future__ import annotations
from .db import PlanStore


def _status_icon(status: str) -> str:
    return {"done": "✅", "open": "⏳", "cancelled": "⏹️"}.get(status, "·")


def _unescape(s: str) -> str:
    """把 shell 传入的字面 \\n / \\t 转成真实换行/制表，方便 Agent 填多行代码。"""
    if not s:
        return s
    return s.replace("\\n", "\n").replace("\\t", "\t")


def _resolve_req(req_ref: str, req_map: dict) -> str:
    """解析任务关联需求的状态展示：path:/api/x → ✅ done / ⏳ open / ❌ missing"""
    if not req_ref:
        return "—"
    status = req_map.get(req_ref)
    if status is None:
        for k, s in req_map.items():
            if k.split(":", 1)[-1] == req_ref:
                status = s
                break
    if status is None:
        return f"`{req_ref}`（需求库无此条目）"
    icon = {"done": "✅", "missing": "❌", "open": "⏳"}.get(status, "·")
    return f"{icon} `{req_ref}` ({status})"


def _resolve_defect(defect_ref: str, defect_map: dict) -> str:
    """展示任务绑定缺陷的状态：缺陷仍在 index.json → 🔴 未修复；已消失 → ✅ 已修复"""
    if not defect_ref:
        return "—"
    d = defect_map.get(defect_ref)
    if d is None:
        return f"✅ `{defect_ref}`（静态报告中已消失）"
    icon = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}[d["severity"]]
    return f"{icon} `{defect_ref}`"


def _slug(text: str) -> str:
    """把传入的计划名/标题转成 id 用短名（保留中文/字母/数字/连字符）。"""
    import re
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text or "").strip("-")
    return s[:40] or "plan"


def _plan_id(name: str = "") -> str:
    """日期+计划名：YYYYMMDD_<slug>（日期自动获取）。"""
    from datetime import datetime
    return f"{datetime.now():%Y%m%d}_{_slug(name)}"


def _refresh(store: PlanStore, pid: str) -> list:
    """双轨自动刷新：变更后重写 PLAN_<pid>.md/.json + plans.csv，返回追加产物行。"""
    from .export import refresh_plan
    code, lines = refresh_plan(store, pid)
    return lines if code == 0 else []


def _plan_of_task(store: PlanStore, task_id: int) -> str | None:
    conn = store.connect()
    row = conn.execute("SELECT plan_id FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def _plan_of_step(store: PlanStore, step_id: int) -> str | None:
    conn = store.connect()
    row = conn.execute(
        "SELECT t.plan_id FROM steps s JOIN tasks t ON t.id = s.task_id "
        "WHERE s.id=?", (step_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def cmd_create(store: PlanStore, title: str, goal: str = "", arch: str = "",
               stack: str = "", constraints: str = "", name: str = "") -> tuple:
    pid = _plan_id(name or title)
    conn = store.connect()
    conn.execute(
        "INSERT INTO plans(id, title, goal, arch, stack, global_constraints) VALUES (?,?,?,?,?,?)",
        (pid, title, goal, arch, stack, constraints))
    conn.commit()
    conn.close()
    return 0, [f"[plan] created id={pid} '{title}'"] + _refresh(store, pid)


def cmd_list(store: PlanStore) -> tuple:
    conn = store.connect()
    rows = conn.execute(
        "SELECT id, title, status, (SELECT count(*) FROM tasks WHERE plan_id=plans.id), "
        "(SELECT count(*) FROM tasks WHERE plan_id=plans.id AND status='done') "
        "FROM plans ORDER BY id DESC").fetchall()
    conn.close()
    if not rows:
        return 0, ["[plan] 无 plan（先 python -m macdev plan create）"]
    out = [f"| id | 状态 | 标题 | 任务 | 完成 |", "|----|------|------|------|------|"]
    for pid, title, status, nt, nd in rows:
        out.append(f"| {pid} | {status} | {title} | {nt} | {nd}/{nt} |")
    return 0, out


def cmd_update(store: PlanStore, pid: int, **fields) -> tuple:
    allowed = {"title", "goal", "arch", "stack", "global_constraints", "status"}
    sets, params = [], []
    for k, v in fields.items():
        if v is not None and k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return 1, ["[plan] 无有效更新字段"]
    params.append(pid)
    conn = store.connect()
    cur = conn.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[plan] id={pid} 不存在"]
    return 0, [f"[plan] id={pid} 已更新"] + _refresh(store, pid)


def cmd_delete(store: PlanStore, pid: int) -> tuple:
    conn = store.connect()
    conn.execute("DELETE FROM steps WHERE task_id IN (SELECT id FROM tasks WHERE plan_id=?)", (pid,))
    conn.execute("DELETE FROM tasks WHERE plan_id=?", (pid,))
    cur = conn.execute("DELETE FROM plans WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[plan] id={pid} 不存在"]
    # 清理单 plan 人类/机器轨产物，重写汇总 csv
    from .export import refresh_csv
    for suf in (".md", ".json"):
        f = store.out_dir / f"PLAN_{pid}{suf}"
        if f.exists():
            f.unlink()
    csv_path = refresh_csv(store)
    return 0, [f"[plan] id={pid} 及其任务/步骤已删除", f"[plan] csv → {csv_path}"]


def cmd_task_add(store: PlanStore, plan_id: int, title: str, detail: str = "",
                 files: str = "", req_ref: str = "", defect_ref: str = "",
                 interfaces: str = "") -> tuple:
    conn = store.connect()
    if not conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone():
        conn.close()
        return 1, [f"[task] plan id={plan_id} 不存在"]
    cur = conn.execute(
        "INSERT INTO tasks(plan_id, title, detail, files, req_ref, defect_ref, interfaces) "
        "VALUES (?,?,?,?,?,?,?)",
        (plan_id, title, detail, _unescape(files), req_ref, defect_ref, interfaces))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return 0, [f"[task] created id={tid} '{title}' (plan={plan_id})"] + _refresh(store, plan_id)


def cmd_task_list(store: PlanStore, plan_id: int) -> tuple:
    conn = store.connect()
    rows = conn.execute(
        "SELECT id, title, status, review_status, req_ref, defect_ref FROM tasks "
        "WHERE plan_id=? ORDER BY id", (plan_id,)).fetchall()
    conn.close()
    if not rows:
        return 0, [f"[task] plan={plan_id} 无任务"]
    defect_map = {d["id"]: d for d in store.load_defects()}
    req_map = store.req_status_map()
    out = ["| # | 状态 | 标题 | Review | 需求 | 缺陷 |", "|---|------|------|--------|------|------|"]
    for tid, title, status, rev, req, defect in rows:
        rev_txt = {"approved": "✅", "review_requested": "🔄", "needs_fix": "❌", "pending": "⏳"}.get(rev, rev)
        out.append(f"| {tid} | {_status_icon(status)} {status} | {title} | {rev_txt} | "
                   f"{_resolve_req(req, req_map)} | {_resolve_defect(defect, defect_map)} |")
    return 0, out


def cmd_task_update(store: PlanStore, tid: int, **fields) -> tuple:
    allowed = {"title", "detail", "files", "req_ref", "defect_ref", "interfaces",
               "status", "review_status", "review_findings"}
    sets, params = [], []
    for k, v in fields.items():
        if v is not None and k in allowed:
            sets.append(f"{k}=?")
            params.append(_unescape(v) if k in ("files", "detail", "review_findings") else v)
    if not sets:
        return 1, ["[task] 无有效更新字段"]
    params.append(tid)
    conn = store.connect()
    cur = conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[task] id={tid} 不存在"]
    pid = _plan_of_task(store, tid)
    return 0, [f"[task] id={tid} 已更新"] + (_refresh(store, pid) if pid else [])


def cmd_task_delete(store: PlanStore, tid: int) -> tuple:
    pid = _plan_of_task(store, tid)
    conn = store.connect()
    conn.execute("DELETE FROM steps WHERE task_id=?", (tid,))
    cur = conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[task] id={tid} 不存在"]
    return 0, [f"[task] id={tid} 及其步骤已删除"] + (_refresh(store, pid) if pid else [])


def cmd_step_add(store: PlanStore, task_id: int, text: str, action: str = "other",
                 code: str = "", lang: str = "", run: str = "", expected: str = "") -> tuple:
    conn = store.connect()
    if not conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
        conn.close()
        return 1, [f"[step] task id={task_id} 不存在"]
    nxt = conn.execute("SELECT COALESCE(MAX(ord)+1, 1) FROM steps WHERE task_id=?",
                       (task_id,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO steps(task_id, ord, text, action, code, lang, run, expected) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (task_id, nxt, text, action, _unescape(code), lang, run, expected))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    pid = _plan_of_task(store, task_id)
    return 0, [f"[step] created id={sid} #{nxt} ({action}) task={task_id}"] + \
        (_refresh(store, pid) if pid else [])


def cmd_step_list(store: PlanStore, task_id: int) -> tuple:
    conn = store.connect()
    rows = conn.execute(
        "SELECT id, ord, text, action, status, run, expected FROM steps "
        "WHERE task_id=? ORDER BY ord", (task_id,)).fetchall()
    conn.close()
    if not rows:
        return 0, [f"[step] task={task_id} 无步骤"]
    out = [f"| # | ord | 状态 | action | 文本 |", "|---|-----|------|--------|------|"]
    for sid, ord_, text, action, status, run, expected in rows:
        mark = "[x]" if status == "done" else "[ ]"
        out.append(f"| {sid} | {ord_} | {mark} {status} | {action} | {text[:60]} |")
    return 0, out


def cmd_step_update(store: PlanStore, sid: int, **fields) -> tuple:
    allowed = {"ord", "text", "action", "code", "lang", "run", "expected", "status"}
    sets, params = [], []
    for k, v in fields.items():
        if v is not None and k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return 1, ["[step] 无有效更新字段"]
    params.append(sid)
    conn = store.connect()
    cur = conn.execute(f"UPDATE steps SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[step] id={sid} 不存在"]
    pid = _plan_of_step(store, sid)
    return 0, [f"[step] id={sid} 已更新"] + (_refresh(store, pid) if pid else [])


def cmd_step_delete(store: PlanStore, sid: int) -> tuple:
    pid = _plan_of_step(store, sid)
    conn = store.connect()
    cur = conn.execute("DELETE FROM steps WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return 1, [f"[step] id={sid} 不存在"]
    return 0, [f"[step] id={sid} 已删除"] + (_refresh(store, pid) if pid else [])
