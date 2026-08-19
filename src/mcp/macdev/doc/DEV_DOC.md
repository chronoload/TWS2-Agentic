# macdev dev 使用文档（自举生成）

> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。

## 用途（学习/模仿目标项目）

用 macdev 了解一个陌生项目怎么做起来的：扫描目标学习项目、编排目录、
了解架构——audit 的「快速探索」用法在 dev 下的显式入口。

## 命令速览

```
python -m macdev dev map --target <dir> [--depth 3] [--project <name>]
   # 目录编排：树 + 模块地图 + 技术栈线索（双轨产物）
python -m macdev dev audit --target <dir> [--strategy base] [--project <name>]
   # 架构了解：自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物
```

## 产物（双轨）

- **map**：`DIR_TREE.md`（人类）+ `dir_tree.json/csv/db`（机器，语言环境无关）
- **audit**：`INTERFACE_CHAIN.md` + `interface_chain.db` + 全维度 CSV + events.ndjson
- 收敛：`--project <name>` → `<name>-project/dev/<目标名>/`；显式 `--out` 优先

## 命令参数树（argparse 底层反射，仅 dev 子集）

```
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
```

## 注册表能力

| 命名空间 | 已注册项 |
|----------|----------|
| `audit.strategy` | base, dsh, ts2 |
| `patch.generator` | insert_defuse_comment, insert_entry_comment, insert_env_todo, insert_guard_comment, insert_merge_comment, insert_reset_comment, insert_set_after_clear, insert_todo_comment |
| `plan.runner` | default |
| `skill.catalog` | base |

## 全部函数（模块底层反射）

见 **DEV_DEV.md**（dev 开发文档，含 dev 组模块函数索引）。
