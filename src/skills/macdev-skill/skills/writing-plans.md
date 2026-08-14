---
name: writing-plans
description: macdev 子技能：编写实施计划（superpowers 整合）。设计获批后写可执行的 plan（writing-plans 格式），先想清楚再写码。
---

# Writing Plans（实施计划）

> 来源：superpowers/writing-plans，整合进 macdev §1-2（Architectural 分支第 6 步）。
> **触发：设计（requirement spec）获批后、写代码前**。输出：`plan`（writing-plans 格式双轨）。

## 原则

- 计划 = 一步步可执行的路径（先想清楚，让执行者无需再设计）
- 每个 task 有：标题、细节、涉及文件（Create/Modify）；每个 step 有：动作 + 期望结果
- TDD 内建：实现步骤前先写失败测试步骤
- 范围聚焦：一个 plan 对应一个 spec（requirement），大项目拆多个 plan

## 步骤

1. `plan create --title ... --goal ... --arch ... --stack ...`（关联 reqdb）
2. `plan task add --plan <id> --title T1 --detail ... --files "Create: ...\nModify: ..." --req <spec-id>`
3. 每 task 加 step：先 `--action test --expected FAIL`（红），再实现（绿）
4. `plan export --format writing-plans` 生成人类可读计划文档
5. 执行中 `plan ledger` 维护进度台账（resume 用）

## macdev 映射

| writing-plans 元素 | macdev |
|---|---|
| 计划文档 | `plan export --format writing-plans` |
| 任务+文件 | `plan task add --files` |
| TDD 步骤 | `plan step add --action test --expected FAIL` |
| 执行跟踪 | `plan ledger` |
