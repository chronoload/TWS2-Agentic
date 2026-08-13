# macdev requirement 开发文档（自举生成）

> 由 `python -m macdev doc` 反射生成。

## 架构

- **db.RequirementStore**：SQLite requirements 表 CRUD + 双轨产物自动刷新
  （db 权威 → requirements.json/csv 机器快照 + REQUIREMENTS.md 人类，UTC/utf-8 语言环境无关）
- **align**：对齐纯逻辑（需求文档提取声明 interface/path/file → 端点/代码对齐），无硬编码路径
- **commands**：add/list/update/delete/export/scan/align，返回 (code, lines) 约定
- **扫描健壮性（参考 audit）**：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过
- **对齐产物四件套**：REQUIREMENT_ALIGNMENT.md + requirement_alignment.json/csv/db
- **产物收敛**：--project/env MACDEV_PROJECT → <name>-project/requirements.db 等

## 全部函数（模块底层反射，requirement 组）

### requirement 需求对齐

**requirement/db.py**（1 个顶层函数/类）
- L0 `RequirementStore`  — 

**requirement/align.py**（7 个顶层函数/类）
- L138 `align` `(items: 'list', index: 'dict', endpoints: 'list') -> 'dict'` — 执行对齐：端点路径 + 代码存在性
- L98 `build_code_index` `(root: 'Path', globs: 'list', exclude: 'tuple' = ()) -> 'dict'` — 预构建代码 token 索引：token -> [file,...]，供存在性快速检查。
- L37 `extract_doc` `(path: 'Path') -> 'list'` — 从单个需求文档提取声明（interface/path/file）
- L189 `gen_markdown` `(res: 'dict', req_dirs: 'list', index: 'dict') -> 'str'` — 
- L178 `load_endpoints` `(index_json: 'str') -> 'list'` — 读取接口索引 JSON，返回端点列表（缺失/解析失败返回空 + warn 打印）。
- L27 `norm_path` `(path: 'str') -> 'str'` — 归一化路径：剥离 query、模板变量（${x}、:param、{id}）统一为 {}
- L79 `scan_dirs` `(dirs: 'list', root: 'Path') -> 'list'` — 扫描所有需求目录，返回带 source（相对 root）的声明列表。

**requirement/commands.py**（11 个顶层函数/类）
- L18 `_check_kind` `(kind: 'str') -> 'str | None'` — 
- L24 `_check_status` `(status: 'str') -> 'str | None'` — 
- L30 `_probe` `(root: 'Path', subdirs: 'tuple') -> 'list'` — 从项目根探测存在的需求文档目录。
- L35 `_resolve_index` `(index: 'str', store: 'RequirementStore') -> 'str'` — 
- L39 `cmd_add` `(store: 'RequirementStore', kind: 'str', name: 'str', detail: 'str' = '', source: 'str' = 'cli') -> 'tuple'` — 
- L105 `cmd_align` `(store: 'RequirementStore', index: 'str' = '', root: 'str' = '', exclude: 'str' = '') -> 'tuple'` — 结构化 DB 需求 → 代码/端点对齐，回写 missing 状态，落盘对齐四件套。
- L83 `cmd_delete` `(store: 'RequirementStore', rid: 'int') -> 'tuple'` — 
- L90 `cmd_export` `(store: 'RequirementStore', fmt: 'str' = 'md') -> 'tuple'` — 
- L49 `cmd_list` `(store: 'RequirementStore', kind: 'str' = '', status: 'str' = '') -> 'tuple'` — 
- L141 `cmd_scan` `(store: 'RequirementStore', req_dirs: 'str' = '', root: 'str' = '', code: 'str' = '', index: 'str' = '', exclude: 'str' = '') -> 'tuple'` — 扫描需求文档目录，提取声明并做对齐（对应原 requirement_align 主流程）。
- L68 `cmd_update` `(store: 'RequirementStore', rid: 'int', **fields) -> 'tuple'` — 

