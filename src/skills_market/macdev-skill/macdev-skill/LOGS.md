# macdev LOG — 经验沉淀库

> 由 `python -m macdev log` 生成；机器可查入口：`logs.db`（表 logs）。
> 共 11 条。

## 随包经验（pkg）— 11 条

### 经验教训（lessons）— 2 条

#### [6] 回归语境核实：链图只是线索

- 分类: lessons ｜ 标签: context,memory,rag,verify ｜ 时间: 2026-08-11 20:07:38

宏观链图只给线索，动手前必须 ls/grep/read 回到语境：记忆(memory/)、RAG 注入、ContextProvider 分层、工具注册、中间件链——不核查无法确认真实角色。链图 broken/同名定义可能是参数或 builtin 噪音。

#### [5] 死代码清理要同步删 re-export

- 分类: lessons ｜ 标签: deadcode,export,test ｜ 时间: 2026-08-11 20:07:37

compact_messages/create_auto_compact/create_context_window 这类无调用方但被 __init__ re-export 的函数：删定义时须同步删 __init__ 的 import 与 __all__，否则 hasattr 断言仍绿、公共 API 残留。


### 陷阱（pitfalls）— 5 条

#### [8] pathlib glob 拼接陷阱：Path(x)/'**' 后 rglob/glob 返回空

- 分类: pitfalls ｜ 标签: pathlib,glob,oswalk,audit ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/requirement/align.py

Path(root) / Path('**') 拼接后再 .rglob('*.py') 在 Windows 上返回空——'**' 已作为字面路径段处理，递归通配失效。正解：直接 oot.glob('**/*.py')，或参考 audit 用 os.walk 逐目录容错 + 目录名剪枝（断链/权限目录只跳过该目录，不整批丢失）。

#### [7] getattr 默认值让 defuse 噪音 + 语义 bug

- 分类: pitfalls ｜ 标签: defuse,getattr,model ｜ 时间: 2026-08-11 20:07:38

agent_assistant._async_compact 用 getattr(self.agent,'model','') 恒返回空字符串：既让 defuse 扫描报 loose_match(self 无 model 赋值)，又是语义 bug(模型窗口恒 128000)。应取 self.agent.config.model_id。

#### [4] builtin 反射噪音：属性与内置函数同名

- 分类: pitfalls ｜ 标签: reflection,builtin,id ｜ 时间: 2026-08-11 20:07:35

harness/turn.py 的 Turn.id property 与 builtin id() 同名污染符号反射/静态扫描。属性访问重命名为 turn_id，同步更新调用方。

#### [3] 依赖缺失误判：pytest.raises(ModuleNotFoundError) 假绿

- 分类: pitfalls ｜ 标签: test,tiktoken,module ｜ 时间: 2026-08-11 20:07:34

模块内部 import tiktoken 失败抛 ModuleNotFoundError，会让 pytest.raises(ModuleNotFoundError) 误捕获(假绿)。判断模块删除一律用 importlib.util.find_spec(...) is None。

#### [2] namespace package 陷阱：import 判断模块已删会误绿

- 分类: pitfalls ｜ 标签: import,module,test ｜ 时间: 2026-08-11 20:07:19

删除 skills.py 后同名目录 skills/ 仍在，importlib.import_module('mcp.skills') 依然成功(namespace package, __file__=None)。断言模块删除不能用 import 抛异常，改用文件存在性 Path(...skills.py).exists() 或 importlib.util.find_spec(...) is None。


### 模式（patterns）— 3 条

#### [11] 测试：随包经验

- 分类: patterns ｜ 标签: — ｜ 时间: 2026-08-11 21:07:41

通用模式，应落在随包库

#### [9] 插件迁移双轨约定：CRUD 每次变更自动刷新 md+json+csv+db 四件套

- 分类: patterns ｜ 标签: 双轨,audit,oswalk,self-evolve ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/requirement

新插件（如 requirement）任何变更（add/update/delete/align）后自动 refresh 双轨产物：db 权威 + json/csv 机器快照 + md 人类可读，时间戳 UTC、编码 utf-8，语言环境无关。代码扫描参考 audit 健壮性：os.walk 逐目录容错 + 排除目录剪枝 + >12MB 极端生成产物跳过（常规大文件不跳过）。

#### [1] skill 体系三分类（A/B/C）

- 分类: patterns ｜ 标签: skill,mcp,refactor ｜ 时间: 2026-08-11 20:07:18

审查 skill 管理链路时先按性质分类：A 类文本技能(SKILL.md+scripts)归唯一注册表门面；B 类硬编码工具(skill_xxx handler/builtin)迁 tools.py 注册 Tool 子类；C 类远程 MCP(技能目录 mcp.json)统一并入 mcp_servers.json(service_type=mcp, transport=stdio|http|sse)，技能包内 mcp.json 保留为外部客户端配置模板。


### 决策（decisions）— 1 条

#### [10] 大文件跳过阈值：文件大小不是问题，仅 12MB 以上极端生成产物跳过

- 分类: decisions ｜ 标签: 阈值,audit,requirement ｜ 时间: 2026-08-11 20:48:52
- 引用: macdev/audit/runner.py

audit collect_files 与 requirement build_code_index 统一：>12MB 才跳过（编译/生成产物），常规大文件不跳过。原 1MB 阈值过小，会漏审真实大文件。

