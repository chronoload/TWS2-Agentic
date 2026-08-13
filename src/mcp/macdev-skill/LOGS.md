# macdev LOG — 经验沉淀库

> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。
> 共 5 条。

## 随包经验（pkg）— 5 条

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


### 陷阱（pitfalls）— 2 条

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


### 模式（patterns）— 1 条

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


### 决策（decisions）— 1 条

#### [4] dsh 策略设计决策：TS monorepo 审计配置

- 分类: decisions ｜ 标签: decision,dsh-strategy,audit ｜ 时间: 2026-08-14 00:35:57

新增 audit.strategy=dsh（strategy_dsh.py）：
1. known_type_files 映射 @deepseek-ai/dsh-* 核心类型 → packages/<group>/<pkg>/src/index.ts（兜底路径带 * 组号）；
2. resolve_type_file 覆写为 .ts 后缀（TS 源文件）；
3. AuditTask（dsh-task.json）：files 入口聚焦 python/sdk（完整链），scan_dirs=packages/apps/python/scripts（4 维扫描全仓），exclude 加 lib/.agents/vendor/website/__snapshots__；
4. chains.entries 必须用 dict（kind=function/name=Class.method 或 kind=endpoint/prefix），字符串会炸 AttributeError。
验证：audit ok=True，亲属追逐链对 HarnessClient.initialize/request 正确展开。
关键取舍：TS 端点提取暂不支持（AST 边界），以 SDK 完整链 + 全仓 4 维扫描为组合覆盖。

