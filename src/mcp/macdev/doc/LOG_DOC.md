# macdev log 使用文档（自举生成）

> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。

## 经验沉淀约定（不写 SKILL.md）

经验/教训/模式/决策沉淀在 log 插件（SQLite logs.db 机器轨 + LOGS.md 人类轨），
SKILL.md 只留指针，避免随包文档膨胀不通用。

经验分**随项目**（project，最主要，须指定 `--project`，产物落 `<name>-project/`）与
**随包**（pkg，`--scope pkg`，通用方法论落 macdev-skill/，包内保持干净）双轨；
显式 `--db` 始终优先。

## 四分类

- **lessons**：工作流/方法论经验
- **pitfalls**：踩坑与陷阱（命名空间、依赖误判、反射噪音等）
- **patterns**：可复用实现模式（双轨产物、插件迁移等）
- **decisions**：关键决策及理由（阈值、约定取舍等）

## 命令速览

```
python -m macdev log add --project ts2 --title "..." --category pitfalls --body "..." --tags a,b --refs macdev/x.py
python -m macdev log add --scope pkg --title "..." --category patterns --file notes.md   # 随包经验
python -m macdev log list [--category pitfalls] [--tag a] [--scope project|pkg]
python -m macdev log get --id 3
python -m macdev log query --keyword glob [--category pitfalls] [--scope project|pkg]  # 全文检索
python -m macdev log update --id 3 --status done [--scope project|pkg]
python -m macdev log delete --id 3
python -m macdev log export [--out LOGS.md] [--scope project|pkg]                     # 刷新人类轨
```

## 产物（双轨）

- 机器轨：`logs.db`（SQLite，可 query 全文检索；scope 列区分归属）
- 人类轨：`LOGS.md`（`log export` 生成，按 scope 分组）
- 随项目：`--project <name>` → `<name>-project/logs.db` + `LOGS.md`（缺省会报错，不落 cwd）
- 随包：`--scope pkg` → macdev-skill/logs.db + LOGS.md（随包经验库）

## 命令参数树（argparse 底层反射，仅 log 子集）

```
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
```

## 注册表能力

| 命名空间 | 已注册项 |
|----------|----------|
| `audit.strategy` | base, dsh, ts2 |
| `patch.generator` | insert_defuse_comment, insert_entry_comment, insert_env_todo, insert_guard_comment, insert_merge_comment, insert_reset_comment, insert_set_after_clear, insert_todo_comment |
| `plan.runner` | default |

## 全部函数（模块底层反射）

见 **LOG_DEV.md**（log 开发文档，含 log 组模块函数索引）。
