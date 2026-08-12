# 原子：_dispatch（原 plan_cli.py 第 1883 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _dispatch(args) -> int:
    """命令分发（返回退出码，供 main 调用）。"""
    if args.cmd == "create":
        return cmd_create(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "update":
        return cmd_update(args)
    if args.cmd == "delete":
        return cmd_delete(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "ledger":
        return cmd_ledger(args)
    if args.cmd == "review":
        return cmd_review(args)
    if args.cmd == "dispatch":
        return cmd_dispatch(args)
    if args.cmd == "task":
        if args.tcmd == "step":
            return {"add": cmd_step_add, "list": cmd_step_list,
                    "update": cmd_step_update, "delete": cmd_step_delete}[args.scmd](args)
        return {"add": cmd_task_add, "list": cmd_task_list,
                "update": cmd_task_update, "delete": cmd_task_delete}[args.tcmd](args)
    if args.cmd == "export":
        return cmd_export(args)
    if args.cmd == "tdd":
        if args.tdd_cmd == "check":
            return cmd_tdd_check(args)
        return 1
    if args.cmd == "defect":
        if args.defect_cmd == "list":
            return cmd_defect_list(args)
        if args.defect_cmd == "gen-test":
            return cmd_defect_gen_test(args)
        return 1
    if args.cmd == "chain":
        return {"stats": cmd_chain_stats, "issues": cmd_chain_issues,
                "endpoints": cmd_chain_endpoints, "models": cmd_chain_models,
                "drifts": cmd_chain_drifts, "tables": cmd_chain_tables}[args.chain_cmd](args)
    if args.cmd == "doc":
        return cmd_doc(args)
    if args.cmd == "openspec":
        return {"list": cmd_openspec_list, "status": cmd_openspec_status,
                "import": cmd_openspec_import, "export": cmd_openspec_export,
                "sync-specs": cmd_openspec_sync_specs}[args.openspec_cmd](args)
    return 1
