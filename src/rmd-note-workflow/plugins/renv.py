"""R 包管理插件 (renv)"""

from ._base import EnvPlugin, DetectionResult, LockFile


class RenvPlugin(EnvPlugin):
    name = "renv"

    def detect(self) -> DetectionResult:
        code, out, err = self._run(["Rscript", "-e", "cat(as.character(packageVersion('renv')))"])
        if code == 0:
            return DetectionResult(name=self.name, detected=True, version=out.strip(), path="Rscript")
        return DetectionResult(name=self.name, detected=False, details=err)

    def install(self, confirm: bool = True) -> bool:
        if confirm:
            resp = input("Install renv? [y/N]: ").strip().lower()
            if resp != "y":
                return False
        code, _, err = self._run(["Rscript", "-e", "install.packages('renv', repos='https://cran.r-project.org')"], timeout=120)
        return code == 0

    def lock(self) -> LockFile:
        code, out, _ = self._run(["Rscript", "-e", "renv::snapshot(prompt=FALSE)"])
        return LockFile(plugin_name=self.name, entries={"status": "ok" if code == 0 else "failed", "output": out})

    def verify(self) -> bool:
        code, _, _ = self._run(["Rscript", "-e", "renv::status()"])
        return code == 0
