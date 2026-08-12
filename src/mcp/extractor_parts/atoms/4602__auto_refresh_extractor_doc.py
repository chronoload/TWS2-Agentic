# 原子：_auto_refresh_extractor_doc（原 interface_chain_extractor.py 第 4602 行）
# 逻辑组：misc · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def _auto_refresh_extractor_doc() -> None:
    if os.environ.get("EXTRACTOR_NO_AUTODOC"):
        return
    try:
        import contextlib
        import io
        import shutil
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # cmd_doc 的 out 参数是【目录】（内部写 EXTRACTOR_DOC.md / EXTRACTOR_DEV_DOC.md）
            cmd_doc(argparse.Namespace(out=str(MCP_ROOT / "docs")))
        # 使用文档 + 开发文档（两者都由 cmd_doc 生成在同目录）
        for doc_name in ("EXTRACTOR_DOC.md", "EXTRACTOR_DEV_DOC.md"):
            src = MCP_ROOT / "docs" / doc_name
            for dst in (MCP_ROOT.parent / "docs" / "interface-chain-audit" / doc_name,
                        MCP_ROOT.parent / ".trae" / "skills" / "interface-chain-audit" / doc_name,
                        MCP_ROOT / "docs" / "interface-chain-audit" / doc_name,
                        MCP_ROOT.parent / "docs" / "skills" / "interface-chain-audit" / doc_name):
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                except Exception as e:
                    print(f"[autodoc] 发布 {doc_name} 失败: {dst}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[autodoc] EXTRACTOR 文档刷新失败: {e}", file=sys.stderr)
