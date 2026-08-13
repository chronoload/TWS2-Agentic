# Claw Shell Logger Enforcer

## 概述

这是一个 **强制执行** skill，确保在 Claw 项目（`c:/Users/qu/WorkBuddy/Claw`）中，所有系统命令执行都必须通过 `shell_logger.run()` 进行，否则拦截并拒绝执行。

## 适用范围

- **工作区**：`c:/Users/qu/WorkBuddy/Claw`
- **触发条件**：任何使用 `execute_command` 工具的操作
- **执行模式**：自动激活（无需手动调用）

## 工作原理

### 1. 拦截检查（execute_command 前置）

当 AI 在 Claw 目录下尝试执行命令时：

```python
# ❌ 不允许（直接 execute_command）
run("python foo.py")

# ✅ 允许（使用 shell_logger）
from shell_logger import run
run("python foo.py")
```

### 2. 强制执行流程

如果检测到 **不符合规范** 的执行方式：

1. **拦截** → 中止 execute_command 调用
2. **告知** → 清晰说明违规原因
3. **改正** → 提示正确的执行方式
4. **重做** → 使用 shell_logger 重新执行

### 3. 例外场景

以下情况 **不需要** shell_logger（因为已经符合日志规范）：

- ✅ 已使用 shell_logger 的 Python 脚本
- ✅ 同步工作流脚本（run_sync.py 等）
- ✅ 自动化任务的外壳命令
- ✅ 纯信息查询命令（tasklist, Get-Process 等）

## 工作流示例

### 场景 1：AI 尝试直接执行（会被拦截）

```
用户: "执行 python test.py"
AI: execute_command("cd /d C:\Users\qu\WorkBuddy\Claw && python test.py")
↓
[SKILL CHECK] Claw Shell Logger Enforcer 触发
✗ 违规：未使用 shell_logger
❌ 执行被拦截
→ 提示正确方式
```

### 场景 2：AI 使用了 shell_logger（通过）

```
用户: "执行 python test.py"
AI: 
  from shell_logger import run
  run("python test.py")
↓
[SKILL CHECK] Claw Shell Logger Enforcer 触发
✓ 符合规范：已使用 shell_logger
✅ 允许执行
```

### 场景 3：Python 脚本内使用 shell_logger（通过）

```python
# test_script.py
import sys
sys.path.insert(0, 'C:/Users/qu/WorkBuddy/Claw')
from shell_logger import run

run("python sub_task.py")
```

## 配置参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `CLAW_DIR` | `c:/Users/qu/WorkBuddy/Claw` | Claw 项目根目录 |
| `ENFORCE_MODE` | `strict` | 严格模式：所有命令都检查 |
| `ALLOW_QUERIES` | `true` | 允许纯信息查询命令 |
| `LOG_DIR` | `Claw/logs/` | 日志存储位置 |

## 规则检查清单

✅ **通过检查** 的条件：

1. 命令不在 Claw 目录下 → 不适用此规则
2. 命令已使用 `shell_logger.run()` → 符合规范
3. 命令是纯查询性质（GET 信息，无副作用）→ 豁免
4. 命令来自已记录的 Python 脚本 → 符合规范

❌ **失败检查** 的条件：

1. 在 Claw 目录下直接 execute_command → **拦截**
2. 使用 subprocess/os.system 而非 shell_logger → **拦截**
3. 执行可执行文件而非 shell_logger.run() → **拦截**
4. 尝试修改 shell_logger 规则本身 → **拦截**

## 日志和审计

所有检查都会记录到：

```
Claw/logs/shelllogger_enforcer.log
```

格式：

```json
{
  "timestamp": "2026-03-17T23:53:00",
  "check_result": "PASS|FAIL|EXEMPT",
  "command": "python test.py",
  "reason": "Using shell_logger.run()",
  "location": "send_research_main.py:45"
}
```

## 与其他规则的交互

### 与 security-policy.mdc 的关系

- **security_guard.py** → 检查命令是否安全（ALLOW/WARN/BLOCK）
- **shell_logger_enforcer** → 检查是否正确调用 shell_logger
- **执行顺序**：shell_logger 优先，然后 security_guard

### 与 network_guard.py 的关系

- network_guard 在 shell_logger.run() **内部** 被调用
- 因此此规则间接保证了网络安全审查

## 禁止绕过

⚠️ **严格禁止以下行为**：

1. ❌ 修改 shell_logger.py 来"伪造"日志
2. ❌ 直接调用 visible_runner.py（必须通过 shell_logger）
3. ❌ 使用 `subprocess.run()` 而非 `shell_logger.run()`
4. ❌ 修改本 skill 的检查逻辑

任何绕过尝试都会被记录到审计日志。

## 何时应用此规则

✅ **应该检查**：

- AI 代码中的 execute_command 调用
- Python 脚本中的命令执行
- 自动化任务的外壳命令
- 任何在 Claw 目录内的操作

❌ **不需要检查**：

- 纯文本回复
- 文件读写操作
- 代码编辑操作
- 搜索和查询操作

## 故障排查

### 症状 1：命令被拦截，提示"未使用 shell_logger"

**解决方案**：修改代码，将命令用 shell_logger 包装

```python
from shell_logger import run
result = run("your_command_here")
```

### 症状 2：Python 脚本内的 subprocess 调用被拦截

**解决方案**：改为 shell_logger

```python
# ❌ 不好
import subprocess
subprocess.run(["python", "test.py"])

# ✅ 好
from shell_logger import run
run("python test.py")
```

### 症状 3：自动化任务无法运行

**解决方案**：自动化任务的工作流脚本应该：

1. 导入 shell_logger
2. 使用 run() 执行内部命令
3. 返回结果给 WorkBuddy

## 维护和更新

此 skill 的检查逻辑 **不应被修改**，但可以：

- 扩展豁免列表
- 增加审计日志详细度
- 更新错误提示信息

任何逻辑变更必须由用户手动审核并确认。

## 相关文档

- [shell_logger.py 源代码](../../Claw/shell_logger.py)
- [Claw Shell-Logging 规则](../../Claw/.workbuddy/rules/shell-logging.mdc)
- [Security Policy](../../Claw/.workbuddy/rules/security-policy.mdc)
