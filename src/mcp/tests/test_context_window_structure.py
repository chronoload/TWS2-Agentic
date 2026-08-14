# -*- coding: utf-8 -*-
"""上下文压缩结构完整性测试（回归：auto_compact 输出必须满足 OpenAI 兼容消息约束）

Bug 背景：auto_compact 按「单条消息」独立挑选 keyword_preserved + recent 拼接，
导致压缩后出现 user→user 相邻 / 非system首条为 assistant / tool 不紧跟
assistant(tool_calls) 等结构违规；sanitize_messages 只修 tool 配对，无法修复
角色交替与开头角色 -> 下一轮 API 调用 400 -> 对话被打断。

修复策略：保护粒度从「消息」提升为「轮」（user 起始到下一个 user 前的完整回合），
压缩输出结构天然合法。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.prompt.context_window import auto_compact  # noqa: E402
from mcp.agent import sanitize_messages  # noqa: E402


# ---------- 结构校验辅助 ----------

def structure_violations(msgs):
    """模拟 OpenAI 兼容 API 的消息顺序约束，返回违规列表（空=合法）。"""
    violations = []
    roles = [m.get("role", "?") for m in msgs]

    # 1) 非 system 首条不能是 assistant / tool
    first = next((r for r in roles if r != "system"), None)
    if first in ("assistant", "tool"):
        violations.append(f"非system首条是 {first!r}（须为 user）")

    # 2) user→user / assistant→assistant 相邻
    for k in range(1, len(roles)):
        if roles[k] == "user" and roles[k - 1] == "user":
            violations.append(f"user→user 相邻 @{k}")
        if roles[k] == "assistant" and roles[k - 1] == "assistant":
            violations.append(f"assistant→assistant 相邻 @{k}")

    # 3) tool 必须紧跟其 assistant(tool_calls)
    pending = set()
    for k, m in enumerate(msgs):
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tid = tc.get("id") if isinstance(tc, dict) else None
                if tid:
                    pending.add(tid)
        elif role == "tool":
            tid = m.get("tool_call_id")
            if not tid or tid not in pending:
                violations.append(f"孤立/无配对 tool @{k} (id={tid})")
            elif k >= 1 and msgs[k - 1].get("role") not in ("assistant", "tool"):
                violations.append(f"tool 未紧跟 assistant @{k}（前序={msgs[k - 1].get('role')}）")
    if roles and roles[-1] == "tool":
        violations.append("序列以 tool 结尾")
    return violations


def assert_valid(compacted, label=""):
    violations = structure_violations(compacted)
    assert not violations, f"{label} 结构违规: " + "; ".join(violations)


# ---------- 场景构造 ----------

def _scenario_adjacent_users():
    """场景X：相邻 user 均含关键词被保护，中间的 assistant 回复被摘要掉 -> user→user"""
    msgs = [{"role": "system", "content": "你是助手。"}]
    msgs.append({"role": "user", "content": "必须记住方案A"})        # 命中「必须」「记住」
    msgs.append({"role": "assistant", "content": "收到，处理中。"})   # 无关键词 -> 摘要
    msgs.append({"role": "user", "content": "重要务必方案B"})        # 命中「重要」「务必」
    msgs.append({"role": "assistant", "content": "好的。"})           # 无关键词 -> 摘要
    for i in range(10, 30):
        msgs.append({"role": "user", "content": f"普通问题 {i}"})
        msgs.append({"role": "assistant", "content": f"普通回答 {i}"})
    return msgs


def _scenario_assistant_first():
    """场景Y：assistant 含关键词被保护，其前 user 无关键词被摘要 -> 保护集合以 assistant 开头"""
    msgs = [{"role": "system", "content": "你是助手。"}]
    msgs.append({"role": "user", "content": "帮我看看这段代码"})       # 无关键词 -> 摘要
    msgs.append({"role": "assistant", "content": "总结结论已完成"})    # 命中「总结」「结论」
    for i in range(10, 30):
        msgs.append({"role": "user", "content": f"普通问题 {i}"})
        msgs.append({"role": "assistant", "content": f"普通回答 {i}"})
    return msgs


def _scenario_tool_chain():
    """工具链场景：user -> assistant(tool_calls) -> tool -> assistant 交替 20 轮"""
    msgs = [{"role": "system", "content": "你是助手。"}]
    for i in range(20):
        if i % 2 == 0:
            msgs.append({"role": "user", "content": f"问题 {i}：请读文件"})
            msgs.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": f"call_{i}", "type": "function",
                                         "function": {"name": "read_file",
                                                      "arguments": f'{{"path": "f{i}.py"}}'}}]})
            msgs.append({"role": "tool", "tool_call_id": f"call_{i}",
                         "content": f"文件 f{i}.py 内容：" + "数据" * 30})
            msgs.append({"role": "assistant", "content": f"第 {i} 轮回复完成。"})
        else:
            msgs.append({"role": "user", "content": f"问题 {i}：直接回答"})
            msgs.append({"role": "assistant", "content": f"第 {i} 轮直接回复。"})
    return msgs


# ---------- 测试 ----------

def test_compact_no_adjacent_user():
    """场景X：压缩后不得出现 user→user 相邻（sanitize 也无法修复的违规）"""
    compacted, did = auto_compact(_scenario_adjacent_users(), "deepseek-chat", force=True)
    assert did
    assert_valid(compacted, "compact")
    assert_valid(sanitize_messages(compacted), "sanitize")


def test_compact_not_start_with_assistant():
    """场景Y：压缩后非 system 首条必须是 user"""
    compacted, did = auto_compact(_scenario_assistant_first(), "deepseek-chat", force=True)
    assert did
    assert_valid(compacted, "compact")
    assert_valid(sanitize_messages(compacted), "sanitize")


def test_compact_tool_pairing():
    """工具链：tool 必须紧跟 assistant(tool_calls)，且成对保留"""
    compacted, did = auto_compact(_scenario_tool_chain(), "deepseek-chat", force=True)
    assert did
    assert_valid(compacted, "compact")
    # 保留的 tool 消息必须成对（assistant tool_calls 也在）
    tool_ids = {m.get("tool_call_id") for m in compacted if m.get("role") == "tool"}
    for tid in tool_ids:
        assert any(
            m.get("role") == "assistant" and any(
                (tc.get("id") if isinstance(tc, dict) else None) == tid
                for tc in m.get("tool_calls", [])
            ) for m in compacted
        ), f"tool_call_id={tid} 缺少 assistant 配对"


def test_compact_keeps_recent():
    """最近轮次必须保留（最后一条 user 消息仍在压缩结果中）"""
    msgs = _scenario_tool_chain()
    last_user_content = next(m["content"] for m in reversed(msgs)
                             if m.get("role") == "user")
    compacted, did = auto_compact(msgs, "deepseek-chat", force=True)
    assert did
    contents = {str(m.get("content", "")) for m in compacted}
    assert last_user_content in contents, "最后一条 user 消息丢失"


def test_compact_normal_structure():
    """常规对话（无关键词命中）：压缩后结构仍合法且不超窗口语义"""
    msgs = [{"role": "system", "content": "你是助手。"}]
    for i in range(50):
        msgs.append({"role": "user", "content": f"普通问题 {i}，" + "细节" * 40})
        msgs.append({"role": "assistant", "content": f"普通回答 {i}，" + "细节" * 40})
    compacted, did = auto_compact(msgs, "deepseek-chat", force=True)
    assert did
    assert_valid(compacted, "compact")
    assert len(compacted) < len(msgs), "压缩应减少消息数"


def test_compact_twice_stable():
    """二次压缩（压缩结果再压缩）结构仍合法（多次压缩可还原场景）"""
    compacted, did = auto_compact(_scenario_tool_chain(), "deepseek-chat", force=True)
    assert did
    compacted2, did2 = auto_compact(compacted, "deepseek-chat", force=True)
    assert_valid(compacted2, "compact2")
    # 无论是否再次触发压缩，结果都必须结构合法
    assert_valid(sanitize_messages(compacted2), "sanitize2")
