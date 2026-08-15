# -*- coding: utf-8 -*-
"""T2 TDD：切换长会话 → 窗口渲染（≤200）+ 加载更早历史入口 + 点击增长 + 无 JS 错误
红：前端尚未适配 has_more（无加载入口）→ FAIL；绿：实现后 PASS
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6908/"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_function("typeof switchToSession === 'function'", timeout=20000)

        # 切到长会话
        sw = page.evaluate("switchToSession('sess_312047a51c36')")
        print("switchToSession 返回:", str(sw)[:200])
        page.wait_for_timeout(1500)

        # 断言 1：窗口消息数 ≤ 200
        count = page.evaluate("(state.agentMessages || []).length")
        print(f"窗口消息数: {count}")
        assert count <= 200, f"FAIL: 窗口 {count} > 200"

        # 断言 2：有"加载更早历史"入口
        has_btn = page.evaluate(
            "!!(document.querySelector('[data-load-earlier]') || document.querySelector('.load-earlier'))")
        print(f"加载更早历史入口: {has_btn}")
        assert has_btn, "FAIL: 无加载更早历史入口"

        # 断言 3：点击 → 消息数增长
        before = count
        clicked = page.evaluate("""() => {
            const el = document.querySelector('[data-load-earlier]') || document.querySelector('.load-earlier');
            if (el) { el.click(); return true; }
            return false;
        }""")
        print(f"点击入口: {clicked}")
        page.wait_for_timeout(2500)
        after = page.evaluate("(state.agentMessages || []).length")
        print(f"加载后消息数: {after} (前 {before})")
        assert after > before, f"FAIL: 加载后 {after} 未增长 (前 {before})"

        # 断言 4：无 JS 错误
        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"

        print("T2 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
