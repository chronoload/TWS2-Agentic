"""Test full Agent flow: simulate multi-round tool call conversation"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Inline the relevant code to avoid import issues
from _sanitize import sanitize_messages

# Replicate ToolCall and LLMResponse inline
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMResponse:
    content: str = ""
    reasoning_content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    finish_reason: str = ""
    
    @property
    def message(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg

# Simulate Agent.chat() flow:
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the weather in Beijing?"},
]

# Round 1: assistant returns tool_calls
tc1 = ToolCall(id="call_abc123", name="get_weather", arguments={"city": "Beijing"})
resp1 = LLMResponse(content="", tool_calls=[tc1])
msg1 = resp1.message
print(f"Round 1 assistant message: {json.dumps(msg1, ensure_ascii=False)}")
messages.append(msg1)

# Add tool result
messages.append({
    "role": "tool",
    "tool_call_id": "call_abc123",
    "content": "Sunny, 25°C"
})

# Round 2: assistant responds with final answer (no tool_calls)
resp2 = LLMResponse(content="The weather in Beijing is sunny, 25°C.")
msg2 = resp2.message
print(f"Round 2 assistant message: {json.dumps(msg2, ensure_ascii=False)}")
messages.append(msg2)

# Round 3: user asks new question
messages.append({"role": "user", "content": "What about Shanghai?"})

print("\n=== Before sanitize ===")
for i, m in enumerate(messages):
    tc = m.get('tool_calls', 'N/A')
    tcid = m.get('tool_call_id', 'N/A')
    print(f'[{i}] role={m["role"]!r} content={m.get("content","")!r:.40} tc={tc!r} tcid={tcid!r}')

safe = sanitize_messages(messages)
print("\n=== After sanitize ===")
for i, m in enumerate(safe):
    tc = m.get('tool_calls', 'N/A')
    tcid = m.get('tool_call_id', 'N/A')
    print(f'[{i}] role={m["role"]!r} content={m.get("content","")!r:.40} tc={tc!r} tcid={tcid!r}')

# Check: does the tool message have a matching assistant message with tool_calls?
print("\n=== Validation ===")
for i, m in enumerate(safe):
    if m["role"] == "tool":
        tcid = m.get("tool_call_id", "")
        found = False
        for j in range(i-1, -1, -1):
            prev = safe[j]
            if prev["role"] == "assistant":
                prev_tcs = prev.get("tool_calls", [])
                if prev_tcs:
                    for ptc in prev_tcs:
                        if isinstance(ptc, dict) and ptc.get("id") == tcid:
                            found = True
                            break
                if found:
                    break
        if found:
            print(f"  ✓ Tool msg [{i}] matches assistant msg with tool_calls")
        else:
            print(f"  ✗ Tool msg [{i}] has NO matching assistant with tool_calls! tcid={tcid!r}")
