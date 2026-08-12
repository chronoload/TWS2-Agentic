"""patch.rules：自演化补丁规则表（缺陷 kind → 生成器策略）。
规则外置可演进（与 ChainStrategy 同哲学）：默认规则内置，AuditTask 可覆盖。
"""
from __future__ import annotations

# 默认规则：缺陷 kind → {strategy, 自动插入的 TODO 说明}
# strategy 对应 patch.generator 命名空间中的生成器函数
DEFAULT_PATCH_RULES: dict = {
    "clear_without_set": {"strategy": "insert_set_after_clear",
                          "auto_fix": True,
                          "detail": "Event 标志 clear() 后无 set() 恢复 → 在函数内补 set()"},
    "stale_cache": {"strategy": "insert_reset_comment",
                    "auto_fix": False,
                    "detail": "跨会话缓存未重置 → 标注待人工确认重置点"},
    "hardcoded_key": {"strategy": "insert_env_todo",
                      "auto_fix": False,
                      "detail": "硬编码密钥/配置 → 标注外置环境变量 TODO"},
    "hardcoded_secret": {"strategy": "insert_env_todo",
                         "auto_fix": False,
                         "detail": "硬编码密钥/配置 → 标注外置环境变量 TODO"},
    "hardcoded_url": {"strategy": "insert_env_todo",
                      "auto_fix": False,
                      "detail": "硬编码 URL → 标注外置配置 TODO"},
    "hardcoded_port": {"strategy": "insert_env_todo",
                       "auto_fix": False,
                       "detail": "硬编码端口 → 标注外置配置 TODO"},
    "hardcoded_path": {"strategy": "insert_todo_comment",
                       "auto_fix": False,
                       "detail": "硬编码路径 → 标注外置配置 TODO"},
    "no_assignment": {"strategy": "insert_defuse_comment",
                      "auto_fix": False,
                      "detail": "getattr 默认值恒为默认 → 标注赋值点待确认"},
    "external_contract": {"strategy": "insert_defuse_comment",
                          "auto_fix": False,
                          "detail": "外部/库对象属性读取 → 标注待人工核查"},
    "missing_behavior": {"strategy": "insert_entry_comment",
                         "auto_fix": False,
                         "detail": "入口缺 must-call 副作用 → 标注入口待补"},
    "count_only_arbitration": {"strategy": "insert_merge_comment",
                               "auto_fix": False,
                               "detail": "数量仲裁无版本字段 → 标注待引入版本仲裁"},
    "cross_namespace_key": {"strategy": "insert_guard_comment",
                            "auto_fix": False,
                            "detail": "跨命名空间 key 误用 → 标注守卫待补"},
    "unguarded_key_consumer": {"strategy": "insert_guard_comment",
                               "auto_fix": False,
                               "detail": "消费者无命名空间守卫 → 标注守卫待补"},
}


def strategy_for(kind: str, rules: dict = None) -> dict:
    """缺陷 kind → 规则（rules 覆盖默认）。"""
    merged = {**DEFAULT_PATCH_RULES, **(rules or {})}
    return merged.get(kind) or {"strategy": "insert_todo_comment", "auto_fix": False,
                                "detail": "未匹配规则 → 仅标注"}
