"""patch.generators：修复插件（PatchPlugin）——从审计缺陷生成补丁脚本。

与工厂平级哲学：每个修复策略是一个 PatchPlugin 子类（继承统一抽象接口），
被 `Registry.discover()` 扫描捕捉（namespace=patch.generator），按名装配。
生成的是**固化补丁脚本**（产物，不改原文件）；应用是独立的显式操作。

- auto_fix=True 的插件做确定性改造（如 Event 标志 clear 后补 set()）；
- 其余生成「行尾 TODO 标注」脚本——固化审查意图，不盲改（领域判断留给人工）。
"""
from __future__ import annotations
import ast
from pathlib import Path
from ..core.plugin import Plugin
from .model import PatchScript
from .rules import strategy_for


def _issue_id(issue: dict, kind: str) -> str:
    return f"{kind}:{issue.get('file', '')}:{issue.get('line', 0)}:{issue.get('attr') or issue.get('entry') or issue.get('fn') or 'x'}"


def _line_text(path: Path, lineno: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
    except Exception:
        return ""


def _comment_ops(path: Path, lineno: int, comment: str) -> list:
    """在指定行尾追加 TODO 注释（replace 操作，幂等）。"""
    text = _line_text(path, lineno)
    if not text:
        return []
    if "TODO(macdev)" in text:
        return []
    return [{"op": "replace", "line": lineno, "text": f"{text}  # TODO(macdev): {comment}"}]


def _find_clear_call(path: Path, attr: str, lineno: int) -> dict:
    """AST 定位 Event 标志 clear() 调用：返回 {line, indent}。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "clear" and node.lineno == lineno:
            if isinstance(f.value, ast.Attribute) and f.value.attr == attr:
                for p in ast.walk(tree):
                    if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and node.lineno >= p.lineno \
                            and node.lineno <= (p.end_lineno or p.lineno):
                        indent = "    " if p.col_offset == 0 else "        "
                        return {"line": node.lineno, "indent": indent}
    return {}


class PatchPlugin(Plugin):
    """修复插件抽象接口（namespace=patch.generator）。"""
    namespace = "patch.generator"
    auto_fix: bool = False          # True = 确定性自动修复；False = 仅标注

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        raise NotImplementedError

    def build(self, issue: dict, root: Path, rule: dict,
              operations: list, title: str) -> PatchScript:
        return PatchScript(id=_issue_id(issue, issue["kind"]), kind=issue["kind"],
                           file=issue.get("file", ""), strategy=self.name,
                           title=title, detail=rule.get("detail", ""),
                           operations=operations)

    def _line_comment(self, issue: dict, root: Path, rule: dict, comment: str) -> PatchScript:
        """行尾标注补丁（自动修复不可行的缺陷统一走此策略）。"""
        file = issue.get("file", "")
        ops = _comment_ops(root / file, int(issue.get("line", 0) or 0), comment)
        if not ops:
            ops = [{"op": "noop", "line": int(issue.get("line", 0) or 0), "text": ""}]
        return self.build(issue, root, rule, ops, comment[:40])


class InsertSetAfterClear(PatchPlugin):
    """自动修复：Event 标志 clear() 后补 set() 恢复（AST 定位 + 插入行）。"""
    name = "insert_set_after_clear"
    auto_fix = True

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        file = issue.get("file", "")
        path = root / file
        attr = issue.get("attr", "")
        ops: list = []
        info = _find_clear_call(path, attr, int(issue.get("line", 0) or 0))
        if info:
            ops.append({"op": "insert", "line": info["line"] + 1,
                        "text": f"{info['indent']}self.{attr}.set()  # macdev 自演化补丁：clear 后恢复标志"})
        if not ops:
            ops = _comment_ops(path, int(issue.get("line", 0) or 0),
                               f"Event 标志 {attr} clear 后需 set() 恢复（自演化建议）")
        return self.build(issue, root, rule, ops, f"恢复 Event 标志 {attr}")


class EnvTodoPatch(PatchPlugin):
    """标注：硬编码配置外置环境变量 TODO。"""
    name = "insert_env_todo"
    _what = {"hardcoded_key": "密钥", "hardcoded_secret": "密钥", "hardcoded_url": "URL",
             "hardcoded_port": "端口", "hardcoded_path": "路径"}

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        what = self._what.get(issue["kind"], "配置")
        return self._line_comment(issue, root, rule,
                                  f"硬编码{what}建议外置到环境变量/配置文件（自演化建议）")


class DefuseCommentPatch(PatchPlugin):
    name = "insert_defuse_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        return self._line_comment(issue, root, rule,
                                  "getattr 默认值可能恒为默认，需确认赋值点（自演化建议）")


class EntryCommentPatch(PatchPlugin):
    name = "insert_entry_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        missing = issue.get("missing") or []
        return self._line_comment(issue, root, rule,
                                  f"入口需补 must-call 副作用：{'、'.join(missing)}（自演化建议）")


class MergeCommentPatch(PatchPlugin):
    name = "insert_merge_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        return self._line_comment(issue, root, rule,
                                  "数量仲裁需引入版本/时间戳字段（自演化建议）")


class GuardCommentPatch(PatchPlugin):
    name = "insert_guard_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        return self._line_comment(issue, root, rule,
                                  "存储消费点需补命名空间前缀守卫（自演化建议）")


class ResetCommentPatch(PatchPlugin):
    name = "insert_reset_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        return self._line_comment(issue, root, rule,
                                  "跨会话缓存需在 _instance_id 变更处重置（自演化建议）")


class TodoCommentPatch(PatchPlugin):
    name = "insert_todo_comment"

    def generate(self, issue: dict, root: Path, rule: dict) -> PatchScript:
        return self._line_comment(issue, root, rule, rule.get("detail", "待人工处理（自演化标注）"))


# 策略名 → 插件类（由 patch.register / Registry.discover 装配）
GENERATORS = {
    "insert_set_after_clear": InsertSetAfterClear,
    "insert_env_todo": EnvTodoPatch,
    "insert_defuse_comment": DefuseCommentPatch,
    "insert_entry_comment": EntryCommentPatch,
    "insert_merge_comment": MergeCommentPatch,
    "insert_guard_comment": GuardCommentPatch,
    "insert_reset_comment": ResetCommentPatch,
    "insert_todo_comment": TodoCommentPatch,
}


def build_patch(issue: dict, root: Path, rules: dict = None,
                generator=None) -> PatchScript:
    """缺陷 issue → 补丁脚本。generator 可由 Registry.create("patch.generator", strategy)
    提供（工厂装配）；缺省走策略名映射。"""
    rule = strategy_for(issue["kind"], rules)
    if generator is not None:
        return generator.generate(issue, root, rule)
    cls = GENERATORS.get(rule["strategy"], TodoCommentPatch)
    return cls().generate(issue, root, rule)
