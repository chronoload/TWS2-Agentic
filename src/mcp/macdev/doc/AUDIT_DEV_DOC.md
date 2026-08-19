# macdev audit 开发文档（自举生成）

> 由 `python -m macdev doc` 反射生成。

## 架构（插件总线微内核）

- **core**：Registry 工厂（按名装配能力）+ EventBus（全量事件，NDJSON 落盘）+ Engine 薄门面
- **Plugin 抽象接口**：一切能力（audit.strategy / patch.generator / 展示/扫描…）继承同一
  抽象基类，声明 namespace+name，被 `Registry.discover()` 扫描捕捉——插件与工厂**平级**。
- **audit**：parse（AST 提取）→ chain（亲属追逐依赖链）→ analyze（6 维分析）→ scan（4 维扫描）→ report（双轨产物）
- **patch**：修复插件（PatchPlugin 子类），审计缺陷 → 固化补丁脚本 → apply/verify 闭环
- 项目语义 = AuditTask JSON + ChainStrategy 子类，**不进内核**

## 新增修复插件（与审计策略平级）

```python
from macdev.core.plugin import Plugin
from macdev.patch.model import PatchScript

class FixMyIssue(Plugin):          # 继承抽象接口即被扫描捕捉
    namespace = "patch.generator"
    name = "fix_my_issue"
    def generate(self, issue, root, rule) -> PatchScript:
        ...
```
`registry.discover()` 自动装配，`patch gen` 按策略名调用。

## 扩展新策略（零特化）

```python
from macdev.audit.strategy import ChainStrategy
class MyStrategy(ChainStrategy):
    name = "my"
    known_type_files = {"MyType": "src/my_type.py"}
registry.register("audit.strategy", "my", MyStrategy)
```

## 全部函数（模块底层反射）

### core 微内核

**core/plugin.py**（3 个顶层函数/类）
- L0 `Plugin`  — 能力插件抽象接口：namespace + name 唯一标识，按名装配。
- L0 `PluginMeta`  — 自动登记所有 Plugin 子类（按 namespace/name 去重）。
- L41 `scan_plugins` `(namespace: 'str' = '') -> 'list'` — 扫描已导入模块中登记的插件类（可按命名空间过滤）。

**core/registry.py**（1 个顶层函数/类）
- L0 `Registry`  — 

**core/bus.py**（1 个顶层函数/类）
- L0 `EventBus`  — 

**core/types.py**（2 个顶层函数/类）
- L0 `Event`  — Event(name: 'str', data: 'dict' = <factory>)
- L0 `Result`  — Result(ok: 'bool' = True, data: 'dict' = <factory>, artifacts: 'list' 

**core/engine.py**（1 个顶层函数/类）
- L0 `Engine`  — 

### audit 静态审计

**audit/task.py**（1 个顶层函数/类）
- L0 `AuditTask`  — AuditTask：外置任务模型（入口/规则/目录/排除/策略），项目语义不进内核。

**audit/strategy.py**（1 个顶层函数/类）
- L0 `ChainStrategy`  — ChainStrategy 基类（零语义）：类型解析语义表由外部子类化提供。

**audit/parse.py**（10 个顶层函数/类）
- L27 `_collect_response_keys` `(func: 'ast.FunctionDef') -> 'list[str]'` — 静态提取 ok(data={...}) / ok(data=dict(...)) 的顶层键
- L56 `_extract_model_class` `(cls: 'ast.ClassDef', file: 'str', models: 'list')` — 
- L20 `_get_doc` `(body: 'list') -> 'str'` — 
- L77 `_type_short` `(t: 'str') -> 'str'` — 
- L13 `_unparse` `(node) -> 'str'` — 
- L186 `extract_all` `(task) -> 'tuple'` — 按 AuditTask 配置提取端点 + 请求模型 → (endpoints, models)
- L130 `extract_endpoints` `(path: 'Path', decorator_names: 'tuple', endpoints: 'list', prefix: 'str' = '', loose: 'bool' = False)` — 提取 FastAPI/APIRouter 端点。decorator_names: ('app.get', 'app.post', ...)
- L115 `extract_func_map` `(path: 'Path') -> 'dict'` — 提取模块内所有函数定义（含嵌套），返回 {函数名: FunctionDef}
- L95 `extract_imports` `(path: 'Path') -> 'dict'` — 提取模块内所有 import（含函数内），返回 {名称: 模块路径}
- L175 `extract_python_models` `(path: 'Path', models: 'list')` — 

**audit/chain.py**（17 个顶层函数/类）
- L235 `_iter_py_files` `(root: 'Path', exclude: 'tuple') -> 'list'` — 遍历项目内 *.py，跳过排除目录；逐目录容错（断链目录只跳过该目录，
- L118 `_method_calls_of` `(module_path: 'Path', cls_name: 'str', method_name: 'str') -> 'list'` — 提取类方法内部的调用目标（1 层）
- L41 `_walk_own` `(node)` — 遍历节点自身 body，跳过嵌套函数/类定义（避免闭包内部调用混入父函数）
- L450 `build_dep_sections` `(endpoints: 'list', root: 'Path', chains_cfg: 'dict' = None, strategy: 'ChainStrategy' = None, exclude: 'tuple' = (), budget=None) -> 'str'` — 关键端点依赖链（亲属追逐 → 跨模块/存储）。
- L256 `build_global_symbol_index` `(root: 'Path', exclude: 'tuple' = (), budget=None) -> 'dict'` — 全局符号索引（亲属反射表）：{符号名: [(相对文件, 行号, 种类)]}
- L419 `chain_mermaid` `(node: 'ChainNode', parent_id: 'str' = '') -> 'list'` — 调用链 → mermaid graph 语句（broken 节点标红，cross_file 显示定义位置）
- L404 `chain_text` `(node: 'ChainNode', indent: 'int' = 0) -> 'list'` — 调用链 → 文本树（broken 断裂节点标红 🔴，cross_file 显示定义位置）
- L221 `changed_file_paths` `(files, db_path) -> 'tuple'` — 对比指纹返回 (changed, removed, fps)。
- L439 `collect_broken_refs` `(node: 'ChainNode', out: 'list') -> 'list'` — 递归收集链路中的断裂引用（broken 节点），返回 [(目标, 调用行)]
- L71 `collect_call_targets` `(func) -> 'list'` — 收集函数体（不含嵌套定义）内的直接调用目标，过滤装饰器与噪声
- L137 `collect_calls_refs` `(files) -> 'tuple'` — 同一遍历产出 calls(调用图) + refs(引用索引)，供 chain callers/kw 查询持久化。
- L50 `extract_var_bindings` `(func) -> 'dict'` — 提取函数体内变量 → 类型名/来源（Assign/AnnAssign 直接赋值）
- L183 `file_fingerprint` `(path: 'Path') -> 'str'` — 文件指纹：size + mtime_ns（够快，不读内容；同大小内容变更靠 mtime 检出）
- L206 `load_fingerprints` `(db_path) -> 'dict'` — 读回指纹 {path: fp}；旧 db 无表/不存在 → {}
- L192 `save_fingerprints` `(db_path, fps: 'dict') -> 'None'` — 持久化指纹到 scan_fingerprints 表（清表重建）
- L294 `trace_chain` `(start_name: 'str', func_map: 'dict', import_map: 'dict', path: 'Path', depth: 'int' = 0, seen=None, max_depth: 'int' = 3, global_index: 'dict' = None, strategy: 'ChainStrategy' = None) -> 'ChainNode'` — 从函数名开始递归展开调用链（亲属追逐 → 亲属反射）
- L554 `write_db` `(db_path: 'Path', endpoints: 'list', models: 'list') -> 'None'` — 写 SQLite：endpoints / models / stats 三表（机器可读轨，最小闭环）。

**audit/analyze.py**（27 个顶层函数/类）
- L640 `_call_fn_name` `(call) -> 'str'` — 
- L276 `_call_repr` `(node: 'ast.AST') -> 'str'` — 把 ast.Call 的 func 转成可读字符串：store.update / _sync_agent_from_store
- L289 `_collect_entry_call_reprs` `(func) -> 'list'` — 收集入口函数体（含嵌套闭包/回调）内所有调用目标的可读串，供 must-call 匹配。
- L525 `_collect_len_compares` `(fn) -> 'list'` — 收集函数内所有基于 len() 或 *_count 的数量比较节点。
- L551 `_collect_version_attrs` `(fn) -> 'set'` — 收集函数内引用的「版本/时间戳仲裁字段」：updated_at/version/hash/seq 等
- L432 `_event_flag_attrs` `(tree) -> 'set'` — 收集文件中初始化为 threading.Event() 的属性名（只对这些做 clear/set 配对）。
- L659 `_expr_sig` `(e) -> 'str'` — 实参表达式 → 签名：req.session_id → session_id；变量 → 变量名；字符串字面量 → str:<值>
- L126 `_extract_defuse_one` `(file: 'Path', reads: 'list', writes: 'list') -> 'None'` — 扫描单个 Python 文件：收集 getattr/hasattr/setattr 调用与 obj.attr 赋值
- L105 `_falsy_literal_text` `(s: 'str') -> 'bool'` — 判断默认值源码文本是否为假值常量（False/None/0/''/[]/{} 等）
- L420 `_flag_attr_of` `(call) -> 'str'` — 从 `self._chat_active.clear()` 提取 attr 名；非 self.attr 形式返回 ''
- L568 `_has_content_arbitration` `(fn) -> 'bool'` — 检测「内容级仲裁」手段（等效于版本仲裁，可替代数量仲裁）。
- L348 `_is_behavior_defect` `(b) -> 'bool'` — 真实行为缺陷判定：must-call 全部缺失才算缺陷；'入口未找到'属规则过期警告。
- L187 `_is_external_obj` `(obj: 'str') -> 'bool'` — 
- L355 `_iter_ancestor_ifs` `(node, tree) -> 'list'` — 收集 node 的所有祖先 if 条件（ast.If 的 test），按从近到远。
- L649 `_key_arg_expr` `(call)` — 取消费者的 key 实参：第一位置参数，或命名的 key/id/checkpoint_id 关键字
- L16 `_normalize_path` `(p: 'str') -> 'str'` — 
- L117 `_obj_root` `(node) -> 'str'` — 取属性读写对象的最左侧名字：agent.state.x → agent；self → self；Name → id
- L196 `_verify_module_attr` `(obj: 'str', attr: 'str') -> 'str'` — 尝试用运行时反射验证「模块级属性」是否真实存在。
- L772 `analyze_all` `(files: 'list', behavior_rules: 'dict' = None, id_source_rules: 'list' = None, chain_break_rules: 'dict' = None, budget=None) -> 'dict'` — 6 维分析聚合 → {defuse, behavior, chain_break, flag, merge, id_source}
- L300 `analyze_behavior` `(files: 'list', rules: 'dict', budget=None) -> 'list'` — 行为契约检查：入口函数正常完成路径必须触发的副作用调用是否存在。
- L366 `analyze_chain_break` `(files: 'list', rules: 'dict', budget=None) -> 'list'` — 链路断裂检查：兜底源调用是否被活跃性守卫保护。
- L215 `analyze_defuse` `(files: 'list', budget=None) -> 'tuple'` — 跨文件 def-use 一致性分析。
- L458 `analyze_flag_lifecycle` `(files: 'list', budget=None) -> 'list'` — 状态标志生命周期检查：(a) clear_without_set (b) stale_cache。
- L672 `analyze_id_source_contract` `(files: 'list', rules: 'list', budget=None) -> 'list'` — 标识符命名空间来源契约检查：(a) cross_namespace_key (b) unguarded_key_consumer。
- L585 `analyze_merge_direction` `(files: 'list', budget=None) -> 'list'` — 状态机合并方向仲裁检查：(a) count_only_arbitration。
- L65 `detect_drift` `(endpoints: 'list', models: 'list', client: 'list') -> 'list'` — 
- L22 `extract_client_methods` `(js_path: 'Path') -> 'list'` — 

**audit/scan.py**（13 个顶层函数/类）
- L275 `_py_collect_data_pools` `(file: 'Path', tree, rel: 'str') -> 'list'` — 
- L185 `_py_collect_env_vars` `(file: 'Path', tree, rel: 'str') -> 'list'` — 
- L56 `_py_collect_hardcoded` `(file: 'Path', tree, rel: 'str') -> 'list'` — 
- L386 `_py_collect_static_resources` `(file: 'Path', tree, rel: 'str') -> 'list'` — 
- L331 `_ts_collect_data_pools` `(file: 'Path', text: 'str', rel: 'str') -> 'list'` — 
- L229 `_ts_collect_env_vars` `(file: 'Path', text: 'str', rel: 'str') -> 'list'` — 
- L116 `_ts_collect_hardcoded` `(file: 'Path', text: 'str', rel: 'str') -> 'list'` — 
- L431 `_ts_collect_static_resources` `(file: 'Path', text: 'str', rel: 'str') -> 'list'` — 
- L491 `scan_all` `(root: 'Path', files: 'list', exclude: 'tuple' = ('test', 'tests', 'migrations', 'node_modules', '.git', '.venv', 'venv', 'build', 'dist', 'site-packages', '__pycache__', 'docs', 'examples', 'assets', 'static_arch', 'static-branch', 'web', 'android', 'archs', 'draft', 'static-capacitor'), budget=None) -> 'dict'` — 四维扫描聚合 → {hardcoded, env_vars, data_pools, static_resources}
- L350 `scan_data_pools` `(root: 'Path', files: 'list', exclude: 'tuple' = ('test', 'tests', 'migrations', 'node_modules', '.git', '.venv', 'venv', 'build', 'dist', 'site-packages', '__pycache__', 'docs', 'examples', 'assets', 'static_arch', 'static-branch', 'web', 'android', 'archs', 'draft', 'static-capacitor'), budget=None) -> 'list'` — 
- L239 `scan_env_vars` `(root: 'Path', files: 'list', exclude: 'tuple' = ('test', 'tests', 'migrations', 'node_modules', '.git', '.venv', 'venv', 'build', 'dist', 'site-packages', '__pycache__', 'docs', 'examples', 'assets', 'static_arch', 'static-branch', 'web', 'android', 'archs', 'draft', 'static-capacitor'), budget=None) -> 'list'` — 
- L145 `scan_hardcoded` `(root: 'Path', files: 'list', exclude: 'tuple' = ('test', 'tests', 'migrations', 'node_modules', '.git', '.venv', 'venv', 'build', 'dist', 'site-packages', '__pycache__', 'docs', 'examples', 'assets', 'static_arch', 'static-branch', 'web', 'android', 'archs', 'draft', 'static-capacitor'), budget=None) -> 'list'` — 
- L451 `scan_static_resources` `(root: 'Path', files: 'list', exclude: 'tuple' = ('test', 'tests', 'migrations', 'node_modules', '.git', '.venv', 'venv', 'build', 'dist', 'site-packages', '__pycache__', 'docs', 'examples', 'assets', 'static_arch', 'static-branch', 'web', 'android', 'archs', 'draft', 'static-capacitor'), budget=None) -> 'list'` — 

**audit/report.py**（5 个顶层函数/类）
- L234 `_write_csv` `(path: 'Path', headers: 'list', rows: 'list') -> 'None'` — 写 CSV（utf-8-sig 便于 Excel 直接打开）
- L12 `gen_markdown` `(endpoints, models, dep_sections: 'str' = '', defuse=None, behavior=None, flag=None, merge=None, id_source=None, hardcoded=None, env_vars=None, data_pools=None, static_resources=None) -> 'str'` — 通用审计报告：端点/模型/语义偏移 + 依赖链（§8）+ 6 维分析 + 4 维扫描。
- L294 `read_db_calls_refs` `(db_path) -> 'tuple'` — 从旧 db 读回 calls/refs（供增量合并；旧库无表 → ([], [])）
- L243 `write_csvs` `(out_dir: 'Path', endpoints, models, drifts, defuse, behavior, flag, merge, id_source, scan_items) -> 'None'` — 四类 CSV 明细产物。
- L308 `write_db` `(db_path: 'Path', endpoints, models, drifts=None, defuse=None, behavior=None, flag=None, merge=None, id_source=None, scan_items=None, calls=None, refs=None) -> 'None'` — 写 SQLite 全维度表：endpoints/models/drifts/defuse/behavior/flag/merge/id_so

**audit/chain_query.py**（9 个顶层函数/类）
- L118 `chain_callers` `(db: 'Path | str | None' = None, func: 'str' = '') -> 'list'` — 按符号追调用链：上游(谁调 X) + 下游(X 调谁)，file:line 定位。
- L9 `chain_connect` `(db: 'Path | str | None' = None) -> 'sqlite3.Connection | None'` — 
- L99 `chain_drifts` `(db: 'Path | str | None' = None) -> 'list'` — 
- L31 `chain_endpoints` `(db: 'Path | str | None' = None, by_file: 'bool' = False, path: 'str' = '', func: 'str' = '', no_model: 'bool' = False) -> 'list'` — 
- L180 `chain_issues` `(db: 'Path | str | None' = None, count: 'bool' = False, kind: 'str' = '', file: 'str' = '', attr: 'str' = '') -> 'list'` — 
- L153 `chain_kw` `(db: 'Path | str | None' = None, keyword: 'str' = '') -> 'list'` — 关键字微扫描：refs 索引中引用位置列表（def/use 标注）。
- L69 `chain_models` `(db: 'Path | str | None' = None, dup: 'bool' = False, name: 'str' = '') -> 'list'` — 
- L18 `chain_stats` `(db: 'Path | str | None' = None) -> 'list'` — 
- L243 `chain_tables` `(db: 'Path | str | None' = None) -> 'list'` — 

### plan 开发流程

**plan/model.py**（3 个顶层函数/类）
- L0 `Plan`  — Plan(id: 'int', title: 'str', goal: 'str' = '', status: 'str' = 'open'
- L0 `Step`  — Step(text: 'str', action: 'str' = 'other', code: 'str' = '', lang: 'st
- L0 `Task`  — Task(id: 'int', plan_id: 'int', title: 'str', status: 'str' = 'pending

**plan/db.py**（2 个顶层函数/类）
- L0 `PlanStore`  — 
- L147 `_migrate_plan_id_text` `(conn: 'sqlite3.Connection') -> 'None'` — 把 plans.id / tasks.plan_id 从 INTEGER 迁移为 TEXT（保留旧数据）。

**plan/commands.py**（21 个顶层函数/类）
- L53 `_plan_id` `(name: 'str' = '') -> 'str'` — 日期+计划名：YYYYMMDD_<slug>（日期自动获取）。
- L73 `_plan_of_step` `(store: 'PlanStore', step_id: 'int') -> 'str | None'` — 
- L66 `_plan_of_task` `(store: 'PlanStore', task_id: 'int') -> 'str | None'` — 
- L59 `_refresh` `(store: 'PlanStore', pid: 'str') -> 'list'` — 双轨自动刷新：变更后重写 PLAN_<pid>.md/.json + plans.csv，返回追加产物行。
- L35 `_resolve_defect` `(defect_ref: 'str', defect_map: 'dict') -> 'str'` — 展示任务绑定缺陷的状态：缺陷仍在 index.json → 🔴 未修复；已消失 → ✅ 已修复
- L19 `_resolve_req` `(req_ref: 'str', req_map: 'dict') -> 'str'` — 解析任务关联需求的状态展示：path:/api/x → ✅ done / ⏳ open / ❌ missing
- L46 `_slug` `(text: 'str') -> 'str'` — 把传入的计划名/标题转成 id 用短名（保留中文/字母/数字/连字符）。
- L8 `_status_icon` `(status: 'str') -> 'str'` — 
- L12 `_unescape` `(s: 'str') -> 'str'` — 把 shell 传入的字面 \n / \t 转成真实换行/制表，方便 Agent 填多行代码。
- L82 `cmd_create` `(store: 'PlanStore', title: 'str', goal: 'str' = '', arch: 'str' = '', stack: 'str' = '', constraints: 'str' = '', name: 'str' = '') -> 'tuple'` — 
- L128 `cmd_delete` `(store: 'PlanStore', pid: 'int') -> 'tuple'` — 
- L94 `cmd_list` `(store: 'PlanStore') -> 'tuple'` — 
- L215 `cmd_step_add` `(store: 'PlanStore', task_id: 'int', text: 'str', action: 'str' = 'other', code: 'str' = '', lang: 'str' = '', run: 'str' = '', expected: 'str' = '') -> 'tuple'` — 
- L270 `cmd_step_delete` `(store: 'PlanStore', sid: 'int') -> 'tuple'` — 
- L235 `cmd_step_list` `(store: 'PlanStore', task_id: 'int') -> 'tuple'` — 
- L250 `cmd_step_update` `(store: 'PlanStore', sid: 'int', **fields) -> 'tuple'` — 
- L147 `cmd_task_add` `(store: 'PlanStore', plan_id: 'int', title: 'str', detail: 'str' = '', files: 'str' = '', req_ref: 'str' = '', defect_ref: 'str' = '', interfaces: 'str' = '') -> 'tuple'` — 
- L203 `cmd_task_delete` `(store: 'PlanStore', tid: 'int') -> 'tuple'` — 
- L164 `cmd_task_list` `(store: 'PlanStore', plan_id: 'int') -> 'tuple'` — 
- L182 `cmd_task_update` `(store: 'PlanStore', tid: 'int', **fields) -> 'tuple'` — 
- L109 `cmd_update` `(store: 'PlanStore', pid: 'int', **fields) -> 'tuple'` — 

**plan/workflow.py**（4 个顶层函数/类）
- L163 `cmd_ledger` `(store: 'PlanStore', plan_id: 'int', out: 'Path | str' = '') -> 'tuple'` — 进度台账：已完成任务标记 ✅（resume 跳过），未完成列出待办。
- L12 `cmd_review` `(store: 'PlanStore', task_id: 'int', action: 'str', findings: 'str' = '') -> 'tuple'` — review 循环：pending → review_requested → approved / needs_fix → fixed → 
- L59 `cmd_tdd_check` `(store: 'PlanStore') -> 'tuple'` — TDD 合规（db 版）：test_missing / test_after_implement / test_unverifiable。
- L93 `cmd_verify` `(store: 'PlanStore', plan_id: 'int | None' = None, project_root: 'Path | str' = '.') -> 'tuple'` — 完成门禁（verification-before-completion）：聚合四类证据。

**plan/export.py**（6 个顶层函数/类）
- L101 `_render_table` `(plan, tasks, steps_by_task, req_map, defect_map) -> 'list'` — 
- L23 `_render_writing_plans` `(plan, tasks, steps_by_task, req_map, defect_map) -> 'list'` — 对齐 writing-plans skill 的格式：头部 + Global Constraints + Task 文件清单 + check
- L11 `export_md` `(plan) -> 'str'` — dataclass 版最小导出（Engine.run_plan export 用）。
- L123 `export_plan` `(store: 'PlanStore', pid: 'int', out: 'Path | str' = '', fmt: 'str' = 'writing-plans') -> 'tuple'` — 导出 plan → (exit_code, [lines], md_path, json_path)
- L171 `refresh_csv` `(store: 'PlanStore', out_dir: 'Path | str' = '') -> 'Path'` — 汇总 plans.csv（全部 plan/task/step 明细，机器轨）。
- L196 `refresh_plan` `(store: 'PlanStore', pid: 'int', out_dir: 'Path | str' = '') -> 'tuple'` — 双轨自动刷新（对齐 requirement 约定）：变更后重写 PLAN_<pid>.md/.json + 汇总 plans.csv。

**plan/openspec.py**（9 个顶层函数/类）
- L33 `_openspec_change_root` `(change: 'str', cwd: 'str' = '') -> 'str'` — 
- L11 `_openspec_exe` `() -> 'str'` — 定位 openspec CLI（优先 PATH，找不到时用裸名让 subprocess 报错）。
- L26 `_parse_openspec_json` `(out: 'str') -> 'dict'` — 
- L16 `_run_openspec` `(*cmd: 'str', cwd: 'str' = '') -> 'tuple'` — 运行 openspec CLI，返回 (exit_code, stdout)。
- L72 `cmd_export` `(change: 'str', cwd: 'str' = '') -> 'tuple'` — 导出 change 为文档。
- L64 `cmd_import` `(change: 'str', cwd: 'str' = '') -> 'tuple'` — 导入/应用 change。
- L44 `cmd_list` `(cwd: 'str' = '') -> 'tuple'` — 列出 changes（只读查询）。
- L56 `cmd_status` `(change: 'str', cwd: 'str' = '') -> 'tuple'` — change 状态（只读查询）。
- L80 `cmd_sync_specs` `(change: 'str', cwd: 'str' = '', req_cli: 'str' = '') -> 'tuple'` — openspec-sync-specs：delta specs → requirements 条目。

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

### dev 学习模仿

**dev/commands.py**（5 个顶层函数/类）
- L27 `_collect` `(root: 'Path', exclude: 'tuple') -> 'list'` — os.walk 逐目录容错收集文件（参考 audit）：跳过 _SKIP_DIRS + exclude 目录剪枝。
- L98 `_stats` `(files: 'list') -> 'dict'` — 摘要：文件数 / 类型分布 / 总行数 / 行数 top / 模块分布 / 技术栈线索。
- L58 `_tree_lines` `(root: 'Path', files: 'list', depth: 'int') -> 'list'` — 目录树（限深）：按层级缩进渲染，目录优先排序。
- L192 `cmd_audit` `(engine, target: 'str' = '', out: 'str' = '', strategy: 'str' = 'base', exclude: 'str' = '', timeout: 'int' = 0) -> 'tuple'` — 架构了解：自动编排默认 AuditTask 跑快速探索，复用 audit 双轨产物。
- L123 `cmd_map` `(target: 'str' = '', out: 'str' = '', depth: 'int' = 3, exclude: 'str' = '') -> 'tuple'` — 扫描目标学习项目，编排目录（树 + 模块地图 + 技术栈线索），双轨产物。

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

### project 产物目录

**project/commands.py**（4 个顶层函数/类）
- L20 `cmd_init` `(name: 'str', git: 'bool' = False, base: 'str' = '') -> 'tuple'` — 
- L39 `cmd_list` `(base: 'str' = '') -> 'tuple'` — 
- L56 `cmd_root` `(name: 'str', base: 'str' = '') -> 'tuple'` — 
- L15 `project_dir` `(name: 'str', base: 'Path' = None) -> 'Path'` — 

### patch 自演化修复

**patch/model.py**（2 个顶层函数/类）
- L0 `PatchScript`  — 一条审计缺陷 → 可执行补丁脚本（落盘 .py，可审查/应用/回滚）。
- L31 `load_patch` `(path) -> 'PatchScript'` — 从固化脚本读取 PATCH 常量。

**patch/rules.py**（1 个顶层函数/类）
- L51 `strategy_for` `(kind: 'str', rules: 'dict' = None) -> 'dict'` — 缺陷 kind → 规则（rules 覆盖默认）。

**patch/generators.py**（14 个顶层函数/类）
- L0 `DefuseCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `EntryCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `EnvTodoPatch`  — 标注：硬编码配置外置环境变量 TODO。
- L0 `GuardCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `InsertSetAfterClear`  — 自动修复：Event 标志 clear() 后补 set() 恢复（AST 定位 + 插入行）。
- L0 `MergeCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `PatchPlugin`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `ResetCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L0 `TodoCommentPatch`  — 修复插件抽象接口（namespace=patch.generator）。
- L30 `_comment_ops` `(path: 'Path', lineno: 'int', comment: 'str') -> 'list'` — 在指定行尾追加 TODO 注释（replace 操作，幂等）。
- L40 `_find_clear_call` `(path: 'Path', attr: 'str', lineno: 'int') -> 'dict'` — AST 定位 Event 标志 clear() 调用：返回 {line, indent}。
- L18 `_issue_id` `(issue: 'dict', kind: 'str') -> 'str'` — 
- L22 `_line_text` `(path: 'Path', lineno: 'int') -> 'str'` — 
- L178 `build_patch` `(issue: 'dict', root: 'Path', rules: 'dict' = None, generator=None) -> 'PatchScript'` — 缺陷 issue → 补丁脚本。generator 可由 Registry.create("patch.generator", strate

**patch/gen.py**（4 个顶层函数/类）
- L55 `_rel_to_root` `(file: 'str', root: 'Path') -> 'str'` — 绝对路径缺陷定位 → 相对 root（补丁脚本 file 字段用相对路径）。
- L51 `_safe_name` `(s: 'str') -> 'str'` — 
- L68 `gen_patches` `(engine, db: 'Path | str', root: 'Path', out_dir: 'Path', rules: 'dict' = None) -> 'Result'` — 逐缺陷生成补丁脚本并落盘 → Result（artifacts = 脚本路径列表）。
- L11 `load_issues` `(db: 'Path | str') -> 'list'` — 从 interface_chain.db 各缺陷表归一化为 issue dict 列表。

**patch/apply.py**（2 个顶层函数/类）
- L7 `apply_patch` `(patch_file: 'Path | str', root: 'Path', backup: 'bool' = True) -> 'tuple'` — 应用单个补丁 → (ok, message, applied_ops)。
- L43 `apply_patches` `(patch_files: 'list', root: 'Path', backup: 'bool' = True) -> 'tuple'` — 批量应用补丁 → (ok, [messages])

**patch/verify.py**（2 个顶层函数/类）
- L8 `count_issues` `(db: 'Path | str') -> 'dict'` — 当前审计缺陷计数（按维度）。
- L17 `verify_patches` `(engine, db_before: 'Path | str', db_after: 'Path | str', expected_kinds: 'tuple' = ()) -> 'Result'` — 比较补丁前后的缺陷集合。

