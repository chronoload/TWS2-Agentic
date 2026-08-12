"""Python 包管理插件 (uv)"""

from ._base import EnvPlugin, DetectionResult, LockFile


class UvPlugin(EnvPlugin):
    name = "uv"

    def detect(self) -> DetectionResult:
        code, out, err = self._run(["uv", "--version"])
        if code == 0:
            return DetectionResult(name=self.name, detected=True, version=out.strip(), path="uv")
        return DetectionResult(name=self.name, detected=False, details=err)

    def install(self, confirm: bool = True) -> bool:
        if confirm:
            resp = input("Install uv? [y/N]: ").strip().lower()
            if resp != "y":
                return False
        # uv 通过 pip 安装或 curl 安装
        code, _, err = self._run(["pip", "install", "uv"], timeout=60)
        return code == 0

    def lock(self) -> LockFile:
        code, out, _ = self._run(["uv", "lock"])
        return LockFile(plugin_name=self.name, entries={"status": "ok" if code == 0 else "failed", "output": out})

    def verify(self) -> bool:
        code, _, _ = self._run(["uv", "pip", "check"])
        return code == 0
