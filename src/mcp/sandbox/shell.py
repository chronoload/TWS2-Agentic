import os
from typing import Dict, List

from .policy import SandboxPolicy
from .executor import SandboxExecutor, ExecutionResult


class ShellSession:
    def __init__(self, policy: SandboxPolicy = None, cwd: str = None):
        self._policy = policy or SandboxPolicy()
        self._cwd = cwd or os.getcwd()
        self._env: Dict[str, str] = {}
        self._history: List[Dict[str, str]] = []
        self._executor = SandboxExecutor(policy=self._policy, cwd=self._cwd)

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def run(self, command: str) -> ExecutionResult:
        result = self._executor.execute(command, env=self._env)
        self._history.append({
            "command": command,
            "exit_code": str(result.exit_code),
            "cwd": self._cwd,
        })
        if result.success and result.stdout:
            stripped = result.stdout.strip()
            lines = stripped.splitlines()
            if len(lines) == 1 and len(stripped) < 512:
                candidate = stripped
                if os.path.isdir(candidate):
                    self._cwd = os.path.abspath(candidate)
                    self._executor.cwd = self._cwd
        return result

    def set_env(self, key: str, value: str):
        self._env[key] = value

    def get_env(self, key: str, default: str = "") -> str:
        if key in self._env:
            return self._env[key]
        return os.environ.get(key, default)

    def cd(self, path: str) -> ExecutionResult:
        target = path if os.path.isabs(path) else os.path.normpath(os.path.join(self._cwd, path))
        if os.path.isdir(target):
            self._cwd = os.path.abspath(target)
            self._executor.cwd = self._cwd
            return ExecutionResult(
                command=f"cd {path}",
                exit_code=0,
                stdout=self._cwd,
            )
        return ExecutionResult(
            command=f"cd {path}",
            exit_code=1,
            stderr=f"Not a directory: {target}",
        )
