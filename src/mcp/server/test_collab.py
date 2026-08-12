"""后端协同 CollabManager 端到端测试（asyncio + mock WebSocket）。

模拟客户端用 Python loro（与前端 wasm 协议一致：snapshot/update 均为 Loro 二进制 base64）。
运行：python -m mcp.server.test_collab  或  python mcp/server/test_collab.py
"""
import asyncio
import base64
import json
import pathlib
import tempfile

import loro

from mcp.server.collab import CollabManager


class MockWS:
    """模拟 WebSocket：send_text 收集消息，receive_text 从队列取输入。"""

    def __init__(self):
        self.sent = []
        self.inbox = asyncio.Queue()
        self.id = hex(id(self))[-6:]

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))

    async def receive_text(self):
        return await self.inbox.get()

    def feed(self, msg: dict):
        self.inbox.put_nowait(json.dumps(msg))


def doc_from_snapshot(b64: str):
    doc = loro.LoroDoc()
    if b64:
        doc.import_(base64.b64decode(b64))
    updates = []
    sub = doc.subscribe_local_update(lambda u: (updates.append(bytes(u)), True)[1])
    return doc, updates, sub


async def test_collab_two_clients():
    ws_dir = tempfile.mkdtemp()
    p = pathlib.Path(ws_dir) / "note.md"
    p.write_text("hello", encoding="utf-8")

    persisted = []
    manager = CollabManager(
        load_text=lambda path: p.read_text(encoding="utf-8"),
        persist_text=lambda path, text: persisted.append(text),
    )

    ws_a = MockWS()
    ws_b = MockWS()

    async def send_a(m):
        ws_a.sent.append(m)

    async def send_b(m):
        ws_b.sent.append(m)

    task_a = asyncio.create_task(manager.handle(ws_a, "note.md", send_json=send_a))
    # 等待 A 初始化
    for _ in range(20):
        if any(m.get("cmd") == "collab_snapshot" for m in ws_a.sent):
            break
        await asyncio.sleep(0.05)
    assert any(m.get("cmd") == "collab_connected" for m in ws_a.sent)
    snap_a = next(m for m in ws_a.sent if m.get("cmd") == "collab_snapshot")
    doc_a, upd_a, sub_a = doc_from_snapshot(snap_a["data"]["bytes"])
    assert doc_a.get_text("md").to_string() == "hello"

    # A 编辑并广播
    doc_a.get_text("md").insert(0, "A-")
    doc_a.commit()
    assert upd_a, "A 应有本地 update"
    ws_a.feed({"cmd": "collab_update", "data": {"bytes": base64.b64encode(upd_a[-1]).decode()}})

    # B 加入
    task_b = asyncio.create_task(manager.handle(ws_b, "note.md", send_json=send_b))
    for _ in range(20):
        if any(m.get("cmd") == "collab_snapshot" for m in ws_b.sent):
            break
        await asyncio.sleep(0.05)
    snap_b = next(m for m in ws_b.sent if m.get("cmd") == "collab_snapshot")
    doc_b, upd_b, sub_b = doc_from_snapshot(snap_b["data"]["bytes"])
    # 等待 B 快照已包含 A 的编辑（服务端权威处理 A 的 update）
    assert doc_b.get_text("md").to_string() == "A-hello", doc_b.get_text("md").to_string()

    # B 编辑并广播
    doc_b.get_text("md").insert(5, "B-")
    doc_b.commit()
    ws_b.feed({"cmd": "collab_update", "data": {"bytes": base64.b64encode(upd_b[-1]).decode()}})

    # A 应收到 B 的广播
    for _ in range(20):
        if any(m.get("cmd") == "collab_update" for m in ws_a.sent):
            break
        await asyncio.sleep(0.05)
    bcast = [m for m in ws_a.sent if m.get("cmd") == "collab_update"]
    assert bcast, "A 应收到 B 的 update 广播"
    doc_a.import_(base64.b64decode(bcast[-1]["data"]["bytes"]))
    # "A-hello" pos5 = 第二个 l → "A-hel" + "B-" + "lo"
    assert doc_a.get_text("md").to_string() == "A-helB-lo", doc_a.get_text("md").to_string()

    # 清理任务
    task_a.cancel()
    task_b.cancel()
    for t in (task_a, task_b):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    # 持久化：最后客户端离开后服务端写回
    await asyncio.sleep(0.2)
    assert persisted, "服务端应持久化文档"
    saved = persisted[-1]
    print("persisted:", repr(saved))
    assert "A-" in saved and "B-" in saved, saved


async def main():
    await test_collab_two_clients()
    print("COLLAB TEST PASS")


if __name__ == "__main__":
    asyncio.run(main())
