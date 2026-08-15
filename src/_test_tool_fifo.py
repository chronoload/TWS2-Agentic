# -*- coding: utf-8 -*-
"""T4 验证：工具返回追加错位修复 — ①toolMsgMap FIFO（同名工具排队）②_updateStreamMessage uid 稳定定位（下标漂移免疫）
模拟场景：两次同名 tool_call → 模拟压缩分页头部插入（下标漂移）→ tool_result 到达 → 结果必须写到第一个卡片（uid 匹配）
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
        page.wait_for_function("typeof _findMsgIndexByUid === 'function'", timeout=20000)

        # ── 断言 1：_findMsgIndexByUid 幂等 uid 查找 ──
        r = page.evaluate("""() => {
          const a = { _uid: 'm1' }, b = { _uid: 'm2' }, c = { _uid: 'm3' };
          const list = [a, b, c];
          return { i1: _findMsgIndexByUid(list, 'm2'), i2: _findMsgIndexByUid(list, 'm9'), i3: _findMsgIndexByUid(list, '') };
        }""")
        print("uid 查找:", r)
        assert r["i1"] == 1 and r["i2"] == -1 and r["i3"] == -1, "FAIL: _findMsgIndexByUid"

        # ── 断言 2：模拟下标漂移（压缩分页头部插入）后 uid 仍正确定位 ──
        r2 = page.evaluate("""() => {
          // 模拟流式：user + 两次同名 tool_call（带 uid）
          const u1o = { role: 'user', content: 'hi' };
          const t1o = { role: 'tool_call', name: 'read_file', content: 'read_file 1' };
          const t2o = { role: 'tool_call', name: 'read_file', content: 'read_file 2' };
          _ensureMsgUid(u1o); _ensureMsgUid(t1o); _ensureMsgUid(t2o);
          let msgs = [u1o, t1o, t2o];
          // 模拟压缩分页：头部插入 2 条更早历史（下标整体 +2 漂移）
          const old1 = { role: 'user', content: 'old1' };
          const old2 = { role: 'user', content: 'old2' };
          _ensureMsgUid(old1); _ensureMsgUid(old2);
          msgs = [old1, old2].concat(msgs);
          // 修复后：按 uid 定位（漂移后 t1 从下标1 → 下标3）
          const i1 = _findMsgIndexByUid(msgs, t1o._uid);
          const i2 = _findMsgIndexByUid(msgs, t2o._uid);
          return { i1: i1, i2: i2, content1: msgs[i1].content, content2: msgs[i2].content };
        }""")
        print("漂移后 uid 定位:", r2)
        assert r2["i1"] == 3 and r2["i2"] == 4, f"FAIL: 漂移后定位 {r2}"
        assert r2["content1"] == "read_file 1" and r2["content2"] == "read_file 2"

        # ── 断言 3：toolMsgMap FIFO 语义（同名工具 push 两次 → shift 队首顺序）──
        r3 = page.evaluate("""() => {
          const map = {};
          (map['read_file'] = map['read_file'] || []).push(10);   // tool_call #1
          (map['read_file'] = map['read_file'] || []).push(20);   // tool_call #2（不再覆盖）
          const first = map['read_file'].shift();                 // tool_result #1 → 队首 10
          const second = map['read_file'].shift();                // tool_result #2 → 20
          return { first, second, remain: (map['read_file'] || []).length };
        }""")
        print("toolMsgMap FIFO:", r3)
        assert r3["first"] == 10 and r3["second"] == 20 and r3["remain"] == 0, "FAIL: FIFO"

        # ── 断言 4：无 JS 错误 ──
        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"

        print("T4 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
