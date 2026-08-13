import logging
from typing import Any, Dict, List, Optional

from .base import AgentMiddleware, MiddlewareContext, MiddlewareResult

logger = logging.getLogger(__name__)


class DynamicContextMiddleware(AgentMiddleware):
    """动态上下文中间件（不再注入伪消息）

    历史版本会把 `<system-reminder>`（日期/记忆）包装成 role=user 伪消息插入
    消息流，污染真实用户消息——这是前端收到 `[7] role=user content='<system-reminder>...'`
    的根源。

    该能力已迁移到 system 消息注入：
    - 日期 → ContextProvider Others 层（context_provider.py collect_others 环境信息段落）
    - 记忆 → agent.py MEMORY_CONTEXT 段落

    before_agent 保持空实现仅作占位，不修改消息，避免破坏 middleware 链注册结构。
    """

    name = "dynamic_context"
    order = 9

    def before_agent(self, messages: List[Dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        # 不再生成 role=user 伪消息：日期/记忆均由 system 消息注入（见类注释）
        return MiddlewareResult()
