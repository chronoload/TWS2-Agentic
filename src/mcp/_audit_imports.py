import sys
import importlib
import inspect
import ast
import os
from pathlib import Path

MCP_DIR = Path(__file__).parent
sys.path.insert(0, str(MCP_DIR.parent))

results = {
    "import_errors": [],
    "missing_attrs": [],
    "signature_mismatches": [],
    "dead_code": [],
}

def check_imports_in_file(filepath):
    """检查文件中所有import语句是否可解析"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        results["import_errors"].append(f"{filepath}: READ_ERROR {e}")
        return

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        results["import_errors"].append(f"{filepath}: SYNTAX_ERROR {e}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            rel_level = node.level

            if rel_level > 0:
                parts = []
                if filepath.name == "__init__.py":
                    pkg = filepath.parent
                else:
                    pkg = filepath.parent
                
                for i in range(rel_level - 1):
                    pkg = pkg.parent
                
                if module_name:
                    full_module = f"mcp.{module_name}" if str(pkg).endswith("mcp") else module_name
                else:
                    full_module = "mcp"
                
                for alias in node.names:
                    try:
                        mod = importlib.import_module(full_module)
                        if not hasattr(mod, alias.name):
                            all_attrs = dir(mod)
                            close = [a for a in all_attrs if alias.name.lower() in a.lower()]
                            results["missing_attrs"].append(
                                f"{filepath.name}:{node.lineno} - "
                                f"from {full_module} import {alias.name} - "
                                f"NOT FOUND (similar: {close[:3]})"
                            )
                    except ImportError as e:
                        results["import_errors"].append(
                            f"{filepath.name}:{node.lineno} - "
                            f"from {full_module} import {alias.name} - "
                            f"IMPORT_ERROR: {e}"
                        )
                    except Exception as e:
                        results["import_errors"].append(
                            f"{filepath.name}:{node.lineno} - "
                            f"from {full_module} import {alias.name} - "
                            f"ERROR: {type(e).__name__}: {e}"
                        )

def check_method_signatures(filepath, class_name, method_name, expected_params):
    """检查类方法的参数签名"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        params = [a.arg for a in item.args.args]
                        defaults = len(item.args.defaults)
                        required = params[:len(params) - defaults] if defaults > 0 else params
                        return params, required
    except:
        pass
    return None, None

def check_call_vs_definition(caller_file, caller_line, callee_module, callee_class, callee_method, call_args):
    """检查调用参数与定义是否匹配"""
    pass

core_files = [
    "agent.py",
    "agent_assistant.py",
    "workflow_engine.py",
    "config_ui.py",
    "tools.py",
    "llm.py",
    "config.py",
    "skills.py",
    "skill_system/__init__.py",
    "skill_system/skill_types.py",
    "skill_system/curator.py",
    "skill_system/security_scanner.py",
    "skill_system/tool_policy.py",
    "harness/__init__.py",
    "harness/approval.py",
    "harness/runner.py",
    "harness/hooks.py",
    "harness/turn.py",
    "harness/events.py",
    "harness/session_store.py",
    "plugins/__init__.py",
    "plugins/plugin_manager.py",
    "plugins/plugin_context.py",
    "plugins/trust_gates.py",
    "extensions/__init__.py",
    "extensions/skills.py",
    "extensions/session_tabs.py",
    "extensions/session_instances.py",
    "extensions/unified_session.py",
    "context_compactor.py",
    "predefined_workflows.py",
    "event_logger.py",
    "git_searcher.py",
    "rag/__init__.py",
    "rag/rag_engine.py",
    "rag/auto_rag.py",
    "rag/knowledge_graph.py",
    "rag/retriever.py",
    "rag/vector_store.py",
    "rag/document_loader.py",
    "rag/text_splitter.py",
    "subagent/__init__.py",
    "subagent/coordinator.py",
    "subagent/agent_tool.py",
    "subagent/session.py",
    "subagent/types.py",
    "middleware/__init__.py",
    "middleware/base.py",
    "middleware/chain.py",
    "middleware/loop_detection.py",
    "middleware/tool_error.py",
    "middleware/memory.py",
    "middleware/dynamic_context.py",
    "cache/__init__.py",
    "cache/disk.py",
    "cache/lru_cache.py",
    "cache/model_cache.py",
    "cache/state_manager.py",
    "cache/ui_state.py",
    "cache/context_reloader.py",
    "prompt/__init__.py",
    "prompt/builder.py",
    "prompt/components.py",
    "prompt/templates.py",
    "prompt/variants.py",
    "prompt/workspace.py",
    "prompt/context_window.py",
    "runtime/__init__.py",
    "runtime/run_manager.py",
    "runtime/journal.py",
    "automation/__init__.py",
    "automation/engine.py",
    "automation/triggers.py",
    "automation/persistence.py",
    "automation/popup_manager.py",
    "automation/event_bus.py",
    "automation/course_simulation.py",
    "sandbox/__init__.py",
    "sandbox/executor.py",
    "sandbox/policy.py",
    "sandbox/shell.py",
    "sandbox/cli.py",
    "mcp_client/__init__.py",
    "mcp_client/client.py",
    "mcp_client/transport.py",
    "mcp_client/tool_adapter.py",
    "scholar/__init__.py",
    "scholar/tools.py",
    "scholar/server.py",
    "scholar/cache.py",
    "scholar/rate_limiter.py",
    "i18n.py",
    "ui.py",
    "ws2_tools.py",
    "ws2_hub_tools.py",
    "wolfram_tools.py",
    "_sanitize.py",
]

print("=" * 60)
print("MCP系统完整排查 - 幻觉代码检测")
print("=" * 60)

for fname in core_files:
    fpath = MCP_DIR / fname
    if fpath.exists():
        check_imports_in_file(fpath)

print(f"\n--- Import错误 ({len(results['import_errors'])}) ---")
for e in results["import_errors"]:
    print(f"  ❌ {e}")

print(f"\n--- 属性不存在 ({len(results['missing_attrs'])}) ---")
for e in results["missing_attrs"]:
    print(f"  ❌ {e}")

print(f"\n--- 统计 ---")
print(f"  Import错误: {len(results['import_errors'])}")
print(f"  属性不存在: {len(results['missing_attrs'])}")
