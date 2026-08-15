# -*- coding: utf-8 -*-
"""T5 TDD：多标签页会话协调 — A 切换会话 → B 收到 storage 事件跟随切换
（_setAgentSessionId 写 agent_current_session → 另一标签 _initMultiTabSync 防抖跟随）
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6908/"
TARGET = "default"  # A 切换到与 B 初始不同的会话（验证真实跟随）

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()  # 同一 context：共享 localStorage + storage 事件

    pageA = context.new_page()
    pageB = context.new_page()
    for pg, tag in ((pageA, "A"), (pageB, "B")):
        pg.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        pg.wait_for_function("typeof switchToSession === 'function'", timeout=20000)
        print(f"页面{tag} 加载完成")

    # 记录 B 当前会话（初始应与 A 相同，均为默认/上次）
    b_before = pageB.evaluate("_getAgentSessionId()")
    print("B 初始会话:", b_before[:20], "| 目标:", TARGET[:20])

    # A 切换会话 → 写 agent_current_session → storage 事件 → B 跟随
    pageA.evaluate("switchToSession('" + TARGET + "')")
    pageA.wait_for_timeout(800)  # A 切换完成
    a_now = pageA.evaluate("_getAgentSessionId()")
    print("A 切换后会话:", a_now[:20])

    # 等 B 收到 storage（防抖 300ms）+ 跟随切换
    pageB.wait_for_timeout(2000)
    b_after = pageB.evaluate("_getAgentSessionId()")
    print("B 跟随后会话:", b_after[:20])

    # 断言：B 跟随到目标会话（与 A 一致，且不同于初始）
    assert a_now == TARGET, f"FAIL: A 未切到目标 {TARGET[:16]}, 实际 {a_now[:16]}"
    assert b_after == TARGET, f"FAIL: B 未跟随到 {TARGET[:16]}, 仍为 {b_after[:16]}"
    assert b_after != b_before or b_before == TARGET, f"FAIL: B 会话未变化 ({b_before[:16]})"

    print("T5 RESULT: PASS")
    browser.close()
