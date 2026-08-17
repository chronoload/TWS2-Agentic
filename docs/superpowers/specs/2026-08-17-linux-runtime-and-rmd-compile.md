# Linux 容器适配：xterm 终端修复

日期：2026-08-17 · 分支：remote

## 背景

TS2 部署在 Render 免费版（Linux 容器，`python:3.12` 底镜像，无持久盘，冷启动恢复数据）。发现 xterm 终端在 Linux 下直接不可用：

**`/api/terminal` 在 Linux 下 500**：`src/mcp/server/app.py:2386` 在 WebSocket 端点**无条件 `import winpty`**。winpty 是 Windows 专用库（PTY 桥接 cmd.exe），容器未安装 → 该端点一连接就 ImportError，整个终端不可用。

Linux 下本应走已有的 subprocess fallback 分支（`bash`/`sh`，app.py:2475 起），但被这个 import 卡死在前头。

**已排除**：
- mindmap：纯前端静态资源，无 Linux 适配问题。
- Rmd 编译 / R 环境：Render 免费版 RAM 太小（512MB），**不装 R**，不在本次范围。

## 目标

- 修复 `/api/terminal`，使 Linux 容器（Render）上 xterm 终端可用（bash subprocess fallback）。
- 不改变本地 Windows 行为（winpty PTY 路径保留）。
- 不改前端（app.js / index.html）、不改 Dockerfile。
- 仅改 remote 分支。

## 设计

### 终端端点修复（app.py /api/terminal）

把 `import winpty` 改为条件导入：仅在 Windows 尝试 import；import 失败（无论平台）置 None，PTY 分支自动跳过，走 subprocess fallback。

```python
import shutil as _shutil
# winpty 仅 Windows 可用；Linux 无此包，跳过 PTY 直接走 subprocess fallback
_winpty = None
if os.name == "nt":
    try:
        import winpty as _winpty
    except ImportError:
        _winpty = None
```

要点：
- `_winpty is None` 时 `_create_pty()` 抛异常 → 被现有 `try/except` 捕获 → `pty = None` → 走已有 fallback 分支（`create_subprocess_exec("bash")` + 输入回显）。无需重写 fallback。
- Windows 行为不变：`winpty` 正常 import 时走原 PTY 分支。
- Windows 未装 winpty 包时也优雅降级到 subprocess（原有 ImportError 崩溃也被修复）。

## 测试

- 语法检查：`python -m py_compile src/mcp/server/app.py`。
- 本地 Windows 回归：`/api/terminal` 仍走 winpty PTY 分支（os.name=="nt"，winpty 已装），终端可用。
- 容器验证（Render 部署后）：xterm 打开 bash，可执行命令，输入回显正常。