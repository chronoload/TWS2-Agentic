# 数据读取多源回退（只读）设计

日期：2026-08-17 · 分支：remote

## 背景

TS2 数据存在两处：

- **工作区** `/data`（容器内）：被 `backup-sync.js` git 备份，冷启动从备份仓库恢复。
- **`~/.ts2`**（容器内 `Path.home()/.ts2`）：本地部署时存真实数据（LLM providers、bookmarks、courses 等），但**不参与备份**，容器冷启动即丢失。

现状读取逻辑各处不一致：

- `courses_structured` 已有三源合并（工作区 + `~/.ts2` + 工作区上级目录）。
- `bookmarks`/`task_board`/`projects` 只读工作区。
- LLM 配置 `providers.json` 硬编码 `~/.ts2/agent_config/providers.json`，且 `get_llm_config()` 有模块级缓存，启动读不到就永久读不到。

## 目标

让所有读数据的前后端统一走「`~/.ts2` 优先 → 工作区回退」的只读多源策略，使本地部署与容器部署都能读到数据。**只读，不改写**；前端不直接访问 Python，故全部在服务端 Python 完成。仅改 remote 分支。

## 设计

### 统一解析函数

在 `src/mcp/server/app.py` 新增：

```python
def _read_resolve(workspace_dir: str, *segs: str) -> Path:
    """~/.ts2 优先，回退工作区。用于只读多源回退。"""
    home_cand = Path.home() / ".ts2" / Path(*segs)
    if home_cand.exists():
        return home_cand
    ws_cand = Path(workspace_dir) / Path(*segs)
    if ws_cand.exists():
        return ws_cand
    return ws_cand  # 保持写行为不变（调用方仅读时按存在性判断）
```

### 改动点

1. **app.py 各读取处**（约 15 处）用 `_read_resolve(workspace_dir, *segs)` 替换 `Path(workspace_dir) / ...` 直读：
   - `bookmarks.json`（2642 / 3823）
   - `task_board.json`（2605 / 2869 / 2899 / 2919 / 3797）
   - `projects.json`（2697 / 3845）
   - `courses_structured.json`（4071 / 4121 / 4137 / 4803）
   - `data/progress/*.json`（2942 / 2953 / 3967 / 3997 / 4038 / 4081 / 4148）
   - `data/resource_index.json`（4210 / 4224 / 4247 / 4299）
   - `data/notebooks/*.json`（3667 / 3682 / 3689 / 3698）
   - `data/workflow_log.json`（4654 / 4666 / 4681）
   - 已有的 `_read_courses_data` 三源合并（2705）**保持不变**。

2. **LLM 配置** `src/mcp/server/saber/llm_manager.py`：
   - `_load_providers()` 改为 `~/.ts2/agent_config/providers.json` 优先 → 回退工作区 `agent_config/providers.json`。
   - 修复模块级缓存：`_SABER_LLM_CACHE` 仅在成功时缓存，失败不缓存，并按需刷新。

3. **ConfigManager** `src/mcp/config.py`：
   - `_resolve_config_file` 已优先 `~/.ts2` + legacy 回退；补充工作区回退（workspace 下 `agent_config/<file>`）。

### 明确不做

- 写入逻辑（仍写工作区）。
- `.db` 数据库文件（saber.db / ts2.db 等，非 JSON，无法简单回退）。
- 前端 JS 改动。

## 测试

- 本地（有真实 `~/.ts2`）：各读取端点优先读到 `~/.ts2` 数据。
- 容器（`~/.ts2` 空 + `/data` 有恢复数据）：各读取端点回退读到 `/data` 数据。
- LLM：`get_llm_config()` 在 providers 缺失时不缓存失败结果。