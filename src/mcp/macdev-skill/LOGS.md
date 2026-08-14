# macdev LOG — 经验沉淀库

> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。
> 共 25 条。

## 随包经验（pkg）— 25 条

### 经验教训（lessons）— 3 条

#### [15] 新对话第一步就查log/plan，不等残缺

- 分类: lessons ｜ 标签: — ｜ 时间: 2026-08-14 14:20:32

用户澄清：看似全新的对话也要第一步查随包+随项目 log/plan，找回历史轨迹——不是等出现残缺/不确定才查。铁律10已强化（任何会话开始第一步查 log/plan）。结合铁律3（压缩后查git）：新会话=查git+查log/plan双查。

#### [14] 进程终止/重启：必须用户明确许可，说明意图不算

- 分类: lessons ｜ 标签: — ｜ 时间: 2026-08-14 14:16:22

用户澄清：进程相关动作（kill/restart/替换）仅'说明意图'不够，必须获得用户明确点头（许可）才能执行。铁律11已强化——'用户未点头一律不动'。新实例优先（换端口/副本后台调试）仍是首选路径。

#### [3] TS monorepo 审计能力边界：完整链仅覆盖 .py，4 维扫描覆盖全仓

- 分类: lessons ｜ 标签: ts,monorepo,audit,boundary ｜ 时间: 2026-08-14 00:35:35

macdev audit 的 parse/chain/analyze（端点提取/亲属追逐/def-use）基于 Python AST，对 TS/JS 项目只收集 *.py（如 deepseek-harness 仅 18 个 .py）。
对 TS 主导项目：
1. 完整链聚焦项目的 Python 侧（如 python/sdk）——files 入口显式列出 .py 核心文件；
2. 4 维扫描（hardcoded/env/data_pools/static_resources）通过 scan.py 的 _JS_SUFFIXES 正则覆盖全仓 TS/JS——scan_dirs 列出 packages/apps 即可；
3. exclude 必须加 lib/（编译产物）、.agents、vendor、*.map、*.tsbuildinfo 剪枝噪声；
4. 期望管理：TS 端点=0 是正常，不是失败。
后续增强方向：TS AST 解析器（tree-sitter）插件化接入 parse 层。


### 陷阱（pitfalls）— 8 条

#### [25] 并发修改同一文件：主工作区 vs worktree 双线冲突

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 23:09:21

本次事故：主工作区（master 带用户未提交改动 update_max_duration）与 worktree（feat/msg-queue 带我的 FIFO 改动）同时改 loop.py/test 文件——两边基线不同（a0792c5 vs 6247159），直接复制会覆盖对方改动，只能逐处精确合并，且测试基线差异导致 3 个存量失败难辨归属。根因：单主体错误使用 worktree 造成双写。教训：①单主体（我一个 agent）开发用单线，绝不分叉；②多主体（子代理并行）才 worktree 隔离；③并发前先查 git status/log 看清两边基线；④绝不整文件覆盖，逐处合并 + diff 验证。铁律13 已修正固化。

#### [23] spec写完未停等审核就实现+plan潦草（HARD-GATE 违反）

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 21:58:04

事故：5 个 spec 全 open 但代码已全部提交（spec1/2/4/5 实现进 git，spec3 只有 plan 0/4）。根因：①spec 写完未导出 REQUIREMENTS.md 呈用户审核，直接进 plan/实现；②plan 潦草——Architecture/Tech Stack 未填、每 task 步骤全是'待补充'占位，颗粒度不对齐 writing-plans。修复：铁律12（spec 写完后必须停等用户明确批准，禁止自行实现；plan 每 task 带 Create/Modify 文件、每 step 带动作+期望结果+TDD 红→绿，禁止'待补充'占位）。教训：设计完成≠可以开工，HARD-GATE 是用户强制门禁。

#### [22] auto_compact消息级保护破坏user-assistant交替-按轮分组根治

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 18:09:19

复现：keyword_preserved+recent按单条消息独立挑选拼接导致压缩后user相邻或assistant开头；sanitize只修tool配对。修复：按轮分组保护+_ensure_valid_sequence收尾+sanitize双保险。测试6用例全过。

#### [16] 数组中间插入后索引型导航块必须整体重建

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 14:27:07

app.js FlowNav：_flowNavBlocks 存 msgIndex=数组绝对下标。压缩历史分页 _loadCompactMorePage 用 splice 中间插入 ui3 后未重建导航块 → 插入点之后 msgIndex 全部偏移，点击导航定位错误/找不到。修复：提取 _makeFlowNavBlock 纯构建 + _rebuildFlowNavBlocksAll 批量重建（插入后调用）。教训：任何'用数组下标做定位'的索引结构，遇中间插入（splice）必须整体重建或改稳定 ID。

#### [11] cmd 传中文参数给 python -c 编码损坏（GBK）

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 14:00:37

Windows cmd 下 python -c 带中文常量会被 GBK 损坏，SQL WHERE 匹配失败且 print 输出被吞。解决：写临时 UTF-8 脚本文件执行，勿用 -c 内联中文。

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


### 模式（patterns）— 11 条

#### [24] worktree 仅用于子代理/多线并行隔离（非默认开发方式）

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 21:58:04

主开发流保持单线（master 直接改）。只有子代理并行开发、多分支实验、高风险隔离才建 worktree（git worktree add 路径 -b 分支）。单主体单线最简。铁律13 已修正。

#### [21] deepseek-harness/cordis 参考：决策归档 + 插件总线分层 + 流程纪律技能

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 15:11:27

为统一 Agent Harness 设计提取的参考：①dsh .agents/notes（archived/implemented/proposed/rejected 四态决策库）→ 项目级 ctx_store 共享记忆，解决多 agent 上下文不同步；②cordis 插件生态（extensions/ cordis-client-runner/host-runner + tool-cordis/ui-cordis）→ harness 分层：前端=client 订阅 EventStream，后端=host 执行，tool/ui 独立插件包；③.agents/skills 流程纪律技能（dsh-code-review/pre-push-checks/merging-stacked-prs/find-simplifications/trim-cot-leakage）→ harness 按任务装载纪律技能；④AGENTS.md/CLAUDE.md 规则文件 → 项目级 harness 配置（approval_policy/工具白名单）；⑤jsonrpc-demo → AgentMessage 协议 JSON-RPC 编码。spec id=3 已记录。

#### [20] 技能双轴扩展：语言驱动（思想） + 工程实践（落地）

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:57:03

langdriven skill 升级：范式清单第二位加入开发实践（TDD/BDD/ATDD/重构/测试金字塔/CI/CD/代码评审/DDD/微服务/遗留代码/混沌/ODD/SRE/SDL/敏捷）。响应格式验证段改'测试与验证'（TDD 先写什么测试/分层/框架）；最小核心附测试骨架；触发词增 [TDD]/[BDD]。teammate 更新需 shutdown+spawn（spawn 对已存在报错，无 update 语义）。

#### [19] 前端流式两大支柱：rAF 合帧 + 稳定消息 ID

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:55:20

流式渲染最佳实践落地：①渲染调度用 requestAnimationFrame 合帧替代 setTimeout debounce（帧对齐、无尾延迟、高吞吐 token 一帧一次）；②消息对象惰性分配 _uid（_ensureMsgUid 幂等），DOM data-mid + 导航 msgId 稳定定位，根治数组 splice 中间插入下标偏移类 bug（压缩分页/懒加载）。组合：纯函数状态 + 单线程调度 + 稳定标识 = 前端流式免疫竞态与错位。

#### [18] 方法论资产三件套包装：skill + workflow + teammate

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:48:28

把可复用方法论（如语言驱动引擎）包装为三件套：① skills/<name>/SKILL.md 技能文档（frontmatter name/description）；② mcp/predefined_workflows.py 注册 <name>_engine_v1 工作流（AGENT 步骤链，checkpoint_after 全步骤）；③ team_spawn_teammate 注册研究员角色（system_prompt=核心准则+响应格式+触发词+禁止行为）。三处独立可组合：skill 供 agent 加载、workflow 供确定性编排、teammate 供委派。

#### [13] 进程调试纪律：新实例优先，不杀运行中进程

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:14:54

需要调试/重启/替换运行中的服务进程时，优先换端口/复制副本构建新实例后台调试，禁止 kill/restart 干扰现有运行实例（服务端/长任务/训练）。只读检查（netstat/wmic/tasklist）随时可做；终止/重启前必须说明意图确认不影响现有实例。已固化铁律11。

#### [12] 私有部署同步清单：macdev-skill + 工具包装

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:11:54

私有部署 TS2 = C:\Users\qu\Desktop\物理科学与技术论题\TS2（与开发版 TS2_dev 分离）。macdev 相关文件同步：TS2_dev/src/skills/macdev-skill/* → TS2/macdev-skill/*（SKILL.md + skills/子技能 + publish.py）；TS2_dev/src/mcp/macdev_tools.py → TS2/mcp/。同步后 fc /b 字节级一致性验证。服务端需重启才加载新工具定义。

#### [10] 技能整合形态C：纪律进SKILL.md流程 + 细节进skills/子技能

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 14:00:37

整合外部技能集（如 superpowers）的最优形态：核心触发纪律提炼进 SKILL.md §1 流程编排（任务类型判定四分支），每个子技能独立 .md 放 macdev-skill/skills/ 包内自含（触发条件+步骤+macdev映射表），发布 publish.py 递归含子目录。requirement --kind spec 替代外部 spec 文件（双轨：db+md+json+csv）。

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


### 决策（decisions）— 3 条

#### [17] 会话启动双查协议：git 与 log/plan 地位并列

- 分类: decisions ｜ 标签: — ｜ 时间: 2026-08-14 14:34:19

用户强制：git 查询（铁律3）与 macdev log/plan 查询（铁律10）地位并列，任何会话开始（含全新/压缩后）都必查：先 git branch/status/log 看仓库现状 → 再 log/plan 看开发历史，双查齐备才允许继续操作。

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

