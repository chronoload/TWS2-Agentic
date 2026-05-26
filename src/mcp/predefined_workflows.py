#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS2 预定义工作流 — 参考 DeerFlow 的 Skills + Metaflow 的 Flow 模式

提供开箱即用的工作流:
  code_analysis    代码架构分析
  research          主题深度研究
  note_generation   智能笔记生成
  code_review       代码审查
  dependency_scan   依赖分析
"""
from __future__ import annotations

from typing import Dict, Any

from .workflow_engine import (
    WorkflowDefinition, StepDefinition, StepType,
)

# ============================================================
# 06_analysis   代码架构分析
# ============================================================

def code_analysis_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="code_analysis_v1",
        name="代码架构分析",
        description="自动分析代码库架构、识别设计模式、对比最新方案、生成报告",
        entry_step="read_code",
        checkpoint_after={"read_code", "identify_patterns", "compare_solutions", "generate_report"},
        steps=[
            StepDefinition(
                step_id="read_code",
                name="读取代码",
                step_type=StepType.AGENT,
                prompt_template="""分析以下代码文件的结构和主要组件:

工作目录: {workspace}
目标文件: {target_files}
分析目标: {analysis_goal}

请执行:
1. 读取代码文件结构
2. 识别主要类/函数/模块
3. 分析依赖关系和调用链
4. 总结关键设计决策

输出结构化分析结果。""",
                tools=["read_file", "list_directory", "search_code"],
            ),
            StepDefinition(
                step_id="identify_patterns",
                name="识别模式",
                step_type=StepType.AGENT,
                prompt_template="""基于代码分析结果，识别设计模式和架构特征:

{step_results}

请识别:
1. GoF设计模式实例
2. 架构模式（分层/MVC/微服务等）
3. 代码组织和模块化策略
4. 潜在问题和代码异味""",
                tools=["search_code", "git_search"],
            ),
            StepDefinition(
                step_id="compare_solutions",
                name="对比方案",
                step_type=StepType.AGENT,
                prompt_template="""对比当前实现与业界最佳实践:

{step_results}

请执行:
1. 搜索相关技术的最新实践
2. 逐项对比当前方案的优缺点
3. 提出具体改进建议（含代码示例）
4. 标注优先级（高/中/低）""",
                tools=["web_search", "git_search"],
            ),
            StepDefinition(
                step_id="generate_report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于所有分析结果，生成完整报告:

{step_results}

报告结构:
1. 执行摘要
2. 代码结构概览
3. 设计模式分析
4. 问题与风险
5. 优化建议（含具体实施步骤）
6. 参考资源

输出 Markdown 格式。""",
                tools=["write_file"],
            ),
        ],
    )


# ============================================================
# 07_research    主题深度研究
# ============================================================

def research_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="research_v1",
        name="主题深度研究",
        description="收集资料、分析整理、生成研究报告",
        entry_step="gather_info",
        checkpoint_after={"gather_info", "analyze_info", "generate_report"},
        steps=[
            StepDefinition(
                step_id="gather_info",
                name="收集信息",
                step_type=StepType.PARALLEL,
                parallel_steps=[
                    StepDefinition(
                        step_id="web_search",
                        name="网络搜索",
                        step_type=StepType.TOOL,
                        config={
                            "tool_name": "web_search",
                            "args": {"query": "{query}"},
                        },
                    ).to_dict(),
                    StepDefinition(
                        step_id="search_docs",
                        name="搜索本地文档",
                        step_type=StepType.TOOL,
                        config={
                            "tool_name": "search_notes",
                            "args": {"query": "{query}"},
                        },
                    ).to_dict(),
                    StepDefinition(
                        step_id="search_papers",
                        name="搜索论文",
                        step_type=StepType.TOOL,
                        config={
                            "tool_name": "search_arxiv",
                            "args": {"query": "{query}", "max_results": 5},
                        },
                    ).to_dict(),
                    StepDefinition(
                        step_id="search_git",
                        name="搜索开源方案",
                        step_type=StepType.TOOL,
                        config={
                            "tool_name": "git_search",
                            "args": {"query": "{query}"},
                        },
                    ).to_dict(),
                ],
            ),
            StepDefinition(
                step_id="analyze_info",
                name="分析整理",
                step_type=StepType.AGENT,
                prompt_template="""整理和综合收集到的信息:

{step_results}

请执行:
1. 去重和筛选高质量内容
2. 按主题维度分类
3. 提取核心知识点
4. 标注信息来源和可靠性
5. 识别知识空白""",
            ),
            StepDefinition(
                step_id="generate_report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""生成深度研究报告:

研究主题: {query}
整理的知识: {step_results}

报告结构:
1. 摘要
2. 背景与动机
3. 核心发现
4. 详细分析
5. 理论基础
6. 实践指导
7. 未来方向
8. 参考资料""",
                tools=["write_file", "save_rmd_note"],
            ),
        ],
    )


# ============================================================
# 08_note    智能笔记生成
# ============================================================

def note_generation_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="note_generation_v1",
        name="智能笔记生成",
        description="解析内容、提取知识点、生成结构化 Rmd 笔记",
        entry_step="parse_content",
        checkpoint_after={"parse_content", "extract_knowledge", "generate_note"},
        steps=[
            StepDefinition(
                step_id="parse_content",
                name="解析内容",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "parse_document",
                    "args": {"path": "{input_path}"},
                },
            ),
            StepDefinition(
                step_id="extract_knowledge",
                name="提取知识点",
                step_type=StepType.AGENT,
                prompt_template="""从以下内容中提取关键知识点:

{step_results}

课程: {course_title}

提取要求:
1. 核心概念定义
2. 重要公式/定理
3. 典型例题和证明
4. 与前置知识的关联
5. 易错点和注意事项

输出结构化 JSON。""",
            ),
            StepDefinition(
                step_id="generate_note",
                name="生成笔记",
                step_type=StepType.AGENT,
                prompt_template="""基于提取的知识点，生成标准 Rmd 笔记:

课程: {course_title}
知识点: {step_results}

遵循 TS2 笔记模板:
- YAML 头 (title, author, date, tags, domain)
- 分层结构 (# ## ###)
- 代码块 (```python ```math)
- 练习题目
- 参考资料

输出完整 .Rmd 内容。""",
                tools=["save_rmd_note", "write_file"],
            ),
        ],
    )


# ============================================================
# 09    代码审查
# ============================================================

def code_review_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="code_review_v1",
        name="代码审查",
        description="自动代码审查：风格检查、安全审计、性能分析",
        entry_step="static_analysis",
        checkpoint_after={"static_analysis", "security_audit", "perf_check", "generate_review"},
        steps=[
            StepDefinition(
                step_id="static_analysis",
                name="静态分析",
                step_type=StepType.AGENT,
                prompt_template="""对以下代码进行静态分析:

{target_files}

检查项:
1. 代码风格和格式
2. 命名规范
3. 注释质量
4. 函数复杂度
5. 重复代码
6. 未使用的导入和变量""",
            ),
            StepDefinition(
                step_id="security_audit",
                name="安全审计",
                step_type=StepType.AGENT,
                prompt_template="""审计代码安全性:

{step_results}

检查项:
1. SQL注入风险
2. XSS漏洞
3. 硬编码密钥
4. 路径遍历
5. 不安全的反序列化
6. 权限检查缺失""",
            ),
            StepDefinition(
                step_id="perf_check",
                name="性能检查",
                step_type=StepType.AGENT,
                prompt_template="""检查代码性能:

{step_results}

检查项:
1. 算法复杂度
2. 不必要的数据库查询
3. 大对象的复制
4. 阻塞I/O
5. 内存泄漏风险
6. 缓存利用""",
            ),
            StepDefinition(
                step_id="generate_review",
                name="生成审查报告",
                step_type=StepType.AGENT,
                prompt_template="""汇总代码审查结果:

{step_results}

输出:
1. 整体评分 (1-10)
2. 分类问题列表（含行号）
3. 修复建议（含代码示例）
4. 改进优先级""",
            ),
        ],
    )


# ============================================================
# workspace     项目依赖分析
# ============================================================

def dependency_scan_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="dependency_scan_v1",
        name="依赖分析",
        description="分析项目依赖、版本兼容性、安全漏洞",
        entry_step="scan_deps",
        checkpoint_after={"scan_deps", "version_check", "security_check", "report"},
        steps=[
            StepDefinition(
                step_id="scan_deps",
                name="扫描依赖",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "analyze_dependencies",
                    "args": {"path": "{workspace}"},
                },
            ),
            StepDefinition(
                step_id="version_check",
                name="版本检查",
                step_type=StepType.AGENT,
                prompt_template="""检查依赖版本兼容性:

{step_results}

检查:
1. 过时的依赖
2. 版本冲突
3. 不兼容的升级
4. 推荐的替代方案""",
                tools=["web_search"],
            ),
            StepDefinition(
                step_id="security_check",
                name="安全检查",
                step_type=StepType.AGENT,
                prompt_template="""检查依赖安全漏洞:

{step_results}

检查:
1. 已知CVE漏洞
2. 弃用的包
3. 未维护的依赖
4. 许可证问题""",
                tools=["web_search"],
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""汇总依赖分析结果:

{step_results}

输出:
1. 依赖总览
2. 问题列表（按严重性排序）
3. 升级计划
4. 风险缓解措施""",
            ),
        ],
    )


# ============================================================
# Registry
# ============================================================

def rss_academic_tracker_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_rss_academic_tracker",
        name="RSS学术追踪",
        description="RSS轻爬取→关键词提取→溯源推送→模型摘要→弹窗推送CourseTracker",
        checkpoint_after={"rss_poll", "keyword_extract", "model_summary"},
        steps=[
            StepDefinition(
                step_id="rss_poll",
                name="RSS轻爬取",
                step_type=StepType.TOOL,
                config={"tool_name": "ws2_hub_poll_rss", "args": {}},
            ),
            StepDefinition(
                step_id="keyword_extract",
                name="关键词提取",
                step_type=StepType.AGENT,
                prompt_template="""分析以下RSS条目，提取结构和关键词:

{step_results}

课程主题关键词字典: {course_keywords}

请执行:
1. 提取每条RSS的结构（标题/摘要/来源）
2. 提取关键词并与课程主题匹配
3. 筛选与课程高度相关的内容
4. 输出: 结构化摘要 + 匹配的关键词列表""",
            ),
            StepDefinition(
                step_id="scholar_trace",
                name="学术溯源",
                step_type=StepType.TOOL,
                config={"tool_name": "search_papers", "args": {"query": "{keywords}", "max_results": 5}},
            ),
            StepDefinition(
                step_id="model_summary",
                name="模型摘要",
                step_type=StepType.AGENT,
                prompt_template="""汇总以下学术动态，生成学习摘要:

RSS内容: {step_results}
学术溯源: {step_results}

请生成:
1. 核心发现 (3-5条)
2. 与课程的关联
3. 推荐深入阅读的论文
4. 学习建议

输出简洁中文摘要。""",
            ),
            StepDefinition(
                step_id="push_notification",
                name="弹窗推送",
                step_type=StepType.NOTIFY,
                config={"message": "📚 新学术动态已汇总，请查看学习助手"},
            ),
        ],
    )


def course_progress_reminder_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_course_progress_reminder",
        name="课程进度提醒",
        description="课程进度捕捉→资料推荐→学习助手弹窗（可替换RSS学术追踪前半截）",
        checkpoint_after={"progress_capture", "resource_recommend"},
        steps=[
            StepDefinition(
                step_id="progress_capture",
                name="课程进度捕捉",
                step_type=StepType.TOOL,
                config={"tool_name": "course_tracker_get_progress", "args": {}},
            ),
            StepDefinition(
                step_id="activity_capture",
                name="操作日志捕捉",
                step_type=StepType.TOOL,
                config={"tool_name": "event_logger_query", "args": {"limit": 20}},
            ),
            StepDefinition(
                step_id="resource_recommend",
                name="资料推荐",
                step_type=StepType.AGENT,
                prompt_template="""根据课程进度和操作日志，推荐学习资料:

课程进度: {step_results}
操作日志: {step_results}

请执行:
1. 分析当前学习进度和薄弱环节
2. 从资料库推荐相关学习资料
3. 询问"有什么需要解答的吗？"

输出推荐列表和引导问题。""",
            ),
            StepDefinition(
                step_id="popup_remind",
                name="学习助手弹窗",
                step_type=StepType.NOTIFY,
                config={"message": "📖 课程进度提醒：请查看推荐学习资料"},
            ),
        ],
    )


def pending_task_reminder_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_pending_task_reminder",
        name="待完成任务提醒",
        description="定时弹窗提醒未完成任务（非模型，从CourseTracker任务栏唤醒）",
        steps=[
            StepDefinition(
                step_id="query_pending",
                name="查询未完成任务",
                step_type=StepType.TOOL,
                config={"tool_name": "course_tracker_get_pending_tasks", "args": {}},
            ),
            StepDefinition(
                step_id="popup_remind",
                name="弹窗提醒",
                step_type=StepType.NOTIFY,
                config={"message": "⚠️ 你有未完成的课程任务，请查看CourseTracker"},
            ),
        ],
    )


def course_mode_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_course_mode",
        name="课程模式进入",
        description="课程表触发→提示音→锁定→教师模型+课程提示+辅助工具",
        checkpoint_after={"detect_slot", "enter_mode"},
        steps=[
            StepDefinition(
                step_id="detect_slot",
                name="课程表检测",
                step_type=StepType.TOOL,
                config={"tool_name": "course_simulation_get_current_slot", "args": {}},
            ),
            StepDefinition(
                step_id="notify_sound",
                name="提示音+弹窗",
                step_type=StepType.NOTIFY,
                config={"message": "🔔 课程即将开始！"},
            ),
            StepDefinition(
                step_id="enter_mode",
                name="进入课程模式",
                step_type=StepType.TOOL,
                config={"tool_name": "course_simulation_enter_mode", "args": {}},
            ),
            StepDefinition(
                step_id="teacher_window",
                name="教师模型窗",
                step_type=StepType.AGENT,
                prompt_template="""你现在是{course_name}课程的教师。

本节内容: {lesson_title}
中心问题: {central_question}

请以教师身份:
1. 简要介绍本节内容
2. 提出引导性问题
3. 等待学生提问

用专业但友好的语气。""",
            ),
            StepDefinition(
                step_id="wait_session",
                name="等待课程结束",
                step_type=StepType.WAIT,
            ),
            StepDefinition(
                step_id="exit_mode",
                name="退出课程模式",
                step_type=StepType.TOOL,
                config={"tool_name": "course_simulation_exit_mode", "args": {}},
            ),
        ],
    )


WORKFLOW_REGISTRY: Dict[str, WorkflowDefinition] = {
    "code_analysis": code_analysis_workflow(),
    "research": research_workflow(),
    "note_generation": note_generation_workflow(),
    "code_review": code_review_workflow(),
    "dependency_scan": dependency_scan_workflow(),
    "rss_academic_tracker": rss_academic_tracker_workflow(),
    "course_progress_reminder": course_progress_reminder_workflow(),
    "pending_task_reminder": pending_task_reminder_workflow(),
    "course_mode": course_mode_workflow(),
}


def get_workflow(workflow_id: str) -> WorkflowDefinition:
    if workflow_id in WORKFLOW_REGISTRY:
        return WORKFLOW_REGISTRY[workflow_id]
    raise KeyError(f"未知工作流: {workflow_id}")


def list_workflows() -> Dict[str, str]:
    return {
        wf_id: wf.description for wf_id, wf in WORKFLOW_REGISTRY.items()
    }


def register_workflow(wf: WorkflowDefinition):
    WORKFLOW_REGISTRY[wf.workflow_id.split("_")[0]] = wf


__all__ = [
    "code_analysis_workflow", "research_workflow",
    "note_generation_workflow", "code_review_workflow",
    "dependency_scan_workflow",
    "WORKFLOW_REGISTRY", "get_workflow", "list_workflows",
    "register_workflow",
]