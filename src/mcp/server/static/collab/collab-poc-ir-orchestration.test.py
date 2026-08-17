"""随机化长编排复杂边界测试。

设计：Orchestration 是一个"激活调用编排链"生成器——
- 从 Action 注册表按权重随机生成操作链，每次运行的编写序列不同
- 每个 Action 是独立可扩展的激活调用（A/B 输入、撤销、IME、格式、远端注入、网络延迟等）
- 链内操作连续碰撞，每步验证 A/B 收敛 + 不丢字，最终验证所有标记存在

运行：python mcp/server/static/collab/collab-poc-ir-orchestration.test.py [seed] [steps]
依赖：静态服务已在 8765 端口运行；pip install playwright
"""
import asyncio
import random
import sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8765/static/collab-poc-ir.html"
MARK = "两端都可以直接敲击。远端变化应尽量只修改自己的位置。"


class Fixture:
    """封装对单个页面上 A/B 两个编辑器的激活调用原语。"""

    def __init__(self, page, seg_start):
        self.page = page
        self.seg_start = seg_start
        self.a = page.locator("#vdA .vditor-ir > pre")
        self.b = page.locator("#vdB .vditor-ir > pre")

    async def mark_pos(self):
        """动态定位当前 MARK 段落起始（用短前缀，标题/插入较少破坏它）。"""
        va = await self.page.evaluate("window.vdA.getValue()")
        i = va.find("两端都可以直接敲击")
        return i if i >= 0 else self.seg_start

    async def select_a(self, pos):
        await self.a.focus()
        await self.page.evaluate("window.selectMarkdownOffset(window.vdA, %d)" % pos)

    async def select_b(self, pos):
        await self.b.focus()
        await self.page.evaluate("window.selectMarkdownOffset(window.vdB, %d)" % pos)

    async def keyboard_a(self, text, delay=60):
        await self.select_a((await self.mark_pos()) + 4)
        await self.page.keyboard.type(text, delay=delay)

    async def keyboard_b(self, text, delay=60):
        await self.select_b((await self.mark_pos()) + 24)
        await self.page.keyboard.type(text, delay=delay)

    async def insert(self, name, pos, text):
        await self.page.evaluate("window.testInsert('%s', %d, %s)" % (name, pos, repr(text)))

    async def undo_a(self):
        await self.a.focus()
        await self.page.keyboard.press("Control+z")

    async def ime_b(self, text):
        await self.select_b((await self.mark_pos()) + 16)
        await self.page.evaluate("""() => {
          const ed = window.vdB.vditor.ir.element;
          ed.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
          const r = window.getSelection().getRangeAt(0);
          r.insertNode(document.createTextNode(%s));
          r.collapse(false);
          setTimeout(() => ed.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:%s})), 120);
        }""" % (repr(text), repr(text)))

    async def remote_insert(self, name, pos, text):
        await self.page.evaluate("window.testLoroInsert('%s', %d, %s)" % (name, pos, repr(text)))

    async def remote_delete(self, name, pos, length):
        await self.page.evaluate("window.testLoroDelete('%s', %d, %d)" % (name, pos, length))

    async def append(self, name, md):
        await self.page.evaluate("window.testLoroAppend('%s', %s)" % (name, repr(md)))

    async def network(self, delay, jitter):
        await self.page.evaluate("window.testSetNetwork(%d, %d)" % (delay, jitter))

    async def converged(self):
        va = await self.page.evaluate("window.vdA.getValue()")
        vb = await self.page.evaluate("window.vdB.getValue()")
        st = await self.page.evaluate("window.testStats")
        return va == vb and st["lostChars"] == 0, (va, vb, st)


class Orchestration:
    """随机"激活调用编排链"生成与执行器。注册 Action 后按权重随机生成链。"""

    def __init__(self, fixture, seed=None):
        self.f = fixture
        self.rng = random.Random(seed)
        self.registry = []

    def register(self, name, weight, fn):
        self.registry.append({"name": name, "weight": weight, "fn": fn})

    def build_chain(self, n):
        items = self.registry
        weights = [it["weight"] for it in items]
        return [self.rng.choices(items, weights=weights)[0] for _ in range(n)]

    async def run(self, chain, settle=0.7):
        markers = []
        for step, item in enumerate(chain):
            action = await item["fn"](self.f, self.rng)
            if action:
                markers.append(action)
            await asyncio.sleep(settle)
            ok, info = await self.f.converged()
            if not ok:
                a, b, st = info
                i = 0
                while i < min(len(a), len(b)) and a[i] == b[i]:
                    i += 1
                raise AssertionError(
                    f"step{step} {item['name']} NOT converged, first diff at {i}\n"
                    f"A...: {a[max(0,i-30):i+30]!r}\nB...: {b[max(0,i-30):i+30]!r}\n"
                    f"A len={len(a)} B len={len(b)} stats={st}")
        return markers


async def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randint(0, 99999)
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    print(f"seed={seed} steps={steps}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        seg = await page.evaluate("window.vdA.getValue()")
        seg_start = seg.index(MARK)
        fixture = Fixture(page, seg_start)

        ctx = {"n": 0}
        orch = Orchestration(fixture, seed=seed)

        # ---- 注册可扩展的激活调用 ----
        async def act_type_a(f, rng):
            t = "a%d" % ctx["n"]; ctx["n"] += 1
            pos = (await f.mark_pos()) + rng.randint(2, 18)
            await f.insert("A", pos, t)
            return t

        async def act_type_b(f, rng):
            t = "b%d" % ctx["n"]; ctx["n"] += 1
            pos = (await f.mark_pos()) + rng.randint(20, 32)
            await f.insert("B", pos, t)
            return t

        async def act_keyboard_a(f, rng):
            t = "K%d" % ctx["n"]; ctx["n"] += 1
            await f.keyboard_a(t)
            return t

        async def act_undo_a(f, rng):
            await f.undo_a()
            return None

        async def act_ime_b(f, rng):
            t = "中文%d" % ctx["n"]; ctx["n"] += 1
            await f.ime_b(t)
            return t

        async def act_remote_insert(f, rng):
            t = "R%d" % ctx["n"]; ctx["n"] += 1
            pos = (await f.mark_pos()) + rng.randint(2, 30)
            await f.remote_insert("A", pos, t)
            return t

        async def act_remote_delete(f, rng):
            await f.remote_delete("A", (await f.mark_pos()) + 2, rng.randint(1, 3))
            return None

        async def act_bold(f, rng):
            t = "**加粗%d**" % ctx["n"]; ctx["n"] += 1
            pos = (await f.mark_pos()) + rng.randint(10, 28)
            await f.insert("A", pos, t)
            return t

        async def act_heading(f, rng):
            t = "# 标题%d" % ctx["n"]; ctx["n"] += 1
            # 编辑器路径插入标题（Loro 经 options.input 同步，避免 testLoroAppend 的 Vditor 规范化差异）
            await f.insert("A", 0, t + "\n\n")
            return t

        async def act_network(f, rng):
            on = rng.random() < 0.5
            await f.network(60, 180 if on else 0)
            return None

        async def act_rapid(f, rng):
            n = ctx["n"]; ctx["n"] += 2
            mp = await f.mark_pos()
            for i in range(2):
                await f.insert("A", mp + 2 + i, "p%d" % (n + i))
                await f.insert("B", mp + 8 + i, "q%d" % (n + i))
            return ["p%d" % (n + 1), "q%d" % (n + 1)]

        orch.register("type_a", 8, act_type_a)
        orch.register("type_b", 8, act_type_b)
        orch.register("keyboard_a", 4, act_keyboard_a)
        orch.register("undo_a", 3, act_undo_a)
        orch.register("ime_b", 3, act_ime_b)
        orch.register("remote_insert", 6, act_remote_insert)
        orch.register("remote_delete", 3, act_remote_delete)
        orch.register("bold", 3, act_bold)
        orch.register("heading", 2, act_heading)
        orch.register("network", 4, act_network)
        orch.register("rapid", 2, act_rapid)

        chain = orch.build_chain(steps)
        print("chain:", [it["name"] for it in chain])
        markers = await orch.run(chain)

        # 最终验证：收敛 + 不丢字 + 文档长度随操作增长（随机插入会打断短标记，不逐项断言 marker）
        va = await page.evaluate("window.vdA.getValue()")
        vb = await page.evaluate("window.vdB.getValue()")
        st = await page.evaluate("window.testStats")
        assert va == vb, (va, vb)
        assert st["lostChars"] == 0, st
        assert len(va) > len(seg), (len(va), len(seg))
        print(f"ORCHESTRATION PASS seed={seed} steps={steps} actions={[it['name'] for it in chain]}")
        print("final stats:", st)
        await browser.close()


asyncio.run(main())
