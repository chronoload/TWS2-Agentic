"""audit 运行器：端点提取 → 亲属追逐依赖链 → 6 维分析 → 4 维扫描 → 双轨产物。"""
from __future__ import annotations
from pathlib import Path
from ..core.progress import ScanBudget
from ..core.types import Result
from . import parse, chain, analyze, scan, report
from .task import AuditTask


def collect_files(task: AuditTask) -> list:
    """审计文件集合：task.files 入口 + 项目内 *.py（排除 exclude）。
    跳过 >12MB 的极端生成/编译产物（常规大文件不是问题，不设过小阈值）。"""
    files: list = []
    seen: set = set()
    for rel in (task.files or {}).values():
        p = task.root / rel
        if p.is_file() and str(p) not in seen:
            seen.add(str(p))
            files.append(p)
    for p in chain._iter_py_files(task.root, task.exclude):
        if str(p) not in seen:
            seen.add(str(p))
            try:
                if p.stat().st_size > 12 * 1024 * 1024:
                    continue
            except OSError:
                continue
            files.append(p)
    return files


def run_audit(engine, task: AuditTask, out_dir: Path) -> Result:
    strategy = engine.registry.create("audit.strategy", task.strategy)
    out_dir.mkdir(parents=True, exist_ok=True)

    endpoints, models = parse.extract_all(task)
    files = collect_files(task)
    # 扫描预算：进度打印 + 超时截断（task.scan_timeout 秒后只出已处理子集）
    budget = ScanBudget(len(files), "scan", interval=200,
                        timeout=int(task.scan_timeout), quiet=not task.progress) \
        if task.progress or int(task.scan_timeout) > 0 else None
    engine.bus.emit("audit.phase.done", {"phase": "parse", "endpoints": len(endpoints),
                                         "files": len(files)})

    dep_sections = chain.build_dep_sections(endpoints, task.root, task.chains,
                                            strategy=strategy, exclude=task.exclude,
                                            budget=budget)
    if budget:
        budget.reset(len(files), "analyze")
    analysis = analyze.analyze_all(files, behavior_rules=task.behavior_rules,
                                   id_source_rules=task.id_source_rules,
                                   budget=budget)
    if budget:
        budget.reset(len(files), "scan")
    scan_items = scan.scan_all(task.root, files, task.exclude, budget=budget)
    if budget and budget.truncated:
        engine.bus.emit("audit.truncated", budget.summary())

    # 语义偏移：前端 client 方法（task.files.client 指向 JS，可选）
    drifts = []
    client_js = (task.files or {}).get("client")
    if client_js:
        clients = analyze.extract_client_methods(task.root / client_js)
        drifts = analyze.detect_drift(endpoints, models, clients)

    md = report.gen_markdown(endpoints, models, dep_sections,
                             defuse=analysis["defuse"],
                             behavior=analysis["behavior"],
                             flag=analysis["flag"],
                             merge=analysis["merge"],
                             id_source=analysis["id_source"],
                             hardcoded=scan_items["hardcoded"],
                             env_vars=scan_items["env_vars"],
                             data_pools=scan_items["data_pools"],
                             static_resources=scan_items["static_resources"])
    header = (f"# INTERFACE_CHAIN\n\n"
              f"> 由 `python -m macdev audit` 生成。端点数: {len(endpoints)} · "
              f"扫描文件: {len(files)} · 策略: {task.strategy}\n\n")
    (out_dir / "INTERFACE_CHAIN.md").write_text(header + md + "\n", encoding="utf-8")

    report.write_csvs(out_dir, endpoints, models, drifts, analysis["defuse"],
                      analysis["behavior"], analysis["flag"], analysis["merge"],
                      analysis["id_source"], scan_items)
    db = out_dir / "interface_chain.db"
    report.write_db(db, endpoints, models, drifts, analysis["defuse"],
                    analysis["behavior"], analysis["flag"], analysis["merge"],
                    analysis["id_source"], scan_items)

    engine.bus.emit("audit.phase.done", {"phase": "report", "artifacts": [str(db)]})
    data = {"endpoints": len(endpoints), "files": len(files),
            "drifts": len(drifts),
            "defuse": len(analysis["defuse"][2]) if analysis["defuse"] else 0,
            "behavior": len([b for b in analysis["behavior"] if b.missing and "未找到" not in b.detail]),
            "flag": len(analysis["flag"]), "merge": len(analysis["merge"]),
            "id_source": len(analysis["id_source"]),
            "hardcoded": len(scan_items["hardcoded"]),
            "env_vars": len(scan_items["env_vars"]),
            "data_pools": len(scan_items["data_pools"]),
            "static_resources": len(scan_items["static_resources"])}
    if budget and budget.truncated:
        data["truncated"] = True
        data["scanned"] = budget.done
        data["total"] = len(files)
    return Result(ok=True, data=data,
                  artifacts=[str(out_dir / "INTERFACE_CHAIN.md"), str(db)])
