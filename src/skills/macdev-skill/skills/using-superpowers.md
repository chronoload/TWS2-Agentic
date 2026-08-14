---
name: using-superpowers
description: macdev 子技能：任务触发纪律（superpowers 整合）。任何会话/任务第一步——先判定类型再动手。
---

# Using Superpowers（触发纪律）

> 来源：superpowers/using-superpowers，整合进 macdev §1-0 类型判定。
> **触发：任何任务开始前**（含澄清问题、探索代码、查文件之前）。

## 铁律

- **技能检查先于一切动作**：如果任务可能匹配某子技能，必须先调用它（见 §9 子技能索引）。
- "只是简单问题 / 先看下代码 / 先查下文件 / 我需要更多上下文" —— 全是反模式，停止合理化。
- 用户指令 > 技能 > 默认行为；被派为 subagent 执行特定任务时忽略本技能。

## 步骤（= macdev §1-0 类型判定）

1. **判定任务类型**（说出来让用户可否决）：
   - **Bounded**：改动既有代码流（新 flag/小端点/单文件修复）→ 短设计 chat 批准 → 直接实施
   - **Architectural**：新子系统/重构/影响他人接口 → brainstorming → requirement(spec) → plan
   - **Spike**：可行性问题 → 探针说明 → 点头 → 验证 → 汇报建议
   - **Bug**：缺陷现象 → systematic-debugging → patch 闭环
2. **不确定取更重一档**（Heavier path）；mid-task 复杂度升级 → 停下说明，只升级不降级。
3. 走对应分支（见 macdev SKILL.md §1-1 ~ §1-6）。

## macdev 映射

| superpowers | macdev |
|---|---|
| skill-first 触发 | §1-0 类型判定 + 铁律 8 |
| 分类后宣布 | 判定时向用户说明 |
| 棘轮升级 | 单向棘轮（只升级不降级） |
