"""消息内容清洗 - 确保所有必须为字符串的字段都不是 null

DeepSeek / OpenAI 等 API 严格要求某些字段为 string 类型，
当消息中任何 string 字段为 null 时会返回 400 错误。

潜在出问题的字段（按概率排序）:
1. content        ← 已修复 (or None → or "")
2. role           ← assistant/system/user/tool 不能为 null
3. tool_call_id   ← tool 消息必须有非 null 的 tool_call_id
4. id (tool_calls)← 工具调用的唯一标识
5. type           ← 工具调用类型 (function)
6. name           ← 函数名
7. arguments      ← 函数参数 (JSON 字符串)
"""

import uuid
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def _ensure_str(value: Any, default: str = "") -> str:
    """将值转为非空字符串，None 或非字符串 → default"""
    if value is None or not isinstance(value, str):
        return default
    return value


def _ensure_tool_id(value: Any) -> str:
    """确保 tool_call_id 不为空，空值生成 UUID"""
    if value is None or not isinstance(value, str) or not value.strip():
        new_id = f"call_{uuid.uuid4().hex[:12]}"
        logger.debug(f"[_sanitize] _ensure_tool_id: {value!r} → {new_id}")
        return new_id
    return value


def _has_tool_messages_following(messages: List[Dict[str, Any]], current_msg: Dict[str, Any]) -> bool:
    """检查在当前消息之后是否有 tool 消息跟随。
    
    用于决定是否保留 assistant 消息的 tool_calls 字段：
    如果后面有 tool 消息，则必须保留 tool_calls 以维持关联。
    """
    found_current = False
    for msg in messages:
        if msg is current_msg:
            found_current = True
            continue
        if found_current and msg.get("role") == "tool":
            return True
    return False


def sanitize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """深度清洗消息数组: 所有 string 字段强制为非 null"""
    result = []
    for idx, msg in enumerate(messages):
        msg_copy = dict(msg)
        orig_role = msg.get("role", "?")
        logger.debug(f"[_sanitize] === Processing msg[{idx}] role={orig_role!r} ===")

        # === 顶层字段 ===
        # role: 必须为非 null 字符串
        msg_copy["role"] = _ensure_str(msg_copy.get("role"), "user")

        # content: 必须为非 null 字符串（最常见问题）
        raw_content = msg_copy.get("content")
        if raw_content is None:
            logger.debug(f"[_sanitize]   content was None → ''")
            msg_copy["content"] = ""
        elif isinstance(raw_content, list):
            # Anthropic 格式: content=[{"type":"text","text":"..."}, ...]
            text_parts = []
            for part in raw_content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
            msg_copy["content"] = "".join(text_parts)
            logger.debug(f"[_sanitize]   content was list → '{msg_copy['content'][:50]}'")
        elif not isinstance(raw_content, str):
            msg_copy["content"] = str(raw_content)
            logger.debug(f"[_sanitize]   content was non-str → '{msg_copy['content'][:50]}'")
        elif raw_content == "tool_use":
            msg_copy["content"] = ""
            logger.debug(f"[_sanitize]   content was 'tool_use' → ''")

        # tool_call_id: tool 消息的关键字段（必须与 tool_calls 中的 id 匹配）
        # 不能留空，也不能设为随机值--必须关联到具体的 tool_call
        if msg_copy.get("role") == "tool":
            tcid = msg_copy.get("tool_call_id")
            logger.debug(f"[_sanitize]   tool msg: original tool_call_id={tcid!r}")
            if tcid is None or (isinstance(tcid, str) and not tcid.strip()):
                # 查找前面最近的 assistant 消息中的 tool_calls 来匹配
                # 按 tool 消息的顺序，依次匹配前面 assistant 消息中的 tool_calls
                found_id = None
                for prev_msg in reversed(result):
                    if prev_msg.get("role") == "assistant":
                        prev_tcs = prev_msg.get("tool_calls", [])
                        if prev_tcs:
                            logger.debug(f"[_sanitize]   found assistant msg with {len(prev_tcs)} tool_calls")
                            # 找到第一个尚未被匹配的 tool_call id
                            for ptc in prev_tcs:
                                ptc_id = ptc.get("id", "") if isinstance(ptc, dict) else ""
                                logger.debug(f"[_sanitize]     checking ptc_id={ptc_id!r}")
                                # 即使 ptc_id 为空也尝试匹配（可能被 _ensure_str 置空）
                                # 如果为空，生成一个 UUID 来匹配
                                if not ptc_id:
                                    ptc_id = _ensure_tool_id(ptc_id)
                                    # 更新 assistant 消息中的 tool_call id
                                    ptc["id"] = ptc_id
                                    logger.debug(f"[_sanitize]     → generated UUID {ptc_id} for empty assistant tool_call id")
                                # 检查这个 id 是否已经被后续的 tool 消息使用
                                already_used = any(
                                    m.get("role") == "tool" and m.get("tool_call_id") == ptc_id
                                    for m in result
                                )
                                if not already_used:
                                    found_id = ptc_id
                                    logger.debug(f"[_sanitize]     → matched ptc_id={ptc_id!r} (not yet used)")
                                    break
                                else:
                                    logger.debug(f"[_sanitize]     → ptc_id={ptc_id!r} already used, skip")
                        if found_id:
                            break
                if found_id:
                    msg_copy["tool_call_id"] = found_id
                    logger.debug(f"[_sanitize]   → set tool_call_id={found_id!r} (matched from assistant)")
                else:
                    # 实在找不到匹配，生成 UUID 作为 fallback
                    new_id = _ensure_tool_id("")
                    msg_copy["tool_call_id"] = new_id
                    logger.debug(f"[_sanitize]   → set tool_call_id={new_id!r} (UUID fallback, no assistant match)")

        # === tool_calls 数组内字段 ===
        raw_tool_calls = msg_copy.get("tool_calls")
        if raw_tool_calls:
            logger.debug(f"[_sanitize]   processing {len(raw_tool_calls)} tool_calls")
            cleaned_calls = []
            for tc_idx, tc in enumerate(raw_tool_calls):
                if not isinstance(tc, dict):
                    logger.debug(f"[_sanitize]     tc[{tc_idx}] is not dict, skip")
                    continue
                tc_copy = dict(tc)
                orig_id = tc_copy.get("id", "")
                tc_copy["id"] = _ensure_tool_id(tc_copy.get("id"))
                if orig_id != tc_copy["id"]:
                    logger.debug(f"[_sanitize]     tc[{tc_idx}] id: {orig_id!r} → {tc_copy['id']!r}")
                tc_copy["type"] = _ensure_str(tc_copy.get("type"), "function")

                # function 对象内的字段
                func = tc_copy.get("function")
                if isinstance(func, dict):
                    func_copy = dict(func)
                    func_copy["name"] = _ensure_str(func_copy.get("name"), "unknown_tool")
                    func_copy["arguments"] = _ensure_str(
                        func_copy.get("arguments"),
                        "{}"
                    )
                    tc_copy["function"] = func_copy
                elif func is None:
                    tc_copy["function"] = {"name": "unknown_tool", "arguments": "{}"}
                    logger.debug(f"[_sanitize]     tc[{tc_idx}] function was None, set to default")

                cleaned_calls.append(tc_copy)
            if cleaned_calls:
                msg_copy["tool_calls"] = cleaned_calls
                logger.debug(f"[_sanitize]   → kept {len(cleaned_calls)} tool_calls")
            else:
                # 所有 tool_call 都无效，移除 key 避免 API 看到 tool_calls: []
                # 但如果有 tool 消息跟随，必须保留 tool_calls 以维持关联
                has_following = _has_tool_messages_following(messages, msg)
                if not has_following:
                    msg_copy.pop("tool_calls", None)
                    logger.debug(f"[_sanitize]   → removed tool_calls (all invalid, no tool msgs follow)")
                else:
                    logger.debug(f"[_sanitize]   → kept empty tool_calls (tool msgs follow)")
        elif raw_tool_calls is not None:
            # tool_calls 是空列表 []，移除 key 避免 API 看到 tool_calls: []
            # 但如果有 tool 消息跟随，必须保留 tool_calls 以维持关联
            has_following = _has_tool_messages_following(messages, msg)
            if not has_following:
                msg_copy.pop("tool_calls", None)
                logger.debug(f"[_sanitize]   → removed tool_calls: [] (no tool msgs follow)")
            else:
                logger.debug(f"[_sanitize]   → kept tool_calls: [] (tool msgs follow)")

        result.append(msg_copy)
        logger.debug(f"[_sanitize]   → result[{len(result)-1}]: role={msg_copy['role']!r} content={msg_copy.get('content','')[:40]!r} tc={'Y' if 'tool_calls' in msg_copy else 'N'} tcid={msg_copy.get('tool_call_id','N/A')!r}")

    return result
