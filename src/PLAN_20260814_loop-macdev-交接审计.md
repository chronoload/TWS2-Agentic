# loop × macdev 交接审计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** loop 完成任务生成结构化交接笔记 + macdev audit 对抗性验证断言 + 笔记/审计结果以可折叠卡片注入普通会话（根治上下文污染与目标漂移）

**Architecture:** （未填写）

**Tech Stack:** （未填写）

**Status:** open · **Created:** 2026-08-14 21:26:20 · **Tasks:** 4

---

### Task 1: T2 macdev 对抗性审计 ⏳

交接时对 handoff.artifacts 断言跑 macdev audit：断言文件存在（file_info）+ 接口链无断裂（audit broken 检测）+ 测试通过（pytest）→ handoff.audit {method: macdev_audit, status: verified|failed, checks[], artifacts_path}。无产物（纯研究）跳过审计。TDD：测试审计 verified/failed 判定

**Review:** ⏳ 待审查

- [ ] _（本任务暂无步骤，待补充）_


### Task 2: T3 前端交接卡片 ⏳

loop 完成时前端渲染交接笔记卡片（可折叠）：goal/summary/decisions/artifacts + audit 状态徽标（✅verified/❌failed）+ failed 时一键重跑按钮；轮询检测 handoff 就位后注入普通会话流。浏览器验证 + 回归

**Review:** ⏳ 待审查

- [ ] _（本任务暂无步骤，待补充）_


### Task 3: T1 交接笔记生成 ⏳

LoopTask 增 handoff: Optional[dict]；_run_task 终态（completed/halted）时生成结构化交接笔记 {goal, status, turns, summary, decisions[], artifacts[], open_issues[]}——summary/decisions/artifacts 从 messages 提炼（工具调用/最终结果/错误）。TDD：测试完成任务后 handoff 生成且含 goal/status/artifacts

**Review:** ⏳ 待审查

- [ ] _（本任务暂无步骤，待补充）_


### Task 4: T0 上下文共享改造（新方向 spec id=4） ⏳

LoopTask 有 session_id 时：_run_task 回合上下文 = 会话历史（普通对话 + 已执行 loop 回合，从 agent session 读取）+ 当前回合；回合结果 append 到 task.messages 且回写会话上下文（同一上下文迭代器）；无 session_id 保持独立上下文（兼容）。终止：目标达成/预算/停止。TDD：测试有 session_id 的任务回合上下文包含会话历史、结果回写

**Review:** ⏳ 待审查

- [ ] _（本任务暂无步骤，待补充）_



---
自动生成: 2026-08-14T21:53:00 由 `macdev plan export`（format=writing-plans）