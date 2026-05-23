#!/usr/bin/env python3
"""
TS2-OpenSource 硬编码检测脚本
检测 src 目录下所有硬编码的路径、URL、密钥等
"""
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"

class HardcodedChecker:
    def __init__(self, src_dir):
        self.src_dir = Path(src_dir)
        self.issues = []
        self.ignored_patterns = [
            r'__file__', r'__name__', r'__doc__',
            r'\.py$', r'\.pyc$',
            r'TK\s*=\s*["\']Tk', r'tkinter',
            r'def\s+\w+', r'class\s+\w+',
            r'#.*', r'""".*?"""', r"'''.*?'''",
        ]
        
    def check(self):
        """检查所有Python文件"""
        print(f"检查目录: {self.src_dir}\n")
        
        for py_file in self.src_dir.rglob("*.py"):
            self._check_file(py_file)
            
        self._check_json_files()
        self._check_md_files()
        
    def _check_file(self, py_file):
        """检查单个Python文件"""
        rel_path = py_file.relative_to(self.src_dir)
        
        try:
            content = py_file.read_text(encoding='utf-8')
            lines = content.split('\n')
        except:
            return
            
        self._check_absolute_paths(content, rel_path, lines)
        self._check_urls(content, rel_path, lines)
        self._check_api_keys(content, rel_path, lines)
        self._check_credentials(content, rel_path, lines)
        self._check_hardcoded_db_paths(content, rel_path, lines)
        
    def _check_absolute_paths(self, content, file_path, lines):
        """检测绝对路径"""
        patterns = [
            (r'["\'][C-Z]:\\[\w\\]+', 'Windows绝对路径'),
            (r'["\']\/[\w\/]+(?<!\/src)(?<!\/tests)', 'Unix绝对路径'),
            (r'["\']\/home\/\w+', 'Linux主目录路径'),
            (r'["\']\/Users\/\w+', 'macOS主目录路径'),
            (r'["\']C:\\[\w\\]+', 'Windows根目录'),
        ]
        
        for pattern, desc in patterns:
            for i, line in enumerate(lines, 1):
                matches = re.findall(pattern, line, re.IGNORECASE)
                if matches and not self._is_ignored(line):
                    for match in matches:
                        if not self._is_ignorable_path(match):
                            self.issues.append({
                                'file': str(file_path),
                                'line': i,
                                'type': '绝对路径',
                                'desc': desc,
                                'content': line.strip()[:80],
                                'value': match
                            })
                            
    def _check_urls(self, content, file_path, lines):
        """检测硬编码的URL"""
        url_pattern = r'["\'](https?://[^\s"\']+)["\']'
        
        for i, line in enumerate(lines, 1):
            if 'import' in line or 'from' in line:
                continue
            matches = re.findall(url_pattern, line, re.IGNORECASE)
            for match in matches:
                if not self._is_ignorable_url(match):
                    self.issues.append({
                        'file': str(file_path),
                        'line': i,
                        'type': '硬编码URL',
                        'desc': 'API/服务地址',
                        'content': line.strip()[:80],
                        'value': match
                    })
                    
    def _check_api_keys(self, content, file_path, lines):
        """检测API密钥和令牌"""
        patterns = [
            (r'["\'][a-zA-Z0-9_-]{20,}["\']', '可能的API密钥'),
            (r'(?i)(api[_-]?key|apikey|secret[_-]?key)["\']?\s*[:=]\s*["\'][^"\']+["\']', 'API密钥声明'),
            (r'(?i)(token|auth)["\']?\s*[:=]\s*["\'][^"\']+["\']', '认证令牌'),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, desc in patterns:
                if re.search(pattern, line):
                    if not self._is_ignored(line):
                        self.issues.append({
                            'file': str(file_path),
                            'line': i,
                            'type': '密钥/令牌',
                            'desc': desc,
                            'content': line.strip()[:80],
                            'value': re.findall(pattern, line)[0] if re.findall(pattern, line) else ''
                        })
                        
    def _check_credentials(self, content, file_path, lines):
        """检测用户名密码"""
        patterns = [
            (r'(?i)(username|user|login)["\']?\s*[:=]\s*["\'][^"\']+["\']', '用户名'),
            (r'(?i)(password|passwd|pwd)["\']?\s*[:=]\s*["\'][^"\']+["\']', '密码'),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, desc in patterns:
                if re.search(pattern, line):
                    if not self._is_ignored(line):
                        self.issues.append({
                            'file': str(file_path),
                            'line': i,
                            'type': '凭证',
                            'desc': desc,
                            'content': line.strip()[:80],
                            'value': ''
                        })
                        
    def _check_hardcoded_db_paths(self, content, file_path, lines):
        """检测硬编码的数据库路径"""
        db_patterns = [
            r'["\'].*\.db["\']',
            r'["\'].*\.sqlite3?["\']',
            r'["\'].*\.sqlite?["\']',
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern in db_patterns:
                matches = re.findall(pattern, line)
                for match in matches:
                    if not self._is_ignored(line):
                        self.issues.append({
                            'file': str(file_path),
                            'line': i,
                            'type': '数据库路径',
                            'desc': '硬编码数据库文件',
                            'content': line.strip()[:80],
                            'value': match
                        })
                        
    def _check_json_files(self):
        """检查JSON配置文件"""
        print("\n检查JSON配置文件...")
        for json_file in self.src_dir.rglob("*.json"):
            try:
                content = json_file.read_text(encoding='utf-8')
                import json
                data = json.loads(content)
                self._check_json_for_secrets(data, json_file)
            except:
                pass
                
    def _check_json_for_secrets(self, data, file_path, path=""):
        """递归检查JSON中的密钥"""
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                if any(k in key.lower() for k in ['key', 'token', 'secret', 'password', 'auth']):
                    self.issues.append({
                        'file': str(file_path.relative_to(self.src_dir)),
                        'line': 0,
                        'type': '配置中的密钥',
                        'desc': f'JSON路径: {new_path}',
                        'content': f'键名包含敏感词: {key}',
                        'value': str(value)[:50] + '...' if len(str(value)) > 50 else str(value)
                    })
                elif isinstance(value, (dict, list)):
                    self._check_json_for_secrets(value, file_path, new_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_json_for_secrets(item, file_path, f"{path}[{i}]")
                
    def _check_md_files(self):
        """检查Markdown文档"""
        for md_file in self.src_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if re.search(r'https://.*(?:key|token|secret|password)[^/\s]*', line, re.I):
                        self.issues.append({
                            'file': str(md_file.relative_to(self.src_dir)),
                            'line': i,
                            'type': '文档中的密钥',
                            'desc': 'Markdown中的URL可能含密钥',
                            'content': line.strip()[:80],
                            'value': ''
                        })
            except:
                pass
                
    def _is_ignored(self, line):
        """检查是否应忽略此行"""
        for pattern in self.ignored_patterns:
            if re.search(pattern, line):
                return True
        return False
        
    def _is_ignorable_path(self, path):
        """检查路径是否可忽略"""
        ignorable = ['__file__', 'sys.executable', 'Path(__file__)']
        for ign in ignorable:
            if ign in path:
                return True
        return False
        
    def _is_ignorable_url(self, url):
        """检查URL是否可忽略"""
        ignorable = ['example.com', 'localhost', '127.0.0.1', 'docs.python.org']
        for ign in ignorable:
            if ign in url.lower():
                return True
        return False
        
    def generate_report(self):
        """生成检测报告"""
        print("\n" + "="*80)
        print("TS2-OpenSource 硬编码检测报告")
        print("="*80)
        
        if not self.issues:
            print("\n✓ 未检测到硬编码问题！")
            return
            
        by_type = {}
        for issue in self.issues:
            issue_type = issue['type']
            if issue_type not in by_type:
                by_type[issue_type] = []
            by_type[issue_type].append(issue)
            
        print(f"\n发现 {len(self.issues)} 个潜在问题：\n")
        
        for issue_type, issues in sorted(by_type.items()):
            print(f"\n【{issue_type}】({len(issues)}个)")
            print("-"*80)
            
            for issue in issues:
                file_rel = Path(issue['file']).relative_to(self.src_dir) if self.src_dir in Path(issue['file']).parents else issue['file']
                print(f"\n  文件: {file_rel}", end="")
                if issue['line'] > 0:
                    print(f":{issue['line']}", end="")
                print(f"\n  描述: {issue['desc']}")
                print(f"  内容: {issue['content']}")
                if issue['value']:
                    print(f"  值: {issue['value']}")
                    
        print("\n" + "="*80)
        print("建议")
        print("="*80)
        print("""
1. 绝对路径 → 使用 Path(__file__).parent 或相对路径
2. 硬编码URL → 移至配置文件或环境变量
3. API密钥 → 使用环境变量或密钥管理服务
4. 用户名密码 → 绝对不要硬编码！
""")
        
def main():
    print("TS2-OpenSource 硬编码检测工具")
    print("="*80)
    
    checker = HardcodedChecker(SRC_DIR)
    checker.check()
    checker.generate_report()
    
    print("\n" + "="*80)
    print("检测完成")
    print("="*80)

if __name__ == "__main__":
    main()
