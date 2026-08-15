# -*- coding: utf-8 -*-
"""T3 验证：流式中点「停止」→ 真停止 + 队列消息原样放回输入框（不丢、不清空）
场景：真实会话 + 后端队列 2 条排队消息 + 模拟流式中 → 点停止按钮
断言：1) 输入框包含两条排队消息  2) 后端队列已清空  3) streaming 复位  4) 无 JS 错误
"""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:6908"
API = BASE + "/api/agent"
SID = "sess_312047a51c36"

def api_post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def api_get(path):
    return json.loads(urllib.request.urlopen(API + path, timeout=10).read())

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_function("typeof _stopAgentChat === 'function'", timeout=20000)

        # 切到真实会话（确保 record 存在，队列可持久化）
        page.evaluate("switchToSession('%s')" % SID)
        page.wait_for_timeout(1200)
        sid = page.evaluate("_getAgentSessionId()")
        print("session:", sid)
        assert sid == SID, f"FAIL: 会话未切换 {sid}"

        # 准备：清空队列 → 入队 2 条 → 验证
        api_post("/queue/clear", {"session_id": sid})
        api_post("/queue/enqueue", {"session_id": sid, "content": "排队消息一"})
        api_post("/queue/enqueue", {"session_id": sid, "content": "排队消息二"})
        q = api_get(f"/queue?session_id={sid}")
        print("入队后队列长度:", q["data"]["queue_len"])
        assert q["data"]["queue_len"] == 2, "FAIL: 入队失败"

        # 模拟流式中 + 点击「停止」按钮
        page.evaluate("""() => { state.agentStreaming = true; updateAgentSendButton(); }""")
        btn_before = page.evaluate("document.getElementById('agentSend').textContent")
        print("流式时按钮文字:", btn_before)
        assert btn_before == "停止"
        page.evaluate("""() => {
          const btn = document.getElementById('agentSend');
          btn.click();  // 直接触发 click（面板未激活时元素不可见，用 JS click 走同一 handler）
        }""")
        page.wait_for_timeout(1500)

        # 断言 1：输入框包含两条排队消息（原样放回）
        input_val = page.evaluate("document.getElementById('agentInput').value")
        print("输入框内容:", repr(input_val))
        assert "排队消息一" in input_val and "排队消息二" in input_val, "FAIL: 排队消息未放回输入框"

        # 断言 2：后端队列已清空
        q2 = api_get(f"/queue?session_id={sid}")
        print("停止后队列长度:", q2["data"]["queue_len"])
        assert q2["data"]["queue_len"] == 0, "FAIL: 队列未清空"

        # 断言 3：streaming 复位 + 按钮恢复「发送」
        streaming = page.evaluate("state.agentStreaming")
        btn_text = page.evaluate("document.getElementById('agentSend').textContent")
        print("streaming 复位:", streaming, "| 按钮:", btn_text)
        assert streaming is False, "FAIL: streaming 未复位"
        assert btn_text == "发送", "FAIL: 按钮未恢复发送"

        # 断言 4：无 JS 错误
        print("JS 错误:", js_errors if js_errors else "无")
        assert not js_errors, f"FAIL: JS 错误 {js_errors}"

        print("T3 RESULT: PASS")
        browser.close()

if __name__ == "__main__":
    run()
