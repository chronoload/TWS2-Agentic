"""deepseek-harness 类 TS monorepo 审计策略（自演化配置，零特化演示）。

针对 deepseek-harness（@deepseek-ai/dsh-* 包，vendored Cordis 插件总线）的语义表：
- known_type_files：核心 TS 类型 → 源文件（import 反查失败时的兜底）
- helper_return_types：已知 helper/工厂的返回类型约定
- resolve_type_file 覆写：TS 项目源文件后缀是 .ts 而非 .py

macdev 内核不含项目语义；本项目通过继承 ChainStrategy 注册自己的语义表，
`build_engine` import 本模块即被 Registry.discover 扫描捕捉（namespace=audit.strategy）。
"""
from __future__ import annotations

from .strategy import ChainStrategy


class DshChainStrategy(ChainStrategy):
    name = "dsh"

    # 已知核心类型 → 源文件（import 反查失败时的兜底；deepseek-harness 包结构 packages/<group>/<pkg>/src）
    known_type_files = {
        # core：产品 API 主干
        "Session": "packages/core/session/src/index.ts",
        "SessionConfig": "packages/core/session/src/index.ts",
        "Agent": "packages/core/agent/src/index.ts",
        "AgentConfig": "packages/core/agent/src/index.ts",
        "AgentLoop": "packages/core/agent-loop/src/index.ts",
        "AgentContext": "packages/core/agent/src/index.ts",
        "SystemPrompt": "packages/core/system-prompt/src/index.ts",
        "Tool": "packages/core/tools/src/index.ts",
        "ToolResult": "packages/core/tools/src/index.ts",
        # llm：LLM 能力
        "LLMService": "packages/llm/llm/src/index.ts",
        "LLMProvider": "packages/llm/llm/src/index.ts",
        "DeepSeekProvider": "packages/llm/llm-deepseek/src/index.ts",
        # shell / fs / subprocess：能力平面
        "BashProvider": "packages/shell/bash-local/src/index.ts",
        "ShellConsumer": "packages/shell/shell/src/index.ts",
        "FileSystem": "packages/fs/fs/src/index.ts",
        "Subprocess": "packages/subprocess/subprocess/src/index.ts",
        # skill / web / session-query / workflow
        "SkillProvider": "packages/skill/skill/src/index.ts",
        "WebSearchProvider": "packages/web/web/src/index.ts",
        "SessionQuery": "packages/session-query/session-query/src/index.ts",
        "Workflow": "packages/workflow/workflow/src/index.ts",
        # sandbox / storage / typert
        "Sandbox": "packages/sandbox/sandbox/src/index.ts",
        "Storage": "packages/storage/storage/src/index.ts",
        "TypeRegistry": "packages/typert/registry/src/index.ts",
    }

    # 已知 helper/工厂的返回类型约定（跨文件变量流简化）
    helper_return_types = {
        "createSession": "Session",
        "createAgent": "Agent",
        "createAgentLoop": "AgentLoop",
        "createLLMService": "LLMService",
        "createTool": "Tool",
        "createSkillProvider": "SkillProvider",
        "createSandbox": "Sandbox",
        "createStorage": "Storage",
        "createWorkflow": "Workflow",
        "loadSession": "Session",
        "getProvider": "LLMProvider",
    }

    # 常见局部变量别名 → 类型（来自代码语义约定）
    type_aliases = {
        "ctx": "AgentContext",
        "session": "Session",
        "agent": "Agent",
        "loop": "AgentLoop",
        "llm": "LLMService",
        "provider": "LLMProvider",
        "fs": "FileSystem",
        "sandbox": "Sandbox",
        "storage": "Storage",
        "wf": "Workflow",
    }

    # 已知 helper 的形参类型约定（用于方法调用归属）
    param_type_hints = {
        "createSession": {"config": "SessionConfig"},
        "createAgent": {"context": "AgentContext", "llm": "LLMService"},
        "createAgentLoop": {"agent": "Agent"},
        "loadSession": {"id": "string"},
        "getProvider": {"name": "string"},
    }

    def resolve_type_file(self, type_name: str, import_map: dict) -> str:
        """覆写：TS 项目类型解析（import 映射可能含 @deepseek-ai/dsh-<pkg> → packages/<group>/<pkg>/src）。"""
        if type_name in self.known_type_files:
            return self.known_type_files[type_name]
        if type_name in import_map:
            mod = import_map[type_name]
            # @deepseek-ai/dsh-<pkg> → packages/<group>/<pkg>/src/index.ts（组名需回查，取兜底约定）
            if mod.startswith("@deepseek-ai/dsh-"):
                pkg = mod.split("/")[1].replace("dsh-", "")
                return f"packages/*/{pkg}/src/index.ts"
            return mod.replace(".", "/") + ".ts"
        return ""
