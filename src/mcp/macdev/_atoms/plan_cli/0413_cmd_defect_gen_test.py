# 原子：cmd_defect_gen_test（原 plan_cli.py 第 413 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def cmd_defect_gen_test(args) -> int:
    """静态缺陷 → 回归测试文件（Agent 通过接口写测试文件，落盘后动态运行冒烟）。

    对绑定静态缺陷的任务，生成 pytest 回归测试文件骨架：
       - 以缺陷详情为 docstring（红：复现缺陷场景的断言）
       - Agent 根据缺陷上下文补全断言后运行 `pytest tests/test_xxx.py` 动态验证
    """
    import re

    conn = _connect(args.db)
    rows = conn.execute(
        "SELECT id, title, defect_ref FROM tasks WHERE id = ?", (args.task,)).fetchall()
    conn.close()
    if not rows:
        print(f"[defect] task id={args.task} 不存在")
        return 1
    tid, title, defect_ref = rows[0]
    if not defect_ref:
        print(f"[defect] task id={tid} '{title}' 未绑定静态缺陷（先 task update --id {tid} --defect dim:file:line:kind）")
        return 1

    # 查找缺陷详情
    defects = _load_defects(args.index)
    detail_d = next((d for d in defects if d["id"] == defect_ref), None)
    if detail_d is None:
        print(f"[defect] 缺陷 {defect_ref} 不在当前 index.json 中——可能已修复；仍生成回归测试骨架")
        dim, file_s, line_s = (defect_ref.split(":") + ["", ""])[:3]
        kind = "fixed"
        detail_txt = "该缺陷已从静态报告消失，本测试为回归保护。"
    else:
        dim, kind, file_s, line_s = detail_d["dim"], detail_d["kind"], detail_d["file"], detail_d["line"]
        detail_txt = detail_d["detail"]

    # 生成安全文件名：test_defect_<dim>_<basename>_<line>.py
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", file_s)
    line_part = f"_{line_s}" if line_s else ""
    out = Path(args.out) if args.out else PROJECT_ROOT / "tests" / f"test_defect_{dim}_{safe}{line_part}.py"
    out.parent.mkdir(parents=True, exist_ok=True)

    severity = (detail_d or {}).get("severity", "yellow")
    sev_txt = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}.get(severity, "·")
    content = (
        f'# 回归测试：静态缺陷 {sev_txt} {defect_ref}\n'
        f'# 来源：interface_chain_extractor 静态分析（plan_cli defect gen-test 生成）\n'
        f'# 缺陷描述：{detail_txt}\n'
        f'# 任务：{title} (task id={tid})\n'
        f'#\n'
        f'# 用法：Agent 补全断言 → 运行 `pytest {out.relative_to(PROJECT_ROOT)} -v` 动态验证\n'
        f'# 闭环：测试通过 + 重跑 extractor 缺陷消失 = 修复完成\n'
        f'import pytest\n'
        f'\n'
        f'\n'
        f'def test_defect_regression():\n'
        f'    """RED 复现：先写失败测试，修复实现后转 GREEN。\n'
        f'\n'
        f'    缺陷类型: {kind}\n'
        f'    位置: {file_s}:{line_s or "?"}\n'
        f'    """\n'
        f'    # TODO(agent): 根据缺陷上下文补全断言。骨架：\n'
        f'    #   from mcp.server.app import ...\n'
        f'    #   assert actual == expected\n'
        f'    pytest.fail("未补全断言：本测试为静态缺陷 {defect_ref} 的回归测试")\n'
    )
    out.write_text(content, encoding="utf-8")
    print(f"[defect] 已生成回归测试文件 → {out}")
    print(f"[defect] 缺陷: {defect_ref} (kind={kind}, {file_s}:{line_s or '?'})")
    print(f"[defect] 动态验证: python -m pytest {out.relative_to(PROJECT_ROOT)} -v")
    return 0
