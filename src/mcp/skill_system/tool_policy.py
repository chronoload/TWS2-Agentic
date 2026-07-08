import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def filter_tools_by_skill_allowed_tools(
    tools: List[Dict[str, Any]],
    skills: List[Any],
) -> List[Dict[str, Any]]:
    any_declares = any(
        getattr(s, "allowed_tools", None) is not None for s in skills
    )

    if not any_declares:
        return tools

    allowed: Set[str] = set()
    for skill in skills:
        skill_tools = getattr(skill, "allowed_tools", None)
        if skill_tools:
            allowed.update(skill_tools)

    if not allowed:
        return tools

    filtered = [t for t in tools if t.get("name") in allowed or t.get("function", {}).get("name") in allowed]

    if len(filtered) < len(tools):
        logger.info(
            f"ToolPolicy: {len(tools)} tools → {len(filtered)} tools "
            f"(skills declared allowed_tools)"
        )

    return filtered
