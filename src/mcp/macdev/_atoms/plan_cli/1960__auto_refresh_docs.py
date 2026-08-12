# 原子：_auto_refresh_docs（原 plan_cli.py 第 1960 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _auto_refresh_docs() -> None:
    """运行时自文档：每次调用后全量刷新命令参考 + 所有 plan 导出文档（quiet，不污染命令输出）。

    - 命令参考 PLAN_CLI.md 从 argparse 幂等生成（无时间戳，argparse 不变则内容不变）。
    - 每个 plan 的 PLAN_<id>.md + json 由 DB 实时渲染（含状态/进度/缺陷修复情况）。
    - 逃生阀：`PLAN_CLI_NO_AUTODOC=1` 可跳过（供批量/CI 调用）。
    """
    if os.environ.get("PLAN_CLI_NO_AUTODOC"):
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            cmd_doc(argparse.Namespace(out=str(DOCS_DIR / "PLAN_CLI.md")))
            _publish_plan_cli_doc()
        except Exception as e:
            print(f"[autodoc] PLAN_CLI.md 刷新失败: {e}", file=sys.stderr)
        conn = _connect(PLANS_DB)
        try:
            ids = [r[0] for r in conn.execute("SELECT id FROM plans ORDER BY id")]
        finally:
            conn.close()
        for pid in ids:
            try:
                cmd_export(argparse.Namespace(id=pid, out="", format="writing-plans", db=str(PLANS_DB)))
            except Exception as e:
                print(f"[autodoc] plan {pid} 导出失败: {e}", file=sys.stderr)
    print(f"[autodoc] 已刷新 PLAN_CLI.md（子技能三处 + 旧顶层发布）+ {len(ids)} 个 plan 文档")
