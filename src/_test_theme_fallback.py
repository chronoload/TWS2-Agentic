# -*- coding: utf-8 -*-
"""T6：主题初始化兜底验证 — __themeInitFallback 存在 + 模拟"app.js 初始化未执行"（清空注册表）→ 兜底恢复
场景：用户保存 chuizi → 模拟 initOnLoad 未跑（注册表空）→ 调 __themeInitFallback → 断言注册表/下拉/主题恢复
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6908"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # 1. 兜底函数存在（index.html head 注入）
        has_fb = page.evaluate("typeof window.__themeInitFallback === 'function'")
        print("兜底函数存在:", has_fb)
        assert has_fb, "FAIL: __themeInitFallback 未注入"

        # 2. 保存 chuizi → 模拟 app.js 初始化未执行（清空注册表 + 移除自定义 CSS）→ 调兜底
        page.evaluate("localStorage.setItem('ts2_static_theme', 'chuizi')")
        page.evaluate("""() => {
          window.__TS2_THEME_REGISTRY = {};          // 模拟 initOnLoad 未跑
          const l = document.getElementById('customThemeCss'); if (l) l.remove();
          window.__themeInitFallback();              // 兜底补初始化
        }""")
        page.wait_for_timeout(800)

        r = page.evaluate("""() => ({
          registry: Object.keys(window.__TS2_THEME_REGISTRY || {}),
          theme: document.documentElement.getAttribute('data-theme'),
          customLink: !!document.getElementById('customThemeCss'),
          customHref: (document.getElementById('customThemeCss') || {}).href || null,
          selectOpts: (document.getElementById('customThemeSelect') || {}).options ? document.getElementById('customThemeSelect').options.length : -1,
          selectVal: document.getElementById('customThemeSelect') ? document.getElementById('customThemeSelect').value : null
        })""")
        print("兜底后状态:", r)
        assert "chuizi" in r["registry"], "FAIL: 注册表未恢复"
        assert r["theme"] == "chuizi", f"FAIL: 主题未应用 {r['theme']}"
        assert r["customLink"], "FAIL: 自定义 CSS 未注入"
        assert r["customHref"] and "chuizi" in r["customHref"], "FAIL: CSS href 错误"
        assert r["selectOpts"] >= 2, "FAIL: 下拉未填充"
        assert r["selectVal"] == "chuizi", f"FAIL: 下拉未选中 chuizi {r['selectVal']}"

        # 3. 幂等：再次调用不重复填充/不报错
        page.evaluate("window.__themeInitFallback()")
        r2 = page.evaluate("Object.keys(window.__TS2_THEME_REGISTRY || {}).length")
        print("幂等后注册表大小:", r2)
        assert r2 == 2, "FAIL: 幂等破坏"

        # 4. 无 JS 错误
        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"

        page.evaluate("localStorage.setItem('ts2_static_theme', 'dark')")
        print("T6 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
