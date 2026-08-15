# macdev requirement 使用文档（自举生成）

> 由 `python -m macdev doc` 从 argparse + Registry + 模块反射生成，勿手改。

## 双轨产物约定（语言环境无关）

需求以结构化条目存 `requirements.db`（机器权威）；任何变更自动刷新：
- 人类轨：`REQUIREMENTS.md`
- 机器轨：`requirements.json` / `requirements.csv`（主库快照）
- 时间戳 UTC、编码 utf-8，不依赖宿主时区/locale

## 命令速览

```
python -m macdev requirement add --kind interface --name createX --detail "签名说明"
python -m macdev requirement add --kind path --name /api/agent/chat/stream --detail "流式聊天"
python -m macdev requirement list [--kind interface] [--status open|done|missing]
python -m macdev requirement update --id 3 --status done [--name ...] [--detail ...]
python -m macdev requirement delete --id 3
python -m macdev requirement export [--format all]               # 刷新双轨
python -m macdev requirement align --root .                      # DB 需求→代码/端点对齐，回写 missing
python -m macdev requirement scan --req-dirs openspec --root .   # 扫需求文档提取声明并对齐
```

## 对齐（参考 audit 扫描健壮性）

`align`（结构化 DB 需求）与 `scan`（需求文档目录）共用对齐逻辑：
- 代码 token 索引：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过
- 端点对齐：声明路径 vs interface_chain_index.json 实际端点（missing/prefix/extra）
- 代码存在性：接口/文件名 vs 源码 token（found / not_found）
- 回写：未找到 → `missing`（不覆盖人工标定的 `done`）

## 产物（对齐四件套）

- `REQUIREMENT_ALIGNMENT.md` + `requirement_alignment.json/csv/db`
- `--project <name>` / env `MACDEV_PROJECT` 收敛到 `<name>-project/requirements.db` 等

## 命令参数树（argparse 底层反射，仅 requirement 子集）

```
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
```

## 注册表能力

| 命名空间 | 已注册项 |
|----------|----------|
| `audit.strategy` | base, dsh, ts2 |
| `patch.generator` | insert_defuse_comment, insert_entry_comment, insert_env_todo, insert_guard_comment, insert_merge_comment, insert_reset_comment, insert_set_after_clear, insert_todo_comment |
| `plan.runner` | default |

## 全部函数（模块底层反射）

见 **REQI_DEV.md**（requirement 开发文档，含 requirement 组模块函数索引）。
