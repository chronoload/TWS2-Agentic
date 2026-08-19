# macdev audit 使用文档（自举生成）

> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。

## 宏观用法（先整体，再定向）

1. **宏观全景**：`python -m macdev audit --task task.json --root . --out out`
   → INTERFACE_CHAIN.md（§8 亲属追逐依赖链 text 树 + mermaid + 断裂索引）。
2. **定向查询**：`python -m macdev audit chain endpoints|issues|models|drifts|tables`
   → 对 interface_chain.db 做 SQL 级查询，替代 grep-read。
3. **缺陷闭环（附加值）**：缺陷清单用于修复，不是主产品。

## 自演化补丁（插件式修复，与工厂平级）

patch 不是直接改原文件——修复插件（PatchPlugin 子类）继承统一抽象接口 Plugin，
被 `Registry.discover()` 扫描捕捉（namespace=patch.generator），与 audit.strategy 平级。
审计缺陷 → `patch gen` 生成固化补丁脚本（产物，不改源码）；`patch apply` 显式应用；
`patch verify` 重审计对比缺陷收敛。
```
python -m macdev patch gen --db out/interface_chain.db --root . --out patches/
python -m macdev patch apply --dir patches/ --root .
python -m macdev patch verify --before out/interface_chain.db --after out2/interface_chain.db
python -m macdev patch plugins   # 列出被扫描捕捉的修复插件
```

## 命令参数树（argparse 底层反射）

```
`macdev` — 机器驱动开发范式库（插件总线微内核）

`macdev audit` — 静态接口审计

- `--task` — AuditTask JSON
- `--root` — 项目根（task 相对路径基准） 默认=`.`
- `--out` — 输出目录 默认=`macdev_out`
- `--project` — 产物目录名：out 缺省指向 <name>-project/audit（重跑覆写）
- `--timeout` — 扫描超时秒数（覆盖 task.scan_timeout，0=不限；超时截断子集汇报）
- `--no-progress` — 关闭进度打印

`macdev audit chain` — 定向查询 interface_chain.db

`macdev audit chain stats` — 统计

- `--db` — interface_chain.db 路径

`macdev audit chain issues` — 缺陷（--count 分布 / --kind/--file/--attr 过滤）

- `--db` — interface_chain.db 路径
- `--count` — issues: 类型计数分布
- `--kind` — issues: 缺陷类型过滤（逗号分隔）
- `--file` — issues: 文件过滤
- `--attr` — issues: 属性过滤

`macdev audit chain endpoints` — 端点（--by-file/--path/--func/--no-model）

- `--db` — interface_chain.db 路径
- `--by-file` — endpoints: 按文件分组
- `--path` — endpoints: 路径过滤
- `--func` — endpoints: 函数过滤
- `--no-model` — endpoints: 无请求模型的端点

`macdev audit chain models` — 模型（--dup 重复定义 / --name 过滤）

- `--db` — interface_chain.db 路径
- `--dup` — models: 跨文件重复定义
- `--name` — models: 模型名过滤

`macdev audit chain drifts` — 语义漂移

- `--db` — interface_chain.db 路径

`macdev audit chain tables` — 表结构

- `--db` — interface_chain.db 路径

`macdev audit chain callers` — 按符号追调用链（--func：上游谁调 X + 下游 X 调谁）

- `--db` — interface_chain.db 路径
- `--func` — callers: 函数名

`macdev audit chain kw` — 关键字微扫描（--keyword：refs 引用位置 def/use 标注）

- `--db` — interface_chain.db 路径
- `--keyword` — kw: 关键字

`macdev plan` — 开发流程机器化

`macdev plan create` — 创建 plan

- `--title`（必填） — 
- `--name` — 计划名（id=YYYYMMDD_<name>；缺省取 title 的 slug）
- `--goal` — 
- `--arch` — 
- `--stack` — 
- `--constraints` — 
- `--db` — 
- `--index` — audit 缺陷 index.json（defect 状态展示）
- `--reqdb` — requirements.db 路径

`macdev plan list` — 列出 plan

- `--db` — 

`macdev plan update` — 更新 plan

- `--id` — plan id（YYYYMMDD_<name> 或旧数字 id）
- `--title` — 
- `--goal` — 
- `--arch` — 
- `--stack` — 
- `--constraints` — 
- `--status` — 
- `--db` — 

`macdev plan delete` — 删除 plan

- `--id`（必填） — 
- `--db` — 

`macdev plan task` — 任务管理

`macdev plan task add`

- `--plan`（必填） — plan id
- `--title`（必填） — 
- `--detail` — 
- `--files` — 
- `--req` — 
- `--defect` — 
- `--interfaces` — 
- `--db` — 

`macdev plan task list`

- `--plan`（必填） — plan id
- `--db` — 

`macdev plan task update`

- `--id`（必填） — 
- `--title` — 
- `--detail` — 
- `--files` — 
- `--req` — 
- `--defect` — 
- `--interfaces` — 
- `--status` — 
- `--review-status` — 
- `--findings` — 
- `--db` — 

`macdev plan task delete`

- `--id`（必填） — 
- `--db` — 

`macdev plan step` — 步骤管理

`macdev plan step add`

- `--task`（必填） — 
- `--text`（必填） — 
- `--action` — test|implement|run|commit|other 默认=`other`
- `--code` — 
- `--lang` — 
- `--run` — 
- `--expected` — 
- `--db` — 

`macdev plan step list`

- `--task`（必填） — 
- `--db` — 

`macdev plan step update`

- `--id`（必填） — 
- `--text` — 
- `--action` — 
- `--status` — 
- `--db` — 

`macdev plan step delete`

- `--id`（必填） — 
- `--db` — 

`macdev plan export` — 导出 plan（writing-plans/table + json）

- `--id`（必填） — plan id
- `--out` — 输出 .md 路径
- `--format` —  可选=`writing-plans/table` 默认=`writing-plans`
- `--db` — 

`macdev plan verify` — 完成门禁

- `--plan` — plan id（缺省全部）
- `--root` — 项目根（测试文件存在性校验基准） 默认=`.`
- `--db` — 

`macdev plan review` — review 循环

- `--task`（必填） — 
- `--action`（必填） —  可选=`request/approve/reject/fix`
- `--findings` — 
- `--db` — 

`macdev plan ledger` — 进度台账

- `--plan`（必填） — plan id
- `--out` — 
- `--db` — 

`macdev plan tdd` — TDD 合规检查

`macdev plan tdd check`

- `--db` — 

`macdev plan openspec` — openspec 桥接

`macdev plan openspec list`

- `--cwd` —  默认=`.`

`macdev plan openspec status`

- `--change` — 
- `--cwd` —  默认=`.`
- `--req-cli` — sync-specs: 写 requirements 的命令模板

`macdev plan openspec import`

- `--change` — 
- `--cwd` —  默认=`.`
- `--req-cli` — sync-specs: 写 requirements 的命令模板

`macdev plan openspec export`

- `--change` — 
- `--cwd` —  默认=`.`
- `--req-cli` — sync-specs: 写 requirements 的命令模板

`macdev plan openspec sync-specs`

- `--change` — 
- `--cwd` —  默认=`.`
- `--req-cli` — sync-specs: 写 requirements 的命令模板

`macdev patch` — 自演化补丁（插件式修复）

`macdev patch gen` — 从审计缺陷生成固化补丁脚本

- `--db`（必填） — interface_chain.db 路径
- `--root` — 项目根（缺陷 file 相对基准） 默认=`.`
- `--out` — 补丁脚本输出目录 默认=`patches`

`macdev patch apply` — 应用补丁（备份 + 幂等，显式操作）

- `--patch` — 单个补丁脚本
- `--dir` — 补丁目录（*.py）
- `--root` — 项目根 默认=`.`
- `--no-backup` — 不写 .bak.macdev 备份

`macdev patch verify` — 自演化闭环验证：补丁前后缺陷对比

- `--before`（必填） — 补丁前 interface_chain.db
- `--after`（必填） — 重审计后的 interface_chain.db

`macdev patch plugins` — 列出被抽象接口扫描捕捉的修复插件

`macdev log` — 经验沉淀库（文档+db，SKILL.md 经验移入此处）

`macdev log add` — 新增一条经验/教训/模式/决策

- `--title`（必填） — 
- `--category`（必填） —  可选=`lessons/pitfalls/patterns/decisions`
- `--body` — 正文（支持 \n 转义，或用 --file 从文件读）
- `--file` — 从文件读正文
- `--tags` — 逗号分隔标签
- `--refs` — 关联文件/产物路径
- `--scope` — 经验归属：project=随项目（默认，最主要）/ pkg=随包 可选=`project/pkg` 默认=`project`
- `--project` — 
- `--db` — 

`macdev log list` — 列出记录

- `--category` — 
- `--tag` — 
- `--scope` — 归属过滤（缺省全部） 可选=`/project/pkg`
- `--project` — 
- `--db` — 

`macdev log get` — 查看单条

- `--id`（必填） — 
- `--project` — 
- `--db` — 

`macdev log query` — 全文检索

- `--keyword`（必填） — 
- `--category` — 
- `--scope` — 归属过滤（缺省全部） 可选=`/project/pkg`
- `--project` — 
- `--db` — 

`macdev log export` — 导出 LOGS.md 人类可读文档

- `--out` — 输出 .md 路径（缺省 logs.db 同目录 LOGS.md）
- `--scope` — 归属过滤（缺省全部） 可选=`/project/pkg`
- `--project` — 
- `--db` — 

`macdev log update` — 更新记录

- `--id`（必填） — 
- `--category` —  可选=`lessons/pitfalls/patterns/decisions`
- `--title` — 
- `--body` — 
- `--tags` — 
- `--refs` — 
- `--scope` — 调整归属 可选=`project/pkg`
- `--project` — 
- `--db` — 

`macdev log delete` — 删除记录

- `--id`（必填） — 
- `--project` — 
- `--db` — 

`macdev requirement` — 需求管理（CRUD + 规范接口对齐，双轨产物）

`macdev requirement add` — 新增需求条目

- `--kind`（必填） —  可选=`interface/path/file/spec`
- `--name`（必填） — 接口/路径/文件名
- `--detail` — 说明
- `--source` — 来源（如 brief-1） 默认=`cli`
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement list` — 列出需求

- `--kind` —  可选=`interface/path/file/spec`
- `--status` —  可选=`open/done/missing`
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement update` — 更新需求

- `--id`（必填） — 
- `--kind` —  可选=`interface/path/file/spec`
- `--name` — 
- `--detail` — 
- `--source` — 
- `--status` —  可选=`open/done/missing`
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement delete` — 删除需求

- `--id`（必填） — 
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement export` — 刷新双轨产物（md/json/csv/all）

- `--format` —  可选=`md/json/csv/all` 默认=`all`
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement align` — DB 需求 → 代码/端点对齐，回写 missing

- `--index` — interface_chain_index.json 路径
- `--root` — 代码扫描项目根（缺省 cwd）
- `--exclude` — 逗号分隔排除目录（剪枝，如 node_modules,tests）
- `--db` — 
- `--out` — 
- `--project` — 

`macdev requirement scan` — 扫描需求文档目录提取声明并对齐

- `--req-dirs` — 逗号分隔需求文档目录（缺省探测 .opencode/sdd 等）
- `--code` — 逗号分隔代码扫描扩展名 glob（如 **/*.py）
- `--index` — interface_chain_index.json 路径
- `--root` — 项目根（扫描/代码基准，缺省 cwd）
- `--exclude` — 逗号分隔排除目录（剪枝）
- `--db` — 
- `--out` — 
- `--project` — 

`macdev dev` — 学习/模仿目标项目（目录编排 + 架构了解）

`macdev dev map` — 扫描目标项目编排目录（树 + 模块地图 + 技术栈线索，双轨产物）

- `--target`（必填） — 要学习的目标项目目录
- `--depth` — 目录树深度（缺省 3） 默认=`3`
- `--exclude` — 逗号分隔排除目录（剪枝）
- `--out` — 产物输出目录
- `--project` — 

`macdev dev audit` — 架构了解：自动编排默认 AuditTask 跑快速探索（复用 audit 双轨）

- `--target`（必填） — 要学习的目标项目目录
- `--strategy` — 审计策略名（缺省 base） 默认=`base`
- `--exclude` — 逗号分隔排除目录（剪枝）
- `--timeout` — 扫描超时秒数（0=不限）
- `--out` — 产物输出目录
- `--project` — 

`macdev project` — 产物目录约定（<name>-project/ 收纳 audit/plan/log 全部产物）

`macdev project init` — 初始化产物目录（可选 git init）

- `--name`（必填） — 项目名（产物目录 = <name>-project/）
- `--git` — 同时 git init 追踪
- `--base` — 产物目录的父路径（缺省 cwd）

`macdev project list` — 列出已初始化的产物目录

- `--base` — 

`macdev project root` — 打印产物目录绝对路径

- `--name`（必填） — 
- `--base` — 

`macdev doc` — 自举生成使用/开发文档

- `--out` — 自举文档输出目录 默认=`macdev-skill`

`macdev skill` — 子技能动态注入（scan/inject/route/list）

`macdev skill list` — 列出默认目录下子技能名

- `--dir` — 技能目录（缺省探测 skills/ 与 skills_market/）
- `--root` — 缺省技能目录的基准根 默认=`.`

`macdev skill scan` — 扫描目录列出子技能含推断字段

- `--dir` — 技能目录（缺省探测 skills/ 与 skills_market/）
- `--root` — 缺省技能目录的基准根 默认=`.`

`macdev skill inject` — 整文件内容输出到 stdout（--name 指定子技能）

- `--name`（必填） — 子技能名（文件名，不含 .md）
- `--dir` — 技能目录（缺省探测 skills/ 与 skills_market/）
- `--root` — 缺省技能目录的基准根 默认=`.`

`macdev skill route` — 任务描述 → 自动匹配子技能名（--task）

- `--task`（必填） — 任务描述
- `--dir` — 技能目录（缺省探测 skills/ 与 skills_market/）
- `--root` — 缺省技能目录的基准根 默认=`.`
```

## 产物清单

- **INTERFACE_CHAIN.md**：审计报告：端点/模型 + §8 亲属追逐依赖链(text+mermaid) + 6 维分析 + 4 维扫描
- **interface_chain.db**：SQLite 全维度可查询索引（endpoints/models/drifts/defuse/behavior/flag/merge/id_source/扫描/stats）
- **endpoints.csv / models.csv / drifts.csv**：端点/模型/漂移明细
- **defuse_issues.csv / defuse_reads.csv**：def-use 缺陷与读取点
- **behavior_issues.csv / flag_lifecycle.csv**：行为契约 / 状态标志缺陷
- **merge_direction.csv / id_source.csv**：合并仲裁 / 命名空间缺陷
- **hardcoded.csv / env_vars.csv / data_pools.csv / static_resources.csv**：4 维扫描明细
- **events.ndjson**：全量事件流（机器可读，可重放）

## 注册表能力

| 命名空间 | 已注册项 |
|----------|----------|
| `audit.strategy` | base, dsh, ts2 |
| `patch.generator` | insert_defuse_comment, insert_entry_comment, insert_env_todo, insert_guard_comment, insert_merge_comment, insert_reset_comment, insert_set_after_clear, insert_todo_comment |
| `plan.runner` | default |
| `skill.catalog` | base |

## 全部函数（模块底层反射）

见 **AUDIT_DEV_DOC.md**（开发文档承载完整函数索引，本文档只负责使用）。
