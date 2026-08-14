# macdev LOG — 经验沉淀库

> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。
> 共 9 条。

## 随包经验（pkg）— 9 条

### 经验教训（lessons）— 1 条

#### [3] TS monorepo 审计能力边界：完整链仅覆盖 .py，4 维扫描覆盖全仓

- 分类: lessons ｜ 标签: ts,monorepo,audit,boundary ｜ 时间: 2026-08-14 00:35:35

macdev audit 的 parse/chain/analyze（端点提取/亲属追逐/def-use）基于 Python AST，对 TS/JS 项目只收集 *.py（如 deepseek-harness 仅 18 个 .py）。
对 TS 主导项目：
1. 完整链聚焦项目的 Python 侧（如 python/sdk）——files 入口显式列出 .py 核心文件；
2. 4 维扫描（hardcoded/env/data_pools/static_resources）通过 scan.py 的 _JS_SUFFIXES 正则覆盖全仓 TS/JS——scan_dirs 列出 packages/apps 即可；
3. exclude 必须加 lib/（编译产物）、.agents、vendor、*.map、*.tsbuildinfo 剪枝噪声；
4. 期望管理：TS 端点=0 是正常，不是失败。
后续增强方向：TS AST 解析器（tree-sitter）插件化接入 parse 层。


### 陷阱（pitfalls）— 3 条

#### [8] 异步提交期间调 _finishModal 被 submitting 挡 → 复位后必须补 drain

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

前端弹窗队列（approval/ask）：_agentModalSubmitting=true 时用户提交 → _finishAgentModal() 内部调 _drainAgentModalQueue() 被 submitting 检查挡住直接 return → finally 复位 submitting 后无人再 drain → 队列下一个弹窗不自动弹出（只有刷新/下次轮询才弹）。修复：submitAskAnswer/webApprovalDecide 的 finally 里 submitting=false 后补 _drainAgentModalQueue()。铁律：异步提交期间的队列推进必须放在 submitting 复位之后，不能依赖 _finishModal 内部 drain。

#### [5] builtin 反射噪音：TypeError/内置异常被误判为 broken 链路断裂

- 分类: pitfalls ｜ 标签: builtin,noise,broken,chain ｜ 时间: 2026-08-14 00:35:57

亲属追逐链把内置异常 TypeError 当作调用目标，判为 🔴 broken（request:177）。
同类已有 builtin 噪音条目（turn.id→turn_id），此处补异常类场景：
链图上的 broken 可能是 builtin/参数/字面量噪音，必须回源码甄别后再下结论（回归语境核实）。

#### [2] macdev 工具 args 中 Windows 路径反斜杠被转义吞掉

- 分类: pitfalls ｜ 标签: windows,path,args,macdev ｜ 时间: 2026-08-14 00:35:35

调用 macdev 工具传绝对路径时，C:\Users\... 的反斜杠在 args 字符串里被 Python 转义为 C:Users...（驱动器相对路径，解析错乱）。
规避：一律用正斜杠 C:/Users/qu/Desktop/...（Path 跨平台兼容）。
教训：工具层的路径参数优先正斜杠；cli_execute 里直接 python -m macdev 不受影响。


### 模式（patterns）— 3 条

#### [9] Agent 并行 ask 挂起：字典按 rid 隔离 + 全局池无条件注册双保险

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

多个 ask_followup_question 并行挂起时，单值字段会互相覆盖（后一个顶掉前一个→answer 匹配不上）。模式：1) _pending_asks 字典按 rid 独立挂起 + _last_ask_answers 字典按 rid 存答案（并发互不覆盖）；2) answer API 用 has_pending_ask(rid) 精确匹配；3) 全局 pending 池无条件注册（不依赖 SSE 通道存在与否），SSE 推送 + 轮询双保险；4) 挂起线程阻塞循环读 _last_ask_answers[rid]，写答案先于 clear_pending_ask（顺序保证唤醒）；5) 300s 超时兜底 + 池过期清理（320s）防泄漏。

#### [7] 流式 Markdown 渲染：结构未闭合守卫 + 轻量渲染器 + 自适应降级 + 免全量重建

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

流式渲染『适当激进 + 无感 + 计算量小』配方：1) _mdStructuralIncomplete 检测代码围栏(```/~~~奇数)/行内公式($奇数，排除$$)未闭合 → 未闭合保持 textContent（不闪烁）；2) 结构完整时用自研轻量行级渲染器（非 markdown-it，<1ms/数百行）流式中实时渲染；3) 自适应降级：超长回复(>800行)流式中纯文本防每30ms全量解析卡顿，流结束 forceRender 强制渲染；4) KaTeX 350ms 节流（renderMathInElement 扫描全 el 不宜逐 token）；5) _streamRendered 键防重（内容未变不重渲染）；6) 流结束免全量重建（finalize 只幂等补收尾+立即 KaTeX），消除'脱掉'闪烁；7) 30ms debounce 合并高频 token。

#### [1] deepseek-harness 开发范式（插件总线 + agent notes + skills 三件套）

- 分类: patterns ｜ 标签: deepseek-harness,monorepo,plugin,cordis ｜ 时间: 2026-08-14 00:35:12

deepseek-harness（@deepseek-ai/dsh-*，vendored Cordis）的规模化开发方式：
1. 插件总线微内核：everything is a plugin，能力按 packages/<group>/<pkg> 分组（core/api/llm/shell/fs/skill/subagent/session/workflow/client...），约 200+ workspace 包；
2. 开发过程留痕：.agents/notes 按状态（archived/implemented/proposed/rejected）× 类别（architecture/bug-fix/feature/process/simplification/testing）沉淀，共 1700+ 篇——这就是项目的'开发史'；
3. 技能化：.agents/skills 一堆 dsh-* SKILL.md（code-review/pre-push-checks/merging-stacked-prs/trim-cot-leakage...），AI 辅助纪律显式化；
4. AGENTS.md 驱动：仓库布局 + 开发规范面向 AI 写，pre-release 期 foundation over blast radius（自由重构不兼容垫片）；
5. 三语文档：*.md + *.zh.md + *.i18n.yaml 三件套；
6. 版本纪律：SQLite SCHEMA_VERSION 单调、SESSION_FORMAT_VERSION=0 无兼容承诺。
与 macdev 哲学同构（插件总线/双轨产物/SKILL.md 指针/经验沉淀），是 monorepo 规模 agent 项目的标杆范式。


### 决策（decisions）— 2 条

#### [6] SKILL.md 自演化：新增 §8 开发安全铁律（危险 git 先问 + 启动查 git + 双轨产物）

- 分类: decisions ｜ 标签: — ｜ 时间: 2026-08-14 03:48:09

用户明确要求自演化 skill（而非仅项目 log）：在 macdev-skill/SKILL.md 与 skills_market/macdev-skill/macdev-skill/SKILL.md 同步追加 §8 开发安全铁律：①危险 git 命令（checkout/reset/clean/push/merge/revert/branch -D/rm）必须先问用户，只读命令随时可跑；②未追踪文件不假设不重要，删除/覆盖/忽略前逐项确认；③上下文开始/压缩后第一时间 git branch -a + status --short + log --oneline -15；④动手前查 macdev log list 与 plan list；⑤macdev 操作必须生成双轨产物（db/csv/json + md）收敛到 <name>-project/；⑥自演化优先：规则固化进 SKILL.md + 随包 log。优先级：用户指令 > skill 内部约定（覆盖原'经验只写 log 不写 SKILL.md'条款）。

#### [4] dsh 策略设计决策：TS monorepo 审计配置

- 分类: decisions ｜ 标签: decision,dsh-strategy,audit ｜ 时间: 2026-08-14 00:35:57

新增 audit.strategy=dsh（strategy_dsh.py）：
1. known_type_files 映射 @deepseek-ai/dsh-* 核心类型 → packages/<group>/<pkg>/src/index.ts（兜底路径带 * 组号）；
2. resolve_type_file 覆写为 .ts 后缀（TS 源文件）；
3. AuditTask（dsh-task.json）：files 入口聚焦 python/sdk（完整链），scan_dirs=packages/apps/python/scripts（4 维扫描全仓），exclude 加 lib/.agents/vendor/website/__snapshots__；
4. chains.entries 必须用 dict（kind=function/name=Class.method 或 kind=endpoint/prefix），字符串会炸 AttributeError。
验证：audit ok=True，亲属追逐链对 HarnessClient.initialize/request 正确展开。
关键取舍：TS 端点提取暂不支持（AST 边界），以 SDK 完整链 + 全仓 4 维扫描为组合覆盖。

