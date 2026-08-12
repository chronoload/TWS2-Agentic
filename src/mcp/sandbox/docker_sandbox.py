import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from .policy import SandboxPolicy, Permission

logger = logging.getLogger(__name__)


@dataclass
class DockerExecutionResult:
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.error

    def __str__(self):
        if self.error:
            return f"Error: {self.error}"
        return self.stdout or self.stderr or "(no output)"


class DockerSandbox:
    def __init__(self, image: str = "python:3.11-slim", policy: SandboxPolicy = None):
        self.image = image
        self.policy = policy or SandboxPolicy()
        self._available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._available

    def execute(self, command: str, cwd: str = None, stdin_data: str = None,
                timeout: float = None) -> DockerExecutionResult:
        if not self._available:
            return DockerExecutionResult(command=command, error="Docker不可用")

        timeout = timeout or self.policy.max_execution_time
        perm = self.policy.check_command(command)
        if perm == Permission.DENY:
            return DockerExecutionResult(command=command, error=f"命令被策略阻止: {command.split()[0] if command.split() else command}")
        if perm == Permission.ASK:
            return DockerExecutionResult(command=command, error=f"命令需要审批: {command.split()[0] if command.split() else command}")

        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none" if not self.policy.allow_network else "bridge",
            "--memory", "512m",
        ]
        if cwd:
            docker_cmd.extend(["-v", f"{Path(cwd).resolve()}:/workspace"])
            docker_cmd.extend(["-w", "/workspace"])
        if not self.policy.allow_file_write:
            docker_cmd.extend(["--read-only", "--tmpfs", "/tmp:size=100m"])

        docker_cmd.append(self.image)
        docker_cmd.extend(["sh", "-c", command])

        try:
            result = subprocess.run(
                docker_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=timeout + 10, input=stdin_data,
            )
            output = result.stdout
            if len(output.encode(errors='replace')) > self.policy.max_output_bytes:
                output = output[:self.policy.max_output_bytes] + "\n... (输出已截断)"
            return DockerExecutionResult(
                command=command,
                stdout=output,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return DockerExecutionResult(command=command, error=f"执行超时 ({timeout}s)")
        except Exception as e:
            return DockerExecutionResult(command=command, error=str(e))

    def execute_script(self, script: str, language: str = "python",
                       timeout: float = None) -> DockerExecutionResult:
        with tempfile.NamedTemporaryFile(
            suffix=f".{language}", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            if language == "python":
                command = f"python3 /workspace/{Path(script_path).name}"
            else:
                command = f"{language} /workspace/{Path(script_path).name}"
            return self.execute(command, cwd=str(Path(script_path).parent), timeout=timeout)
        finally:
            Path(script_path).unlink(missing_ok=True)
