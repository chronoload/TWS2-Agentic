# 原子：_publish_plan_cli_doc（原 plan_cli.py 第 1932 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _publish_plan_cli_doc() -> None:
    """把 mcp/docs/PLAN_CLI.md + PLAN_CLI_DEV.md 发布到三处子技能位置 + 保留旧顶层发布。

    三处子技能同构：trae（.trae/skills/）、mcp（mcp/docs/）、docs（docs/skills/），
    路径均为 <root>/interface-chain-audit/ts2-plan-cli/。
    使用文档（PLAN_CLI.md）+ 开发文档（PLAN_CLI_DEV.md）都由 cmd_doc 自举生成。
    旧顶层发布（docs/superpowers 与 .trae/skills/ts2-plan-cli/）保留，兼容历史引用。
    """
    subskill_dsts = (
        PROJECT_ROOT / ".trae" / "skills" / "interface-chain-audit" / "ts2-plan-cli",
        PROJECT_ROOT / "mcp" / "docs" / "interface-chain-audit" / "ts2-plan-cli",
        PROJECT_ROOT / "docs" / "skills" / "interface-chain-audit" / "ts2-plan-cli",
    )
    legacy_dsts = (
        PROJECT_ROOT / "docs" / "superpowers" / "skills" / "ts2-plan-cli",
        PROJECT_ROOT / ".trae" / "skills" / "ts2-plan-cli",
    )
    for doc_name in ("PLAN_CLI.md", "PLAN_CLI_DEV.md"):
        src = DOCS_DIR / doc_name
        for dst in (*subskill_dsts, *legacy_dsts):
            target = dst / doc_name
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            except Exception as e:
                print(f"[autodoc] 发布 {doc_name} 失败: {target}: {e}", file=sys.stderr)
