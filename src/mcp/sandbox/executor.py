import os
import time
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from subprocess import Popen, PIPE, TimeoutExpired

from .policy import SandboxPolicy, Permission


@dataclass
class ExecutionResult:
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: int = 0
    command: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.error

    def to_text(self) -> str:
        parts = [f"$ {self.command}", self.stdout]
        if self.stderr:
            parts.append(self.stderr)
        parts.append(f"[exit code: {self.exit_code}]")
        if self.timed_out:
            parts.append("[TIMEOUT]")
        parts.append(f"[{self.duration_ms}ms]")
        return "\n".join(parts)


class SandboxExecutor:
    def __init__(self, policy: SandboxPolicy = None, cwd: str = None):
        self.policy = policy or SandboxPolicy()
        self.cwd = cwd or os.getcwd()
        self._active_processes: list = []

    def execute(self, command: str, stdin_data: str = None, env: dict = None) -> ExecutionResult:
        permission = self.policy.check_command(command)
        if permission == Permission.DENY:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                error="Command denied by sandbox policy",
            )
        if permission == Permission.ASK:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                error="Command requires approval",
            )

        merged_env = dict(os.environ)
        merged_env.update(self.policy.env_vars)
        if env:
            merged_env.update(env)
        if not self.policy.allow_network:
            merged_env["NO_PROXY"] = "*"

        start = time.monotonic()
        try:
            proc = Popen(
                command,
                shell=True,
                stdout=PIPE,
                stderr=PIPE,
                stdin=PIPE if stdin_data else None,
                cwd=self.cwd,
                env=merged_env,
            )
            self._active_processes.append(proc)
            try:
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=stdin_data.encode() if stdin_data else None,
                    timeout=self.policy.max_execution_time,
                )
            except TimeoutExpired:
                proc.kill()
                stdout_bytes, stderr_bytes = proc.communicate()
                duration_ms = int((time.monotonic() - start) * 1000)
                self._active_processes.remove(proc)
                return ExecutionResult(
                    command=command,
                    exit_code=proc.returncode,
                    stdout=stdout_bytes.decode(errors="replace")[:self.policy.max_output_bytes],
                    stderr=stderr_bytes.decode(errors="replace")[:4096],
                    timed_out=True,
                    duration_ms=duration_ms,
                )
            self._active_processes.remove(proc)
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                command=command,
                exit_code=proc.returncode,
                stdout=stdout_bytes.decode(errors="replace")[:self.policy.max_output_bytes],
                stderr=stderr_bytes.decode(errors="replace")[:4096],
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                command=command,
                exit_code=-1,
                error=str(exc),
                duration_ms=duration_ms,
            )

    def execute_script(self, script: str, language: str = "python", stdin_data: str = None) -> ExecutionResult:
        ext_map = {"python": ".py", "javascript": ".js", "js": ".js", "shell": ".sh", "sh": ".sh"}
        cmd_map = {"python": "python", "javascript": "node", "js": "node", "shell": "bash", "sh": "bash"}
        ext = ext_map.get(language, ".txt")
        cmd = cmd_map.get(language, language)
        fd, script_path = tempfile.mkstemp(suffix=ext)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script)
            return self.execute(f'{cmd} "{script_path}"', stdin_data=stdin_data)
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

    def kill_all(self):
        for proc in list(self._active_processes):
            try:
                proc.kill()
            except OSError:
                pass
        self._active_processes.clear()
