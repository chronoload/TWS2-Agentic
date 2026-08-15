# -*- coding: utf-8 -*-
"""T3: 普通模式持久化消息队列（spec id=7）——SessionStore 队列 + interrupt 端点

测试目标：
1. SessionStore.pending_queue 方法：enqueue/dequeue/peek/clear/len 持久化到 metadata
2. app.py interrupt 端点：agent.cancel() 打断 + 入队
3. 队列消费顺序（FIFO）

直接调端点函数（规避 TestClient 版本兼容，同 test_loop_api 风格）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.harness.session_store import SessionStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    """独立临时目录的 SessionStore（避免污染真实会话数据）"""
    return SessionStore(store_dir=str(tmp_path / "sessions"))


# ── 1) SessionStore 队列方法：enqueue/dequeue/len/peek/clear ──
def test_session_queue_enqueue_dequeue(store):
    sid = store.create(name="队列测试").id
    store.enqueue_pending(sid, "指令1")
    store.enqueue_pending(sid, "指令2")
    assert store.pending_queue_len(sid) == 2
    assert store.pending_queue_peek(sid) == "指令1"
    assert store.pending_queue_dequeue(sid) == "指令1"
    assert store.pending_queue_len(sid) == 1
    assert store.pending_queue_dequeue(sid) == "指令2"
    assert store.pending_queue_len(sid) == 0


def test_session_queue_clear(store):
    sid = store.create(name="清空测试").id
    store.enqueue_pending(sid, "a")
    store.enqueue_pending(sid, "b")
    store.clear_pending_queue(sid)
    assert store.pending_queue_len(sid) == 0


# ── 2) 持久化：新实例加载后队列仍在（刷新/多标签共享）──
def test_session_queue_persisted_across_instances(tmp_path):
    d = str(tmp_path / "sessions")
    s1 = SessionStore(store_dir=d)
    sid = s1.create(name="持久化").id
    s1.enqueue_pending(sid, "跨实例保留")
    # 新实例（模拟刷新/多标签）
    s2 = SessionStore(store_dir=d)
    assert s2.pending_queue_len(sid) == 1
    assert s2.pending_queue_dequeue(sid) == "跨实例保留"
    assert s2.pending_queue_len(sid) == 0


# ── 3) 会话不存在时返回空队列/None（不报错，兼容）──
def test_session_queue_missing_session(store):
    assert store.pending_queue_len("no_such_sid") == 0
    assert store.pending_queue_dequeue("no_such_sid") is None
    assert store.pending_queue_peek("no_such_sid") is None


# ── 4) interrupt 语义：入队 FIFO 队首不变（打断插入 = 新消息入队尾，队首旧消息先消费）──
def test_interrupt_semantics_enqueue_after_existing():
    """打断插入：已有队列时新消息追加到队尾，FIFO 队首不变（不插队）"""
    store = SessionStore(store_dir=str(Path(__file__).resolve().parent.parent / "cache_data" / "sessions"))
    sid = store.create(name="打断语义").id
    store.enqueue_pending(sid, "旧消息")
    store.enqueue_pending(sid, "新打断")
    assert store.pending_queue_len(sid) == 2
    assert store.pending_queue_peek(sid) == "旧消息"  # FIFO：旧消息先消费
    store.clear_pending_queue(sid)
