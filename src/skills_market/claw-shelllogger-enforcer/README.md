# Claw Shell Logger Enforcer Skill

强制在 Claw 项目中使用 `shell_logger.run()`，否则拦截执行。

## 快速开始

### 安装

此 skill 已在 `~/.workbuddy/skills/claw-shelllogger-enforcer/` 中。

### 启用

在 Claw 项目的 `.workbuddy/rules/` 中添加规则（或已自动添加）：

```
Claw/.workbuddy/rules/shelllogger-enforcer.mdc
```

### 使用

当在 Claw 目录下执行任何命令时，此 skill 会自动检查：

```python
# ✅ 正确方式
from shell_logger import run
result = run("python test.py")

# ❌ 被拦截
execute_command("python test.py")  # 会被拦截并要求纠正
```

## 工作原理

### 1. 拦截

当 AI 尝试调用 `execute_command` 时，Claw Shell Logger Enforcer 会在**前置** 检查是否：

- 工作目录在 Claw 项目下？
- 命令是纯查询性质吗？
- 是否已使用 shell_logger？

### 2. 判决

根据检查结果：

- **PASS** → 允许执行（已使用 shell_logger）
- **EXEMPT** → 豁免执行（纯查询或非 Claw 目录）
- **FAIL** → 拦截执行（违规，要求纠正）

### 3. 纠正

如果被拦截，AI 会：

1. 输出违规说明
2. 提供正确的调用方式
3. 使用 shell_logger 重新执行

## 规则检查

### 会被拦截的

❌ 在 Claw 目录下执行这些会被拦截：

```python
# 1. 直接 execute_command（非 shell_logger）
execute_command("python test.py")

# 2. Python 脚本内使用 subprocess
import subprocess
subprocess.run(["python", "test.py"])

# 3. 使用 os.system
import os
os.system("python test.py")
```

### 不会被拦截的

✅ 这些操作不会被拦截：

```python
# 1. 已使用 shell_logger
from shell_logger import run
run("python test.py")

# 2. 纯查询命令
execute_command("tasklist")
execute_command("dir C:\\...")

# 3. 不在 Claw 目录
execute_command("cd /d C:\\Other && python test.py")

# 4. 同步工作流脚本
execute_command("python sync_workflows/run_sync.py")
```

## 日志

所有检查结果记录在：

```
Claw/logs/shelllogger_enforcer.log
```

查看最近的检查：

```bash
# PowerShell
tail -f Claw/logs/shelllogger_enforcer.log

# 或用 Python
python -c "import json; [print(json.loads(line)) for line in open('Claw/logs/shelllogger_enforcer.log')]"
```

## 豁免列表

以下命令**自动豁免**（不需要 shell_logger）：

| 类型 | 命令例 | 说明 |
|------|--------|------|
| 查询 | `tasklist`, `Get-Process` | 只读 |
| 文件 | `dir`, `ls`, `find` | 只读 |
| 搜索 | `findstr`, `grep` | 只读 |
| 信息 | `echo`, `type`, `cat`, `pwd` | 无副作用 |

## 常见问题

### Q1：为什么我的命令被拦截了？

**A**：如果你在 Claw 目录下执行非查询命令，必须使用 shell_logger：

```python
from shell_logger import run
run("your_command_here")
```

### Q2：如何在 Python 脚本中调用其他命令？

**A**：导入 shell_logger，使用 `run()` 函数：

```python
# test_script.py
import sys
sys.path.insert(0, 'c:/Users/qu/WorkBuddy/Claw')
from shell_logger import run

result = run("python sub_task.py", title="Sub Task")
print(f"Return code: {result.returncode}")
```

### Q3：如何豁免某个特定命令？

**A**：
1. 检查是否是纯查询命令（如 `tasklist`）→ 自动豁免
2. 如果需要手动豁免，修改 `EXEMPT_PATTERNS` 或 `QUERY_COMMANDS`
3. 联系维护者讨论是否应该豁免

### Q4：同步工作流脚本为什么没被拦截？

**A**：因为 `sync_log_to_wechat.py` 在豁免列表中，但**脚本内部** 仍需使用 shell_logger。

### Q5：我可以禁用此规则吗？

**A**：可以，但**强烈不建议**。此规则存在是为了：
- 保证所有操作都有日志
- 确保网络安全审查被执行
- 防止意外的系统变更

## 配置

### 修改豁免列表

编辑 `claw_shelllogger_enforcer.py` 中的配置：

```python
# 添加查询命令豁免
QUERY_COMMANDS.add("my_query_command")

# 添加豁免命令模式
EXEMPT_PATTERNS.add("pattern_to_exempt")
```

### 改变严格程度

```python
ENFORCE_MODE = "strict"    # 严格模式（推荐）
ENFORCE_MODE = "relaxed"   # 宽松模式（测试用）
```

## 集成到 Claw 工作流

此 skill 与其他 Claw 组件的协作：

```
AI 调用 execute_command
    ↓
[shell_logger_enforcer] 检查方式是否合规
    ↓
shell_logger.run() 执行命令（弹窗 + 日志）
    ↓
[network_guard] 检查网络安全
    ↓
[security_guard] 检查命令安全
    ↓
[visible_runner] 实际执行
```

## 故障排查

### 问题：命令总是被拦截

**检查清单**：

1. ✓ 工作目录是否在 Claw 下？
2. ✓ 命令是否是查询类型（如 `tasklist`）？
3. ✓ 是否已导入并使用 `shell_logger.run()`？
4. ✓ 日志中的原因是什么？（`shelllogger_enforcer.log`）

### 问题：同步脚本无法运行

**排查**：

```bash
# 1. 检查 run_sync.py 是否使用了 shell_logger
grep -n "shell_logger" Claw/sync_workflows/run_sync.py

# 2. 检查错误日志
tail -20 Claw/logs/shell_calls.log
```

### 问题：想要调试此规则

**启用测试模式**：

```python
# claw_shelllogger_enforcer.py
from claw_shelllogger_enforcer import check_and_enforce

# 允许绕过（仅测试）
allowed = check_and_enforce(
    "python test.py",
    allow_bypass=True
)
```

## 维护

此 skill 由用户维护。禁止修改：

- ❌ 检查逻辑
- ❌ 规则文件本身
- ❌ shell_logger 调用方式

可以修改：

- ✅ 豁免命令列表
- ✅ 错误提示信息
- ✅ 日志格式

## 更新日志

### v1.0 (2026-03-17)

- 初版发布
- 支持基本的 shell_logger 强制检查
- 包含豁免列表和查询命令识别
- 完整的日志记录

## 许可和责任

此 skill 用于保护 Claw 项目的完整性。使用者应理解：

- ✅ 提高了执行的可追溯性
- ✅ 增强了安全性
- ✅ 防止了误操作
- ⚠️ 可能会偶尔拦截合法操作（需手动豁免）

## 相关文档

- [shell_logger.py](../../../Claw/shell_logger.py)
- [Claw Shell-Logging 规则](../../../Claw/.workbuddy/rules/shell-logging.mdc)
- [Security Policy](../../../Claw/.workbuddy/rules/security-policy.mdc)
- [Skill SKILL.md](./SKILL.md)
