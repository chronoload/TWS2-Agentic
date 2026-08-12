# 原子：cmd_dispatch（原 plan_cli.py 第 1198 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_dispatch(args) -> int:
    """并行任务派发（dispatching-parallel-agents 机器化）。

    基于「文件冲突 + 接口依赖」做独立性判定（wave 分组）：
      - 无共享文件交集 且 无接口消费依赖 → 同 wave 可并行
      - 共享文件 / Consumes 命中其他任务 Produces → 串行（前序完成后才能派发）
    并给出每任务的模型选择建议（mechanical → cheap / integration → standard /
    architecture → capable），对齐 sdd 的 Model Selection 章节。
    """
    conn = _connect(args.db)
    tasks = conn.execute(
        "SELECT id, title, detail, files, req_ref, defect_ref, interfaces, status, review_status "
        "FROM tasks WHERE plan_id = ? AND status != 'done' ORDER BY id",
        (args.plan,)).fetchall()
    conn.close()
    if not tasks:
        print(f"[dispatch] plan={args.plan} 无待执行任务")
        return 0

    # 归一化文件清单
    def _files_set(files: str) -> set:
        out = set()
        for ln in (files or "").splitlines():
            ln = ln.strip()
            if ln:
                out.add(ln.split(":", 1)[-1].strip())
        return out

    def _parse_ifaces(interfaces: str) -> tuple[set, set]:
        """返回 (produces, consumes) 两个函数名集合。"""
        produces, consumes = set(), set()
        for ln in (interfaces or "").splitlines():
            ln = ln.strip()
            low = ln.lower()
            if low.startswith("produces") and ":" in ln:
                name = ln.split(":", 1)[1].strip().split("(")[0].strip()
                if name:
                    produces.add(name)
            elif low.startswith("consumes") and ":" in ln:
                name = ln.split(":", 1)[1].strip().split("(")[0].strip()
                if name:
                    consumes.add(name)
        return produces, consumes

    file_sets = {t[0]: _files_set(t[3]) for t in tasks}
    iface_data = {t[0]: _parse_ifaces(t[6]) for t in tasks}
    # 全任务 Produces 汇总：fn → 生产该接口的 task
    producer_of: dict[str, int] = {}
    for t in tasks:
        prods, _ = iface_data[t[0]]
        for fn in prods:
            producer_of.setdefault(fn, t[0])

    def _conflicts(t, wave_ids: set) -> bool:
        """与已入 wave 的任务是否冲突：文件交集 或 消费了 wave 内任务产出的接口。"""
        if not wave_ids:
            return False
        wave_file_union: set = set()
        for i in wave_ids:
            wave_file_union |= file_sets[i]
        if file_sets[t[0]] & wave_file_union:
            return True
        _, consumes = iface_data[t[0]]
        for fn in consumes:
            prod_task = producer_of.get(fn)
            if prod_task is not None and prod_task in wave_ids:
                return True
        return False

    waves: list[list] = []
    remaining = list(tasks)
    while remaining:
        wave, rest = [], []
        wave_ids: set = set()
        for t in remaining:
            if _conflicts(t, wave_ids):
                rest.append(t)
            else:
                wave.append(t)
                wave_ids.add(t[0])
        if not wave:  # 全部互相冲突（理论上不应发生，防御）
            wave, rest = remaining[:1], remaining[1:]
        waves.append(wave)
        remaining = rest

    def _model_choice(t) -> str:
        detail_len = len(t[2] or "")
        n_files = len(file_sets[t[0]])
        ifaces = t[6] or ""
        consumes = "consumes" in ifaces.lower()  # 消费上游接口 → 集成判断
        if n_files <= 2 and detail_len < 300 and not consumes:
            return "cheap（机械实现，1-2 文件，spec 完整）"
        if consumes or n_files >= 4:
            return "capable（架构/集成判断）"
        return "standard（多文件集成）"

    print(f"[dispatch] plan={args.plan} 并行派发方案 — {len(tasks)} 个待执行任务，分成 {len(waves)} 个 wave\n")
    for wi, wave in enumerate(waves, 1):
        print(f"Wave {wi}（可并行 {len(wave)} 个）:")
        for t in wave:
            files_txt = ", ".join(file_sets[t[0]]) or "—"
            review = t[8] or "pending"
            print(f"  • Task {t[0]}: {t[1]}  [files: {files_txt}]  [review: {review}]")
            print(f"      → 模型: {_model_choice(t)}")
        print()
    print("[dispatch] 说明：Wave 内任务可并行派发；Wave 间必须串行（文件依赖）。")
    return 0
