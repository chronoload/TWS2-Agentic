---
name: test-driven-development
description: macdev 子技能：TDD 红绿节奏（superpowers 整合）。实现功能先写失败测试，转绿后重构。macdev plan step 原生支持。
---

# Test-Driven Development（TDD）

> 来源：superpowers/test-driven-development，整合进 macdev §1-5 通用纪律。
> **触发：任何实现工作**。节奏：红（失败测试）→ 绿（最小实现）→ 重构。

## 节奏

1. **红**：写一个失败测试（`plan step add --action test --run <cmd> --expected FAIL`）
2. **绿**：最小实现让它通过（`--expected PASS`）
3. **重构**：清理重复/命名（不改变行为，测试保绿）
4. 循环直到功能完整

## 纪律

- 一次只写一个失败测试；测试失败先于实现存在
- 不写"永远不会失败的测试"；测试要快、独立、可重复
- 完成后 `plan tdd check` 做 TDD 合规检查

## macdev 映射

| TDD 步骤 | macdev |
|---|---|
| 失败测试 | `plan step add --action test --expected FAIL` |
| 实现转绿 | `plan step update --id N --status done` |
| 合规检查 | `plan tdd check` |
| 完成门禁 | `plan verify`（TDD 合规 + 缺陷清零 + 测试就位 + review） |
