# 原子：analyze_merge_direction（原 interface_chain_extractor.py 第 1673 行）
# 逻辑组：audit · 由 scripts/split_extractor.py 机械生成，勿手改。
# 依赖整理与模块间 import 属上层抽象（superpowers spec/plan 流程），本文件不保证独立运行。
from __future__ import annotations

def analyze_merge_direction(files: list) -> list:
    """状态机合并方向仲裁检查（规范 H）：

    在「双向同步/合并函数」中：
      (a) count_only_arbitration：用消息数量比较决定覆盖方向，但函数内完全没有
          版本/时间戳字段参与 → 数量相等而内容不同时无法识别新旧，旧数据可能
          反向覆盖新数据（加载旧会话/回滚的根因）。
      (b) arbiter_without_source：引用了版本字段但没参与「比较/决策」——空转。

    判定为合并函数的信号：函数体内出现 restore_messages / snapshot_messages /
    store.update / create_with_id 等「双向覆盖」操作。
    """
    issues: list[MergeDirectionIssue] = []

    def _has_merge_op(fn) -> bool:
        """合并函数必须「既有读回又有写入」：restore_messages/restore（从存储加载）
        + update/create_with_id（保存到存储）同时存在，才是双向覆盖仲裁场景。
        单向保存（如 create 时仅 store.update）不做方向仲裁，不应命中。
        """
        LOAD_OPS = ("restore_messages", "load_messages")
        SAVE_OPS = ("store.update", "create_with_id", "snapshot_messages",
                    "append_message", "merge_sessions")
        has_load = False
        has_save = False
        for sub in ast.walk(fn):
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Attribute):
                continue
            # 读回：xxx.restore_messages / xxx.load_messages
            if sub.func.attr in LOAD_OPS:
                has_load = True
            # 写入：store.update / xxx.create_with_id / snapshot_messages ...
            obj = getattr(sub.func.value, 'id', None) or getattr(sub.func.value, 'attr', '')
            if sub.func.attr in SAVE_OPS or f"{obj}.{sub.func.attr}" in SAVE_OPS:
                has_save = True
        return has_load and has_save

    for f in files:
        if not Path(f).exists():
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn = node
            if not _has_merge_op(fn):
                continue
            cmp_nodes = _collect_len_compares(fn)
            version_attrs = _collect_version_attrs(fn)
            has_content = _has_content_arbitration(fn)

            if cmp_nodes and not version_attrs and not has_content:
                issues.append(MergeDirectionIssue(
                    kind="count_only_arbitration", fn=fn.name, file=str(f),
                    line=cmp_nodes[0].lineno,
                    detail="用消息数量比较决定覆盖方向，但函数内无 updated_at/version/hash/seq "
                           "等版本字段参与仲裁——数量相等而内容不同时新旧无法识别，"
                           "旧存储可能反向覆盖新数据（加载旧会话的根因）。"
                           "建议引入 updated_at/版本号比较。"))
    return issues
