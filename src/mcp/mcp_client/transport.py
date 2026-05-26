import json
import os
import subprocess
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TransportConfig:
    type: str = "stdio"
    command: str = ""
    args: List[str] = field(default_factory=list)
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 15


class BaseTransport(ABC):
    @abstractmethod
    def start(self) -> bool:
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def send(self, request: dict) -> dict:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...


class StdioTransport(BaseTransport):
    def __init__(self, config: TransportConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> bool:
        try:
            merged_env = {**os.environ, **self.config.env}
            self._process = subprocess.Popen(
                [self.config.command, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=merged_env,
            )
            return self.is_connected()
        except Exception:
            return False

    def stop(self):
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def send(self, request: dict) -> dict:
        if not self.is_connected():
            raise ConnectionError("Transport not connected")
        line = json.dumps(request) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()
        response_line = self._process.stdout.readline()
        if not response_line:
            raise ConnectionError("Empty response from transport")
        return json.loads(response_line)

    def is_connected(self) -> bool:
        return self._process is not None and self._process.poll() is None


class HttpTransport(BaseTransport):
    def __init__(self, config: TransportConfig):
        self.config = config

    def start(self) -> bool:
        return True

    def stop(self):
        pass

    def send(self, request: dict) -> dict:
        data = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(
            self.config.url,
            data=data,
            headers={**self.config.headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def is_connected(self) -> bool:
        return bool(self.config.url)


class SSETransport(BaseTransport):
    def __init__(self, config: TransportConfig):
        self.config = config

    def start(self) -> bool:
        return True

    def stop(self):
        pass

    def send(self, request: dict) -> dict:
        data = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(
            self.config.url,
            data=data,
            headers={**self.config.headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def is_connected(self) -> bool:
        return bool(self.config.url)


def create_transport(config: TransportConfig) -> BaseTransport:
    transport_map = {
        "stdio": StdioTransport,
        "http": HttpTransport,
        "sse": SSETransport,
    }
    cls = transport_map.get(config.type)
    if cls is None:
        raise ValueError(f"Unknown transport type: {config.type}")
    return cls(config)
