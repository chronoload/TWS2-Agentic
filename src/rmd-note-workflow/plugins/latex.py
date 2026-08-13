"""LaTeX 环境检测插件"""

from ._base import EnvPlugin, DetectionResult, LockFile


class LatexPlugin(EnvPlugin):
    name = "latex"

    def detect(self) -> DetectionResult:
        code, out, err = self._run(["xelatex", "--version"])
        if code == 0:
            version = out.split("\n")[0] if out else "unknown"
            return DetectionResult(name=self.name, detected=True, version=version, path="xelatex")
        # 尝试 pdflatex
        code, out, err = self._run(["pdflatex", "--version"])
        if code == 0:
            version = out.split("\n")[0] if out else "unknown"
            return DetectionResult(name=self.name, detected=True, version=version, path="pdflatex")
        return DetectionResult(name=self.name, detected=False, details="xelatex and pdflatex not found")

    def install(self, confirm: bool = True) -> bool:
        print("LaTeX 需要手动安装：")
        print("  Windows: https://miktex.org/download")
        print("  macOS: brew install --cask mactex")
        print("  Linux: sudo apt install texlive-full")
        return False

    def lock(self) -> LockFile:
        return LockFile(plugin_name=self.name, entries={"note": "LaTeX is system-level, not lockable"})

    def verify(self) -> bool:
        code, _, _ = self._run(["xelatex", "--version"])
        return code == 0
