# -*- coding: utf-8 -*-
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8")
B = "http://127.0.0.1:6908/api/agent"

def post(p, b):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=8).read())
    except Exception as e:
        return {"ERR": str(e)}

def get(p):
    try:
        return json.loads(urllib.request.urlopen(B + p, timeout=8).read())
    except Exception as e:
        return {"ERR": str(e)}

# 拿真实会话
s = get("/sessions")
sids = [x.get("id") or x.get("session_id") for x in (s.get("data") or {}).get("sessions", [])][:3]
print("sessions:", sids)
for sid in sids:
    print("sid:", sid)
    print("  clear:", post("/queue/clear", {"session_id": sid}))
    print("  enq1:", post("/queue/enqueue", {"session_id": sid, "content": "msg1"}))
    print("  enq2:", post("/queue/enqueue", {"session_id": sid, "content": "msg2"}))
    print("  query:", get("/queue?session_id=" + sid))
    # 清回
    print("  clear2:", post("/queue/clear", {"session_id": sid}))
