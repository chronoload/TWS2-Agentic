---
name: writing-skills
description: macdev 子技能：编写/自演化技能（superpowers 整合）。把重复工作流固化为可复用技能；macdev 自演化优先走 log + SKILL.md §8。
---

# Writing Skills（编写技能）

> 来源：superpowers/writing-skills，整合进 macdev 自演化（§8 铁律 6）。
> **触发：发现重复流程/方法论值得固化时**。

## 步骤

1. **识别模式**：同一流程重复 2+ 次 → 值得固化
2. **沉淀经验**（macdev 方式）：
   - 方法论/教训 → `log add`（随包 pkg 或随项目 project）
   - 强制规则 → SKILL.md §8 铁律（用户指令级）
   - 独立可复用能力 → 新子技能 skills/*.md（本目录模板）
3. **写技能文件**：触发条件 + 步骤 + macdev 映射（简洁，一次能读完）
4. **注册/索引**：更新 SKILL.md §9 子技能索引
5. **发布**：publish.py 发布到 .trae/docs（含 skills/）

## 技能质量

- 触发条件明确（什么时候用）
- 步骤可执行（不依赖猜测）
- macdev 映射（对应哪个命令/工具）
- 简洁（指针式，细节进 DOC）

## macdev 映射

| writing-skills | macdev |
|---|---|
| 经验沉淀 | `log add --scope pkg` |
| 强制规则 | SKILL.md §8（用户指令 > skill 约定） |
| 新子技能 | skills/*.md + §9 索引 |
| 发布 | publish.py（含 skills/） |
