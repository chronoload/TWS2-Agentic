---
name: subagent-driven-development
description: macdev 子技能：子代理驱动开发（superpowers 整合）。把独立子任务委派给专门 agent（coder/task/research/review），并行推进。
---

# Subagent-Driven Development（子代理驱动）

> 来源：superpowers/subagent-driven-development，整合进 macdev §1-5 subagent 执行。
> **触发：任务有明确独立子任务时**（实现/研究/审查可分派）。

## 步骤

1. **切分子任务**：找出可独立完成的单元（实现模块/调研问题/审查范围）
2. **写清楚委托**：目标 + 上下文 + 验收标准 + 约束（prompt 要完整）
3. **委派**：`sub_agent(agent=coder|task|research|review, prompt=..., context=...)`
4. **收结果**：检查产物是否符合验收标准；不符合 → 反馈迭代或自行修复
5. **整合**：子任务产物合入主线（plan task/step 标记完成）

## 子代理角色

| agent | 用途 | 上限 |
|---|---|---|
| coder | 编写/调试/重构代码 | 15 轮 |
| task | 完成特定任务 | 10 轮 |
| research | 搜索/分析/总结 | 8 轮 |
| review | 审查代码质量/安全 | 5 轮 |

## 纪律

- 委托要完整（prompt 缺上下文 = 子代理瞎猜）
- 大任务先切分再委派，不把整个 plan 丢给一个子代理
- 关键路径自己掌握，子代理处理支线

## macdev 映射

| superpowers | macdev |
|---|---|
| 委派子任务 | `sub_agent(agent=...)` 工具 |
| 并行子代理 | `dispatching-parallel-agents` 子技能 + team 工具 |
| 进度 | `plan task/step` 状态机 |
