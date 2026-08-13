#!/usr/bin/env python3
# encoding: utf-8
"""
verify_skill.py
===============
简单验证 Shell Logger Enforcer skill 是否正确安装
"""

import os
import sys
import json

SKILL_DIR = r"c:/Users/qu/.workbuddy/skills/claw-shelllogger-enforcer"

def verify():
    print("[VERIFY] Claw Shell Logger Enforcer Skill")
    print("=" * 70)
    
    # 检查文件
    required_files = [
        "SKILL.md",
        "claw_shelllogger_enforcer.py",
        "enforcer.rule.mdc",
        "README.md",
        "config.json",
        "test_enforcer.py",
    ]
    
    all_ok = True
    
    for fname in required_files:
        fpath = os.path.join(SKILL_DIR, fname)
        if os.path.exists(fpath):
            size = os.path.getsize(fpath)
            print(f"[OK] {fname:<40} ({size} bytes)")
        else:
            print(f"[FAIL] {fname:<40} NOT FOUND")
            all_ok = False
    
    print("=" * 70)
    
    # 检查 config.json 是否有效
    try:
        with open(os.path.join(SKILL_DIR, "config.json"), "r") as f:
            cfg = json.load(f)
        print("[OK] config.json is valid JSON")
        print(f"     Skill: {cfg['skill']['name']}")
        print(f"     Version: {cfg['skill']['version']}")
    except Exception as e:
        print(f"[FAIL] config.json error: {e}")
        all_ok = False
    
    # 尝试导入主模块
    try:
        sys.path.insert(0, SKILL_DIR)
        from claw_shelllogger_enforcer import check_and_enforce
        print("[OK] claw_shelllogger_enforcer module can be imported")
    except Exception as e:
        print(f"[FAIL] Cannot import module: {e}")
        all_ok = False
    
    print("=" * 70)
    
    if all_ok:
        print("[SUCCESS] Skill installation verified!")
        return 0
    else:
        print("[FAILED] Some checks failed")
        return 1

if __name__ == "__main__":
    sys.exit(verify())
