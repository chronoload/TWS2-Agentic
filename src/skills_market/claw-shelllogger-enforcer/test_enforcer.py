#!/usr/bin/env python3
# encoding: utf-8
"""
test_shelllogger_enforcer.py
============================
测试 Shell Logger Enforcer skill 的功能
"""

import sys
import os

# 添加 Claw 目录到路径
sys.path.insert(0, r"c:/Users/qu/WorkBuddy/Claw")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claw_shelllogger_enforcer import check_and_enforce, report_violation

def test_case(name: str, command: str, working_dir: str, expected: bool):
    """执行一个测试用例"""
    print(f"\n{'='*70}")
    print(f"[TEST] {name}")
    print(f"  Command: {command}")
    print(f"  Working Dir: {working_dir}")
    print(f"  Expected: {'PASS' if expected else 'FAIL'}")
    
    result = check_and_enforce(command, working_dir=working_dir, context=f"test:{name}")
    
    status = "[OK]" if result == expected else "[FAIL]"
    print(f"  Result: {status}")
    
    if result != expected:
        print(f"  Expected {expected}, got {result}")
    
    return result == expected

def main():
    print("="*70)
    print("Claw Shell Logger Enforcer - Test Suite")
    print("="*70)
    
    tests = [
        # 应该通过的用例
        ("Pure query command", "tasklist", r"c:/Users/qu/WorkBuddy/Claw", True),
        ("Dir command", "dir C:\\...", r"c:/Users/qu/WorkBuddy/Claw", True),
        ("Using shell_logger", "from shell_logger import run; run('test')", r"c:/Users/qu/WorkBuddy/Claw", True),
        ("Sync script", "python sync_log_to_wechat.py", r"c:/Users/qu/WorkBuddy/Claw", True),
        ("Outside Claw", "python test.py", r"c:/Users/qu/Desktop", True),
        
        # 应该被拦截的用例
        ("Direct execute in Claw", "python test.py", r"c:/Users/qu/WorkBuddy/Claw", False),
        ("Subprocess call", "import subprocess; subprocess.run(['python', 'test.py'])", r"c:/Users/qu/WorkBuddy/Claw", False),
        ("OS system call", "import os; os.system('python test.py')", r"c:/Users/qu/WorkBuddy/Claw", False),
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        if test_case(*test):
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*70}")
    print(f"Test Summary: {passed} passed, {failed} failed")
    print(f"{'='*70}")
    
    if failed == 0:
        print("[OK] All tests passed!")
        return 0
    else:
        print(f"[FAIL] {failed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
