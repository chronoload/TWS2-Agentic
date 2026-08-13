"""公共基础模块：config 读取、日志、路径处理"""

import json
import logging
import os
from pathlib import Path
from typing import Any


class Config:
    """RMD 项目配置，合并 content + infra 两层"""

    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        """读取 config.json"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    @classmethod
    def default(cls) -> "Config":
        """返回最小默认配置（bootstrap 前使用）"""
        return cls({
            "content": {
                "project": {"name": "", "type": "custom", "language": "zh", "author": ""},
                "structure": {"layout": "flat", "file_pattern": "{name}.Rmd", "dir_pattern": ".", "sections": []},
                "reference": {"lesson": "", "lines": 0, "source_files": [], "style_baseline": "human"},
                "narrative": {
                    "philosophy": "re-kctsw",
                    "section_order": ["R", "E", "K", "C", "T", "S", "W"],
                    "header_format": "# {X}：{title}",
                    "opening_format": "## 中心问题：{desc}",
                    "closing_format": "## 习题",
                },
                "quality": {
                    "min_chars": 20000, "min_lines": 500,
                    "require_theorem_proof": True, "require_workflow_dag": True,
                    "require_numerical": True, "max_filler_ratio": 0.05,
                },
                "dependencies": {"graph": "auto", "edges": []},
                "terminology": {"file": "terminology.json", "auto_track": True},
            },
            "infra": {
                "output_formats": {},
                "knitr": {"error": True, "fig_width": 8, "fig_height": 5, "dpi": 300, "cache": False, "python_trycatch": True, "disable_pdfcrop": True},
                "pandoc": {"extensions": ["+fenced_divs", "+bracketed_spans"], "defaults": None, "csl": None, "bibliography": None},
                "environment": {"r": {"renv": True, "packages": []}, "python": {"manager": "uv", "packages": []}, "system": {"latex": "miktex", "pandoc": ">=3.0"}},
                "assets": {"images": "images/", "data": "data/", "output": "output/", "temp": "temp/"},
                "compilation": {"workers": 4, "failure_log": "_compile_failures.csv", "summary_log": "_compile_summary.txt", "preprocess_inline_r": True, "safe_filenames": True, "kill_zombies": True, "retry_on_fix": True},
                "editor": {"rproj": True, "gitignore_patterns": ["*.html", "*.tex", "*.log", "*.aux", "temp/", "cache/", "_freeze/"]},
            },
        })

    def get(self, key_path: str, default: Any = None) -> Any:
        """点分路径读取: config.get('content.project.name')"""
        keys = key_path.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key_path: str, value: Any) -> None:
        """点分路径写入"""
        keys = key_path.split(".")
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def save(self, path: str | Path) -> None:
        """保存到 JSON"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @property
    def data(self) -> dict:
        return self._data


def setup_logging(level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """统一日志配置"""
    logger = logging.getLogger("rmd_workflow")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def resolve_path(base: str | Path, relative: str) -> Path:
    """相对路径解析（base 可以是文件或目录）"""
    b = Path(base)
    if b.is_file():
        b = b.parent
    return (b / relative).resolve()


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，返回 Path"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def count_chars(text: str, exclude_code: bool = True) -> int:
    """统计字符数（可排除代码块）"""
    if not exclude_code:
        return len(text)
    # 移除 ``` 代码块
    import re
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    # 移除 YAML 头
    cleaned = re.sub(r"^---[\s\S]*?---", "", cleaned, count=1)
    return len(cleaned)


def count_lines(file_path: str | Path) -> int:
    """统计文件行数"""
    with open(file_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)
