# macdev LOG — 经验沉淀库

> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。
> 共 23 条。

## 随包经验（pkg）— 23 条

### 经验教训（lessons）— 3 条

#### [15] TS monorepo 审计能力边界：完整链仅覆盖 .py，4 维扫描覆盖全仓

- 分类: lessons ｜ 标签: ts,monorepo,audit,boundary ｜ 时间: 2026-08-14 00:35:35

macdev audit 的 parse/chain/analyze（端点提取/亲属追逐/def-use）基于 Python AST，对 TS/JS 项目只收集 *.py（如 deepseek-harness 仅 18 个 .py）。
对 TS 主导项目：
1. 完整链聚焦项目的 Python 侧（如 python/sdk）——files 入口显式列出 .py 核心文件；
2. 4 维扫描（hardcoded/env/data_pools/static_resources）通过 scan.py 的 _JS_SUFFIXES 正则覆盖全仓 TS/JS——scan_dirs 列出 packages/apps 即可；
3. exclude 必须加 lib/（编译产物）、.agents、vendor、*.map、*.tsbuildinfo 剪枝噪声；
4. 期望管理：TS 端点=0 是正常，不是失败。
后续增强方向：TS AST 解析器（tree-sitter）插件化接入 parse 层。

#### [6] 回归语境核实：链图只是线索

- 分类: lessons ｜ 标签: context,memory,rag,verify ｜ 时间: 2026-08-11 20:07:38

宏观链图只给线索，动手前必须 ls/grep/read 回到语境：记忆(memory/)、RAG 注入、ContextProvider 分层、工具注册、中间件链——不核查无法确认真实角色。链图 broken/同名定义可能是参数或 builtin 噪音。

#### [5] 死代码清理要同步删 re-export

- 分类: lessons ｜ 标签: deadcode,export,test ｜ 时间: 2026-08-11 20:07:37

compact_messages/create_auto_compact/create_context_window 这类无调用方但被 __init__ re-export 的函数：删定义时须同步删 __init__ 的 import 与 __all__，否则 hasattr 断言仍绿、公共 API 残留。


### 陷阱（pitfalls）— 10 条

#### [24] 并发修改同一文件：主工作区 vs worktree 双线冲突

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 23:09:28

本次事故：主工作区（master 带用户未提交改动）与 worktree（feat/msg-queue 带 FIFO 改动）同时改 loop.py——两边基线不同，只能逐处精确合并。根因：单主体错误使用 worktree 造成双写。教训：单主体单线，多主体（子代理）才 worktree；并发前先查两边基线；绝不整文件覆盖。铁律13 已修正固化。

#### [23] spec写完未停等审核就实现+plan潦草（HARD-GATE 违反）

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 22:01:17

事故：5 个 spec 全 open 但代码已全部提交（spec1/2/4/5 实现进 git，spec3 只有 plan 0/4）。根因：①spec 写完未导出 REQUIREMENTS.md 呈用户审核，直接进 plan/实现；②plan 潦草——Architecture/Tech Stack 未填、每 task 步骤全是'待补充'占位，颗粒度不对齐 writing-plans。修复：铁律12（spec 写完后必须停等用户明确批准，禁止自行实现；plan 每 task 带 Create/Modify 文件、每 step 带动作+期望结果+TDD 红→绿，禁止'待补充'占位）。教训：设计完成≠可以开工，HARD-GATE 是用户强制门禁。

#### [20] 异步提交期间调 _finishModal 被 submitting 挡 → 复位后必须补 drain

- 分类: pitfalls ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

前端弹窗队列（approval/ask）：_agentModalSubmitting=true 时用户提交 → _finishAgentModal() 内部调 _drainAgentModalQueue() 被 submitting 检查挡住直接 return → finally 复位 submitting 后无人再 drain → 队列下一个弹窗不自动弹出（只有刷新/下次轮询才弹）。修复：submitAskAnswer/webApprovalDecide 的 finally 里 submitting=false 后补 _drainAgentModalQueue()。铁律：异步提交期间的队列推进必须放在 submitting 复位之后，不能依赖 _finishModal 内部 drain。

#### [17] builtin 反射噪音：TypeError/内置异常被误判为 broken 链路断裂

- 分类: pitfalls ｜ 标签: builtin,noise,broken,chain ｜ 时间: 2026-08-14 00:35:57

亲属追逐链把内置异常 TypeError 当作调用目标，判为 🔴 broken（request:177）。
同类已有 builtin 噪音条目（turn.id→turn_id），此处补异常类场景：
链图上的 broken 可能是 builtin/参数/字面量噪音，必须回源码甄别后再下结论（回归语境核实）。

#### [14] macdev 工具 args 中 Windows 路径反斜杠被转义吞掉

- 分类: pitfalls ｜ 标签: windows,path,args,macdev ｜ 时间: 2026-08-14 00:35:35

调用 macdev 工具传绝对路径时，C:\Users\... 的反斜杠在 args 字符串里被 Python 转义为 C:Users...（驱动器相对路径，解析错乱）。
规避：一律用正斜杠 C:/Users/qu/Desktop/...（Path 跨平台兼容）。
教训：工具层的路径参数优先正斜杠；cli_execute 里直接 python -m macdev 不受影响。

#### [8] pathlib glob 拼接陷阱：Path(x)/'**' 后 rglob/glob 返回空

- 分类: pitfalls ｜ 标签: pathlib,glob,oswalk,audit ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/requirement/align.py

Path(root) / Path('**') 拼接后再 .rglob('*.py') 在 Windows 上返回空——'**' 已作为字面路径段处理，递归通配失效。正解：直接 oot.glob('**/*.py')，或参考 audit 用 os.walk 逐目录容错 + 目录名剪枝（断链/权限目录只跳过该目录，不整批丢失）。

#### [7] getattr 默认值让 defuse 噪音 + 语义 bug

- 分类: pitfalls ｜ 标签: defuse,getattr,model ｜ 时间: 2026-08-11 20:07:38

agent_assistant._async_compact 用 getattr(self.agent,'model','') 恒返回空字符串：既让 defuse 扫描报 loose_match(self 无 model 赋值)，又是语义 bug(模型窗口恒 128000)。应取 self.agent.config.model_id。

#### [4] builtin 反射噪音：属性与内置函数同名

- 分类: pitfalls ｜ 标签: reflection,builtin,id ｜ 时间: 2026-08-11 20:07:35

harness/turn.py 的 Turn.id property 与 builtin id() 同名污染符号反射/静态扫描。属性访问重命名为 turn_id，同步更新调用方。

#### [3] 依赖缺失误判：pytest.raises(ModuleNotFoundError) 假绿

- 分类: pitfalls ｜ 标签: test,tiktoken,module ｜ 时间: 2026-08-11 20:07:34

模块内部 import tiktoken 失败抛 ModuleNotFoundError，会让 pytest.raises(ModuleNotFoundError) 误捕获(假绿)。判断模块删除一律用 importlib.util.find_spec(...) is None。

#### [2] namespace package 陷阱：import 判断模块已删会误绿

- 分类: pitfalls ｜ 标签: import,module,test ｜ 时间: 2026-08-11 20:07:19

删除 skills.py 后同名目录 skills/ 仍在，importlib.import_module('mcp.skills') 依然成功(namespace package, __file__=None)。断言模块删除不能用 import 抛异常，改用文件存在性 Path(...skills.py).exists() 或 importlib.util.find_spec(...) is None。


### 模式（patterns）— 7 条

#### [22] worktree 仅用于子代理/多线并行隔离（非默认开发方式）

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 22:01:17

主开发流保持单线（master 直接改）。只有子代理并行开发、多分支实验、高风险隔离才建 worktree。单主体单线最简。铁律13 已修正。

#### [21] Agent 并行 ask 挂起：字典按 rid 隔离 + 全局池无条件注册双保险

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

多个 ask_followup_question 并行挂起时，单值字段会互相覆盖（后一个顶掉前一个→answer 匹配不上）。模式：1) _pending_asks 字典按 rid 独立挂起 + _last_ask_answers 字典按 rid 存答案（并发互不覆盖）；2) answer API 用 has_pending_ask(rid) 精确匹配；3) 全局 pending 池无条件注册（不依赖 SSE 通道存在与否），SSE 推送 + 轮询双保险；4) 挂起线程阻塞循环读 _last_ask_answers[rid]，写答案先于 clear_pending_ask（顺序保证唤醒）；5) 300s 超时兜底 + 池过期清理（320s）防泄漏。

#### [19] 流式 Markdown 渲染：结构未闭合守卫 + 轻量渲染器 + 自适应降级 + 免全量重建

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-14 13:06:37

流式渲染『适当激进 + 无感 + 计算量小』配方：1) _mdStructuralIncomplete 检测代码围栏(```/~~~奇数)/行内公式($奇数，排除$$)未闭合 → 未闭合保持 textContent（不闪烁）；2) 结构完整时用自研轻量行级渲染器（非 markdown-it，<1ms/数百行）流式中实时渲染；3) 自适应降级：超长回复(>800行)流式中纯文本防每30ms全量解析卡顿，流结束 forceRender 强制渲染；4) KaTeX 350ms 节流（renderMathInElement 扫描全 el 不宜逐 token）；5) _streamRendered 键防重（内容未变不重渲染）；6) 流结束免全量重建（finalize 只幂等补收尾+立即 KaTeX），消除'脱掉'闪烁；7) 30ms debounce 合并高频 token。

#### [13] deepseek-harness 开发范式（插件总线 + agent notes + skills 三件套）

- 分类: patterns ｜ 标签: deepseek-harness,monorepo,plugin,cordis ｜ 时间: 2026-08-14 00:35:12

deepseek-harness（@deepseek-ai/dsh-*，vendored Cordis）的规模化开发方式：
1. 插件总线微内核：everything is a plugin，能力按 packages/<group>/<pkg> 分组（core/api/llm/shell/fs/skill/subagent/session/workflow/client...），约 200+ workspace 包；
2. 开发过程留痕：.agents/notes 按状态（archived/implemented/proposed/rejected）× 类别（architecture/bug-fix/feature/process/simplification/testing）沉淀，共 1700+ 篇——这就是项目的'开发史'；
3. 技能化：.agents/skills 一堆 dsh-* SKILL.md（code-review/pre-push-checks/merging-stacked-prs/trim-cot-leakage...），AI 辅助纪律显式化；
4. AGENTS.md 驱动：仓库布局 + 开发规范面向 AI 写，pre-release 期 foundation over blast radius（自由重构不兼容垫片）；
5. 三语文档：*.md + *.zh.md + *.i18n.yaml 三件套；
6. 版本纪律：SQLite SCHEMA_VERSION 单调、SESSION_FORMAT_VERSION=0 无兼容承诺。
与 macdev 哲学同构（插件总线/双轨产物/SKILL.md 指针/经验沉淀），是 monorepo 规模 agent 项目的标杆范式。

#### [11] 测试：随包经验

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-11 21:07:41

通用模式，应落在随包库

#### [9] 插件迁移双轨约定：CRUD 每次变更自动刷新 md+json+csv+db 四件套

- 分类: patterns ｜ 标签: 双轨,audit,oswalk,self-evolve ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/requirement

新插件（如 requirement）任何变更（add/update/delete/align）后自动 refresh 双轨产物：db 权威 + json/csv 机器快照 + md 人类可读，时间戳 UTC、编码 utf-8，语言环境无关。代码扫描参考 audit 健壮性：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过（常规大文件不跳过）。

#### [1] skill 体系三分类（A/B/C）

- 分类: patterns ｜ 标签: skill,mcp,refactor ｜ 时间: 2026-08-11 20:07:18

审查 skill 管理链路时先按性质分类：A 类文本技能(SKILL.md+scripts)归唯一注册表门面；B 类硬编码工具(skill_xxx handler/builtin)迁 tools.py 注册 Tool 子类；C 类远程 MCP(技能目录 mcp.json)统一并入 mcp_servers.json(service_type=mcp, transport=stdio|http|sse)，技能包内 mcp.json 保留为外部客户端配置模板。


### 决策（decisions）— 3 条

#### [18] SKILL.md 自演化：新增 §8 开发安全铁律（危险 git 先问 + 启动查 git + 双轨产物）

- 分类: decisions ｜ 标签: — ｜ 时间: 2026-08-14 03:48:09

用户明确要求自演化 skill（而非仅项目 log）：在 macdev-skill/SKILL.md 与 skills_market/macdev-skill/macdev-skill/SKILL.md 同步追加 §8 开发安全铁律：①危险 git 命令（checkout/reset/clean/push/merge/revert/branch -D/rm）必须先问用户，只读命令随时可跑；②未追踪文件不假设不重要，删除/覆盖/忽略前逐项确认；③上下文开始/压缩后第一时间 git branch -a + status --short + log --oneline -15；④动手前查 macdev log list 与 plan list；⑤macdev 操作必须生成双轨产物（db/csv/json + md）收敛到 <name>-project/；⑥自演化优先：规则固化进 SKILL.md + 随包 log。优先级：用户指令 > skill 内部约定（覆盖原'经验只写 log 不写 SKILL.md'条款）。

#### [16] dsh 策略设计决策：TS monorepo 审计配置

- 分类: decisions ｜ 标签: decision,dsh-strategy,audit ｜ 时间: 2026-08-14 00:35:57

新增 audit.strategy=dsh（strategy_dsh.py）：
1. known_type_files 映射 @deepseek-ai/dsh-* 核心类型 → packages/<group>/<pkg>/src/index.ts（兜底路径带 * 组号）；
2. resolve_type_file 覆写为 .ts 后缀（TS 源文件）；
3. AuditTask（dsh-task.json）：files 入口聚焦 python/sdk（完整链），scan_dirs=packages/apps/python/scripts（4 维扫描全仓），exclude 加 lib/.agents/vendor/website/__snapshots__；
4. chains.entries 必须用 dict（kind=function/name=Class.method 或 kind=endpoint/prefix），字符串会炸 AttributeError。
验证：audit ok=True，亲属追逐链对 HarnessClient.initialize/request 正确展开。
关键取舍：TS 端点提取暂不支持（AST 边界），以 SDK 完整链 + 全仓 4 维扫描为组合覆盖。

#### [10] 大文件跳过阈值：文件大小不是问题，仅 12MB 以上极端生成产物跳过

- 分类: decisions ｜ 标签: 阈值,audit,requirement ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/audit/runner.py

audit collect_files 与 requirement build_code_index 统一：>12MB 才跳过（编译/生成产物），常规大文件不跳过。原 1MB 阈值过小，会漏审真实大文件。

