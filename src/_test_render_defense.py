# -*- coding: utf-8 -*-
"""T4 TDD：渲染防御补全 — 全局异常提示条可见 + 畸形消息渲染不崩
红：无 pageerror 监听时抛错无提示条 → FAIL；绿：监听注入提示条 → PASS
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6908/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_function("typeof _expandBackendMessages === 'function'", timeout=20000)

    # 断言 1：抛错 → 提示条可见（#agentErrorBar）
    page.evaluate("setTimeout(() => { throw new Error('T4 测试渲染异常'); }, 100)")
    page.wait_for_timeout(600)
    bar_visible = page.evaluate(
        "(() => { const b = document.getElementById('agentErrorBar'); return !!(b && b.style.display !== 'none' && b.textContent.includes('T4 测试渲染异常')); })()")
    print("异常提示条可见:", bar_visible)
    assert bar_visible, "FAIL: 抛错后无提示条（pageerror 监听缺失）"

    # 断言 2：畸形消息（tool_calls=null/非数组/msg非对象）→ 页面不崩 + 展开安全
    malformed = [
        None, 123, "x",
        {"role": "assistant", "content": "ok", "tool_calls": None},
        {"role": "assistant", "content": "ok", "tool_calls": "not-list"},
        {"role": "assistant", "content": "ok", "tool_calls": [{"id": "t1", "function": None}]},
        {"role": "tool", "tool_call_id": None, "content": None},
    ]
    out = page.evaluate("""(msgs) => {
        try {
            const ui = _expandBackendMessages(msgs);
            return { ok: true, len: ui.length, first: JSON.stringify(ui[0] || {}).slice(0, 100) };
        } catch (e) { return { ok: false, err: String(e) }; }
    }""", malformed)
    print("畸形消息展开:", out)
    assert out.get("ok"), f"FAIL: 畸形消息展开抛异常 {out.get('err')}"

    print("T4 RESULT: PASS")
    browser.close()
