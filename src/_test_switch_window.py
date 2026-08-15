# -*- coding: utf-8 -*-
"""T1 TDD：switch 响应窗口裁剪（has_more/total/window_size）
红：端点尚无窗口字段 → 断言失败；绿：实现后 PASS
短会话用现有 sess_win_short_5ea02c（7 条），长会话用 sess_312047a51c36（446 条）
"""
import json, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:6908"
N = 200  # 窗口大小（与实现约定一致）

def post(path, body):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=60))

# ── 短会话（7 条）──
r_short = post("/api/agent/sessions/switch", {"session_id": "sess_win_short_5ea02c"})["data"]
msgs_short = r_short.get("messages") or []
assert "has_more" in r_short, f"短会话缺 has_more 字段: {list(r_short.keys())}"
assert "total" in r_short, "短会话缺 total"
assert "window_size" in r_short, "短会话缺 window_size"
assert r_short["has_more"] is False, f"短会话应 has_more=False, 实际={r_short['has_more']}"
assert r_short["total"] == len(msgs_short), f"短会话 total={r_short['total']} != len={len(msgs_short)}"

# ── 长会话（446 条）──
r_long = post("/api/agent/sessions/switch", {"session_id": "sess_312047a51c36"})["data"]
msgs_long = r_long.get("messages") or []
assert r_long.get("has_more") is True, f"长会话应 has_more=True, 实际={r_long.get('has_more')}"
assert len(msgs_long) <= N, f"长会话窗口应 <= {N}, 实际={len(msgs_long)}"
assert r_long.get("total", 0) > N, f"长会话 total 应 > {N}, 实际={r_long.get('total')}"
assert r_long.get("window_size") == N, f"window_size 应 = {N}, 实际={r_long.get('window_size')}"

print(f"PASS 短会话: total={r_short['total']} has_more={r_short['has_more']} window={r_short['window_size']}")
print(f"PASS 长会话: total={r_long['total']} has_more={r_long['has_more']} window={len(msgs_long)}/{r_long['window_size']}")
print("T1 RESULT: PASS")
