---
name: receiving-code-review
description: macdev 子技能：接收代码审查反馈（superpowers 整合）。以成长心态对待反馈：先理解、再逐条处理、不辩解。
---

# Receiving Code Review（接收审查反馈）

> 来源：superpowers/receiving-code-review，整合进 macdev §1-5 review 循环。
> **触发：收到 review 反馈时**。

## 步骤

1. **完整倾听**：先读完所有反馈，不打断、不辩解
2. **理解再回应**：确认理解每条反馈（可复述）；有歧义就问，不假设
3. **分类处理**：
   - 正确的 → 修复（`fix` → 重新 request）
   - 可商榷的 → 说明理由或采纳折中
   - 误解的 → 澄清事实（提供证据）
4. **修复后验证**：改完跑测试 + 重请求 review，直到 approve

## 纪律

- 反馈针对代码，不是针对人——不对抗
- 每条反馈都回应（修复/说明/澄清），不留悬空
- 审查是质量门，不是指责

## macdev 映射

| 接收反馈步骤 | macdev |
|---|---|
| 处理反馈 | `plan task update --findings` + `plan review --action fix` |
| 循环 | fix → `plan review --action request`（直至 approve） |
