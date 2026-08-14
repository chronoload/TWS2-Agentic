---
name: dispatching-parallel-agents
description: macdev 子技能：并行代理调度（superpowers 整合）。多个独立子任务并行跑，减少串行等待。
---

# Dispatching Parallel Agents（并行代理）

> 来源：superpowers/dispatching-parallel-agents，整合进 macdev §1-5 并行执行。
> **触发：多个互不依赖的子任务**（并行调研/并行实现/并行审查）。

## 步骤

1. **确认独立性**：任务间无数据依赖（有依赖则串行/分层）
2. **并行派发**：多个 `sub_agent` 或 team 队列（`team_task`/`team_run_task`）
3. **聚合结果**：`team_await_runs` 等待完成，逐项验收
4. **冲突仲裁**：并行改动同一文件 → 提前分区避免冲突；冲突按合并仲裁处理

## 纪律

- 并行 ≠ 乱序：每个子任务边界清晰、输出可合并
- 共享资源（同一文件/同一 DB）避免并行写
- 验收标准在派发时就写清楚

## macdev 映射

| superpowers | macdev |
|---|---|
| 并行派发 | `team_run_task(agent_id=..., message=...)` |
| 等待聚合 | `team_await_runs(run_ids=...)` |
| 依赖编排 | `team_task(depends_on=...)` / workflow 引擎 |
| 冲突仲裁 | 分区避免 + plan review 把关 |
