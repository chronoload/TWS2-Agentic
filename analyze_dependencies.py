#!/usr/bin/env python3
"""
TS2-OpenSource 依赖分析脚本
分析 src 目录下所有 Python 文件的依赖关系
"""
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"

class DependencyAnalyzer:
    def __init__(self, src_dir):
        self.src_dir = Path(src_dir)
        self.modules = {}
        self.dependencies = defaultdict(set)
        self.external_deps = set()
        
    def scan_files(self):
        """扫描所有Python文件"""
        for py_file in self.src_dir.rglob("*.py"):
            rel_path = py_file.relative_to(self.src_dir)
            module_name = self._path_to_module(rel_path)
            self.modules[module_name] = py_file
        print(f"扫描到 {len(self.modules)} 个Python文件")
        
    def _path_to_module(self, path):
        """将路径转换为模块名"""
        parts = list(path.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts) if parts else ""
    
    def analyze_imports(self):
        """分析所有文件的导入"""
        for module_name, py_file in self.modules.items():
            try:
                content = py_file.read_text(encoding='utf-8')
            except:
                continue
            
            content = re.sub(r'\\\n', '', content)
            content = re.sub(r'\([^)]*\)', lambda m: m.group(0).replace('\n', ' '), content)
            
            import_pattern = re.compile(r'^from (\.[\w.]+|\w+) import', re.MULTILINE)
            
            for match in import_pattern.finditer(content):
                imported = match.group(1)
                if imported.startswith('.'):
                    parts = imported.strip('.').split('.')
                    current_parts = module_name.split('.')
                    parent = current_parts[:-1] if len(current_parts) > 1 else []
                    resolved = parent + parts
                    imported = '.'.join(resolved)
                else:
                    pass
                
                if imported in self.modules:
                    self.dependencies[module_name].add(imported)
                elif imported not in ('os', 'sys', 're', 'json', 'tkinter', 'datetime', 
                                     'pathlib', 'typing', 'threading', 'sqlite3', 'uuid',
                                     'hashlib', 'webbrowser', 'platform', 'subprocess',
                                     'collections', 'numpy', 'matplotlib', 'traceback',
                                     'dataclasses', 'functools', 'copy', 'pickle',
                                     'time', 'shutil', 'io', 'gc', 'weakref',
                                     'configparser', 'urllib', 'http', 'socket',
                                     'email', 'html', 'xml', 'csv', 'zipfile',
                                     'tarfile', 'gzip', 'logging', 'warnings',
                                     'tempfile', 'shelve', 'base64', 'binascii',
                                     'ast', 'dis', 'inspect', 'linecache', 'tokenize',
                                     'abc', 'enum', 'concurrent'):
                    self.external_deps.add(imported)
                    
    def generate_report(self):
        """生成依赖报告"""
        print("\n" + "="*70)
        print("TS2-OpenSource 依赖分析报告")
        print("="*70)
        
        print("\n【1】模块列表")
        print("-"*70)
        for module in sorted(self.modules.keys()):
            print(f"  {module}")
            
        print("\n【2】模块依赖关系")
        print("-"*70)
        for module in sorted(self.dependencies.keys()):
            deps = sorted(self.dependencies[module])
            if deps:
                print(f"\n  {module}")
                for dep in deps:
                    print(f"    └─ {dep}")
                    
        print("\n【3】外部依赖（非标准库）")
        print("-"*70)
        if self.external_deps:
            for dep in sorted(self.external_deps):
                print(f"  - {dep}")
        else:
            print("  无外部依赖")
            
        print("\n【4】依赖树（MCP系统）")
        print("-"*70)
        mcp_modules = [m for m in self.modules.keys() if m.startswith('mcp')]
        for module in sorted(mcp_modules):
            deps = [d for d in self.dependencies[module] if d.startswith('mcp')]
            if deps:
                print(f"  {module}")
                for dep in deps:
                    print(f"    └─ {dep}")
                    
        print("\n【5】入口文件依赖链")
        print("-"*70)
        entry_points = ['course_tracker', 'md_builder', 'tex_to_utf8']
        for entry in entry_points:
            self._print_dependency_tree(entry, "", set())
            
    def _print_dependency_tree(self, module, prefix, visited):
        """递归打印依赖树"""
        if module in visited:
            print(f"{prefix}└─ {module} (循环引用)")
            return
        visited.add(module)
        
        deps = sorted(self.dependencies.get(module, []))
        if not deps:
            print(f"{prefix}└─ {module}")
            return
            
        for i, dep in enumerate(deps):
            is_last = (i == len(deps) - 1)
            connector = "└─" if is_last else "├─"
            new_prefix = prefix + "   " if is_last else prefix + "│  "
            print(f"{prefix}{connector} {module}")
            self._print_dependency_tree(dep, new_prefix, visited.copy())
            
    def check_circular_deps(self):
        """检查循环依赖"""
        print("\n【6】循环依赖检测")
        print("-"*70)
        
        def find_cycle(module, path):
            if module in path:
                cycle_start = path.index(module)
                cycle = path[cycle_start:] + [module]
                print(f"  发现循环: {' -> '.join(cycle)}")
                return True
            for dep in self.dependencies.get(module, []):
                if find_cycle(dep, path + [module]):
                    return True
            return False
            
        for module in self.modules:
            find_cycle(module, [])
            
        print("  检测完成")
        
def main():
    print("TS2-OpenSource 依赖分析工具")
    print("="*70)
    
    analyzer = DependencyAnalyzer(SRC_DIR)
    analyzer.scan_files()
    analyzer.analyze_imports()
    analyzer.generate_report()
    analyzer.check_circular_deps()
    
    print("\n" + "="*70)
    print("分析完成")
    print("="*70)

if __name__ == "__main__":
    main()
