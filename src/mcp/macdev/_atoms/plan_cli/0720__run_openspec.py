# 原子：_run_openspec（原 plan_cli.py 第 720 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _run_openspec(*cmd: str, cwd: str = "") -> tuple[int, str]:
    """运行 openspec CLI，返回 (exit_code, stdout)。"""
    try:
        r = subprocess.run([_openspec_exe(), *cmd], capture_output=True, text=True,
                           cwd=cwd or str(PROJECT_ROOT), timeout=60, encoding="utf-8")
        return r.returncode, (r.stdout or "")
    except Exception as e:
        return 1, f"openspec 调用失败: {e}"
