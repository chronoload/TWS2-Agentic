"""Python 引擎配置插件 (reticulate)"""

from ._base import EnvPlugin, DetectionResult, LockFile


class ReticulatePlugin(EnvPlugin):
    name = "reticulate"

    def detect(self) -> DetectionResult:
        code, out, err = self._run(["Rscript", "-e", "cat(as.character(packageVersion('reticulate')))"])
        if code == 0:
            return DetectionResult(name=self.name, detected=True, version=out.strip(), path="Rscript")
        return DetectionResult(name=self.name, detected=False, details="reticulate not installed")

    def install(self, confirm: bool = True) -> bool:
        if confirm:
            resp = input("Install reticulate? [y/N]: ").strip().lower()
            if resp != "y":
                return False
        code, _, err = self._run(["Rscript", "-e", "install.packages('reticulate', repos='https://cran.r-project.org')"], timeout=120)
        return code == 0

    def lock(self) -> LockFile:
        return LockFile(plugin_name=self.name, entries={"note": "reticulate version locked via renv"})

    def verify(self) -> bool:
        code, _, _ = self._run(["Rscript", "-e", "library(reticulate); cat(reticulate::py_version())"])
        return code == 0
