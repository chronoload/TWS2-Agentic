---
name: systematic-debugging
description: macdev 子技能：系统化调试（superpowers 整合）。Bug 必须走：复现→根因→假设→验证→修复，禁止猜测式改码。
---

# Systematic Debugging（系统化调试）

> 来源：superpowers/systematic-debugging，整合进 macdev §1-4（Bug 分支）。
> **触发：任何缺陷/bug**。核心：不臆断，用证据链定位根因。

## 步骤

1. **复现**：建立最小复现路径（测试/脚本）。不能复现 = 信息不足，先收集。
2. **读代码找假设**：沿数据流读相关代码（macdev：audit 依赖链 + 回归语境核实），
   形成 2-3 个候选根因假设（不臆断——每个假设都要有代码证据支撑）。
3. **验证假设（二分/最小实验）**：为最可能假设写一个**失败测试**（expected FAIL）
   或最小探针脚本，确认假设成立（红）。
4. **修复**：最小改动实现修复 → 测试转绿（绿）。
5. **回归**：跑全量相关测试 + 重审计（patch verify）对比缺陷收敛；沉淀 log。

## 反模式

- 猜一个改一个（shotgun debugging）→ 先根因后修复
- 跳过复现直接修 → 无法验证"修好了"
- 假设不验证就改 → 可能修错地方

## macdev 映射

| 调试步骤 | macdev |
|---|---|
| 复现 | `plan step add --action test --expected FAIL` |
| 根因分析 | audit 依赖链 + 语境核实 |
| 假设→修复 | `patch gen/apply` + 失败测试转绿 |
| 收敛验证 | `patch verify --before/--after` + 重审计 |
| 沉淀 | `log add --category pitfalls` |
