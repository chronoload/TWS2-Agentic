# 原子：run_plugins（原 interface_chain_extractor.py 第 3243 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def run_plugins(root: Path, out: Path, plugins: list[str],
                context: dict, timeout: int = 180) -> list[dict]:
    """编排 subprocess 插件：逐个运行，收集 stdout JSON，artifacts 落盘。

    返回插件结果列表（各含 name/lang/stats/report_md/artifacts/sections）。
    脚本类插件（node/python）自动追加 --stdin-json 切换到插件协议；
    裸可执行文件（rust 二进制）默认即 stdin JSON 协议，无需标志。
    """
    import subprocess
    results: list[dict] = []
    for spec in plugins:
        resolved = _resolve_plugin(spec)
        if resolved is None:
            continue
        lang, exe, script = resolved
        argv = [str(script)] if not exe else [exe, str(script)]
        if lang in ("node", "python"):
            argv.append("--stdin-json")
        print(f"[plugin] 运行: {' '.join(argv)}（--root={root}）")
        try:
            r = subprocess.run(argv, input=json.dumps(context, ensure_ascii=False),
                               capture_output=True, text=True, encoding="utf-8",
                               timeout=timeout)
        except Exception as e:
            print(f"[plugin] 执行失败 {script}: {e}")
            continue
        if r.stderr and r.stderr.strip():
            print(f"[plugin] {script} stderr: {r.stderr.strip()[:300]}")
        try:
            data = json.loads(r.stdout or "{}")
        except Exception as e:
            print(f"[plugin] {script} stdout 非 JSON（协议要求 stdout 只输出 JSON），跳过: {e}")
            continue
        data.setdefault("name", script.stem)
        data.setdefault("lang", exe or "exec")
        results.append(data)
        stats = data.get("stats") or {}
        if stats:
            print(f"[plugin] {data['name']}: " + " ".join(f"{k}={v}" for k, v in stats.items()))
        for a in data.get("artifacts") or []:
            try:
                ap = out / str(a["path"])
                ap.parent.mkdir(parents=True, exist_ok=True)
                ap.write_text(str(a["content"]), encoding="utf-8")
                print(f"[plugin] artifact → {ap}")
            except Exception as e:
                print(f"[plugin] artifact 写入失败 {a.get('path')}: {e}")
    return results
