"""
express 算子——表达（固化）。

将概念表达为外部产物（笔记、论文、代码）。
这是"熵减"操作——把头脑中的概念固化到文件系统中。

影响：
  - 被表达的概念 freshness↑ 50%
  - 所在线程 clarity↑
  - 产生 Artifact（文件系统中的持久产物）
  - TS2 交互：自动创建对应文件并打开编辑器
"""

import uuid
import time
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, List
from ..models import EcosystemState, Concept, Artifact, ActionRecord, Observation
from .base import BaseOperator, OperatorResult

logger = logging.getLogger(__name__)


_TARGET_EXTENSIONS = {
    "note": ".md",
    "paper": ".tex",
    "code": ".py",
    "diagram": ".md",
}


@dataclass
class ExpressResult(OperatorResult):
    artifact: Optional[Artifact] = None
    clarity_gained: float = 0.0


class ExpressOperator(BaseOperator):

    def validate(self, concept_ids, target_type: str = "note", **kwargs) -> Optional[str]:
        if not concept_ids:
            return "至少需要一个概念"
        for cid in concept_ids:
            c = self.state.concepts.get(cid)
            if not c:
                return f"概念不存在: {cid}"
            if c.is_fossilized:
                return f"概念已化石化: {c.label}"
        if target_type not in _TARGET_EXTENSIONS:
            return f"不支持的产物类型: {target_type}（支持: {', '.join(_TARGET_EXTENSIONS.keys())}）"
        return None

    async def execute(self, concept_ids, target_type: str = "note",
                      thread_id: str = "", **kwargs) -> ExpressResult:
        concepts = [self.state.concepts.get(cid) for cid in concept_ids]
        concepts = [c for c in concepts if c and not c.is_fossilized]
        if not concepts:
            return ExpressResult(success=False, error="没有可表达的概念")

        # 生成产物
        content = self._compose_content(concepts, target_type)
        file_path = self._create_file(content, target_type, concepts)
        title = " × ".join(c.label for c in concepts[:3])

        artifact = Artifact(
            id=uuid.uuid4().hex[:12],
            artifact_type=target_type,
            title=title,
            file_path=file_path,
            concept_ids=[c.id for c in concepts],
            thread_id=thread_id or "",
            created_at=time.time(),
            word_count=len(content),
        )
        self.state.artifacts[artifact.id] = artifact

        # 更新概念 freshness
        freshness_changes = {}
        for c in concepts:
            old = c.freshness
            c.freshness = min(1.0, c.freshness + 0.5)
            c.updated_at = time.time()
            freshness_changes[c.id] = c.freshness - old

        # 线程清晰度提升
        clarity_gained = 0.0
        if thread_id:
            thread = self.state.threads.get(thread_id)
            if thread and not thread.is_archived:
                old = thread.clarity
                thread.clarity = min(1.0, thread.clarity + 0.15)
                thread.updated_at = time.time()
                clarity_gained = thread.clarity - old

        action = ActionRecord(
            id=uuid.uuid4().hex[:12],
            action_type="express",
            concept_ids=[c.id for c in concepts],
            narrative=f"表达: {title} ({target_type})",
            depth_changes={},
            freshness_changes=freshness_changes,
            timestamp=time.time(),
        )
        self.state.actions.append(action)

        obs = Observation(
            id=uuid.uuid4().hex[:12],
            action_record_id=action.id,
            action_type="express",
            content=f"创建 {target_type}: {title}",
            mentioned_concept_ids=[c.id for c in concepts],
            timestamp=time.time(),
            narrative=f"将 {len(concepts)} 个概念表达为 {target_type}",
        )
        self.state.observations.append(obs)
        self.state.player.total_actions += 1
        self.state.player.total_artifacts_created += 1

        return ExpressResult(
            success=True,
            action_record=action,
            narrative=f"表达完成: {file_path}",
            depth_changes={},
            freshness_changes=freshness_changes,
            artifact=artifact,
            clarity_gained=clarity_gained,
        )

    def _compose_content(self, concepts: List[Concept], target_type: str) -> str:
        """根据概念和类型生成文件内容"""
        labels = [c.label for c in concepts]
        title = " × ".join(labels)
        now = time.strftime("%Y-%m-%d %H:%M")

        parts = [f"# {title}\n", f"生成时间: {now}\n", "---\n"]

        if target_type == "note":
            parts.append(f"\n## 摘要\n\n")
            parts.append("## 概念\n\n")
            for c in concepts:
                parents = [self.state.concepts.get(pid) for pid in c.parent_ids]
                parent_str = ", ".join(p.label for p in parents if p) if c.parent_ids else "无"
                parts.append(f"- **{c.label}**: depth={c.depth:.1f}, freshness={c.freshness:.2f}\n")
                if c.source_refs:
                    parts.append(f"  - 来源: {c.source_refs[0].label}\n")
            parts.append("\n## 关联\n\n")
            for c in concepts:
                for rel_id, strength in c.related_ids.items():
                    rel = self.state.concepts.get(rel_id)
                    if rel:
                        parts.append(f"- 与 {rel.label} 的关联度: {strength:.2f}\n")

        elif target_type == "paper":
            parts.append(f"\\title{{{title}}}\n\\date{{{now}}}\n\\begin{{document}}\n\\maketitle\n\n")
            parts.append("\\section{概念}\n\n")
            for c in concepts:
                parts.append(f"\\subsection{{{c.label}}}\nDepth: {c.depth:.1f}\n\n")
            parts.append("\\end{document}\n")

        else:
            parts.append(f"\n# {title}\n\n")
            for c in concepts:
                parts.append(f"- {c.label}: depth {c.depth:.1f}\n")

        return "".join(parts)

    def _create_file(self, content: str, target_type: str,
                     concepts: List[Concept]) -> str:
        """写入文件系统，返回路径"""
        ext = _TARGET_EXTENSIONS.get(target_type, ".md")
        safe_name = "_".join(c.label for c in concepts[:2]).replace(" ", "_")[:60]
        filename = f"{safe_name}{ext}"

        # 优先写入 TS2 Notes 目录
        base_dir = os.path.join(os.getcwd(), "Notes")
        if not os.path.exists(base_dir):
            base_dir = os.getcwd()
        file_path = os.path.join(base_dir, filename)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Express created file: {file_path}")
        except Exception as e:
            logger.warning(f"Express file write failed: {e}")
            file_path = os.path.join(os.getcwd(), filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        return file_path
