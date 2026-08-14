---
name: using-git-worktrees
description: macdev 子技能：git worktree 多工作区（superpowers 整合）。同时维护多个分支时用 worktree 隔离，避免频繁 stash/切换。
---

# Using Git Worktrees（多工作区）

> 来源：superpowers/using-git-worktrees，整合进 macdev §1-5（可选）。
> **触发：需要在多个分支并行工作/避免切换成本时**。

## 步骤

1. **创建 worktree**：`git worktree add <path> <branch>`（为每个进行中的分支建独立工作区）
2. **各自开发**：每个 worktree 独立 checkout/构建/测试，互不干扰
3. **完成收尾**：按 finishing-a-development-branch 合并回主分支
4. **清理**：`git worktree remove <path>`（已合并分支才移除）

## 纪律

- worktree 是只读共享 .git（一个仓库多工作区）
- 同一仓库并行分支避免改同一文件（合并时冲突）
- 危险 git 操作（worktree remove/prune）先确认（铁律 1）

## macdev 映射

| worktrees | macdev |
|---|---|
| 多分支并行 | `git worktree add`（先问，铁律 1） |
| 独立验证 | 每个 worktree 内 `plan verify` / 测试 |
| 收尾 | 并入 finishing-a-development-branch |
