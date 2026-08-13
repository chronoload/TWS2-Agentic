"""
record 算子——第五算子。

用户在任何场景中主动输入自由文本，立即解析并生效。
所有 TS2 无法自动追踪的线下活动由此算子处理。

设计原则：
  - 不脱离当前场景（没有独立页面）
  - 任何场景中都可以使用（"按下 record → 弹出文本输入 → 立即解析"）
  - 不依赖 observe 或任何队列

数据流：
  User text → execute() → IngestOperator.parse()
    → 加固已有概念 → 创建种子概念
    → 生成 ActionRecord + Observation
"""

import uuid
import time
import logging
from typing import Optional
from ..models import EcosystemState, ActionRecord, Observation
from .base import BaseOperator, OperatorResult
from .ingest import IngestOperator

logger = logging.getLogger(__name__)


class RecordOperator(BaseOperator):
    """
    第五算子：在任意场景中记录自由文本

    使用方式：
      record = RecordOperator(state)
      result = await record.execute("今天和张老师讨论了退相干问题", scene="图书馆")

    效果：
      - 匹配到的已有概念 depth +0.3, freshness = 1.0
      - 未匹配的新术语创建为 depth=0.5 的概念种子
      - 自动生成 Observation 和 ActionRecord
    """

    def __init__(self, state: EcosystemState):
        super().__init__(state)
        self._ingest = IngestOperator(state)

    async def execute(self, content: str, scene: str = "",
                      in_place: bool = True, **kwargs) -> OperatorResult:
        """
        执行 record 操作

        Args:
            content:  自由文本（不限长度和格式）
            scene:    当前场景名称
            in_place: 是否原地执行（True=不跳转，False=跳转到新概念页面）

        Returns:
            OperatorResult: 包含加固和种子的结果
        """
        if not content or not content.strip():
            return OperatorResult(success=False, error="空文本")

        # 1. 文本解析
        parsed = self._ingest.parse(content, scene)

        # 2. 加固已有概念
        depth_gain = 0.3
        for cid in parsed.mentioned_concept_ids:
            concept = self.state.concepts.get(cid)
            if concept and not concept.is_fossilized:
                old_depth = concept.depth
                concept.depth = min(10.0, concept.depth + depth_gain)
                concept.freshness = 1.0
                concept.updated_at = time.time()

        # 3. 创建新种子
        new_ids = []
        for label in parsed.new_term_labels:
            concept = self._ingest.seed(label, source="record")
            if concept:
                new_ids.append(concept.id)

        # 4. 构建 depth_changes 字典
        depth_changes = {}
        for cid in parsed.mentioned_concept_ids[:10]:
            concept = self.state.concepts.get(cid)
            if concept:
                depth_changes[cid] = depth_gain  # 简化：所有匹配概念 gain 一致

        # 5. 生成 ActionRecord
        action = ActionRecord(
            id=uuid.uuid4().hex[:12],
            action_type="record",
            concept_ids=parsed.mentioned_concept_ids + new_ids,
            narrative=f"[record] {content[:100]}{'...' if len(content) > 100 else ''}",
            depth_changes=depth_changes,
            new_concept_ids=new_ids,
            scene=scene,
            timestamp=time.time(),
        )
        self.state.actions.append(action)

        # 6. 生成 Observation
        obs = Observation(
            id=uuid.uuid4().hex[:12],
            action_record_id=action.id,
            action_type="record",
            content=content,
            mentioned_concept_ids=parsed.mentioned_concept_ids,
            new_concept_labels=parsed.new_term_labels,
            timestamp=time.time(),
            narrative=parsed.narrative,
        )
        self.state.observations.append(obs)

        # 7. 更新玩家统计
        self.state.player.total_actions += 1
        self.state.player.total_concepts_encountered = len(self.state.concepts)

        return OperatorResult(
            success=True,
            action_record=action,
            narrative=f"record: {parsed.narrative}",
            new_concepts=new_ids,
            depth_changes=depth_changes,
        )

    def validate(self, content: str, **kwargs) -> Optional[str]:
        if not content or not content.strip():
            return "内容不能为空"
        if len(content) > 10000:
            return "内容过长（最多 10000 字符）"
        return None
