# 原子：cmd_review（原 plan_cli.py 第 1143 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_review(args) -> int:
    """review 循环状态机（requesting/receiving-code-review 机器化）。

    状态流转（对齐 subagent-driven-development 的 task review 循环）：
      pending → review_requested → approved（spec ✅ + quality ✅）
                                 ↘ needs_fix（记录 findings）→ fixed → review_requested
    """
    conn = _connect(args.db)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT id, title, review_status, review_findings FROM tasks WHERE id = ?",
        (args.task,)).fetchone()
    if not row:
        print(f"[review] task id={args.task} 不存在")
        conn.close()
        return 1
    tid, title, cur_status, cur_findings = row

    def _set(status: str, findings: str = "") -> None:
        cur.execute("UPDATE tasks SET review_status=?, review_findings=? WHERE id=?",
                    (status, findings, tid))
        conn.commit()
        conn.close()
        print(f"[review] task={tid} '{title}' → {status}"
              + (f"\n[review] findings:\n{findings}" if findings else ""))
        return 0

    if args.action == "request":
        if cur_status in ("approved",):
            print(f"[review] task={tid} 已 approved，无需重新 request")
            conn.close()
            return 0
        return _set("review_requested")
    if args.action == "approve":
        if cur_status == "approved":
            print(f"[review] task={tid} 已是 approved")
            conn.close()
            return 0
        return _set("approved")
    if args.action == "reject":
        if not args.findings:
            print("[review] reject 必须提供 --findings（Critical/Important/Minor）")
            conn.close()
            return 1
        return _set("needs_fix", _unescape(args.findings))
    if args.action == "fix":
        if cur_status != "needs_fix":
            print(f"[review] task={tid} 状态是 {cur_status}，只有 needs_fix 才能 fix")
            conn.close()
            return 1
        return _set("review_requested", cur_findings)
    conn.close()
    return 1
