import sys
import importlib
import ast
from pathlib import Path

MCP_DIR = Path(__file__).parent
sys.path.insert(0, str(MCP_DIR.parent))

results = {
    "import_errors": [],
    "missing_attrs": [],
    "syntax_errors": [],
}

def get_module_path(filepath, level, module_name):
    """根据文件路径和相对导入级别计算完整模块名"""
    filepath = Path(filepath)
    if filepath.name == "__init__.py":
        pkg_dir = filepath.parent
    else:
        pkg_dir = filepath.parent
    
    parts = list(pkg_dir.parts)
    mcp_idx = None
    for i, p in enumerate(parts):
        if p == "mcp":
            mcp_idx = i
            break
    
    if mcp_idx is None:
        return None
    
    base_parts = parts[mcp_idx:]
    for _ in range(level - 1):
        if len(base_parts) > 1:
            base_parts = base_parts[:-1]
    
    if module_name:
        full_module = ".".join(base_parts) + "." + module_name
    else:
        full_module = ".".join(base_parts)
    
    return full_module

def check_imports_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        results["import_errors"].append(f"{filepath}: READ_ERROR {e}")
        return

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        results["syntax_errors"].append(f"{filepath}: SYNTAX_ERROR {e}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            module_name = node.module or ""
            full_module = get_module_path(filepath, node.level, module_name)
            
            if full_module is None:
                continue
            
            for alias in node.names:
                try:
                    mod = importlib.import_module(full_module)
                    if not hasattr(mod, alias.name):
                        all_attrs = [a for a in dir(mod) if not a.startswith('_')]
                        close = [a for a in all_attrs if alias.name.lower() in a.lower()]
                        results["missing_attrs"].append(
                            f"{Path(filepath).name}:{node.lineno} - "
                            f"from {full_module} import {alias.name} - "
                            f"NOT FOUND (similar: {close[:5]})"
                        )
                except ImportError as e:
                    results["import_errors"].append(
                        f"{Path(filepath).name}:{node.lineno} - "
                        f"from {full_module} import {alias.name} - "
                        f"IMPORT_ERROR: {str(e)[:80]}"
                    )
                except Exception as e:
                    results["import_errors"].append(
                        f"{Path(filepath).name}:{node.lineno} - "
                        f"from {full_module} import {alias.name} - "
                        f"ERROR: {type(e).__name__}: {str(e)[:80]}"
                    )

core_files = []
for p in MCP_DIR.rglob("*.py"):
    if p.name.startswith("test_") or p.name.startswith("_audit"):
        continue
    core_files.append(p)

core_files.sort()

print("=" * 60)
print("MCP系统完整排查 - 修正版")
print("=" * 60)

for fpath in core_files:
    check_imports_in_file(fpath)

print(f"\n--- 语法错误 ({len(results['syntax_errors'])}) ---")
for e in results["syntax_errors"]:
    print(f"  ❌ {e}")

print(f"\n--- Import错误 ({len(results['import_errors'])}) ---")
for e in results["import_errors"]:
    print(f"  ❌ {e}")

print(f"\n--- 属性不存在 ({len(results['missing_attrs'])}) ---")
for e in results["missing_attrs"]:
    print(f"  ❌ {e}")

print(f"\n--- 统计 ---")
print(f"  语法错误: {len(results['syntax_errors'])}")
print(f"  Import错误: {len(results['import_errors'])}")
print(f"  属性不存在: {len(results['missing_attrs'])}")
