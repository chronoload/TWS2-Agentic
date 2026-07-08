import re
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# === 黑名单关键词：这些类型的内容不应被当作技能创建 ===
_BLACKLIST_PATTERNS = [
    # 抱怨/情绪表达
    r'怎么.*参数.*填.*明白',
    r'怎么.*不行',
    r'为什.*不好用',
    r'不是.*继续.*修复',
    r'怎么.*这么.*慢',
    r'怎么.*这么.*差',
    r'不好用',
    r'不行',
    r'不对',
    r'错误',
    r'失败',
    r'崩',
    r'死机',
    r'垃圾',
    r'智障',
    # 测试/调试
    r'测试',
    r'试一下',
    r'试试',
    r'debug',
    r'调试',
    r'排查',
    # 纯疑问句（非技能请求）
    r'你能.*吗',
    r'你会.*吗',
    r'你.*什么',
    r'谁.*',
    r'怎么.*\?',
    # 太短或无意义
    r'^\s*$',
    r'^[.\s!?]+$',
    r'^[a-z]$',
]


# === 白名单关键词：出现这些词更可能是一个真正的技能请求 ===
_WHITELIST_PATTERNS = [
    r'创建.*技能',
    r'新建.*技能',
    r'保存.*为技能',
    r'保存.*流程',
    r'记住.*步骤',
    r'把这个.*保存',
    r'把这个.*做成',
    r'自动化',
    r'以后.*这样',
    r'每次.*这样',
    r'快捷操作',
    r'一键',
]

# 技能名黑名单（已知的垃圾技能名模式）
_SKILL_NAME_BLACKLIST = [
    r'^auto_skill',
    r'^_v\d+$',
    r'^test',
    r'^debug',
    r'^trash',
    r'^垃圾',
]


@dataclass
class SkillCreationRequest:
    trigger: str
    task_description: str
    tools_used: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    success_indicators: List[str] = field(default_factory=list)


@dataclass
class SkillCreationResult:
    skill_name: str
    skill_dir: Path
    skill_md_path: Path
    success: bool
    error: Optional[str] = None


class SkillCreator:
    def __init__(self, skills_dir: Path, llm=None):
        if skills_dir is None:
            self.skills_dir = None
            self._llm = llm
            return
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._llm = llm

    def _should_skip_trigger(self, trigger: str) -> bool:
        """检查触发词是否在黑名单中"""
        text = trigger.lower().strip()
        if len(text) < 4:
            return True  # 太短的文本不创建技能
        for pattern in _BLACKLIST_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def _should_accept_trigger(self, trigger: str) -> bool:
        """检查是否命中白名单（高优先级）"""
        text = trigger.lower().strip()
        for pattern in _WHITELIST_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def should_create_skill(self, messages: List[Dict]) -> Optional[SkillCreationRequest]:
        """判断是否应该自动创建技能"""
        if len(messages) < 6:
            return None

        # 统计工具调用
        tool_calls_count = sum(
            1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls")
        )
        if tool_calls_count < 3:
            return None

        # 收集使用的工具
        tools_used = []
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    tc_dict = tc if isinstance(tc, dict) else {}
                    func = tc_dict.get("function", {})
                    name = func.get("name", "")
                    if name and name not in tools_used:
                        tools_used.append(name)
        if len(tools_used) < 2:
            return None

        # 获取最后用户消息
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return None
        trigger = user_msgs[-1].get("content", "")[:200]

        # 黑名单过滤
        if self._should_skip_trigger(trigger):
            logger.debug(f"跳过技能创建（黑名单匹配）: {trigger[:50]}")
            return None

        # 白名单命中则直接通过
        if self._should_accept_trigger(trigger):
            return SkillCreationRequest(
                trigger=trigger,
                task_description=trigger,
                tools_used=tools_used,
            )

        # 非白名单情况下：需要更高的门槛（更多工具调用、更多轮次）
        if tool_calls_count < 5 or len(messages) < 10:
            logger.debug(f"跳过技能创建（未达白名单，门槛不足）: {trigger[:50]}")
            return None

        return SkillCreationRequest(
            trigger=trigger,
            task_description=trigger,
            tools_used=tools_used,
        )

    def create_skill(self, request: SkillCreationRequest) -> SkillCreationResult:
        if self.skills_dir is None:
            return SkillCreationResult(
                skill_name=request.trigger[:50],
                skill_dir=Path("."),
                skill_md_path=Path("SKILL.md"),
                success=False,
                error="skills_dir 未初始化",
            )
        skill_name = self._generate_skill_name(request.trigger)
        if not skill_name:
            return SkillCreationResult(
                skill_name="invalid",
                skill_dir=Path("."),
                skill_md_path=Path("SKILL.md"),
                success=False,
                error="技能名生成失败",
            )
        skill_dir = self.skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md_path = skill_dir / "SKILL.md"
        content = self._generate_skill_md(request, skill_name)
        try:
            skill_md_path.write_text(content, encoding="utf-8")
            logger.info(f"自动创建技能: {skill_name}")
            return SkillCreationResult(
                skill_name=skill_name,
                skill_dir=skill_dir,
                skill_md_path=skill_md_path,
                success=True,
            )
        except Exception as e:
            logger.error(f"创建技能失败: {e}")
            return SkillCreationResult(
                skill_name=skill_name,
                skill_dir=skill_dir,
                skill_md_path=skill_md_path,
                success=False,
                error=str(e),
            )

    def generate_skill_for_review(self, request: SkillCreationRequest) -> Optional[str]:
        """生成技能内容供 Agent/用户审核

        返回生成的 SKILL.md 内容，但不保存到磁盘。
        Agent 可以审核、修改后调用 save_skill() 保存。
        """
        if self.skills_dir is None:
            return None
        skill_name = self._generate_skill_name(request.trigger)
        if not skill_name:
            return None
        return self._generate_skill_md(request, skill_name)

    def save_skill(self, content: str, skill_name: str) -> SkillCreationResult:
        """保存已审核的技能

        Agent/用户审核并可能修改 content 后调用此方法保存。
        """
        if self.skills_dir is None:
            return SkillCreationResult(
                skill_name=skill_name,
                skill_dir=Path("."),
                skill_md_path=Path("SKILL.md"),
                success=False,
                error="skills_dir 未初始化",
            )
        skill_dir = self.skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md_path = skill_dir / "SKILL.md"
        try:
            skill_md_path.write_text(content, encoding="utf-8")
            logger.info(f"保存审核通过的技能: {skill_name}")
            return SkillCreationResult(
                skill_name=skill_name,
                skill_dir=skill_dir,
                skill_md_path=skill_md_path,
                success=True,
            )
        except Exception as e:
            logger.error(f"保存技能失败: {e}")
            return SkillCreationResult(
                skill_name=skill_name,
                skill_dir=skill_dir,
                skill_md_path=skill_md_path,
                success=False,
                error=str(e),
            )

    def _generate_skill_name(self, trigger: str) -> Optional[str]:
        """生成合理的技能名，避免垃圾名称"""
        # 1. 尝试从触发词中提取关键词
        # 去除特殊字符
        name = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', trigger[:50]).strip()
        # 空白替换为下划线
        name = re.sub(r'[\s]+', '_', name)
        name = name.strip('_').lower()

        # 2. 如果名字太短或无意义，返回 None
        if not name or len(name) < 2:
            return None

        # 3. 检查名字是否在黑名单中
        for pattern in _SKILL_NAME_BLACKLIST:
            if re.search(pattern, name):
                return None

        # 4. 避免与已有技能重名
        try:
            existing = set(p.name for p in self.skills_dir.iterdir() if p.is_dir())
        except OSError:
            existing = set()

        if name in existing:
            name = f"{name}_v2"

        # 5. 最终验证
        if len(name) > 50:
            name = name[:50]

        return name

    def _generate_skill_md(self, request: SkillCreationRequest, skill_name: str) -> str:
        tools_yaml = "\n".join(f"  - {t}" for t in request.tools_used)
        return f"""---
name: {skill_name}
version: "0.1.0"
description: "自动创建的技能: {request.task_description[:100]}"
category: auto_created
enabled: true
author: ts2_agent
allowed_tools:
{tools_yaml}
---

# {skill_name}

## 触发条件
{request.trigger}

## 执行步骤
此技能由Agent自动创建，执行步骤将在使用中逐步完善。

## 工具依赖
{', '.join(request.tools_used)}
"""

    def cleanup_invalid_skills(self) -> List[str]:
        """清理无效技能（名称在黑名单中的）

        返回被删除的技能名列表
        """
        if self.skills_dir is None:
            return []

        deleted = []
        try:
            for skill_dir in self.skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_name = skill_dir.name

                # 检查技能名是否在黑名单中
                should_delete = False
                for pattern in _SKILL_NAME_BLACKLIST:
                    if re.search(pattern, skill_name):
                        should_delete = True
                        break

                # 检查是否有有效的 SKILL.md
                md_file = skill_dir / "SKILL.md"
                if not md_file.exists():
                    should_delete = True
                else:
                    # 检查内容是否只是模板文本
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        if "此技能由Agent自动创建" in content and "逐步完善" in content:
                            # 从未被完善过的技能，且名字奇怪
                            if len(skill_name) < 5 or any(
                                re.search(p, skill_name) for p in _BLACKLIST_PATTERNS
                            ):
                                should_delete = True
                    except Exception:
                        should_delete = True

                if should_delete:
                    import shutil
                    shutil.rmtree(skill_dir, ignore_errors=True)
                    deleted.append(skill_name)
                    logger.info(f"清理无效技能: {skill_name}")

        except OSError as e:
            logger.error(f"清理技能时出错: {e}")

        return deleted


class SaveSkillTool:
    """save_skill 工具 — 供 Agent 审核并保存技能

    Agent 收到技能草稿后，可以修改内容再调用此工具保存。
    """
    name = "save_skill"
    description = "保存经过审核的技能。可以修改内容后保存。如果技能已存在则覆盖。"
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "SKILL.md 的完整内容（YAML frontmatter + Markdown 正文）",
            },
            "skill_name": {
                "type": "string",
                "description": "技能名称（也是目录名），如 'arxiv-paper-search'",
            },
        },
        "required": ["content", "skill_name"],
    }

    def __init__(self, creator_getter: Callable):
        self._creator_getter = creator_getter

    def execute(self, content: str, skill_name: str) -> str:
        creator = self._creator_getter()
        if not creator:
            return json.dumps({"success": False, "error": "SkillCreator 未初始化"}, ensure_ascii=False)
        result = creator.save_skill(content, skill_name)
        return json.dumps({
            "success": result.success,
            "skill_name": result.skill_name,
            "error": result.error,
        }, ensure_ascii=False)

