# -*- coding: utf-8 -*-
"""P0 验证：GET /sessions/{id} 与 POST /sessions/switch 输出一致性（防漂移断言）"""
import json, sys, urllib.request
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:6911"
SID = "sess_312047a51c36"

def get(path, body=None):
    if body is not None:
        req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(f"{BASE}{path}")
    return json.load(urllib.request.urlopen(req, timeout=60))

g = get(f"/api/agent/sessions/{SID}")
A = (g.get("data") or {}).get("messages") or []
s = get("/api/agent/sessions/switch", {"session_id": SID})
B = (s.get("data") or {}).get("messages") or []

FIELDS = ("role", "content", "reasoning_content", "tool_calls",
          "tool_call_id", "tool_name", "checkpoint_hash", "expanded_total")

def norm(msgs):
    return [{k: v for k, v in m.items() if k in FIELDS} for m in msgs]

A2, B2 = norm(A), norm(B)
roles_a, roles_b = Counter(m["role"] for m in A2), Counter(m["role"] for m in B2)
sys_a = sum(1 for m in A2 if m["role"] == "system" and m.get("expanded_total"))
sys_b = sum(1 for m in B2 if m["role"] == "system" and m.get("expanded_total"))
reason_a = sum(1 for m in A2 if m["role"] == "assistant" and m.get("reasoning_content"))
reason_b = sum(1 for m in B2 if m["role"] == "assistant" and m.get("reasoning_content"))

print(f"GET    : {len(A2)} 条 | roles={dict(roles_a)} | 摘要卡={sys_a} | reasoning={reason_a}")
print(f"switch : {len(B2)} 条 | roles={dict(roles_b)} | 摘要卡={sys_b} | reasoning={reason_b}")
same = A2 == B2
print("GET == switch:", "PASS" if same else "FAIL")
if not same:
    for i, (a, b) in enumerate(zip(A2, B2)):
        if a != b:
            print(f"  diff@{i}: GET={a} != switch={b}")
            break
print("P0 RESULT:", "PASS" if same and sys_a == sys_b and reason_a == reason_b else "FAIL")
