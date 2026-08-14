---
name: verification-before-completion
description: macdev 子技能：完成前验证（superpowers 整合）。宣称"完成"前必须过验证门禁：测试/门禁/review，不留未验证的尾巴。
---

# Verification Before Completion（完成前验证）

> 来源：superpowers/verification-before-completion，整合进 macdev §1-5 通用纪律。
> **触发：任何任务宣称完成前**。完成 = 验证过，不是"代码写完了"。

## 验证清单

1. **测试就位且绿**：功能测试/回归测试通过（TDD 红绿闭环完整）
2. **门禁过**：`plan verify`（TDD 合规 + 缺陷清零 + 测试就位 + review）
3. **review 完成**：`plan review --action approve`（或 request→fix→approve 循环）
4. **缺陷收敛**：重审计对比（`patch verify` / 前后 interface_chain.db 对比）
5. **双轨产物**：plan/requirement/log 的 md + db 双轨齐全
6. **未留 TODO/throwaway**：临时产物已清理或标注

## 反模式

- "看起来没问题" → 跑验证，不信直觉
- "测试都过了"但没跑 → 真跑一遍
- "先提交再说" → 验证在提交前

## macdev 映射

| 验证项 | macdev |
|---|---|
| 完成门禁 | `plan verify --plan <id>` |
| 缺陷收敛 | `patch verify --before --after` / 重 audit |
| review | `plan review --action approve` |
| 台账 | `plan ledger`（确认无遗留 open） |
