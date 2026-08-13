# 原子：_run_frontend_trace（原 interface_chain_extractor.py 第 3177 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _run_frontend_trace(node_script: Path, file: str, cls: str, client: str, out_dir: Path,
                        backend: str = "") -> int:
    """调用 trace_agent_frontend.mjs（Node 词法级前端对齐）"""
    import shutil
    import subprocess
    if not shutil.which("node"):
        print("[project] 未找到 node，跳过前端追踪（可安装 Node 后重跑）")
        return 1
    if not Path(file).exists():
        print(f"[project] 前端入口不存在: {file}")
        return 1
    cmd = ["node", str(node_script), "--file", str(file), "--class", cls,
           "--client", client, "--out", str(_art(out_dir, "FRONTEND_TRACE.md")),
           "--label", str(file)]
    if backend and Path(backend).exists():
        cmd += ["--backend", str(backend)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.stdout:
        print(r.stdout.strip()[:400])
    if r.returncode != 0 and r.stderr:
        print(r.stderr.strip()[:400])
    return r.returncode
