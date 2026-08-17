# Linux 容器适配：终端修复 + Rmd 编译异步就绪

日期：2026-08-17 · 分支：remote

## 背景

TS2 部署在 Render 免费版（Linux 容器，`python:3.12` 底镜像，无持久盘，冷启动恢复数据）。发现两个 Linux 下不可用/缺失的功能：

1. **xterm 终端在 Linux 下直接 500**：`src/mcp/server/app.py:2386` 在 `/api/terminal` WebSocket 端点**无条件 `import winpty`**。winpty 是 Windows 专用库，容器未安装 → 该端点一连接就 ImportError，整个终端不可用。Linux 下本应走已有的 subprocess fallback 分支（`bash`/`sh`），但被这个 import 卡死在前头。

2. **Rmd 编译不可用**：`/api/tools/knit-rmd`（app.py:3139）和编辑器三格式编译都调 `Rscript -e "rmarkdown::render(...)"`，但容器没有 R / rmarkdown / pandoc / LaTeX。本地 `course_tracker._add_rmd_compile_buttons` 同样依赖本地 R。

3. **mindmap**：纯前端静态资源，已确认无 Linux 适配问题（排除）。

## 目标

- 修复 `/api/terminal`，使 Linux 容器（Render）上 xterm 终端可用（bash subprocess fallback）。
- 容器运行时**异步安装完整 R 环境**（R + rmarkdown + knitr + pandoc + tinytex），使 `/api/tools/knit-rmd` 能产出 PDF/HTML/DOCX。
- **不阻塞启动**：Web 服务（页面、终端、API）立即可用；R 环境在后台安装，未就绪时编译接口返回明确提示。
- 不改变本地 Windows 行为（winpty PTY 路径保留）。
- 不改 Dockerfile 构建（保持轻量，避免免费版构建超时）；仅改 remote 分支。

## 设计

### 1. 终端端点修复（app.py /api/terminal）

`import winpty` 仅在 `os.name == "nt"` 时执行；Linux 直接跳过 PTY 分支，走已有的 subprocess fallback。

```python
# 伪码
shell = "cmd.exe" if os.name == "nt" else "bash"
if os.name == "nt":
    import winpty as _winpty
    # ... 原 winpty PTY 分支（spawn/read/write/set_size） ...
    return
# Linux: 直接进入现有 subprocess fallback 分支（bash/sh）
```

要点：
- `winpty` 相关 import 移到 `if os.name == "nt":` 块内（函数级 import，改动最小）。
- Linux 下跳过 PTY 创建，走现有 fallback（`create_subprocess_exec(shell=...bash)` + 输入回显）。fallback 分支已存在且完整，无需重写。
- 前端 `__shell__:bash` 消息继续发送，texpile 语法高亮逻辑不变。

### 2. R 环境异步安装（新增 src/mcp/server/r_env.py）

```python
_STATE = {"installing": False, "ready": False, "error": "", "log": [], "done_at": None}
def is_r_ready() -> bool: ...
def get_r_status() -> dict: ...
def setup_r_environment(workspace_dir, interval=15):
    """后台线程：apt 装 R+pandoc → Rscript 装 rmarkdown/knitr/tinytex → tinytex 装 LaTeX
    轮询 apt/dpkg 是否空闲（避免与部署脚本抢锁），失败记录到 _STATE。"""
```

- 启动时由 `deploy_start.py` spawn 一个 `threading.Thread(daemon=True)` 调 `setup_r_environment`，**不 join**，不阻塞服务启动。
- 安装分阶段：
  1. `apt-get update && apt-get install -y --no-install-recommends r-base pandoc`（Debian 源，`--no-install-recommends` 减小体积）。
  2. `Rscript -e "install.packages(c('rmarkdown','knitr','tinytex'), repos='https://cloud.r-project.org')"`。
  3. `Rscript -e "tinytex::install_tinytex()"`（LaTeX 精简版，支持 PDF）。
  4. 完成 → `_STATE["ready"]=True`；任一步失败 → 记录 `_STATE["error"]`，可重试。
- 状态端点 `/api/tools/r-status`（简单 GET，返回 `_STATE` 子集），前端可用轮询展示"R 环境安装中/就绪/失败"。
- 用 `apt` 安装避免 Dockerfile 构建膨胀；`apt-get` 需 root（容器默认 root，无需 sudo）。

### 3. 编译接口适配（app.py /api/tools/knit-rmd）

`tools_knit_rmd` 开头增加：

```python
if not is_r_ready():
    return ok(data={"success": False, "error": "R 环境安装中或未就绪，请稍后重试",
                    "r_status": get_r_status()})
```

就绪后原逻辑不变（`Rscript` 调用、超时 300s、输出扩展名映射）。未就绪时不再启动子进程。

### 4. deploy_start.py

在启动 Web 服务前 spawn 后台线程：

```python
threading.Thread(target=r_env.setup_r_environment, args=(workspace_dir,), daemon=True).start()
```

不等待。若容器冷启动，R 安装与 backup-sync 恢复并行，互不干扰。

### 明确不做

- 不改 Dockerfile / render.yaml 构建阶段（保持镜像轻量，R 体积 ~数百 MB 不进镜像）。
- 不重写 Linux PTY（pyte 等第三方 PTY 库），subprocess fallback 足够。
- 不改前端 app.js / index.html（终端、编译按钮复用现有调用）。
- 不处理 R 包运行时依赖（用户 Rmd 用的额外 R 包不在本次范围，仅保证 rmarkdown 渲染链路）。

## 测试

- 本地 Windows 回归：`/api/terminal` 仍走 winpty PTY（`os.name=="nt"` 分支不变），终端可用。
- 语法检查：`python -m py_compile` app.py / r_env.py / deploy_start.py。
- `r_env.py` 单测：`is_r_ready()` / `get_r_status()` 状态机（不真跑 apt）；可用 monkeypatch 模拟。
- 容器验证（Render 部署后）：终端 `bash` 可用；`/api/tools/r-status` 从 installing → ready；`/api/tools/knit-rmd` 未就绪时返回安装提示，就绪后能产出 PDF/HTML/DOCX。
