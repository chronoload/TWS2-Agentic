import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .transport import TransportConfig, create_transport


class ClientState(Enum):
    DISABLED = "disabled"
    STARTING = "starting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ClientInfo:
    name: str
    state: ClientState
    error: Optional[str] = None
    tool_count: int = 0
    connected_at: Optional[float] = None


class MCPClientManager:
    def __init__(self):
        self._clients: Dict[str, Any] = {}
        self._states: Dict[str, ClientInfo] = {}
        self._tools: Dict[str, Dict] = {}

    def register(self, name: str, config: TransportConfig) -> bool:
        try:
            self._states[name] = ClientInfo(name=name, state=ClientState.STARTING)
            transport = create_transport(config)
            started = transport.start()
            if not started:
                self._states[name] = ClientInfo(name=name, state=ClientState.ERROR, error="Transport failed to start")
                return False
            response = transport.send({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            })
            tools = response.get("result", {}).get("tools", [])
            for tool in tools:
                tool_name = tool.get("name", "")
                self._tools[tool_name] = {
                    "client": name,
                    "schema": tool,
                }
            self._clients[name] = transport
            self._states[name] = ClientInfo(
                name=name,
                state=ClientState.CONNECTED,
                tool_count=len(tools),
                connected_at=time.time(),
            )
            return True
        except Exception as e:
            self._states[name] = ClientInfo(name=name, state=ClientState.ERROR, error=str(e))
            return False

    def unregister(self, name: str):
        transport = self._clients.pop(name, None)
        if transport is not None:
            transport.stop()
        self._states.pop(name, None)
        to_remove = [t for t, info in self._tools.items() if info.get("client") == name]
        for t in to_remove:
            del self._tools[t]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        tool_info = self._tools.get(tool_name)
        if tool_info is None:
            raise ValueError(f"Tool not found: {tool_name}")
        client_name = tool_info["client"]
        transport = self._clients.get(client_name)
        if transport is None:
            raise ConnectionError(f"Client not connected: {client_name}")
        response = transport.send({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        })
        return response.get("result")

    def list_tools(self) -> List[Dict]:
        return [info["schema"] for info in self._tools.values()]

    def get_state(self, name: str) -> Optional[ClientInfo]:
        return self._states.get(name)

    def list_clients(self) -> Dict[str, ClientInfo]:
        return dict(self._states)

    def close_all(self):
        for name in list(self._clients.keys()):
            self.unregister(name)
