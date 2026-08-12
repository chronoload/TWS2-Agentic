"""macdev.requirement：需求管理插件（CRUD + 规范接口对齐）。

自演化迁移自 mcp/requirement_cli.py + mcp/requirement_align.py，纳入 macdev 平级插件体系：
- db.py        RequirementStore（requirements 表 CRUD + 对齐/导出产物落盘）
- align.py     对齐纯逻辑（需求文档提取声明 → 代码/端点对齐），无硬编码路径
- commands.py  命令层（add/list/update/delete/export/scan/align），返回 (code, lines)

双轨产物：requirements.db（机器）+ REQUIREMENTS.md / REQUIREMENT_ALIGNMENT.md（人类）。
产物目录收敛：--db/--out/--index 缺省时走 <name>-project/（--project / env MACDEV_PROJECT）。
"""
