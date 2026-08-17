"""有焦点时格式介入的同步测试（编辑器路径）：远端插入 markdown 语法经 Vditor 规范化，
B 端正确渲染且两端一致。增量定位的精准性由 E1/E2（纯文本）覆盖。
运行前需先启动静态服务：python -m http.server 8765 --bind 127.0.0.1（工作目录 mcp/server）
"""
import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/static/collab-poc-ir.html"
MARK = "两端都可以直接敲击。远端变化应尽量只修改自己的位置。"


async def fresh_page(browser):
    page = await browser.new_page()
    await page.goto(URL, wait_until="networkidle")
    await page.wait_for_timeout(1500)
    assert await page.evaluate("!!window.vdA && !!window.vdB")
    return page


async def stats(page):
    return await page.evaluate("window.testStats")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # G1: A inserts bold syntax after the caret -> B converges and renders <strong>
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        await a.focus()
        await page.evaluate("window.testInsert('A', %d, '**加粗**')" % (seg_start + 30))
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("G1", va, vb)
        assert "**加粗**" in va, va
        strong = await page.locator("#vdB .vditor-ir strong").count()
        assert strong >= 1, strong
        assert st["lostChars"] == 0, st
        print("G1 bold sync + <strong> in B: PASS", st)
        await page.close()

        # G2: A inserts inline math -> B converges and renders math preview
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        await a.focus()
        await page.evaluate("window.testInsert('A', %d, '$E=mc^2$')" % seg_start)
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("G2", va, vb)
        assert "$E=mc^2$" in va, va
        math = await page.locator("#vdB .vditor-ir .vditor-ir__preview, #vdB .vditor-ir .language-math").count()
        assert math >= 1, math
        assert st["lostChars"] == 0, st
        print("G2 math sync + render in B: PASS", st)
        await page.close()

        # G3: A inserts heading at document start -> B converges and renders <h1>
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        await a.focus()
        await page.evaluate("window.testInsert('A', 0, '# 新标题\\n\\n')")
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("G3", va, vb)
        assert va.startswith("# 新标题"), va
        h1 = await page.locator("#vdB .vditor-ir h1").count()
        assert h1 >= 1, h1
        assert st["lostChars"] == 0, st
        print("G3 heading sync + <h1> in B: PASS", st)
        await page.close()

        print("ALL FOCUSED FORMAT-SYNC TESTS PASS")
        await browser.close()


asyncio.run(main())
