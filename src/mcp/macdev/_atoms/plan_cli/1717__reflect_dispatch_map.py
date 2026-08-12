# 原子：_reflect_dispatch_map（原 plan_cli.py 第 1717 行）
# 由 split_atoms.py 机械生成，勿手改。
from __future__ import annotations

def _reflect_dispatch_map() -> list:
    """反射提取命令→处理函数映射（从 _dispatch 的 if/return 链解析）。"""
    import inspect as _inspect
    mapping = []
    try:
        src = _inspect.getsource(_dispatch)
        for m in re.finditer(r'if\s+args\.cmd\s*==\s*["\'](\w+)["\']', src):
            cmd = m.group(1)
            block_start = m.end()
            next_if = re.search(r'\n\s+if\s+args\.cmd', src[block_start:])
            block = src[block_start:block_start + (next_if.start() if next_if else 500)]
            for sm in re.finditer(r'if\s+args\.(\w+)\s*==\s*["\'](\w+)["\']', block):
                sub_cmd = sm.group(2)
                inner_block_start = sm.end()
                next_inner = re.search(r'\n\s+if\s+args\.', block[inner_block_start:])
                inner_block = block[inner_block_start:inner_block_start + (next_inner.start() if next_inner else 300)]
                for fm in re.finditer(r'return\s+(\w+(?:\.\w+)*)\(args\)', inner_block):
                    mapping.append((cmd, sub_cmd, fm.group(1)))
            if not any(m[0] == cmd for m in mapping):
                for fm in re.finditer(r'return\s+(\w+(?:\.\w+)*)\(args\)', block):
                    mapping.append((cmd, '', fm.group(1)))
    except Exception:
        pass
    return mapping
