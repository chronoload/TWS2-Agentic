"""算子基类"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from ..models import ActionRecord, EcosystemState


@dataclass
class OperatorResult:
    """
    算子的标准返回格式
    """
    success: bool = True
    action_record: Optional[ActionRecord] = None
    narrative: str = ""
    new_concepts: List[str] = field(default_factory=list)   # 新概念 IDs
    depth_changes: Dict[str, float] = field(default_factory=dict)   # concept_id → delta
    freshness_changes: Dict[str, float] = field(default_factory=dict)
    entropy_changes: Dict[str, float] = field(default_factory=dict)
    error: str = ""


class BaseOperator:
    """所有算子的父类"""

    def __init__(self, state: EcosystemState):
        self.state = state

    def validate(self, **kwargs) -> Optional[str]:
        """校验输入，返回 error 字符串或 None"""
        return None

    async def execute(self, **kwargs) -> OperatorResult:
        """执行算子"""
        raise NotImplementedError
