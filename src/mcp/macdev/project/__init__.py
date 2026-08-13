"""macdev project：工作流产物目录约定。

所有 audit / plan / log 产物收敛到 `<name>-project/`，不溢出该目录：
- audit  → <name>-project/audit/        （重跑覆写，不另建新目录）
- plan   → <name>-project/plans.db      + 导出的 .md
- log    → <name>-project/logs.db       + LOGS.md

命令以 `--project <name>` 指向产物目录（显式 --db/--out 优先）。
"""
