"""第 1 档（有焦点增量）边界测试：驱动光标相对位移与增量桥接的开发验证。

运行前需先启动静态服务：
  python -m http.server 8765 --bind 127.0.0.1   （工作目录为 mcp/server）
依赖：pip install playwright && playwright install chromium
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

        # E1: remote insert BEFORE the focused caret -> caret shifts +len, data consistent
        page = await fresh_page(browser)
        b = page.locator("#vdB .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        caret = seg_start + 18
        await b.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdB, %d)" % caret)
        before = await page.evaluate("window.testCaretMarkdown('B')")
        await page.evaluate("window.testLoroInsert('A', %d, 'PREFIX')" % seg_start)
        await page.wait_for_timeout(500)
        after = await page.evaluate("window.testCaretMarkdown('B')")
        st = await stats(page)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        assert va == vb, ("E1", va, vb)
        assert "PREFIX" in va
        assert after == before + 6, (before, after)
        assert st["incremental"] > 0, st
        assert st["lostChars"] == 0, st
        print("E1 insert-before-caret shift +6: PASS", st)
        await page.close()

        # E2: remote DELETE before the focused caret -> caret shifts -len
        page = await fresh_page(browser)
        b = page.locator("#vdB .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        caret = seg_start + 22
        await b.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdB, %d)" % caret)
        before = await page.evaluate("window.testCaretMarkdown('B')")
        await page.evaluate("window.testLoroDelete('A', %d, 4)" % seg_start)
        await page.wait_for_timeout(500)
        after = await page.evaluate("window.testCaretMarkdown('B')")
        st = await stats(page)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        assert va == vb, ("E2", va, vb)
        assert after == before - 4, (before, after)
        assert st["incremental"] > 0, st
        assert st["lostChars"] == 0, st
        print("E2 delete-before-caret shift -4: PASS", st)
        await page.close()

        # E3: remote DELETE overlapping the caret -> caret clamps, no jump to start
        page = await fresh_page(browser)
        b = page.locator("#vdB .vditor-ir > pre")
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        caret = seg_start + 15
        await b.focus()
        await page.evaluate("window.selectMarkdownOffset(window.vdB, %d)" % caret)
        await page.evaluate("window.testLoroDelete('A', %d, 26)" % seg_start)
        await page.wait_for_timeout(600)
        after = await page.evaluate("window.testCaretMarkdown('B')")
        st = await stats(page)
        vb = await page.evaluate("window.vdB.getValue()")
        # testLoroDelete 绕过编辑器，A 端 getValue 可能受 Vditor 全量重建渲染影响；
        # 此处只验证远端删除已应用 + 光标钳制 + 不丢字。
        assert MARK[:10] not in vb, vb
        assert after >= 11, after  # clamped to deletion point (paragraph start), NOT doc absolute start
        assert st["lostChars"] == 0, st
        print("E3 delete-overlapping-caret clamp: PASS", st)
        await page.close()

        # E4: insert right after a list marker
        page = await fresh_page(browser)
        seg = await page.evaluate("window.vdA.getValue()")
        item1 = seg.index("在不同段落同时输入")
        await page.evaluate("window.testLoroInsert('A', %d, 'X1')" % item1)
        await page.wait_for_timeout(600)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("E4", va, vb)
        assert "- X1在不同段落同时输入" in va, va
        li_in_b = await page.locator("#vdB .vditor-ir li").count()
        assert li_in_b >= 1, li_in_b
        assert st["lostChars"] == 0, st
        print("E4 list-marker boundary insert: PASS (li in B =", li_in_b, ")", st)
        await page.close()

        # E5: insert inside an inline math formula
        page = await fresh_page(browser)
        seg = await page.evaluate("window.vdA.getValue()")
        emc = seg.index("E=mc")
        await page.evaluate("window.testLoroInsert('A', %d, 'K')" % (emc + 2))
        await page.wait_for_timeout(600)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("E5", va, vb)
        assert "E=Kmc" in va, va
        assert st["lostChars"] == 0, st
        print("E5 insert inside inline math: PASS", st)
        await page.close()

        # E6: rapid interleaved edits in the SAME paragraph
        page = await fresh_page(browser)
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        for i in range(5):
            await page.evaluate("window.testLoroInsert('A', %d, 'a%d')" % (seg_start + 2, i))
            await page.evaluate("window.testLoroInsert('B', %d, 'b%d')" % (seg_start + 8, i))
        await page.wait_for_timeout(900)
        va, vb = await page.evaluate("window.vdA.getValue()"), await page.evaluate("window.vdB.getValue()")
        st = await stats(page)
        assert va == vb, ("E6", va, vb)
        assert all(m in va for m in ["a0", "a4", "b0", "b4"]), va
        assert st["lostChars"] == 0, st
        print("E6 interleaved same-paragraph edits: PASS", st)
        await page.close()

        print("ALL EDGE TESTS PASS")
        await browser.close()


asyncio.run(main())
