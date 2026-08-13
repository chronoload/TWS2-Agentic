"""子代理/团队成员的提示词构建模块。

本模块负责生成两类 Agent 的系统提示词，对应 Cline 中
subagent-prompts.ts（子代理提示词）与 agent teams（团队成员提示词）的
结构划分：
- build_subagent_system_prompt：普通子代理（SubAgent），由 Lead 单次委派执行；
- build_teammate_system_prompt：团队成员（Teammate），加入团队协作流程，
  比子代理多了团队目标对齐与团队协作规则。

两个函数都以"逐段拼接 parts 列表"的方式组装提示词，最终用换行符连接，
便于按需增删片段；未传入的可选参数（cwd/team_goal/extra_instructions）
会直接跳过对应片段，保证提示词简洁。
"""

from __future__ import annotations


def build_subagent_system_prompt(role: str, cwd: str = "", extra_instructions: str = "") -> str:
    """构建"子代理（SubAgent）"的系统提示词

    对应 Cline 中 subagent-prompts.ts 为普通子代理生成的系统提示词：
    - 子代理由主 Agent（Lead）单次委派，聚焦执行分配给自己的任务；
    - 结构：身份定位 -> 工作目录 -> 约束（越权/只读优先/汇报格式）-> 附加指令；
    - 参数说明：
        role                当前承担的角色名（如 coder/review），写入身份定位；
        cwd                 工作目录，非空时要求所有操作以其为基准；
        extra_instructions  额外的自定义指令，追加到"## 附加指令"节。
    """
    parts = [
        f"你是子代理（SubAgent），当前承担角色：{role}。",
        "你由主 Agent（Lead）委派，专注于执行分配给你的任务，无需处理职责之外的事项。",
    ]
    # 指定工作目录时追加目录约束，保证子代理操作范围与主 Agent 一致
    if cwd:
        parts.append(f"工作目录：{cwd}。你的所有操作都应以该目录为基准。")
    parts.append("## 约束")
    parts.append("- 不可越权：只执行分配的任务，不得擅自启动后台进程、修改系统配置或调用未授权的工具。")
    parts.append("- 只读优先：默认先使用只读操作（读取、搜索、分析），确需写入或修改时先说明目的与影响。")
    parts.append("- 汇报格式：完成后以结构化摘要汇报，包含结论、关键依据与后续建议。")
    # 仅当调用方传入附加指令时才追加该节，保持无附加指令时提示词精简
    if extra_instructions:
        parts.append("## 附加指令")
        parts.append(extra_instructions)
    return "\n".join(parts)


def build_teammate_system_prompt(role: str, team_goal: str = "", cwd: str = "", extra_instructions: str = "") -> str:
    """构建"团队成员（Teammate Agent）"的系统提示词

    对应 Cline AgentTeam（agent teams）中 teammate 角色的系统提示词：
    与 build_subagent_system_prompt 相比，差异在于：
    - 新增"团队目标"定位：teammate 服务于团队整体目标，而非单次委派任务；
    - 新增"团队协作规则"节：包含任务接收（复述目标/验收标准）、结果回报、
      失败上报三类协作约定，体现 teammate 与 Lead 之间持续的双向协作关系；
    - 结构：身份定位 -> 团队目标 -> 工作目录 -> 约束 -> 团队协作规则 -> 附加指令；
    - 参数说明：
        role                当前承担的角色名（如 coder/task），写入身份定位；
        team_goal           团队整体目标，非空时写入以对齐工作方向；
        cwd                 工作目录，非空时要求所有操作以其为基准；
        extra_instructions  额外的自定义指令，追加到"## 附加指令"节。
    """
    parts = [f"你是团队成员（Teammate Agent），当前承担角色：{role}。"]
    # 与子代理不同：teammate 先对齐团队目标，再落位工作目录
    if team_goal:
        parts.append(f"团队目标：{team_goal}。你的工作服务于该目标。")
    if cwd:
        parts.append(f"工作目录：{cwd}。你的所有操作都应以该目录为基准。")
    parts.append("## 约束")
    parts.append("- 不可越权：只执行被指派的团队任务，不得擅自扩大职责范围或调用未授权的工具。")
    parts.append("- 只读优先：默认先使用只读操作（读取、搜索、分析），确需写入或修改时先说明目的与影响。")
    parts.append("- 汇报格式：结果按团队约定格式汇报，包含产出、关键假设与风险。")
    parts.append("## 团队协作规则")
    parts.append("- 任务接收：接到 Lead 派发的任务后，先复述任务目标与验收标准，确认无误后再执行。")
    parts.append("- 结果回报：完成后及时向 Lead 汇报，说明产出内容、完成方式与遗留问题。")
    parts.append("- 失败上报：遇到阻塞、异常或失败，立即上报 Lead，说明原因并提出可选的替代方案。")
    # 仅当调用方传入附加指令时才追加该节，保持无附加指令时提示词精简
    if extra_instructions:
        parts.append("## 附加指令")
        parts.append(extra_instructions)
    return "\n".join(parts)
