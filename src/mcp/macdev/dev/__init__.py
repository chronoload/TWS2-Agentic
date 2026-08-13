"""macdev.dev：学习/模仿目标项目（用 macdev 了解一个陌生项目怎么做起来的）。

- map   扫描目标学习项目，编排目录（树 + 模块地图 + 技术栈线索），双轨产物
        （DIR_TREE.md 人类 + dir_tree.json/csv/db 机器，语言环境无关）
- audit 自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物
        （INTERFACE_CHAIN.md + interface_chain.db + CSV + events.ndjson）

产物收敛：--project <name> → <name>-project/dev/<target名>/；显式 --out 优先。
"""
from __future__ import annotations
