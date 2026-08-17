"""undo/redo 与协同交错测试：本地撤销必须同步到 Loro，远端不能脱节。

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

        # U1: A types, then undoes -> B must converge (no leftover)
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        caret = seg_start + 6
        await a.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdA, %d)" % caret)
        await page.keyboard.type("AAA", delay=80)
        await page.wait_for_timeout(1300)
        va = await page.evaluate("window.vdA.getValue()")
        assert "AAA" in va, va
        # undo
        await page.keyboard.press("Control+z")
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        print("U1 va has AAA:", "AAA" in va, "vb has AAA:", "BBB" in vb.replace("AAA", "BBB"))
        print("U1 va==vb:", va == vb, "lenA", len(va), "lenB", len(vb), "stats", st)
        print("U1 A head:", va[:50].encode("unicode_escape"))
        print("U1 B head:", vb[:50].encode("unicode_escape"))
        assert va == vb, ("U1", va, vb)
        assert "AAA" not in va, va
        assert st["lostChars"] == 0, st
        print("U1 local undo syncs to remote: PASS", st)
        await page.close()

        # U2: interleave — A types, B types remotely, A undoes only its own edit
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        await a.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdA, %d)" % (seg_start + 6))
        await page.keyboard.type("AAA", delay=80)
        await page.wait_for_timeout(400)
        # B's remote edit at a different location
        await page.evaluate("window.testLoroInsert('B', %d, 'BBB')" % (seg_start + 30))
        await page.wait_for_timeout(500)
        va = await page.evaluate("window.vdA.getValue()")
        assert "BBB" in va, va
        # undo on A should remove AAA but keep BBB
        await page.keyboard.press("Control+z")
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("U2", va, vb)
        assert "AAA" not in va, va
        assert "BBB" in va, va
        assert st["lostChars"] == 0, st
        print("U2 undo keeps remote edit: PASS", st)
        await page.close()

        # U3: redo restores and syncs
        page = await fresh_page(browser)
        a = page.locator("#vdA .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        await a.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdA, %d)" % (seg_start + 6))
        await page.keyboard.type("AAA", delay=80)
        await page.wait_for_timeout(1300)
        await page.keyboard.press("Control+z")
        await page.wait_for_timeout(500)
        va = await page.evaluate("window.vdA.getValue()")
        assert "AAA" not in va, va
        await page.keyboard.press("Control+y")
        await page.wait_for_timeout(800)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("U3", va, vb)
        assert "AAA" in va, va
        assert st["lostChars"] == 0, st
        print("U3 redo restores and syncs: PASS", st)
        await page.close()

        print("ALL UNDO TESTS PASS")
        await browser.close()


asyncio.run(main())
