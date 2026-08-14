---
name: brainstorming
description: macdev 子技能：构思→设计（superpowers 整合）。创意工作前必须用——澄清意图、细化需求、设计获批后才实现。spec 由 requirement 组件承载。
---

# Brainstorming（构思进设计）

> 来源：superpowers/brainstorming，整合进 macdev §1-2（Architectural 分支）。
> **触发：任何创意工作前**（新功能/组件/改行为/架构）。HARD-GATE：设计获批前不写实现。

## 三条路径

- **Spike**（可行性）：2-3 句说明问题+探针 → 点头 → 廉价验证 → 汇报建议（临时产物标 throwaway）
- **Bounded**（小改动既有流）：澄清关键问题 → chat 内短设计 → 批准 → 实施（无需 spec 文件）
- **Architectural**（新系统/重构/接口变更）：完整流程如下

## Architectural 流程

1. **探索上下文**：文件/文档/近期提交（macdev：audit 快速探索 / dev map）
2. **澄清问题**：一次一个，优先选择题；聚焦目的/约束/成功标准
3. **提 2-3 方案**：权衡 + 推荐 + 理由；YAGNI 砍冗余
4. **分段展示设计**：每段问"看起来对吗"；覆盖架构/组件/数据流/错误处理/测试
5. **spec 用 requirement 承载**（替代 design doc 文件）：
   - `requirement add --kind spec --name ... --detail ...`（机器权威，双轨自动刷新）
   - `requirement export` → REQUIREMENTS.md 人类轨；`requirement align` → 代码/端点对齐
   - 自审（placeholder/一致性/范围/歧义）→ **用户审查 REQUIREMENTS.md 后放行**
6. **转 plan**：`plan create/task/step`（TDD 节奏）→ 实施 → 重审计收敛

## 反模式

- "太简单不用设计" → 简单任务=短设计，不是无设计；批准门永不取消
- "设计明显，边做边看" → 门是批准，不是设计长度；展示后停住等"是"
- "Spike 跑通了就留代码" → spike 输出是答案；保留代码是新请求，重新分类

## macdev 映射

| superpowers 步骤 | macdev |
|---|---|
| 分类 spike/bounded/architectural | §1-0 类型判定 |
| 澄清/方案/设计 | grilling（一次一问，2-3 方案） |
| 写 design doc | `requirement add --kind spec` + export（双轨） |
| spec 自审/用户审查 | requirement export + REQUIREMENTS.md 审查 |
| 转 writing-plans | `plan create`（TDD 节奏） |
