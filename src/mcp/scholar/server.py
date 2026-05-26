import threading
from typing import List

from ..tools import Tool
from .tools import SCHOLAR_TOOLS


class ScholarMCPServer:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._tools = None
            return cls._instance

    def get_scholar_tools(self) -> List[Tool]:
        if self._tools is None:
            self._tools = [tool_cls() for tool_cls in SCHOLAR_TOOLS]
        return self._tools

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._instance = None
