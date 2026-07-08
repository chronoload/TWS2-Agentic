"""
SaberDecayMiddleware — Agent 建议职能衰减中间件

在 Agent before_agent 阶段检查 I(P) = I₀·e^(-kP)：
- I(P) < 0.1 → STOP（Agent 已退役，不再生成建议）
- 0.1 ≤ I(P) < 0.5 → MODIFY（半衰减状态，注入提示）
- I(P) ≥ 0.5 → CONTINUE（正常处理）

依赖 SaberStore.get_proficiency(plan_id) 计算熟练度 P。
"""
from __future__ import annotations
from typing import Any

from mcp.middleware.base import (
    AgentMiddleware, MiddlewareResult, MiddlewareAction, MiddlewareContext,
)


class SaberDecayMiddleware(AgentMiddleware):
    name: str = "saber_decay"
    order: int = 50

    def __init__(self, get_proficiency, compute_intensity, retirement_threshold: float = 0.1):
        self._get_proficiency = get_proficiency
        self._compute_intensity = compute_intensity
        self._retirement_threshold = retirement_threshold

    def before_agent(self, messages: list[dict[str, Any]], context: MiddlewareContext) -> MiddlewareResult:
        plan_id = context.extra.get("plan_id", "")
        if not plan_id:
            return MiddlewareResult()

        proficiency = self._get_proficiency(plan_id)
        intensity = self._compute_intensity(proficiency)

        if intensity < self._retirement_threshold:
            return MiddlewareResult(
                action=MiddlewareAction.STOP,
                reason=f"agent_retired: I(P)={intensity:.3f} < threshold={self._retirement_threshold}",
                metadata={"intensity": intensity, "proficiency": proficiency, "retired": True},
            )

        if intensity < 0.5:
            return MiddlewareResult(
                action=MiddlewareAction.MODIFY,
                reason=f"semi_retired: I(P)={intensity:.3f}",
                metadata={"intensity": intensity, "proficiency": proficiency, "semi_retired": True},
                modified_messages=messages + [
                    {
                        "role": "system",
                        "content": (
                            f"[SaberSystem] Agent 建议职能已进入半衰减状态（介入度 {intensity:.1%}）。"
                            "请优先鼓励用户自主决策，仅在必要时提供引导。"
                        ),
                    }
                ],
            )

        return MiddlewareResult()
