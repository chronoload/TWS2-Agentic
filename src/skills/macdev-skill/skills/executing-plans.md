---
name: executing-plans
description: macdev 子技能：计划执行（superpowers 整合）。按 plan 逐步执行：读计划→做一步→验证→更新状态→继续；中断可 resume。
---

# Executing Plans（执行计划）

> 来源：superpowers/executing-plans，整合进 macdev §1-2 plan 实施。
> **触发：plan 创建后执行阶段**。

## 步骤

1. **读 plan**：`plan export` 或 `plan task list --plan <id>` 看清全部任务
2. **按序执行**：每个 task 的 step 逐个做（TDD 红绿节奏）
3. **验证再前进**：每步验证（测试/门禁）通过才标 done
4. **更新状态**：`plan step update --status done` / `plan task update --status done`
5. **中断/恢复**：`plan ledger --plan <id>` 看进度台账；恢复时从最近未完成处继续
6. **收尾**：全部 done → `plan verify`（完成门禁）→ review → 分支收尾

## 纪律

- 一步一验证，不跳步；遇到阻塞记录原因（log）
- 计划偏离时更新 plan（不悄悄改行为）
- 完成标准 = verify 过 + review approve，不是"代码写完"

## macdev 映射

| executing-plans | macdev |
|---|---|
| 读计划 | `plan export --id <plan>` / `plan task list` |
| 执行步骤 | `plan step add/update` |
| 进度台账 | `plan ledger --plan <id>` |
| 完成门禁 | `plan verify --plan <id>` |
