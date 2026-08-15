# -*- coding: utf-8 -*-
"""T2 TDD（无感版）：切换长会话 → 窗口渲染（≤200）+ 无按钮 + 滚动到顶部自动补载 + 无 JS 错误
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6907/"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_function("typeof switchToSession === 'function'", timeout=20000)

        page.evaluate("switchToSession('sess_312047a51c36')")
        page.wait_for_timeout(1500)

        # 断言 1：窗口消息数 ≤ 200
        count = page.evaluate("(state.agentMessages || []).length")
        print(f"窗口消息数: {count}")
        assert count <= 200, f"FAIL: 窗口 {count} > 200"

        # 断言 2：无按钮（无感滚动加载，无手动入口）
        has_btn = page.evaluate(
            "!!(document.querySelector('[data-load-earlier]') || document.querySelector('.load-earlier'))")
        print(f"加载按钮（应无）: {has_btn}")
        assert not has_btn, "FAIL: 不应有加载按钮（无感滚动）"

        # 断言 3：滚动到顶部 → 自动补载（消息增长 + 滚动位置补偿）
        before = count
        page.evaluate("""() => {
            const c = document.getElementById('agentMessages');
            if (c) { c.scrollTop = 0; c.dispatchEvent(new Event('scroll')); }
        }""")
        page.wait_for_timeout(2500)
        after = page.evaluate("(state.agentMessages || []).length")
        print(f"滚动到顶部后消息数: {after} (前 {before})")
        assert after > before, f"FAIL: 滚动到顶部未自动补载 ({after} == {before})"

        # 断言 4：无 JS 错误
        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"

        print("T2 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
