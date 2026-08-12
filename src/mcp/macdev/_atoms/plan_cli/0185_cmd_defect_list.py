# 原子：cmd_defect_list（原 plan_cli.py 第 185 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_defect_list(args) -> int:
    defects = _load_defects(args.index)
    if not defects:
        print(f"[defect] 无缺陷（或索引不存在: {args.index}）")
        return 0
    n_red = sum(1 for d in defects if d["severity"] == "red")
    print(f"[defect] 静态缺陷 {len(defects)} 条（🔴 {n_red}）— 来自 {args.index}\n")
    for d in defects:
        icon = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}[d["severity"]]
        loc = f"{d['file']}:{d['line']}" if d["line"] else d["file"]
        print(f"  {icon} {d['id']}  — {d['detail'][:110]}")
    print("\n绑定到任务: task add --defect '<id>' （如 flag:app.py:1140:clear_without_set）")
    return 0
