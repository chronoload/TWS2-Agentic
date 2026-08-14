---
name: finishing-a-development-branch
description: macdev 子技能：分支收尾（superpowers 整合）。功能分支完成（verify+review 过）后：合并、清理、记录，不留半成品分支。
---

# Finishing a Development Branch（分支收尾）

> 来源：superpowers/finishing-a-development-branch，整合进 macdev §1-5 分支收尾。
> **触发：plan 全部完成、verify/review 通过后**。

## 步骤

1. **确认完成门禁**：`plan verify` 过 + review approve（未过不许收尾）
2. **审查分支范围**：`git log main..branch` 确认改动都在计划内
3. **合并**：合并到主分支（git merge/rebase —— 危险操作，**按 §8 铁律先向用户确认**）
4. **清理**：删除已合并分支（`branch -D` 需确认）；临时产物清理
5. **沉淀**：`log add` 记录本次经验（patterns/pitfalls）
6. **双轨产物**：plan/requirement 状态归档（done/archived）

## 纪律

- 未过门禁不合并；未合并不删分支
- 合并前检查工作区干净（`git status`）
- 破坏性 git 操作一律先确认（铁律 1）

## macdev 映射

| 收尾步骤 | macdev |
|---|---|
| 完成确认 | `plan verify` + `plan review --action approve` |
| 分支检查 | `git log main..branch`（只读） |
| 合并/清理 | git merge/branch -D（**先问**，铁律 1） |
| 经验沉淀 | `log add --category patterns` |
