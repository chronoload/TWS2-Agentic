# macdev dev 开发文档（自举生成）

> 由 `python -m macdev doc` 反射生成。

## 架构

- **commands**：cmd_map（目录编排：树 + 模块地图 + 技术栈线索，双轨产物）/  cmd_audit（自动编排默认 AuditTask 跑快速探索，复用 audit 双轨），返回 (code, lines)
- **扫描健壮性（参考 audit）**：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过
- **目录树**：Path.parts 计算层级（跨平台，不依赖 os.sep 拼接），限深渲染、入口文件标 ⭐
- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/dev/<目标名>/

## 全部函数（模块底层反射，dev 组）

### dev 学习模仿

**dev/commands.py**（5 个顶层函数/类）
- L27 `_collect` `(root: 'Path', exclude: 'tuple') -> 'list'` — os.walk 逐目录容错收集文件（参考 audit）：跳过 _SKIP_DIRS + exclude 目录剪枝。
- L98 `_stats` `(files: 'list') -> 'dict'` — 摘要：文件数 / 类型分布 / 总行数 / 行数 top / 模块分布 / 技术栈线索。
- L58 `_tree_lines` `(root: 'Path', files: 'list', depth: 'int') -> 'list'` — 目录树（限深）：按层级缩进渲染，目录优先排序。
- L192 `cmd_audit` `(engine, target: 'str' = '', out: 'str' = '', strategy: 'str' = 'base', exclude: 'str' = '', timeout: 'int' = 0) -> 'tuple'` — 架构了解：自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物。
- L123 `cmd_map` `(target: 'str' = '', out: 'str' = '', depth: 'int' = 3, exclude: 'str' = '') -> 'tuple'` — 扫描目标学习项目，编排目录（树 + 模块地图 + 技术栈线索），双轨产物。

