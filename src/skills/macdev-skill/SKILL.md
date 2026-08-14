---
name: macdev
description: 机器驱动开发范式库：加载即用的流程编排（启发式扫描→编排 audit task→读产物知架构→跟随链路审查→可选 patch→grilling/spec→plan→再审查），audit 兼具静态审计与快速探索双用途。Use when auditing call chains, generating architecture docs, running structured plan workflows, or onboarding large codebases.
---

# macdev — 机器驱动开发范式库

> **加载即用**：本文档不是用来复述的。第一条消息就直接按下方「流程编排」开始干活；
> 所有命令细节以 `PLAN.md` / `AUDIT_DOC.md` 为准，不确定就查文档，不靠猜。

## 0. 强制前置（**必须读完**，读完才算加载完成）

> ⚠️ **一定要读**：首次使用（或文档更新）时必须完整阅读下列全部使用文档与子技能，
> 读完才算加载完成，否则禁止动手。文档若缺失或过期：先 `python -m macdev doc` 重生成，再读。

**使用文档（命令全集，包内自包含 `macdev/doc/`，发布版在 `macdev-skill/` 同名）：**

- **PLAN.md** — plan 命令全集：create/task/step/export/verify/review/ledger/tdd/openspec + 状态机
- **AUDIT_DOC.md** — audit 命令全集：audit task / chain 定向查询（endpoints/issues/models/drifts/tables）+ patch 自演化闭环
- **LOG_DOC.md** — log 经验沉淀命令全集：四分类 add/list/query/export/update/delete（project/pkg 双轨）
- **REQI_DOC.md** — requirement 命令全集：需求 CRUD + align/scan（interface/path/file/spec 四类 + 双轨产物）
- **DEV_DOC.md** — dev 命令全集：学习/模仿目标项目（map 目录编排 + audit 架构了解）

**子技能（整合 superpowers 纪律，见 §9 索引）：** `skills/brainstorming.md`、`skills/systematic-debugging.md`、
`skills/test-driven-development.md`、`skills/using-superpowers.md`、`skills/verification-before-completion.md` 等 14 个。

**开发文档（架构 + 模块函数索引，扩展时才需要）：** AUDIT_DEV_DOC / PLAN_DEV / LOG_DEV / REQI_DEV / DEV_DEV

## 0.5 学习/模仿目标项目（dev 也是一种用法）

陌生项目怎么起来的？用 dev 扫一遍就能编排目录 + 了解架构（产物收敛到 `<name>-project/dev/<目标名>/`）：

```bash
python -m macdev dev map --target <项目目录> --project ts2     # 目录编排：树+模块地图+技术栈线索
python -m macdev dev audit --target <项目目录> --project ts2   # 架构了解：自动编排 audit 快速探索
```

- **map**：DIR_TREE.md（人类）+ dir_tree.json/csv/db（机器）双轨产物
- **audit**：INTERFACE_CHAIN.md + interface_chain.db + 全维度 CSV（复用 audit 双轨）
- 想模仿就对着 map 的模块地图 + audit 的依赖链照做；这也是 onboarding 陌生仓库最快路径。

## 1. 流程编排（任务类型判定 → 对应纪律分支）

> 每个任务第一步：**判定类型**（吸收 superpowers 触发纪律），再走对应分支。
> 判定不追求完美——隐藏复杂度出现时随时升级分支（单向棘轮：只升级不降级）。

### 0) 类型判定（必做，先于任何动作/澄清/探索）

| 任务类型 | 判定特征 | 走哪条纪律 |
|---|---|---|
| **Bounded** | 改动既有代码流（新 flag/小端点/单文件修复），流已存在可读 | 短设计 chat 批准 → 直接实施（TDD） |
| **Architectural** | 新子系统/重构组件关系/影响他人接口 | brainstorming → requirement spec → plan |
| **Spike** | 可行性问题（"能不能…/是否可能…/快速验证"） | 探针说明 → 点头 → 验证 → 汇报建议 |
| **Bug** | 缺陷现象 | systematic-debugging → patch 闭环 |

> 不确定时取更重一档；mid-task 发现复杂度升级 → 停下说明并升级，永不降级。

### 1) Bounded：短设计 → 批准 → 实施
1. 读既有流程（ls/grep/read 语境核实，不臆断）
2. chat 内短设计（改动文件 + 测试方式），**等用户批准**
   （HARD-GATE：批准前不动手；简单任务也需批准——"太简单不用设计"是反模式）
3. 实施走 plan（TDD 节奏）或直接改 + 测试

### 2) Architectural：brainstorming → requirement(spec) → plan
1. **grilling/brainstorming**（一次一个问题，优先选择题）：
   - 澄清：目的/约束/成功标准
   - 提 2-3 方案 + 权衡 + 推荐（YAGNI 砍冗余）
   - 分段展示设计，逐段获批（HARD-GATE：设计批准前不写实现）
2. **spec 由 requirement 组件替代**（不写 design doc 文件）：
   - `requirement add --kind spec --name ... --detail ...`（机器权威，双轨自动刷新）
   - `requirement export` → REQUIREMENTS.md 人类轨；`requirement align` → 代码/端点对齐
   - 自审（placeholder/一致性/范围/歧义）→ 用户审查 REQUIREMENTS.md 后放行
3. **plan 实施**：`plan create/task/step`（TDD 节奏）+ 实施后重审计收敛

### 3) Spike：探针 → 汇报
1. 2-3 句说明问题与探针方案 → 用户点头
2. 尽可能廉价验证（audit 快速探索 / 小脚本）
3. 汇报结论为**建议**；临时产物标注 throwaway，不保留

### 4) Bug：systematic-debugging → patch 闭环
1. **复现**：最小复现路径（测试/脚本）
2. **根因分析**：5-Why / 二分定位；不臆断，回语境核实
3. **假设→验证**：写失败测试（expected FAIL）→ 修复 → 转绿
4. `patch gen/apply/verify` 收敛 + 重审计对比

### 5) 通用纪律（所有分支生效）
- **TDD 节奏**：step 先红后绿（`--action test --expected FAIL` → 实现 → 转绿）
- **完成门禁**：`plan verify`（TDD 合规 + 缺陷清零 + 测试就位 + review）
- **review 循环**：`plan review --action request/approve`；需要时 `sub_agent(agent=review)` 指派
- **subagent 执行**：`step` 可指派 `sub_agent(agent=coder|research|task)`；并行用 team 工具
- **分支收尾**：完成后合并/清理分支（git 危险操作按 §8 铁律先确认）

### 6) 理解系统主线（audit 快速探索，作为上述分支的手段）

```bash
# 编排一屏流
python -m macdev audit --task task.json --root . --out out      # 1. 审查
python -m macdev audit chain endpoints --db out/interface_chain.db  # 2. 快速索引
python -m macdev patch gen --db out/interface_chain.db --root . --out patches/   # 4. 可选
python -m macdev requirement add --kind spec --name X --detail "..."  # 2. spec(替代 design doc)
python -m macdev plan create --title "..." --goal "..."          # 3. 开发流程
python -m macdev plan task add --plan 1 --title "T1" --detail "..."
python -m macdev plan step add --task 1 --text "写失败测试" --action test --run "pytest -q" --expected "FAIL"
python -m macdev plan verify --plan 1                            # 完成门禁
python -m macdev audit --task task.json --root . --out out2      # 再审查（收敛对比）
```

> 子技能速查：`skills/brainstorming.md`、`skills/systematic-debugging.md`、
> `skills/test-driven-development.md`、`skills/using-superpowers.md` 等（见 §9）。

## 2. audit 双用途（审查 + 快速探索）

- **审查**：8 维分析（def-use/行为契约/链路断裂/状态标志/合并仲裁/命名空间）+ 4 维扫描
  （硬编码/env/数据池/静态资源）→ 缺陷清单，供修复与 verify 门禁。
- **快速探索**（同等重要）：从任意入口（端点 prefix/函数名/`Class.method`）生成依赖链图，
  就是最快的系统地图。不确定「某功能在哪、谁在调谁」时，audit 比 grep 快。

## 3. 设计哲学（浓缩，展开版见 AUDIT_DEV_DOC.md）

1. **插件总线微内核**：core 只有 Registry + EventBus + Engine，能力皆可挂载插件。
2. **零特化**：项目语义 = AuditTask JSON + ChainStrategy 子类，内核零改动。
3. **双轨产物**：机器可读（db/csv/json/事件流）+ 人类可读（md/亲属追逐图）。
4. **亲属追逐**：跨文件调用反射全项目符号索引定位（↦ 亲属 / 🔴 broken 一步定位）。
5. **插件平级**：审查/修复/展示皆继承统一 `Plugin` 接口，被 `Registry.discover()` 扫描捕捉。

## 4. 双轨产物

- 机器可读：interface_chain.db / *.csv / *.json / events.ndjson（可重放）
- 人类可读：INTERFACE_CHAIN.md（亲属追逐图）/ PLAN.md（writing-plans 格式）

## 5. 安装 / 自举 / 扩展 / 打包

- 安装：`python macdev/scripts/install.py`（写 .pth 注册到当前解释器）
- 自举文档：`python -m macdev doc` → macdev-skill/ + 包内 macdev/doc/，代码为唯一事实源
- 扩展：新增策略 = `ChainStrategy` 子类；新增能力 = `Plugin` 子类（一个文件），内核零改动
- 打包成可执行文件：`python macdev/scripts/build_exe.py` → `dist/macdev.exe`（pyinstaller 单文件，
  含全部插件 + 随包数据 macdev-skill/ 与 macdev/doc/；无需 Python 环境即可运行）

## 6. 经验沉淀：走 log 插件，不写进 SKILL.md

经验/教训/模式沉淀在 **log 插件**（与 plan 平级），SKILL.md 只留本指针，避免文档膨胀不通用。
经验分**随项目**（project，最主要，须指定项目文件夹）与**随包**（pkg，通用方法论随 skill 分发）双轨，
随项目产物全部落在 `<name>-project/`，包内（macdev-skill）保持干净只放随包经验：

- **随项目（最主要，必须指定）**：`log add --project <name> --title ... --category ...`
  → `<name>-project/logs.db` + `LOGS.md`（条目 scope=project；缺 --project/env 会报错，不落 cwd）
- **随包**：`log add --scope pkg --title ... --category ...`
  → `macdev-skill/logs.db` + `LOGS.md`（条目 scope=pkg，通用方法论随 skill 分发）
- 显式 `--db` 始终优先；`log list/query/export [--scope project|pkg]` 按归属过滤
- 机器可查：`python -m macdev log query --keyword <词> [--category ...] [--scope ...]`
- 列出/查看/导出：`log list [--category]` / `log get --id N` / `log export [--out LOGS.md]`
- 项目级经验走 `<name>-project/logs.db`（见 §7 产物目录约定）

典型已沉淀条目：skill 三分类(A/B/C)、namespace package 陷阱、依赖缺失误判(find_spec)、
builtin 反射噪音(turn.id→turn_id)、死代码 re-export 清理、回归语境核实、getattr 默认值陷阱、
pathlib glob 拼接陷阱、双轨产物约定(requirement 参考 audit 扫描健壮性)、大文件阈值决策(12MB)。

## 7. 产物目录约定（<name>-project/，全部产物不溢出）

整个工作流的产物收敛到唯一目录 `<name>-project/`，重跑覆写、不另建新目录：

```
python -m macdev project init --name ts2 [--git]     # 建 ts2-project/（可选 git init 追踪）
python -m macdev project list                        # 列出已初始化的产物目录
```

- **audit** → `ts2-project/audit/`：`audit --project ts2`（或显式 `--out` 优先）；重跑同目录覆写
- **plan**  → `ts2-project/plans.db` + 导出的 .md（`plan export --out ts2-project/...`）
- **log**   → `ts2-project/logs.db` + `LOGS.md`
- **requirement** → `ts2-project/requirements.db` + `REQUIREMENTS.md` / `requirements.json` / `requirements.csv`
  （双轨自动同步）；对齐产物 `REQUIREMENT_ALIGNMENT.md` + `requirement_alignment.json/csv/db`

指向方式：显式 `--project <name>`（audit 支持）或环境变量 `MACDEV_PROJECT=<name>`
（plan/log/requirement 全部子命令缺省 db/out 自动收敛）；显式 `--db`/`--out` 始终优先。
不设置时保持 cwd 下的 `plans.db` / `logs.db` / `requirements.db` 缺省行为，不强制。

## 8. 开发安全铁律（用户强制，自演化固化——违反即停）

以下规则由用户明确要求固化进 skill 本体，任何会话/上下文（含压缩恢复后）都必须无条件遵守：

1. **危险 git 命令必须先问**：自演化/开发流程中，绝不允许在未向用户提问确认前直接执行任何危险 git 命令
   （`checkout` / `reset` / `clean` / `push` / `force-push` / `merge` / `revert` / `branch -D` / `rm` 等）。
   只读命令（`status` / `branch` / `log` / `diff` / `show`）可随时直接执行。
2. **绝不假设未追踪（untracked）文件不重要**：`git status` 中的 `??` 项在删除/覆盖/忽略前必须逐项向用户确认，
   不得擅自忽略或清理。
3. **上下文开始/压缩后第一步查 git 状态**：任何新上下文开始、或上下文压缩恢复后，第一时间执行
   `git branch -a` + `git status --short` + `git log --oneline -15`，看清分支/提交/工作区现状再动手。
4. **动手前查阅 macdev log 与 plan**：用 `log list/query` 与 `plan list` 了解开发历史与进行中的计划，
   避免重复劳动或遗漏未完成事项。
5. **macdev 操作必须生成双轨产物**：机器可读（db/csv/json）+ 人类可读（md）双轨缺一不可；
   产物收敛到 `<name>-project/`，重跑覆写、不另建新目录。
6. **自演化优先**：新教训/规则优先固化进本 SKILL.md（§8 或新章节）+ 随包 log（scope=pkg），
   让能力随使用进化，而非仅停留在项目级 log。
7. **跨目录覆盖/部署/批量删除文件先问**：向私有部署或其他目录复制/覆盖文件（`copy`/`cp` 覆盖部署、
   跨目录同步）、批量删除文件（`del`/`rm` 通配）、覆盖写入配置文件等破坏性文件操作，执行前先向用户
   确认目标目录与文件范围（多候选时用提问确认，如多个同名部署目录）；`dir`/`ls`/`git status` 等只读
   查看可随时直接执行。覆盖后必须做一致性验证（哈希/语法检查）。
8. **任务必须先判定类型再动手（superpowers 触发纪律）**：任何任务（含澄清/探索/查文件之前）第一步
   按 §1-0 判定类型（Bounded/Architectural/Spike/Bug）并走对应纪律分支；"只是简单问题/先看下代码/
   先查下文件"都是反模式——技能检查先于一切动作；判定后若发现更复杂，停下升级分支（单向棘轮）。
9. **完整阅读 DOC 与子技能后才算加载完成（用户强制）**：首次使用 macdev（或文档更新）必须按 §0
   读完全部使用文档 + 子技能，禁止跳读/凭记忆使用；不确定命令细节时回查对应 DOC，不靠猜。
10. **上下文残缺/不确定 → 立即查 log 与 plan（用户强制）**：对话出现信息残缺、记忆断层、或对
    "当前做了什么/部署在哪/某能力现状"不确定时，**立刻**查阅**随包 log**（`log list --scope pkg`）
    与**随项目 log/plan**（`log list --scope project`、`plan list`、`log query --keyword <词>`），
    找回既定事实与历史轨迹，**禁止凭猜测回答或继续操作**；私有部署等外部环境信息同样先查
    log/plan/会话缓存确认，再动手。

> 本节优先级高于 skill 内其他「经验只写 log 不写 SKILL.md」的约定——用户指令 > skill 内部约定。

## 9. 能力总览（自 DOC 自演化，命令全集以对应 DOC 为准）

### 顶层命令（`python -m macdev <cmd>`，或经 macdev 工具）

| 命令 | 能力 | 关键子命令 |
|---|---|---|
| **audit** | 静态接口审计 + 快速探索（8 维分析 + 4 维扫描 → 双轨产物） | task / chain（endpoints/issues/models/drifts/tables/stats） |
| **plan** | 开发流程机器化（状态机 + 双轨导出 + 完成门禁） | create/list/update/delete / task / step / export / verify / review / ledger / tdd / openspec |
| **patch** | 自演化补丁（插件式修复闭环） | gen / apply / verify / plugins |
| **log** | 经验沉淀库（四分类 + project/pkg 双轨） | add/list/get/query/export/update/delete |
| **requirement** | 需求管理 + 代码/端点对齐（**spec 替代组件**） | add/list/update/delete/export / align / scan |
| **dev** | 学习/模仿目标项目 | map / audit |
| **project** | 产物目录约定（<name>-project/ 收敛） | init / list / root |
| **doc** | 自举生成使用/开发文档（代码为唯一事实源） | — |

### 子技能索引（skills/，superpowers 纪律整合，14 个）

| 子技能 | 触发场景 | macdev 映射 |
|---|---|---|
| using-superpowers.md | 任何会话开始（技能触发纪律） | §1-0 类型判定 |
| brainstorming.md | 构思/新功能/架构 | §1-2 grilling + requirement(spec) |
| systematic-debugging.md | Bug/缺陷 | §1-4 复现→根因→patch |
| writing-plans.md | 计划文档 | plan export --format writing-plans |
| test-driven-development.md | 实现 | plan step --action test（红→绿） |
| verification-before-completion.md | 收尾 | plan verify（完成门禁） |
| requesting-code-review.md / receiving-code-review.md | 审查 | plan review |
| subagent-driven-development.md | 子任务执行 | sub_agent(agent=coder/research/task) |
| dispatching-parallel-agents.md | 并行 | team 工具 |
| executing-plans.md | 计划执行 | plan ledger（resume） |
| finishing-a-development-branch.md | 分支收尾 | git 流程（按 §8 确认） |
| using-git-worktrees.md | 多分支 | git worktree（按 §8 确认） |
| writing-skills.md | 自演化新技能 | skill-creator + log 沉淀 |

### 注册表能力（扩展用）

| 命名空间 | 已注册项 |
|---|---|
| `audit.strategy` | base, ts2 |
| `patch.generator` | insert_defuse_comment, insert_entry_comment, insert_env_todo, insert_guard_comment, insert_merge_comment, insert_reset_comment, insert_set_after_clear, insert_todo_comment |
| `plan.runner` | default |
