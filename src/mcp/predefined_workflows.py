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

from typing import Dict, Any, Optional

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


def gt_basic_prove_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_gt_basic_prove",
        name="GT基础证明",
        description="使用GT Agent基础模式进行数学证明：验证→评分→Gap分析→假设审计",
        checkpoint_after={"validate", "rate", "gap_analysis"},
        steps=[
            StepDefinition(
                step_id="validate",
                name="验证证明",
                step_type=StepType.GT_PROVE,
                config={
                    "gt_mode": "basic",
                    "allowed_references": [],
                    "forbidden_assumptions": [],
                },
                prompt_template="{source_code}",
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于GT证明结果，生成可读的证明报告:

证明结果: {step_results}

请整理:
1. 证明状态（成功/失败/部分）
2. 已关闭的引理
3. 剩余Gap列表
4. 假设审计结果
5. 评分和改进建议

输出 Markdown 格式报告。""",
            ),
        ],
    )


def gt_evolution_prove_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_gt_evolution_prove",
        name="GT进化证明",
        description="使用GT Agent进化模式：种群搜索+P-UCB平衡探索与利用，适合困难证明",
        checkpoint_after={"evolve_prove", "validate_final"},
        steps=[
            StepDefinition(
                step_id="evolve_prove",
                name="进化搜索证明",
                step_type=StepType.GT_PROVE,
                config={
                    "gt_mode": "evolution",
                    "allowed_references": [],
                    "forbidden_assumptions": [],
                },
                prompt_template="{source_code}",
            ),
            StepDefinition(
                step_id="validate_final",
                name="最终验证",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "gt_validate",
                    "args": {"final": True},
                },
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于GT进化证明结果，生成完整证明报告:

证明结果: {step_results}

请整理:
1. 证明状态和进化代数
2. 最优候选证明
3. 种群多样性分析
4. Gap解决路径
5. 假设审计结果
6. 评分和改进建议

输出 Markdown 格式报告。""",
            ),
        ],
    )


# ============================================================
# Lean4 证明检查工作流
# ============================================================

def lean4_proof_check_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_lean4_proof_check",
        name="Lean4证明检查",
        description="Lean 4 代码编译检查→诊断→目标状态查询→报告生成",
        checkpoint_after={"check", "diagnose"},
        steps=[
            StepDefinition(
                step_id="check",
                name="编译检查",
                step_type=StepType.LEAN_CHECK,
                config={"timeout": 60},
                prompt_template="{source_code}",
            ),
            StepDefinition(
                step_id="diagnose",
                name="获取诊断",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "lean4_get_diagnostics",
                    "args": {"uri": "{file_uri}"},
                },
            ),
            StepDefinition(
                step_id="goal_state",
                name="查询目标状态",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "lean4_get_goal_state",
                    "args": {"uri": "{file_uri}", "line": 0},
                },
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于 Lean 4 检查结果，生成证明状态报告:

编译检查: {step_results}
诊断信息: {step_results}
目标状态: {step_results}

请整理:
1. 编译是否通过
2. 错误和警告列表
3. 未完成的目标状态
4. 修复建议（含代码示例）
5. 下一步行动

输出 Markdown 格式。""",
            ),
        ],
    )


def lean4_lake_build_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_lean4_lake_build",
        name="Lean4项目构建",
        description="Lake 项目构建→诊断→报告",
        checkpoint_after={"build"},
        steps=[
            StepDefinition(
                step_id="build",
                name="Lake Build",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "lean4_lake_build",
                    "args": {"project_dir": "{project_dir}", "timeout": 300},
                },
            ),
            StepDefinition(
                step_id="report",
                name="构建报告",
                step_type=StepType.AGENT,
                prompt_template="""基于 Lake Build 结果，生成构建报告:

构建结果: {step_results}

请整理:
1. 构建是否成功
2. 编译错误列表
3. 依赖问题
4. 修复建议

输出 Markdown 格式。""",
            ),
        ],
    )


# ============================================================
# Manim 动画生成工作流
# ============================================================

def manim_animation_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_manim_animation",
        name="Manim动画生成",
        description="从文本描述生成 Manim 动画视频：生成→检查→渲染",
        checkpoint_after={"generate", "review"},
        steps=[
            StepDefinition(
                step_id="generate",
                name="生成动画",
                step_type=StepType.MANIM_GEN,
                config={
                    "mode": "simple",
                    "quality": "h",
                    "audio": False,
                },
                prompt_template="{animation_prompt}",
            ),
            StepDefinition(
                step_id="review",
                name="审查代码",
                step_type=StepType.AGENT,
                prompt_template="""审查以下 Manim 动画生成结果:

生成结果: {step_results}

请检查:
1. 场景结构是否完整
2. 动画逻辑是否正确
3. 是否有渲染风险（内存/时间）
4. 改进建议

输出审查意见。""",
            ),
            StepDefinition(
                step_id="edit",
                name="编辑优化",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_edit",
                    "args": {"render_id": "{manim_render_id}", "instruction": "{edit_instruction}"},
                },
            ),
        ],
    )


def manim_rag_search_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_manim_rag_search",
        name="Manim场景搜索",
        description="搜索 RAG 数据库中的相似 Manim 场景，辅助动画开发",
        steps=[
            StepDefinition(
                step_id="search",
                name="RAG搜索",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_rag_search",
                    "args": {"query": "{query}", "collection": "manim_scenes", "limit": 5},
                },
            ),
            StepDefinition(
                step_id="summarize",
                name="汇总结果",
                step_type=StepType.AGENT,
                prompt_template="""汇总 Manim RAG 搜索结果:

搜索结果: {step_results}

请整理:
1. 最相关的场景
2. 可复用的代码模式
3. API 用法参考
4. 建议的动画方案

输出 Markdown 格式。""",
            ),
        ],
    )


# ============================================================
# Lean4 形式化工作流
# ============================================================

def lean4_formalize_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_lean4_formalize",
        name="Lean4形式化",
        description="非正式数学→Lean4代码→编译→证明→审查: formalize→check→prove→review",
        checkpoint_after={"draft", "check", "prove"},
        steps=[
            StepDefinition(
                step_id="draft",
                name="形式化草案",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_formalize", "args": {"informal_spec": "{spec}", "mode": "autonomous"}},
            ),
            StepDefinition(
                step_id="check",
                name="编译检查",
                step_type=StepType.LEAN_CHECK,
                config={"timeout": 60},
                prompt_template="{lean4_code}",
            ),
            StepDefinition(
                step_id="prove",
                name="引导式证明",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_prove", "args": {"file_path": "{target_file}", "max_cycles": 10}},
            ),
            StepDefinition(
                step_id="review",
                name="审查",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_review", "args": {"file_path": "{target_file}", "focus": "all"}},
            ),
            StepDefinition(
                step_id="report",
                name="形式化报告",
                step_type=StepType.AGENT,
                prompt_template="""基于 Lean 4 形式化结果，生成报告:

草案: {step_results}
编译: {step_results}
证明: {step_results}
审查: {step_results}

请整理:
1. 形式化覆盖率
2. 编译状态
3. 证明完成度
4. 审查问题和建议""",
            ),
        ],
    )


def lean4_golf_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_lean4_golf",
        name="Lean4证明优化",
        description="Lean 4 证明高尔夫: review→golf→check 循环优化证明",
        checkpoint_after={"golf"},
        steps=[
            StepDefinition(
                step_id="review_before",
                name="优化前审查",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_review", "args": {"file_path": "{file_path}", "focus": "all"}},
            ),
            StepDefinition(
                step_id="golf",
                name="Golf优化",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_golf", "args": {"file_path": "{file_path}", "search_mode": "quick", "max_hunks": 3}},
            ),
            StepDefinition(
                step_id="verify",
                name="验证编译",
                step_type=StepType.LEAN_CHECK,
                config={"timeout": 60},
                prompt_template="{lean4_code}",
            ),
            StepDefinition(
                step_id="report",
                name="优化报告",
                step_type=StepType.AGENT,
                prompt_template="""Lean4 证明优化结果:

优化前: {step_results}
优化后: {step_results}
编译验证: {step_results}

请总结:
1. 行数变化
2. mathlib 引用优化
3. 可读性改进
4. 性能影响""",
            ),
        ],
    )


# ============================================================
# Manim 完整流水线工作流
# ============================================================

def manim_pipeline_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_manim_pipeline",
        name="Manim动画流水线",
        description="完整动画制作流水线: 概念分析→Schema规划→代码生成→审查→渲染",
        checkpoint_after={"analyze", "schema", "review"},
        steps=[
            StepDefinition(
                step_id="analyze",
                name="概念分析",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_concept_analyze",
                    "args": {"concept": "{concept}", "style": "{style}", "target_audience": "{audience}"},
                },
            ),
            StepDefinition(
                step_id="schema",
                name="Schema规划",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_schema_generate",
                    "args": {"concept": "{concept}", "use_latex": True, "scene_count": 5},
                },
            ),
            StepDefinition(
                step_id="generate",
                name="生成动画",
                step_type=StepType.MANIM_GEN,
                config={"mode": "simple", "quality": "h"}, prompt_template="{animation_prompt}",
            ),
            StepDefinition(
                step_id="review",
                name="代码审查",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_code_review",
                    "args": {"code": "{manim_code}", "engine": "manimce"},
                },
            ),
            StepDefinition(
                step_id="render",
                name="渲染",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_render",
                    "args": {"script_path": "script.py", "scene_name": "MainScene", "quality": "h"},
                },
            ),
        ],
    )


def manim_self_improve_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_manim_self_improve",
        name="Manim自我改进",
        description="Manim 动画自我审查→改进循环: critique→edit→render",
        checkpoint_after={"critique", "render"},
        steps=[
            StepDefinition(
                step_id="critique",
                name="自我审查",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_self_critique",
                    "args": {"render_id": "{render_id}", "check_aspects": ["layout", "timing", "color", "text", "math"]},
                },
            ),
            StepDefinition(
                step_id="fix",
                name="修复问题",
                step_type=StepType.AGENT,
                prompt_template="""根据 self_critique 结果修复 Manim 动画问题:

批评: {step_results}
代码: {manim_code}

请修复布局、时机、颜色、文字和数学方面的问题。输出修复后的完整代码。""",
            ),
            StepDefinition(
                step_id="edit",
                name="应用修改",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_edit",
                    "args": {"render_id": "{render_id}", "instruction": "{fix_result}"},
                },
            ),
            StepDefinition(
                step_id="render",
                name="重新渲染",
                step_type=StepType.TOOL,
                config={
                    "tool_name": "manim_render",
                    "args": {"script_path": "{script_path}", "scene_name": "{scene_name}", "quality": "h"},
                },
            ),
        ],
    )


# ============================================================
# MathLens 教学视频工作流
# ============================================================

def mathlens_video_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_mathlens_video",
        name="MathLens教学视频",
        description="8步 MathLens 工作流：初始化→脚本编写→TTS→验证→检查→渲染→报告",
        checkpoint_after={"init", "tts", "render"},
        steps=[
            StepDefinition(
                step_id="init",
                name="初始化项目",
                step_type=StepType.MATHLENS,
                config={"action": "init", "project_dir": "{project_dir}"},
            ),
            StepDefinition(
                step_id="write_script",
                name="编写分镜脚本",
                step_type=StepType.AGENT,
                prompt_template="""为以下数学主题编写 MathLens 分镜脚本:

主题: {math_topic}
项目目录: {project_dir}

请按照 MathLens 分镜脚本格式编写:
1. 每个分镜包含: scene_id, narration, manim_code, duration
2. narration 用于 TTS 配音
3. manim_code 使用 Manim Community Edition 语法
4. 合理控制每个分镜时长（3-10秒）

输出分镜脚本 CSV 格式。""",
                tools=["write_file"],
            ),
            StepDefinition(
                step_id="tts",
                name="生成TTS音频",
                step_type=StepType.MATHLENS,
                config={
                    "action": "tts",
                    "csv_path": "{csv_path}",
                    "voice": "xiaoxiao",
                },
            ),
            StepDefinition(
                step_id="validate",
                name="验证音频",
                step_type=StepType.MATHLENS,
                config={
                    "action": "validate",
                    "storyboard_path": "{storyboard_path}",
                },
            ),
            StepDefinition(
                step_id="check",
                name="检查Manim代码",
                step_type=StepType.MATHLENS,
                config={"action": "check", "script_path": "script.py"},
            ),
            StepDefinition(
                step_id="render",
                name="渲染视频",
                step_type=StepType.MATHLENS,
                config={
                    "action": "render",
                    "script_path": "script.py",
                    "scene_name": "MathScene",
                    "quality": "h",
                },
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于 MathLens 教学视频制作结果，生成报告:

初始化: {step_results}
TTS: {step_results}
验证: {step_results}
检查: {step_results}
渲染: {step_results}

请整理:
1. 视频制作状态
2. 音频同步情况
3. 代码质量评估
4. 渲染输出信息
5. 改进建议

输出 Markdown 格式。""",
            ),
        ],
    )


# ============================================================
# AutoResearch 自动研究工作流
# ============================================================

def autoresearch_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_autoresearch",
        name="自动研究",
        description="AutoResearch 23阶段研究管线的简化版：选题→文献→综合→实验→分析→报告",
        checkpoint_after={"scope", "literature", "experiment", "analysis"},
        steps=[
            StepDefinition(
                step_id="scope",
                name="研究范围界定",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["topic_init", "problem_decompose"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="literature",
                name="文献发现与筛选",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["search_strategy", "literature_collect", "literature_screen", "knowledge_extract"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="synthesis",
                name="知识综合与假设生成",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["synthesis", "hypothesis_gen"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="experiment",
                name="实验设计与执行",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["experiment_design", "code_generation", "experiment_run", "iterative_refine"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="analysis",
                name="结果分析与决策",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["result_analysis", "research_decision"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="paper",
                name="论文撰写与审校",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["paper_outline", "paper_draft", "peer_review", "paper_revision"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="finalize",
                name="质量门控与发布",
                step_type=StepType.AUTORESEARCH,
                config={
                    "stages": ["quality_gate", "knowledge_archive", "export_publish", "citation_verify"],
                    "max_iterations": 1,
                },
                prompt_template="{research_topic}",
            ),
            StepDefinition(
                step_id="report",
                name="研究总结",
                step_type=StepType.AGENT,
                prompt_template="""基于自动研究管线的结果，生成完整研究报告:

研究范围: {step_results}
文献综述: {step_results}
知识综合: {step_results}
实验结果: {step_results}
分析决策: {step_results}
论文草稿: {step_results}
质量门控: {step_results}

请整理:
1. 研究主题和问题
2. 文献综述摘要
3. 核心假设
4. 实验设计与结果
5. 主要发现
6. 论文状态
7. 后续建议

输出 Markdown 格式。""",
            ),
        ],
    )


# ============================================================
# 参数链示例工作流 — 展示 param_inputs / param_outputs
# ============================================================

def param_chain_demo_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_param_chain_demo",
        name="参数链示例",
        description="演示参数链: 步骤A的输出作为步骤B的输入，支持 transform、默认值、类型转换",
        checkpoint_after={"normalize", "fetch", "report"},
        steps=[
            StepDefinition(
                step_id="normalize",
                name="规范化主题",
                step_type=StepType.AGENT,
                param_inputs=[
                    {"target": "raw_topic", "source": "$input.topic", "transform": "strip", "default": ""},
                    {"target": "topic_length", "source": "$input.topic", "transform": "length", "default": 0},
                ],
                param_outputs=[
                    {"name": "normalized_topic", "path": "topic", "type": "string"},
                    {"name": "tokens", "path": "tokens", "type": "list"},
                ],
                prompt_template="""规范化用户输入的研究主题:
原始主题: {raw_topic}
长度: {topic_length}

请以 JSON 格式输出:
{
  "topic": "规范化后的主题",
  "tokens": ["token1", "token2", "token3"]
}""",
            ),
            StepDefinition(
                step_id="fetch",
                name="拉取数据",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_mathlib_search"},
                param_inputs=[
                    {"target": "query", "source": "$node.normalize.normalized_topic", "default": ""},
                    {"target": "max_results", "source": "$node.normalize.tokens", "transform": "length", "default": 3},
                ],
                param_outputs=[
                    {"name": "fetched_results", "path": "results", "type": "list"},
                ],
            ),
            StepDefinition(
                step_id="report",
                name="生成报告",
                step_type=StepType.AGENT,
                prompt_template="""基于规范化主题和搜索结果生成报告:

主题: $node.normalize.normalized_topic
搜索词数: $node.normalize.tokens
搜索结果: $node.fetch.fetched_results

输出 Markdown 报告。""",
            ),
        ],
    )


def lean4_param_chain_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_lean4_param_chain",
        name="Lean4参数链工作流",
        description="Lean4 形式化+证明+优化: 三步通过参数链自动传递 source_code/diagnostics/suggestions",
        checkpoint_after={"formalize", "check", "prove"},
        steps=[
            StepDefinition(
                step_id="formalize",
                name="形式化",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_formalize", "args": {"mode": "autonomous"}},
                param_inputs=[
                    {"target": "informal_spec", "source": "$input.spec", "default": ""},
                    {"target": "target_file", "source": "$input.file", "default": "Theorem.lean"},
                ],
                param_outputs=[
                    {"name": "code", "path": "code", "type": "string"},
                    {"name": "file_path", "path": "file_path", "type": "string"},
                ],
            ),
            StepDefinition(
                step_id="check",
                name="编译检查",
                step_type=StepType.LEAN_CHECK,
                config={"timeout": 60},
                param_inputs=[
                    {"target": "code", "source": "$node.formalize.code", "default": ""},
                ],
                prompt_template="{code}",
            ),
            StepDefinition(
                step_id="prove",
                name="引导证明",
                step_type=StepType.TOOL,
                config={"tool_name": "lean4_prove", "args": {"max_cycles": 8}},
                param_inputs=[
                    {"target": "file_path", "source": "$node.formalize.file_path", "default": "Theorem.lean"},
                ],
                param_outputs=[
                    {"name": "proof_status", "path": "status", "type": "string"},
                ],
            ),
            StepDefinition(
                step_id="report",
                name="报告",
                step_type=StepType.AGENT,
                prompt_template="""Lean4 形式化+证明结果:

形式化代码:
{node_outputs}

证明状态: $node.prove.proof_status

请生成总结报告。""",
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
    "gt_basic_prove": gt_basic_prove_workflow(),
    "gt_evolution_prove": gt_evolution_prove_workflow(),
    "lean4_proof_check": lean4_proof_check_workflow(),
    "lean4_lake_build": lean4_lake_build_workflow(),
    "lean4_formalize": lean4_formalize_workflow(),
    "lean4_golf": lean4_golf_workflow(),
    "manim_animation": manim_animation_workflow(),
    "manim_rag_search": manim_rag_search_workflow(),
    "manim_pipeline": manim_pipeline_workflow(),
    "manim_self_improve": manim_self_improve_workflow(),
    "mathlens_video": mathlens_video_workflow(),
    "autoresearch": autoresearch_workflow(),
    "param_chain_demo": param_chain_demo_workflow(),
    "lean4_param_chain": lean4_param_chain_workflow(),
}


def get_workflow(workflow_id: str) -> WorkflowDefinition:
    if workflow_id in WORKFLOW_REGISTRY:
        return WORKFLOW_REGISTRY[workflow_id]
    raise KeyError(f"未知工作流: {workflow_id}")


def list_workflows() -> Dict[str, str]:
    return {
        wf_id: wf.description for wf_id, wf in WORKFLOW_REGISTRY.items()
    }


def register_workflow(wf: WorkflowDefinition, registry_key: Optional[str] = None):
    WORKFLOW_REGISTRY[registry_key or wf.workflow_id] = wf


__all__ = [
    "code_analysis_workflow", "research_workflow",
    "note_generation_workflow", "code_review_workflow",
    "dependency_scan_workflow",
    "WORKFLOW_REGISTRY", "get_workflow", "list_workflows",
    "register_workflow",
]