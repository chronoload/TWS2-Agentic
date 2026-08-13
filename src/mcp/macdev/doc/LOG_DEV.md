# macdev log 开发文档（自举生成）

> 由 `python -m macdev doc` 反射生成。

## 架构

- **db.LogStore**：SQLite 经验库（四分类 lessons/pitfalls/patterns/decisions + scope 归属），路径全可配
- **commands**：add/list/get/query/export/update/delete，返回 (code, lines) 约定
- **双轨产物**：logs.db（机器，全文检索 query）+ LOGS.md（人类，log export 生成，按 scope 分组）
- **经验双轨**：scope=project（随项目，最主要，须 --project，产物落 <name>-project/）/  scope=pkg（随包，通用方法论落 macdev-skill/，包内保持干净）
- **经验沉淀约定**：经验写 log 不写 SKILL.md（防随包文档膨胀不通用）
- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/logs.db；缺省会报错不落 cwd
## 全部函数（模块底层反射，log 组）

### log 经验沉淀

**log/db.py**（1 个顶层函数/类）
- L0 `LogStore`  — 

**log/commands.py**（10 个顶层函数/类）
- L17 `_check_category` `(category: 'str') -> 'str | None'` — 
- L24 `_check_scope` `(scope: 'str') -> 'str | None'` — 
- L10 `_unescape` `(s: 'str') -> 'str'` — 把 shell 传入的字面 \n / \t 转成真实换行/制表。
- L31 `cmd_add` `(store: 'LogStore', title: 'str', category: 'str', body: 'str' = '', tags: 'str' = '', refs: 'str' = '', file: 'str' = '', scope: 'str' = 'project') -> 'tuple'` — 
- L125 `cmd_delete` `(store: 'LogStore', lid: 'int') -> 'tuple'` — 
- L115 `cmd_export` `(store: 'LogStore', out: 'str' = '', scope: 'str' = '') -> 'tuple'` — 
- L73 `cmd_get` `(store: 'LogStore', lid: 'int') -> 'tuple'` — 
- L53 `cmd_list` `(store: 'LogStore', category: 'str' = '', tag: 'str' = '', scope: 'str' = '') -> 'tuple'` — 
- L90 `cmd_query` `(store: 'LogStore', keyword: 'str', category: 'str' = '', scope: 'str' = '') -> 'tuple'` — 
- L131 `cmd_update` `(store: 'LogStore', lid: 'int', **fields) -> 'tuple'` — 

