#!/usr/bin/env python3
# encoding: utf-8
"""
integration_test.py
===================
Shell Logger Enforcer 集成测试 - 验证实际可用性
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claw_shelllogger_enforcer import check_and_enforce, get_correction

def test_case(name, cmd, working_dir, expected_allow, expected_reason=None):
    """执行一个测试用例"""
    print(f"\n[TEST] {name}")
    print(f"  Cmd: {cmd}")
    print(f"  Dir: {working_dir}")
    
    allowed, reason = check_and_enforce(cmd, working_dir=working_dir, context=f"test:{name}")
    
    status = "[PASS]" if allowed == expected_allow else "[FAIL]"
    print(f"  Result: {status}")
    print(f"  Reason: {reason}")
    
    if allowed != expected_allow:
        print(f"  ERROR: Expected {expected_allow}, got {allowed}")
        return False
    
    return True

def main():
    """运行完整测试"""
    print("=" * 70)
    print("Claw Shell Logger Enforcer - Integration Test")
    print("=" * 70)
    
    CLAW_DIR = r"c:/Users/qu/WorkBuddy/Claw"
    OTHER_DIR = r"c:/Users/qu/Desktop"
    
    tests = [
        # ✅ 应该通过的用例
        ("Query: tasklist", "tasklist", CLAW_DIR, True),
        ("Query: dir", "dir C:\\", CLAW_DIR, True),
        ("Shell Logger", "from shell_logger import run; run('test')", CLAW_DIR, True),
        ("Outside Claw", "python test.py", OTHER_DIR, True),
        ("No working_dir", "python test.py", "", True),
        
        # ❌ 应该被拦截的用例
        ("Direct execute", "python test.py", CLAW_DIR, False),
        ("Subprocess", "import subprocess; subprocess.run(['python'])", CLAW_DIR, False),
        ("OS system", "import os; os.system('dir')", CLAW_DIR, False),
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        if test_case(*test):
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"[FAILED] {failed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
