"""Vditor 主动介入格式（标题/公式/链接/列表/图片）与 IME 切换的协同边界测试。

这些格式 Vditor 会用 Lute 主动重构 DOM，是 buildMap 映射与增量应用的难点。
运行前需先启动静态服务：python -m http.server 8765 --bind 127.0.0.1（工作目录 mcp/server）
"""
import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/static/collab-poc-ir.html"


async def fresh_page(browser):
    page = await browser.new_page()
    await page.goto(URL, wait_until="networkidle")
    await page.wait_for_timeout(1500)
    assert await page.evaluate("!!window.vdA && !!window.vdB")
    return page


async def append_and_sync(page, md):
    """在 A 末尾追加一段 markdown，A setValue 触发 Vditor 解析，B 同步。返回两端 value 与 stats。"""
    await page.evaluate("window.testLoroAppend('A', %s)" % md.__repr__())
    await page.wait_for_timeout(900)
    va = await page.evaluate("window.vdA.getValue()")
    vb = await page.evaluate("window.vdB.getValue()")
    st = await page.evaluate("window.testStats")
    return va, vb, st


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # F1: heading
        page = await fresh_page(browser)
        va, vb, st = await append_and_sync(page, "\n\n# 新标题")
        assert va == vb, ("F1", va, vb)
        assert "# 新标题" in va, va
        h1 = await page.locator("#vdB .vditor-ir h1").count()
        assert h1 >= 1, h1
        assert st["lostChars"] == 0, st
        print("F1 heading sync + h1 in B: PASS", st)
        await page.close()

        # F2: inline math formula
        page = await fresh_page(browser)
        va, vb, st = await append_and_sync(page, "\n\n行内公式 $E=mc^2$ 结束")
        assert va == vb, ("F2", va, vb)
        assert "$E=mc^2$" in va, va
        math = await page.locator("#vdB .vditor-ir .vditor-ir__preview, #vdB .vditor-ir .language-math").count()
        assert math >= 1, math
        assert st["lostChars"] == 0, st
        print("F2 inline math sync + render in B: PASS", st)
        await page.close()

        # F3: link
        page = await fresh_page(browser)
        va, vb, st = await append_and_sync(page, "\n\n[示例链接](https://example.com)")
        assert va == vb, ("F3", va, vb)
        assert "[示例链接](https://example.com)" in va, va
        a_cnt = await page.locator("#vdB .vditor-ir .vditor-ir__link").count()
        assert a_cnt >= 1, a_cnt
        assert st["lostChars"] == 0, st
        print("F3 link sync + <a> in B: PASS", st)
        await page.close()

        # F4: list item
        page = await fresh_page(browser)
        va, vb, st = await append_and_sync(page, "\n\n- 新列表项")
        assert va == vb, ("F4", va, vb)
        assert "- 新列表项" in va, va
        li = await page.locator("#vdB .vditor-ir li").count()
        assert li >= 1, li
        assert st["lostChars"] == 0, st
        print("F4 list item sync + <li> in B: PASS", st)
        await page.close()

        # F5: image
        page = await fresh_page(browser)
        va, vb, st = await append_and_sync(page, "\n\n![配图](https://example.com/a.png)")
        assert va == vb, ("F5", va, vb)
        assert "![配图](https://example.com/a.png)" in va, va
        img = await page.locator("#vdB .vditor-ir img").count()
        assert img >= 1, img
        assert st["lostChars"] == 0, st
        print("F5 image sync + <img> in B: PASS", st)
        await page.close()

        # F6: IME 中英文切换 —— 中文组合期间 A 远端到达应排队，切换英文后合并
        page = await fresh_page(browser)
        b_editor = page.locator("#vdB .vditor-ir > pre")
        await b_editor.dispatch_event("compositionstart")
        queued_before = (await page.evaluate("window.testStats"))["imeQueued"]
        await page.evaluate("window.testLoroAppend('A', '\\n\\n远端在组合期间')")
        await page.wait_for_timeout(200)
        queued_after = (await page.evaluate("window.testStats"))["imeQueued"]
        assert queued_after > queued_before, (queued_before, queued_after)
        # 切换英文：组合结束
        await b_editor.dispatch_event("compositionend")
        await page.wait_for_timeout(900)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await page.evaluate("window.testStats")
        assert va == vb, ("F6", va, vb)
        assert "远端在组合期间" in va, va
        assert st["lostChars"] == 0, st
        print("F6 IME 中英文切换（组合期间远端排队）: PASS", st)
        await page.close()

        print("ALL FORMAT-INTERVENTION TESTS PASS")
        await browser.close()


asyncio.run(main())
