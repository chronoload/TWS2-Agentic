import sys
import os
sys.path.insert(0, r"c:\Users\qu\.workbuddy\skills\claw-shelllogger-enforcer")

from claw_shelllogger_enforcer import check_and_enforce

# Test 1: Query command (should pass)
result1 = check_and_enforce("tasklist", working_dir=r"c:/Users/qu/WorkBuddy/Claw")
print(f"Test 1 (query): {result1}")

# Test 2: Direct execute (should fail)
result2 = check_and_enforce("python test.py", working_dir=r"c:/Users/qu/WorkBuddy/Claw")
print(f"Test 2 (direct): {result2}")

# Test 3: Shell logger (should pass)
result3 = check_and_enforce("from shell_logger import run; run('test')", working_dir=r"c:/Users/qu/WorkBuddy/Claw")
print(f"Test 3 (shell_logger): {result3}")

print("\nAll tests completed!")
