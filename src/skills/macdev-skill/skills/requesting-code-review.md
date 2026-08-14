---
name: requesting-code-review
description: macdev 子技能：请求代码审查（superpowers 整合）。实现完成自测后，主动请求 review 再合入，不自我批准。
---

# Requesting Code Review（请求审查）

> 来源：superpowers/requesting-code-review，整合进 macdev §1-5 review 循环。
> **触发：实现完成、自测通过后**。请求审查是合入前的必经环节。

## 步骤

1. **自测先行**：TDD 绿 + 相关测试全过（不给审查者留明显问题）
2. **准备审查上下文**：改动文件清单、设计意图、测试结果、已知权衡
3. **请求 review**：`plan review --task <id> --action request --findings "审查要点..."`
4. **等待结果**：approve / needs_fix（不催促；给足审查信息）
5. **处理反馈**：fix 后回到 request（循环直至 approve）

## 纪律

- 不自我批准：review 必须由他人/审查 agent 完成（`sub_agent(agent=review)` 或用户）
- 审查聚焦行为契约/边界/错误处理/测试覆盖，不只语法
- 反馈逐条回应，不回避

## macdev 映射

| review 步骤 | macdev |
|---|---|
| 请求 | `plan review --task <id> --action request` |
| 批准/拒绝 | `plan review --action approve/reject --findings` |
| 修复循环 | `plan task update --review-status needs_fix → fix → request` |
| 审查 agent | `sub_agent(agent=review, prompt=...)` |
