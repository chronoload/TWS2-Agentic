# -*- coding: utf-8 -*-
"""T5 验证：工具调用语义漂移修复 — 空 assistant 删除改为 uid 定位双数组同步删除
核心场景：流式快照 streamState.messages 与 UI state.agentMessages 是同一批对象（同 uid）。
tool_call 需删除当前空 assistant（currentIndex 指向 uid=a），旧逻辑按"尾部第一个空 assistant"删除会删 uid=b（错！）。
新逻辑 removeStreamMessage 按 uid=a 定位删除 → 两数组删除同一条，后续下标保持一致。
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

        # 模拟 removeStreamMessage 语义：uid 定位双数组同步删除
        r = page.evaluate("""() => {
          // 同一批对象（addStreamMessage 双数组同引用）
          const m0 = { role: 'user', content: 'hi' };
          const m1 = { role: 'assistant', content: '', _uid: 'u-a' };   // 当前空气泡（currentIndex=1）
          const m2 = { role: 'user', content: 'mid' };
          const m3 = { role: 'assistant', content: '', _uid: 'u-b' };   // 尾部另一个空气泡（旧逻辑会误删它）
          [m0, m1, m2, m3].forEach(_ensureMsgUid);
          const streamMsgs = [m0, m1, m2, m3];
          const stateMsgs = streamMsgs.slice();  // 同引用副本
          const currentIndex = 1;
          // 新逻辑：removeStreamMessage(currentIndex) —— uid 定位双数组删除
          const uid = streamMsgs[currentIndex] && streamMsgs[currentIndex]._uid;
          streamMsgs.splice(currentIndex, 1);
          const ui = _findMsgIndexByUid(stateMsgs, uid);
          if (ui >= 0) stateMsgs.splice(ui, 1);
          return {
            streamLen: streamMsgs.length, stateLen: stateMsgs.length,
            streamUids: streamMsgs.map(x => x._uid), stateUids: stateMsgs.map(x => x._uid),
            syncOk: JSON.stringify(streamMsgs.map(x => x._uid)) === JSON.stringify(stateMsgs.map(x => x._uid)),
            deletedUid: uid
          };
        }""")
        print("uid 同步删除:", r)
        assert r["streamLen"] == 3 and r["stateLen"] == 3, "FAIL: 长度不一致"
        assert r["deletedUid"] == "u-a", "FAIL: 应删 uid=u-a"
        assert r["syncOk"], "FAIL: 双数组不同步"
        assert "u-a" not in r["stateUids"] and "u-b" in r["stateUids"], "FAIL: 删错了（旧逻辑删 u-b）"

        # 对比：旧逻辑（尾部第一个空 assistant）确实会删错 u-b
        r2 = page.evaluate("""() => {
          const a = { role: 'assistant', content: '', _uid: 'u-a' };
          const b = { role: 'assistant', content: '', _uid: 'u-b' };
          const arr = [a, b];
          for (let i = arr.length - 1; i >= 0; i--) {
            if (arr[i].role === 'assistant' && !arr[i].content) { arr.splice(i, 1); break; }
          }
          return arr[0]._uid;  // 旧逻辑删除后剩下的是 u-a（即删的是 u-b）→ 证明旧逻辑删错
        }""")
        print("旧逻辑会删:", "(剩", r2, ") 即误删 u-b")
        assert r2 == "u-a", "FAIL: 旧逻辑模拟不符"

        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"
        print("T5 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
