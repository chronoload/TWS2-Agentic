"""Debug sanitize_messages with tool_calls"""
import sys
sys.path.insert(0, 'TS2/mcp')
from _sanitize import sanitize_messages

messages = [
    {'role': 'system', 'content': 'You are a helpful assistant.'},
    {'role': 'user', 'content': 'What is the weather?'},
    {'role': 'assistant', 'content': '', 'tool_calls': [
        {'id': 'call_abc123', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city": "Beijing"}'}}
    ]},
    {'role': 'tool', 'tool_call_id': 'call_abc123', 'content': 'Sunny, 25°C'},
    {'role': 'assistant', 'content': 'The weather in Beijing is sunny, 25°C.'},
    {'role': 'user', 'content': 'What about Shanghai?'},
]

safe = sanitize_messages(messages)
for i, m in enumerate(safe):
    tc = m.get('tool_calls', 'N/A')
    tcid = m.get('tool_call_id', 'N/A')
    print(f'[{i}] role={m["role"]!r} content={m.get("content","")!r:.40} tc={tc!r} tcid={tcid!r}')
