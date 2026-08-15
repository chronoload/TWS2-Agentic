# -*- coding: utf-8 -*-
"""T3 TDD：消息 schema 归一化防御
红：畸形消息（msg 非 dict / function 非 dict / content=None）当前崩溃 → FAIL
绿：_build_ui_messages 补防御 → PASS
"""
import sys
sys.path.insert(0, r"C:\Users\qu\Desktop\物理科学与技术论题\TS2_dev\src")
sys.stdout.reconfigure(encoding="utf-8")
from mcp.server.app import _build_ui_messages

# 畸形消息集
malformed = [
    None,                         # msg 非 dict
    123,                          # msg 非 dict
    "string-msg",                 # msg 非 dict
    {"role": None, "content": None},                      # role None + content None
    {"role": "assistant", "content": None, "tool_calls": None},  # tool_calls None
    {"role": "assistant", "content": 123, "tool_calls": "not-list"},  # tool_calls 非 list
    {"role": "assistant", "content": "ok",
     "tool_calls": [{"id": "t1", "type": "function", "function": "not-dict"}]},  # function 非 dict
    {"role": "tool", "tool_call_id": None, "content": None},  # tool_call_id None
    {"role": "weird_role", "content": "unknown-role"},        # 未知 role
]

# 逐个喂，断言不抛异常 + 输出结构合法
for i, m in enumerate(malformed):
    try:
        out = _build_ui_messages([m])
        assert isinstance(out, list), f"case{i}: 输出非 list: {out!r}"
        for item in out:
            assert isinstance(item, dict), f"case{i}: 消息项非 dict: {item!r}"
            # tool 项 tool_call_id 必须 str；assistant tool_calls 若存在必须 list 且 function 兜底
            if item.get("role") == "tool":
                assert isinstance(item.get("tool_call_id", ""), str), f"case{i}: tool_call_id 非 str"
            if item.get("tool_calls") is not None:
                assert isinstance(item["tool_calls"], list), f"case{i}: tool_calls 非 list"
    except Exception as e:
        print(f"FAIL case{i}: 畸形消息 {m!r} 抛异常: {type(e).__name__}: {e}")
        raise

print(f"PASS: {len(malformed)} 个畸形消息全部安全处理")
print("T3 RESULT: PASS")
