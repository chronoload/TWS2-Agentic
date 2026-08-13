# Workflow 注册指南

> 如何定义、注册、启动一个工作流（Workflow）。适用 TS2 / WS2 系统。

---

## 1. 总览：三层注册架构

一个工作流从"代码定义"到"可运行"经历 **三层注册**：

```
① 定义层    predefined_workflows.py（或任意模块）里写工厂函数返回 WorkflowDefinition
        │
② 注册表层  WORKFLOW_REGISTRY: Dict[str, WorkflowDefinition]   （内存注册表）
        │      register_workflow(wf) / register_macdev_workflows(REGISTRY)
        │
③ 持久化层  WorkflowEngine.register_builtin_workflows()
        │      → persistence.save_definition(wf)  （写入 data/workflow.db 的 workflow_definitions 表）
        │
        ▼
   运行     get_workflow_engine().start_workflow(wf_def, input_data)
```

- **注册表**（`WORKFLOW_REGISTRY`）是进程内"已知工作流清单"，按 `workflow_id` 索引；
- **持久化**（SQLite `workflow.db`）让工作流定义跨重启保留，且**已存在的定义不重复写入**（幂等）；
- **启动**时既可传 `WorkflowDefinition` 对象，也可从持久化库按 id 读取。

---

## 2. 核心数据模型

### 2.1 WorkflowDefinition（工作流定义）

```python
@dataclass
class WorkflowDefinition:
    workflow_id: str                       # 唯一 ID（注册表 key）
    name: str                              # 显示名
    description: str = ""                  # 描述（list_workflows 展示）
    version: str = "1.0"
    input_schema: Optional[Dict] = None    # 入参 JSON Schema（可选）
    output_schema: Optional[Dict] = None   # 出参 JSON Schema（可选）
    steps: List[StepDefinition] = []       # 步骤列表
    entry_step: Optional[str] = None       # 入口步骤 id（缺省 = steps[0]）
    checkpoint_after: Set[str] = set()     # 在这些步骤后落检查点（可恢复）
```

### 2.2 StepDefinition（步骤）

```python
@dataclass
class StepDefinition:
    step_id: str                    # 步骤唯一 id（流程内）
    name: str                       # 步骤名
    step_type: StepType             # 步骤类型（见下）
    config: Dict[str, Any] = {}     # 类型相关配置（如 tool 名、agent 参数）

    prompt_template: Optional[str] = None   # AGENT 步骤的提示词模板
    tools: Optional[List[str]] = None       # AGENT 步骤可用的工具名列表
    max_retries: int = 3

    # 条件分支
    condition_expr: Optional[str] = None    # 条件表达式（python eval，可访问 ctx 变量）
    true_steps: Optional[List[str]] = None  # 条件成立时执行的步骤
    false_steps: Optional[List[str]] = None # 不成立时执行的步骤

    # 并行
    parallel_steps: Optional[List[Dict]] = None

    # 循环
    loop_var: Optional[str] = None
    loop_items: Optional[str] = None        # 迭代来源（ctx 变量名）
    max_iterations: int = 10

    # 参数链（前一步输出 → 下一步输入）
    param_inputs: Optional[List[Dict[str, Any]]] = None
    param_outputs: Optional[List[Dict[str, Any]]] = None
    param_transforms: Optional[Dict[str, str]] = None
```

### 2.3 StepType（步骤类型）

| 枚举             | 值                 | 用途                                           |
| ---------------- | ------------------ | ---------------------------------------------- |
| `AGENT`        | `"agent"`        | 调 LLM（prompt_template + tools）              |
| `TOOL`         | `"tool"`         | 直接执行工具（config.tool_name + args）        |
| `CONDITION`    | `"condition"`    | 条件分支（condition_expr → true/false_steps） |
| `PARALLEL`     | `"parallel"`     | 并行执行子步骤                                 |
| `LOOP`         | `"loop"`         | 循环执行（loop_items / max_iterations）        |
| `WAIT`         | `"wait"`         | 等待                                           |
| `NOTIFY`       | `"notify"`       | 通知/推送                                      |
| `GT_PROVE`     | `"gt_prove"`     | 数学证明（GT 系统）                            |
| `LEAN_CHECK`   | `"lean_check"`   | Lean4 校验                                     |
| `MANIM_GEN`    | `"manim_gen"`    | Manim 动画生成                                 |
| `MATHLENS`     | `"mathlens"`     | MathLens 视频                                  |
| `AUTORESEARCH` | `"autoresearch"` | 自动研究管线                                   |

---

## 3. 内置注册表（WORKFLOW_REGISTRY）

位置：`src/mcp/predefined_workflows.py`（末尾）

```python
WORKFLOW_REGISTRY: Dict[str, WorkflowDefinition] = {
    "code_analysis":      code_analysis_workflow(),
    "research":           research_workflow(),
    "note_generation":    note_generation_workflow(),
    "code_review":        code_review_workflow(),
    "dependency_scan":    dependency_scan_workflow(),
    "rss_academic_tracker": rss_academic_tracker_workflow(),
    "course_progress_reminder": course_progress_reminder_workflow(),
    "pending_task_reminder":   pending_task_reminder_workflow(),
    "course_mode":        course_mode_workflow(),
    "gt_basic_prove":     gt_basic_prove_workflow(),
    "gt_evolution_prove": gt_evolution_prove_workflow(),
    "rmd_workflow":       rmd_workflow_workflow(),
    "lean4_proof_check":  lean4_proof_check_workflow(),
    "lean4_lake_build":   lean4_lake_build_workflow(),
    "lean4_formalize":    lean4_formalize_workflow(),
    "lean4_golf":         lean4_golf_workflow(),
    "manim_animation":    manim_animation_workflow(),
    "manim_rag_search":   manim_rag_search_workflow(),
    "manim_pipeline":     manim_pipeline_workflow(),
    "manim_self_improve": manim_self_improve_workflow(),
    "mathlens_video":     mathlens_video_workflow(),
    "autoresearch":       autoresearch_workflow(),
    "param_chain_demo":   param_chain_demo_workflow(),
    "lean4_param_chain":  lean4_param_chain_workflow(),
}

# 追加 macdev 工作流（wf_macdev_*）
register_macdev_workflows(WORKFLOW_REGISTRY)
```

注册表提供的三个函数：

```python
from mcp.predefined_workflows import (
    get_workflow,          # get_workflow("research") → WorkflowDefinition
    list_workflows,        # → {wf_id: description, ...}
    register_workflow,     # register_workflow(wf_def, registry_key=None) 追加到注册表
)
```

---

## 4. 引擎与持久化

### 4.1 获取引擎（进程内单例）

```python
from mcp.workflow_engine import get_workflow_engine

engine = get_workflow_engine(Path("data/workflow.db"))   # 同 db 路径 → 同一实例
```

### 4.2 内置工作流注册（幂等）

```python
engine.register_builtin_workflows()
# 遍历 WORKFLOW_REGISTRY：
#   - persistence 中不存在 → save_definition 写入
#   - 已存在 → 跳过（不覆盖，保留用户修改）
```

### 4.3 持久化 API（WorkflowPersistence）

```python
engine.persistence.save_definition(wf_def)      # INSERT OR REPLACE
engine.persistence.get_definition(wf_id)        # → WorkflowDefinition | None
engine.persistence.list_definitions()           # → [dict]
```

---

## 5. 如何注册一个新工作流（三种方式）

### 方式 A：加入内置注册表（随系统分发）

1. 在 `predefined_workflows.py`（或独立模块）写工厂函数：

```python
def my_pipeline_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="my_pipeline",
        name="我的流水线",
        description="示例：TOOL → AGENT 两步流水线",
        steps=[
            StepDefinition(
                step_id="fetch",
                name="拉取数据",
                step_type=StepType.TOOL,
                config={"tool_name": "fetch_url", "url_var": "url"},
                param_inputs=[{"name": "url", "source": "input.url"}],
                param_outputs=[{"name": "content", "key": "result"}],
            ),
            StepDefinition(
                step_id="summarize",
                name="总结",
                step_type=StepType.AGENT,
                prompt_template="请总结以下内容：\n{{ctx.fetch.content}}",
                tools=["read_file", "web_search"],
            ),
        ],
        entry_step="fetch",
        checkpoint_after={"fetch"},   # fetch 后落检查点，可断点恢复
    )
```

2. 挂进 `WORKFLOW_REGISTRY`：

```python
# predefined_workflows.py 末尾
WORKFLOW_REGISTRY["my_pipeline"] = my_pipeline_workflow()
```

3. 引擎注册（幂等写入 db）：

```python
engine = get_workflow_engine()
engine.register_builtin_workflows()   # 或单独：engine.persistence.save_definition(get_workflow("my_pipeline"))
```

### 方式 B：运行期注册到内存注册表（不落库）

```python
from mcp.predefined_workflows import register_workflow, get_workflow

register_workflow(my_pipeline_workflow())   # 进程内可用
wf = get_workflow("my_pipeline")
engine.start_workflow(wf, {"url": "https://example.com"})
```

### 方式 C：仅持久化（不挂注册表）

```python
engine.persistence.save_definition(my_pipeline_workflow())
# 后续从 db 读回
wf = engine.persistence.get_definition("my_pipeline")
engine.start_workflow(wf, {...})
```

---

## 6. 启动 / 暂停 / 恢复

```python
# 启动：返回 instance_id
instance_id = engine.start_workflow(
    get_workflow("my_pipeline"),
    input_data={"url": "https://example.com"},
)

# 恢复（断点续跑）
engine.resume_workflow(instance_id)

# 可恢复实例列表
engine.list_recoverable()

# 订阅事件（WS 推送等）
engine.on_event(lambda e: print(e.type, e.instance_id, e.data))
```

---

## 7. 外部入口（Agent / 工具 / API）

- **Agent 工具**：`workflow` 工具（action=define/start/status/pause/resume/cancel/list/logs/step_results）
- **服务端 API**：`/api/workflow/*`（列表 / 详情 / 启动 / 状态）
- **AgentCore**（`agent_core.py` 注入到 Agent 实例）：

```python
agent.submit_workflow("my_pipeline", {"url": "..."})   # → instance_id
agent.resume_workflow(instance_id)
agent.list_recoverable_workflows()
```

- **预定义工作流**：`predefined_workflows.get_workflow(id)` 直接取定义启动。

---

## 8. macdev 工作流注册示例（模块级追加模式）

参考 `src/mcp/macdev_workflows.py`：模块内定义 `wf_*` 工厂函数，导出一个注册函数统一追加到注册表：

```python
def register_macdev_workflows(registry: Dict[str, WorkflowDefinition]):
    registry["wf_macdev_audit"] = macdev_audit_workflow()
    registry["wf_macdev_dev_cycle"] = macdev_dev_cycle_workflow()
    registry["wf_macdev_patch"] = macdev_patch_workflow()
    registry["wf_macdev_log"] = macdev_log_workflow()
    # ...
```

`predefined_workflows.py` 顶部 `from .macdev_workflows import register_macdev_workflows`，
模块加载时调用 `register_macdev_workflows(WORKFLOW_REGISTRY)` —— 新增业务工作流可完全按此模式
**不侵入 predefined_workflows 主体**，独立模块 + 注册函数 + 顶部一行调用即可。

---

## 9. 检查与验证

```bash
# 1) 注册表可见性
python -c "from mcp.predefined_workflows import list_workflows; print(list_workflows())"

# 2) 引擎注册（幂等）后 db 持久化
python -c "
from mcp.workflow_engine import get_workflow_engine
e = get_workflow_engine()
e.register_builtin_workflows()
print([d['workflow_id'] for d in e.persistence.list_definitions()])
"
```

---

## 10. FAQ

**Q: 修改了工作流定义，重启后还是旧版本？**
`register_builtin_workflows` 幂等：`workflow_id` 已存在则跳过。强制刷新：
`engine.persistence.save_definition(get_workflow("xxx"))`（INSERT OR REPLACE 覆盖）。

**Q: workflow_id 重名会怎样？**
注册表以 `workflow_id` 为 key，后注册覆盖先注册；持久化 INSERT OR REPLACE 覆盖。

**Q: 步骤之间如何传数据？**
`WorkflowContext`（`get_var/set_var/set_node_output/get_node_output`）+ 步骤的
`param_inputs/param_outputs/param_transforms` 参数链。

**Q: AGENT 步骤如何绑定 Agent？**
引擎创建后调用 `engine.set_agent(agent, {t.name: t for t in agent.tools})`
（服务端 app.py 在创建 Agent 处自动注入，AgentCore 亦复用同一单例）。

**Q: 什么时候落检查点？**
`WorkflowDefinition.checkpoint_after` 列出的步骤执行后落检查点 → 支持 `resume_workflow` 断点续跑。
