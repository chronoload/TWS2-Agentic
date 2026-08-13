#!/usr/bin/env python3
# encoding: utf-8
"""
claw_shelllogger_enforcer.py
=============================
Shell Logger 强制执行检查器 - 实际可用版本

这个模块会在 AI 调用 execute_command 时进行拦截，检查是否符合
Claw 项目的 shell_logger 强制规范。

核心逻辑：
  1. 检查工作目录是否在 Claw
  2. 检查命令是否是查询类型（豁免）
  3. 检查代码是否已使用 shell_logger
  4. 失败则拦截 + 建议纠正

使用方式：
  from claw_shelllogger_enforcer import check_and_enforce, get_correction
  
  is_allowed = check_and_enforce(
      command="python test.py",
      working_dir="c:/Users/qu/WorkBuddy/Claw",
      context="send_research_main.py:45"
  )
  
  if not is_allowed:
      print(get_correction("python test.py"))
      sys.exit(1)
"""

import os
import sys
import json
import datetime
from pathlib import Path
from typing import Optional, Tuple

# ── 配置 ──────────────────────────────────────────────────────────────
CLAW_DIR = r"c:/Users/qu/WorkBuddy/Claw"
ENFORCE_MODE = "strict"
ALLOW_QUERIES = True
LOG_FILE = os.path.join(CLAW_DIR, "logs", "shelllogger_enforcer.log")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# 查询命令白名单（无副作用的纯信息查询）
QUERY_COMMANDS = {
    # Windows 命令
    "tasklist", "taskkill", "Get-Process", "Stop-Process",
    "dir", "chdir", "cd", "pushd", "popd",
    "type", "more", "cat", "echo",
    "findstr", "find", "where", "which",
    "wmic", "systeminfo", "sc", "driverquery",
    "reg query", "reg check",
    "netstat", "ipconfig", "ping", "tracert",
    # Unix/Linux 命令（WSL 等）
    "ls", "pwd", "whoami", "id", "groups",
    "cat", "head", "tail", "grep", "awk",
    "ps", "top", "df", "du", "lsof",
    # Python 相关查询
    "python -V", "python --version", "pip list", "pip show",
    # 其他信息查询
    "date", "time", "uname", "hostnamectl",
}

# 豁免的命令模式（关键词匹配）
EXEMPT_PATTERNS = {
    # shell_logger 的标志
    "from shell_logger import run",
    "shell_logger.run(",
    "run(",  # 必须和 shell_logger 一起，不能单独
    # 同步工作流脚本
    "sync_log_to_wechat.py",
    "run_sync.py",
    "record_session.py",
    # 其他工作流脚本（可添加）
    "send_research",
}


def _normalize_cmd(cmd: str) -> str:
    """规范化命令字符串"""
    return cmd.strip().lower()


def _is_query_command(cmd: str) -> bool:
    """检查是否是纯查询命令（无副作用）"""
    cmd_norm = _normalize_cmd(cmd)
    cmd_name = cmd_norm.split()[0] if cmd_norm else ""
    
    # 精确匹配查询命令
    for qcmd in QUERY_COMMANDS:
        if cmd_norm.startswith(qcmd):
            return True
    
    return False


def _is_shelllogger_call(cmd: str, context: str = "") -> bool:
    """检查是否已使用 shell_logger"""
    cmd_lower = cmd.lower()
    context_lower = context.lower() if context else ""
    
    # 检查命令中是否包含 shell_logger 标志
    for pattern in EXEMPT_PATTERNS:
        if pattern.lower() in cmd_lower or pattern.lower() in context_lower:
            # 特殊情况：run( 必须伴随 shell_logger
            if pattern == "run(" and "shell_logger" not in cmd_lower:
                continue
            return True
    
    return False


def _is_in_claw_directory(working_dir: str) -> bool:
    """检查是否在 Claw 目录"""
    if not working_dir:
        return False
    
    # 规范化路径
    wd_norm = os.path.normpath(working_dir).lower()
    claw_norm = os.path.normpath(CLAW_DIR).lower()
    
    return wd_norm.startswith(claw_norm)


def _log_check(result: str, command: str, reason: str, context: str = ""):
    """记录检查结果到日志"""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    record = {
        "timestamp": ts,
        "check_result": result,  # PASS, FAIL, EXEMPT
        "command": command[:300],  # 截断过长命令
        "reason": reason,
        "context": context,
    }
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARNING] 无法写入强制检查日志: {e}", file=sys.stderr)


def check_and_enforce(
    command: str,
    working_dir: str = "",
    context: str = "",
    allow_bypass: bool = False,
) -> Tuple[bool, str]:
    """
    检查命令是否符合 shell_logger 强制规范。
    
    参数：
        command: 要执行的命令
        working_dir: 工作目录
        context: 上下文（调用位置）
        allow_bypass: 是否允许绕过（仅供测试）
    
    返回：
        (allowed: bool, reason: str) - 是否允许及原因
    """
    if allow_bypass:
        _log_check("EXEMPT", command, "Bypass enabled (test mode)", context)
        return True, "绕过（测试模式）"
    
    # 检查 1：不在 Claw 目录，不适用此规则
    if working_dir and not _is_in_claw_directory(working_dir):
        _log_check("EXEMPT", command, "Not in Claw directory", context)
        return True, "不在 Claw 目录，规则不适用"
    
    # 检查 2：纯查询命令（豁免）
    if ALLOW_QUERIES and _is_query_command(command):
        _log_check("EXEMPT", command, "Pure query command", context)
        return True, "纯查询命令，自动豁免"
    
    # 检查 3：已使用 shell_logger（通过）
    if _is_shelllogger_call(command, context):
        _log_check("PASS", command, "Already using shell_logger", context)
        return True, "已正确使用 shell_logger"
    
    # 检查失败：必须使用 shell_logger
    reason = "在 Claw 项目中必须使用 shell_logger.run()"
    _log_check("FAIL", command, reason, context)
    return False, reason


def get_correction(command: str) -> str:
    """返回纠正建议"""
    return f"""
[ENFORCEMENT VIOLATION] Shell Logger Enforcer

❌ 命令违规：未使用 shell_logger

在 Claw 项目中，所有系统命令必须通过 shell_logger 执行。

✅ 正确方式：

# Python 代码中：
from shell_logger import run

# 方式 1：基础执行
result = run("{command}")

# 方式 2：自定义标题和等待
result = run("{command}", title="[操作描述]", wait=True)

# 方式 3：无弹窗执行（仅后台记录）
result = run("{command}", popup=False)

result 对象包含：
  - result.returncode: 返回码（0=成功）
  - result.stdout: 标准输出内容
  - result.stderr: 标准错误内容

📖 详细说明：~/.workbuddy/skills/claw-shelllogger-enforcer/README.md
"""


def report_violation(command: str, context: str = "") -> str:
    """生成完整违规报告"""
    report = f"""
{'='*70}
[CLAW SHELL LOGGER ENFORCER] VIOLATION REPORT
{'='*70}

Time: {datetime.datetime.now().isoformat(timespec="seconds")}
Location: {context or "unknown"}
Command: {command}

REASON: 
  在 Claw 项目中必须使用 shell_logger.run() 执行命令

{get_correction(command)}

AUDIT LOG:
  All violations have been recorded to: {LOG_FILE}

{'='*70}
"""
    return report


# ── 主入口（用于命令行测试）────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Shell Logger Enforcer 检查器")
    parser.add_argument("command", nargs="?", help="要检查的命令")
    parser.add_argument("--dir", default=CLAW_DIR, help="工作目录")
    parser.add_argument("--context", default="", help="上下文")
    parser.add_argument("--allow-bypass", action="store_true", help="允许绕过（测试）")
    args = parser.parse_args()
    
    if not args.command:
        print("Usage: python claw_shelllogger_enforcer.py <command> [--dir DIR] [--context CTX]")
        sys.exit(1)
    
    allowed, reason = check_and_enforce(
        args.command,
        working_dir=args.dir,
        context=args.context,
        allow_bypass=args.allow_bypass,
    )
    
    if allowed:
        print(f"[PASS] {reason}")
        sys.exit(0)
    else:
        print(report_violation(args.command, args.context))
        sys.exit(1)

