from typing import Any, Callable, Dict, List

from .client import MCPClientManager


class MCPToolAdapter:
    def __init__(self, client_manager: MCPClientManager):
        self._manager = client_manager

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        for tool_info in self._manager._tools.values():
            tool = tool_info["schema"]
            schema = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            schemas.append(schema)
        return schemas

    def get_tool_handlers(self) -> Dict[str, Callable]:
        handlers = {}
        for tool_name in list(self._manager._tools.keys()):
            handlers[tool_name] = lambda arguments, _name=tool_name: self._manager.call_tool(_name, arguments)
        return handlers
