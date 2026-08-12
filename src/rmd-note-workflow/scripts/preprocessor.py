"""Rmd 预处理：inline R 防护、安全文件名、僵尸进程清理"""

import os
import re
import shutil
import subprocess
from pathlib import Path


# pandoc 拒绝的字符
UNSAFE_CHARS_RE = re.compile(r"[<>()|&;#?*']")


def preprocess_rmd(src: str | Path, dst: str | Path) -> Path:
    """
    预处理 Rmd：
    1. 跳过 YAML 区域
    2. 正文中 `r =` → `r\u200B=` 防止 knitr 误解析为 inline R
    """
    src_path = Path(src)
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    with open(src_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 跳过 YAML 区域（--- 之间）
    yaml_end = 0
    if content.startswith("---"):
        second_dash = content.find("---", 3)
        if second_dash != -1:
            yaml_end = second_dash + 3

    # 分离 YAML 和正文
    yaml_part = content[:yaml_end]
    body_part = content[yaml_end:]

    # 在正文中：`r\s*=` → `r\u200B=`
    # 匹配反引号包围的 r = 模式
    body_part = re.sub(r"`(r\s*=)", r"`r\u200B=", body_part)

    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(yaml_part + body_part)

    return dst_path


def safe_filename(name: str) -> str:
    """
    将特殊字符替换为下划线
    'L01_A < B > C.Rmd' → 'L01_A _ B _ C.Rmd'
    """
    return UNSAFE_CHARS_RE.sub("_", name)


def safe_copy_with_rename(src: str | Path, dst_dir: str | Path) -> tuple[Path, bool]:
    """
    安全复制文件（处理特殊字符文件名）
    返回 (实际写入路径, 是否重命名了)
    """
    src_path = Path(src)
    dst_dir = Path(dst_dir)
    original_name = src_path.name
    safe_name = safe_filename(original_name)

    if original_name != safe_name:
        dst_path = dst_dir / safe_name
        shutil.copy2(src_path, dst_path)
        return dst_path, True
    else:
        dst_path = dst_dir / original_name
        shutil.copy2(src_path, dst_path)
        return dst_path, False


def restore_original_name(safe_path: Path, original_name: str) -> None:
    """将安全文件名恢复为原始文件名"""
    if safe_path.name != original_name:
        target = safe_path.parent / original_name
        shutil.move(str(safe_path), str(target))


def kill_zombie_rscript() -> int:
    """清理僵尸 Rscript 进程，返回杀掉的数量"""
    count = 0
    try:
        if os.name == "nt":
            # Windows
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Rscript.exe", "/FO", "CSV"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.strip().split("\n")[1:]:
                if "Rscript" in line:
                    pid = line.split(",")[1].strip('"')
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                    count += 1
        else:
            # Unix
            result = subprocess.run(["pkill", "-f", "Rscript"], capture_output=True, timeout=10)
            count = result.returncode == 0
    except Exception:
        pass
    return count
