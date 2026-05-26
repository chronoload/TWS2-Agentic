"""LLM provider layer - single unified module.

Contains:
- Core types: ToolCall, LLMResponse
- LLM class (OpenAI-compatible API)
- SimulatorLLM (testing)
- LiteLLM (100+ providers)
- MultiProviderManager (fallback across providers)
- MCP protocol (MCPTool, MCPToolCall, MCPServer, MCPClient)
- Provider configs, model info, pricing
- Sanitize helpers (inline, no external deps)

IMPORTANT: on_token signature is Callable[[str], Any] (single param) everywhere.
"""

import json
import logging
import time
import uuid
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Callable, Any, List, Dict, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logger.warning("openai package not installed; will use simulator")


# ============================================================
# 安全工具函数
# ============================================================

def _safe_parse_args(args_str: str) -> dict:
    """安全解析工具调用参数字符串为 dict。"""
    if not args_str or not isinstance(args_str, str) or args_str.strip() == "":
        return {}
    try:
        result = json.loads(args_str)
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, ValueError, KeyError):
        return _try_repair_json(args_str)


def _try_repair_json(raw: str) -> dict:
    """尝试修复损坏的 JSON 字符串并解析为 dict。"""
    if not raw or not isinstance(raw, str):
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    for end_pos in range(len(raw), 0, -1):
        candidate = raw[:end_pos]
        stripped = candidate.rstrip()
        if stripped.endswith(":") or stripped.endswith(","):
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            return json.loads(candidate + "}")
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            return json.loads(candidate + "}}")
        except (json.JSONDecodeError, ValueError):
            continue
    cleaned = ""
    for ch in raw:
        if ord(ch) >= 0x20 or ch in "\n\r\t":
            cleaned += ch
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass
    for end_pos in range(len(cleaned), 0, -1):
        candidate = cleaned[:end_pos]
        stripped = candidate.rstrip()
        if stripped.endswith(":") or stripped.endswith(","):
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    logger.warning(f"[_try_repair_json] 无法修复损坏的 JSON: {raw[:100]}...")
    return {}


def _safe_tool_name(name: str) -> str:
    """确保工具名称不为空。"""
    if not name or not isinstance(name, str) or not name.strip():
        return "unknown_tool"
    return name


def _safe_tool_id(tool_id: str) -> str:
    """确保 tool_call_id 不为空，为空时生成 UUID。"""
    if not tool_id or not isinstance(tool_id, str) or not tool_id.strip():
        return f"call_{uuid.uuid4().hex[:12]}"
    return tool_id


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Ensure all content fields are strings, not null/None.
    Also ensures tool_call_id is never None (empty string is acceptable)."""
    if not messages:
        return []
    sanitized = []
    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content")
        if content is None:
            msg_copy["content"] = ""
        elif isinstance(content, list):
            cleaned_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text" and part.get("text") is None:
                        part = dict(part)
                        part["text"] = ""
                    cleaned_parts.append(part)
                else:
                    cleaned_parts.append(part)
            msg_copy["content"] = cleaned_parts
        # 确保 tool_call_id 不为 None（API 要求 string 类型）
        if msg_copy.get("role") == "tool" and msg_copy.get("tool_call_id") is None:
            msg_copy["tool_call_id"] = ""
        sanitized.append(msg_copy)
    return sanitized


# ============================================================
# 核心数据类型
# ============================================================

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    finish_reason: str = ""

    @property
    def message(self) -> dict:
        """Convert to OpenAI message format for appending to history."""
        msg: dict = {"role": "assistant", "content": self.content or ""}
        if self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


# Pricing per million tokens: (input, output)
_PRICING = {
    "gpt-5.4": (2.5, 15),
    "gpt-5.4-mini": (0.75, 4.5),
    "gpt-5.4-nano": (0.2, 1.25),
    "o4-mini": (1.1, 4.4),
    "gpt-4.1": (2, 8),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "gpt-4o": (2.5, 10),
    "gpt-4o-mini": (0.15, 0.6),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "claude-opus-4-6": (5, 25),
    "claude-sonnet-4-6": (3, 15),
    "claude-haiku-4-5": (1, 5),
    "qwen3-max": (0.78, 3.9),
    "qwen3-plus": (0.26, 0.78),
    "qwen-max": (0.78, 3.9),
    "kimi-k2.5": (0.6, 3),
    "mimo-v2.5-pro": (2.0, 10.0),
    "mimo-v2.5": (1.0, 5.0),
    "mimo-v2-flash": (0.1, 0.5),
    "mimo-v2-pro": (1.5, 7.5),
    "mimo-v2-omni": (1.0, 5.0),
}


# ============================================================
# 提供商类型与配置（从 llm_providers.py 合并）
# ============================================================

class ProviderType(str, Enum):
    """LLM 提供商类型"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CLAUDE_CODE = "claude-code"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    QWEN_CODE = "qwen-code"
    DOUBAO = "doubao"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    LM_STUDIO = "lm-studio"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    BEDROCK = "bedrock"
    VERTEX = "vertex"
    LITELLM = "litellm"
    GROQ = "groq"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    XAI = "xai"
    MOONSHOT = "moonshot"
    NEBIUS = "nebius"
    HUGGINGFACE = "huggingface"
    HUAWEI_MAAS = "huawei-maas"
    DIFY = "dify"
    BASETEN = "baseten"
    VERCEL_AI = "vercel-ai"
    ZAI = "zai"
    OCA = "oca"
    AIHUBMIX = "aihubmix"
    MINIMAX = "minimax"
    HICAP = "hicap"
    NOUS_RESEARCH = "nous-research"
    WANDB = "wandb"
    MIMO = "mimo"
    CUSTOM = "custom"
    SIMULATOR = "simulator"


PROVIDER_DISPLAY_NAMES = {
    ProviderType.OPENAI: "OpenAI",
    ProviderType.ANTHROPIC: "Anthropic (Claude)",
    ProviderType.CLAUDE_CODE: "Claude Code",
    ProviderType.DEEPSEEK: "DeepSeek",
    ProviderType.QWEN: "Qwen (通义千问)",
    ProviderType.QWEN_CODE: "Qwen Code",
    ProviderType.DOUBAO: "豆包",
    ProviderType.MISTRAL: "Mistral",
    ProviderType.OLLAMA: "Ollama (本地)",
    ProviderType.LM_STUDIO: "LM Studio (本地)",
    ProviderType.GEMINI: "Google Gemini",
    ProviderType.OPENROUTER: "OpenRouter",
    ProviderType.BEDROCK: "AWS Bedrock",
    ProviderType.VERTEX: "Google Vertex AI",
    ProviderType.LITELLM: "LiteLLM (多模型)",
    ProviderType.GROQ: "Groq",
    ProviderType.TOGETHER: "Together AI",
    ProviderType.FIREWORKS: "Fireworks AI",
    ProviderType.XAI: "xAI (Grok)",
    ProviderType.MOONSHOT: "Moonshot (月之暗面)",
    ProviderType.NEBIUS: "Nebius",
    ProviderType.HUGGINGFACE: "Hugging Face",
    ProviderType.HUAWEI_MAAS: "华为盘古 MaaS",
    ProviderType.DIFY: "Dify",
    ProviderType.BASETEN: "Baseten",
    ProviderType.VERCEL_AI: "Vercel AI",
    ProviderType.ZAI: "ZAI",
    ProviderType.OCA: "OCA",
    ProviderType.AIHUBMIX: "AI Hub Mix",
    ProviderType.MINIMAX: "MiniMax",
    ProviderType.HICAP: "HiCap",
    ProviderType.NOUS_RESEARCH: "Nous Research",
    ProviderType.WANDB: "Weights & Biases",
    ProviderType.MIMO: "小米 MiMo",
    ProviderType.CUSTOM: "自定义 API",
    ProviderType.SIMULATOR: "模拟器 (测试用)",
}


PROVIDER_DEFAULT_BASE_URL = {
    ProviderType.OPENAI: "https://api.openai.com/v1",
    ProviderType.ANTHROPIC: "https://api.anthropic.com",
    ProviderType.CLAUDE_CODE: "https://api.anthropic.com",
    ProviderType.DEEPSEEK: "https://api.deepseek.com/v1",
    ProviderType.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ProviderType.QWEN_CODE: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ProviderType.DOUBAO: "https://ark.cn-beijing.volces.com/api/v3",
    ProviderType.MISTRAL: "https://api.mistral.ai/v1",
    ProviderType.OLLAMA: "http://localhost:11434/v1",
    ProviderType.LM_STUDIO: "http://localhost:1234/v1",
    ProviderType.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    ProviderType.OPENROUTER: "https://openrouter.ai/api/v1",
    ProviderType.GROQ: "https://api.groq.com/openai/v1",
    ProviderType.TOGETHER: "https://api.together.xyz/v1",
    ProviderType.FIREWORKS: "https://api.fireworks.ai/inference/v1",
    ProviderType.XAI: "https://api.x.ai/v1",
    ProviderType.MOONSHOT: "https://api.moonshot.cn/v1",
    ProviderType.NEBIUS: "https://api.studio.nebius.ai/v1",
    ProviderType.HUGGINGFACE: "https://api-inference.huggingface.co/models",
    ProviderType.DIFY: "",
    ProviderType.BASETEN: "https://api.baseten.ai/v1",
    ProviderType.ZAI: "https://api.zai.ai/v1",
    ProviderType.MINIMAX: "https://api.minimax.chat/v1",
    ProviderType.HICAP: "",
    ProviderType.MIMO: "https://api.xiaomimimo.com/v1",
}


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    provider: ProviderType
    max_tokens: int = 4096
    context_window: int = 8192
    pricing_input: float = 0.0
    pricing_output: float = 0.0
    supports_tools: bool = True
    supports_streaming: bool = True
    is_reasoning_model: bool = False


PROVIDER_DEFAULT_MODELS: Dict[ProviderType, List[str]] = {
    ProviderType.OPENAI: ["gpt-5.4", "gpt-5.4-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "o3-mini"],
    ProviderType.ANTHROPIC: ["claude-3-5-sonnet-20241022", "claude-3-opus", "claude-3-sonnet"],
    ProviderType.CLAUDE_CODE: ["claude-3-5-sonnet-20241022"],
    ProviderType.DEEPSEEK: ["deepseek-chat", "deepseek-reasoner"],
    ProviderType.QWEN: ["qwen-max", "qwen-plus", "qwen-turbo"],
    ProviderType.QWEN_CODE: ["qwen-coder-turbo"],
    ProviderType.DOUBAO: ["doubao-pro-32k", "doubao-lite-32k"],
    ProviderType.MISTRAL: ["mistral-large-2411", "mistral-small-2503"],
    ProviderType.OLLAMA: ["llama3.3", "qwen2.5", "gemma2"],
    ProviderType.LM_STUDIO: ["local-model"],
    ProviderType.GEMINI: ["gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro"],
    ProviderType.OPENROUTER: ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
    ProviderType.GROQ: ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    ProviderType.TOGETHER: ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    ProviderType.FIREWORKS: ["accounts/fireworks/models/llama-v3p3-70b-instruct"],
    ProviderType.XAI: ["grok-3-latest"],
    ProviderType.MOONSHOT: ["moonshot-v1-128k", "moonshot-v1-32k"],
    ProviderType.NEBIUS: ["nebius/llama-3-70b"],
    ProviderType.HUGGINGFACE: ["HuggingFaceH4/zephyr-7b-beta"],
    ProviderType.DIFY: ["dify-model"],
    ProviderType.BASETEN: ["llama-3-70b"],
    ProviderType.ZAI: ["zai/glm-4.6"],
    ProviderType.MINIMAX: ["abab6.5-s", "abab6.5-chat"],
    ProviderType.HICAP: ["hicap-model"],
    ProviderType.OCA: ["oca/llama-3-70b"],
    ProviderType.AIHUBMIX: ["aihubmix-model"],
    ProviderType.NOUS_RESEARCH: ["nousresearch/hermes-3-llama-3.1-70b"],
    ProviderType.WANDB: ["wandb-model"],
    ProviderType.MIMO: ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-flash", "mimo-v2-pro", "mimo-v2-omni"],
    ProviderType.LITELLM: ["gpt-4o-mini"],
    ProviderType.CUSTOM: ["custom-model"],
    ProviderType.SIMULATOR: ["simulator"],
}


DEFAULT_MODEL_INFOS: Dict[str, ModelInfo] = {
    "gpt-5.4": ModelInfo(name="gpt-5.4", provider=ProviderType.OPENAI, max_tokens=8192, context_window=128000, pricing_input=2.5, pricing_output=15.0, is_reasoning_model=True),
    "gpt-5.4-mini": ModelInfo(name="gpt-5.4-mini", provider=ProviderType.OPENAI, max_tokens=8192, context_window=128000, pricing_input=0.75, pricing_output=4.5),
    "gpt-4.1": ModelInfo(name="gpt-4.1", provider=ProviderType.OPENAI, max_tokens=8192, context_window=128000, pricing_input=2.0, pricing_output=8.0),
    "gpt-4o": ModelInfo(name="gpt-4o", provider=ProviderType.OPENAI, max_tokens=4096, context_window=128000, pricing_input=2.5, pricing_output=10.0),
    "gpt-4o-mini": ModelInfo(name="gpt-4o-mini", provider=ProviderType.OPENAI, max_tokens=4096, context_window=128000, pricing_input=0.15, pricing_output=0.6),
    "o3-mini": ModelInfo(name="o3-mini", provider=ProviderType.OPENAI, max_tokens=100000, context_window=200000, pricing_input=1.1, pricing_output=4.4, is_reasoning_model=True),
    "deepseek-chat": ModelInfo(name="deepseek-chat", provider=ProviderType.DEEPSEEK, max_tokens=4096, context_window=128000, pricing_input=0.27, pricing_output=1.10),
    "deepseek-reasoner": ModelInfo(name="deepseek-reasoner", provider=ProviderType.DEEPSEEK, max_tokens=4096, context_window=128000, pricing_input=0.55, pricing_output=2.19, is_reasoning_model=True),
    "claude-3-5-sonnet-20241022": ModelInfo(name="claude-3-5-sonnet-20241022", provider=ProviderType.ANTHROPIC, max_tokens=8192, context_window=200000, pricing_input=3.0, pricing_output=15.0),
    "qwen-max": ModelInfo(name="qwen-max", provider=ProviderType.QWEN, max_tokens=4096, context_window=32000, pricing_input=0.78, pricing_output=3.9),
    "qwen-plus": ModelInfo(name="qwen-plus", provider=ProviderType.QWEN, max_tokens=4096, context_window=128000, pricing_input=0.26, pricing_output=0.78),
    "gemini-3-pro-preview": ModelInfo(name="gemini-3-pro-preview", provider=ProviderType.GEMINI, max_tokens=8192, context_window=1048576, pricing_input=2.0, pricing_output=12.0),
    "gemini-3-flash-preview": ModelInfo(name="gemini-3-flash-preview", provider=ProviderType.GEMINI, max_tokens=65536, context_window=1048576, pricing_input=0.5, pricing_output=3.0),
    "moonshot-v1-128k": ModelInfo(name="moonshot-v1-128k", provider=ProviderType.MOONSHOT, max_tokens=4096, context_window=128000, pricing_input=6.0, pricing_output=12.0),
    "llama-3.3-70b-versatile": ModelInfo(name="llama-3.3-70b-versatile", provider=ProviderType.GROQ, max_tokens=8192, context_window=128000, pricing_input=0.29, pricing_output=0.79),
    "mimo-v2.5-pro": ModelInfo(name="mimo-v2.5-pro", provider=ProviderType.MIMO, max_tokens=131072, context_window=131072, pricing_input=2.0, pricing_output=10.0, is_reasoning_model=True),
    "mimo-v2.5": ModelInfo(name="mimo-v2.5", provider=ProviderType.MIMO, max_tokens=32768, context_window=131072, pricing_input=1.0, pricing_output=5.0, is_reasoning_model=True),
    "mimo-v2-flash": ModelInfo(name="mimo-v2-flash", provider=ProviderType.MIMO, max_tokens=65536, context_window=131072, pricing_input=0.1, pricing_output=0.5),
    "mimo-v2-pro": ModelInfo(name="mimo-v2-pro", provider=ProviderType.MIMO, max_tokens=131072, context_window=131072, pricing_input=1.5, pricing_output=7.5, is_reasoning_model=True),
    "mimo-v2-omni": ModelInfo(name="mimo-v2-omni", provider=ProviderType.MIMO, max_tokens=32768, context_window=131072, pricing_input=1.0, pricing_output=5.0),
}


@dataclass
class ProviderConfig:
    """API 提供商配置"""
    provider: ProviderType
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120
    enabled: bool = True
    priority: int = 0
    name: str = ""
    thinking_enabled: Optional[bool] = None

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.provider.value}-{self.model}"

    @property
    def model_info(self) -> ModelInfo:
        if self.model in DEFAULT_MODEL_INFOS:
            return DEFAULT_MODEL_INFOS[self.model]
        return ModelInfo(name=self.model, provider=self.provider, max_tokens=self.max_tokens, context_window=8192)


def get_models_for_provider(provider: ProviderType) -> List[ModelInfo]:
    models = []
    for name in PROVIDER_DEFAULT_MODELS.get(provider, []):
        if name in DEFAULT_MODEL_INFOS:
            models.append(DEFAULT_MODEL_INFOS[name])
        else:
            models.append(ModelInfo(name=name, provider=provider, max_tokens=4096, context_window=8192))
    return models


def create_default_provider_config(provider: ProviderType, api_key: str = "") -> ProviderConfig:
    default_models = PROVIDER_DEFAULT_MODELS.get(provider, [""])
    default_model = default_models[0] if default_models else ""
    base_url = PROVIDER_DEFAULT_BASE_URL.get(provider, "")
    return ProviderConfig(
        provider=provider, api_key=api_key, base_url=base_url,
        model=default_model, name=f"{PROVIDER_DISPLAY_NAMES.get(provider, provider.value)} Default"
    )


# ============================================================
# MCP 协议（从 protocol.py 合并）
# ============================================================

@dataclass
class MCPResource:
    """MCP 资源对象"""
    uri: str
    name: str
    description: str
    content: Optional[str] = None
    mime_type: str = "text/plain"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


@dataclass
class MCPToolCall:
    """MCP 工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    result: Optional[Any] = None
    success: bool = True
    error: Optional[str] = None


class MCPServer:
    """MCP 服务器 - 管理工具和资源"""

    def __init__(self, name: str = "WS2-MCP-Server"):
        self.name = name
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.call_history: List[MCPToolCall] = []
        logger.info(f"初始化 MCP 服务器: {name}")

    def register_tool(self, tool: MCPTool) -> None:
        self.tools[tool.name] = tool
        logger.info(f"工具已注册: {tool.name}")

    def register_resource(self, resource: MCPResource) -> None:
        self.resources[resource.uri] = resource
        logger.info(f"资源已注册: {resource.uri}")

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_dict() for tool in self.tools.values()]

    def list_resources(self) -> List[Dict[str, Any]]:
        return [{"uri": r.uri, "name": r.name, "description": r.description, "mimeType": r.mime_type} for r in self.resources.values()]

    async def call_tool(self, call: MCPToolCall) -> Any:
        if call.name not in self.tools:
            call.success = False
            call.error = f"工具不存在: {call.name}"
            self.call_history.append(call)
            raise ValueError(call.error)
        tool = self.tools[call.name]
        if not tool.handler:
            call.success = False
            call.error = f"工具 {call.name} 没有实现"
            self.call_history.append(call)
            raise ValueError(call.error)
        try:
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**call.arguments)
            else:
                result = tool.handler(**call.arguments)
            call.result = result
            call.success = True
            self.call_history.append(call)
            return result
        except Exception as e:
            call.success = False
            call.error = str(e)
            self.call_history.append(call)
            raise

    async def read_resource(self, uri: str) -> Optional[MCPResource]:
        return self.resources.get(uri)


class MCPClient:
    """MCP 客户端"""

    def __init__(self, server: MCPServer):
        self.server = server
        logger.info(f"初始化 MCP 客户端, 连接到: {server.name}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        return self.server.list_tools()

    async def list_resources(self) -> List[Dict[str, Any]]:
        return self.server.list_resources()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        call = MCPToolCall(id=str(uuid.uuid4()), name=name, arguments=arguments)
        return await self.server.call_tool(call)

    async def read_resource(self, uri: str) -> Optional[MCPResource]:
        return await self.server.read_resource(uri)


# ============================================================
# LLM 基类
# ============================================================

class BaseLLMProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_token: Optional[Callable[[str], Any]] = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @property
    def estimated_cost(self) -> Optional[float]:
        info = self.config.model_info
        if info.pricing_input == 0 and info.pricing_output == 0:
            return None
        return (self.total_prompt_tokens * info.pricing_input / 1_000_000 +
                self.total_completion_tokens * info.pricing_output / 1_000_000)


# ============================================================
# LLM 类（OpenAI 兼容 API）
# ============================================================

class LLM(BaseLLMProvider):
    """OpenAI 兼容 API 提供商"""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 120,
        **kwargs,
    ):
        config = ProviderConfig(
            provider=ProviderType.OPENAI,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        super().__init__(config)
        self.extra = kwargs
        self.client = None
        self._init_client()

    def _init_client(self):
        if HAS_OPENAI:
            base_url = self.config.base_url or "https://api.openai.com/v1"
            kwargs = {"api_key": self.config.api_key, "base_url": base_url, "timeout": self.config.timeout}
            if self.config.provider == ProviderType.MIMO:
                kwargs["default_headers"] = {"api-key": self.config.api_key}
            self.client = OpenAI(**kwargs)
        else:
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """简单的文本生成接口"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self.chat(messages)
        return response.content

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_token: Callable[[str], Any] | None = None,
    ) -> LLMResponse:
        if not self.client:
            return self._simulate_response(messages)

        safe_messages = _sanitize_messages(messages)

        # === DEBUG: 打印即将发送的消息 ===
        print("\n" + "=" * 70, flush=True)
        print(f"[LLM.chat] >>> 发送给 {self.config.model} ({self.config.provider.value})", flush=True)
        print(f"[LLM.chat] >>> 消息数: {len(safe_messages)}", flush=True)
        for i, msg in enumerate(safe_messages):
            role = msg.get("role", "?")
            content_preview = str(msg.get("content", ""))[:120]
            has_tc = "tool_calls" in msg
            tc_id = msg.get("tool_call_id", "")
            print(f"  [{i}] role={role} content={content_preview!r} tc={has_tc} tcid={tc_id!r}", flush=True)
        if tools:
            print(f"[LLM.chat] >>> tools: {len(tools)} 个工具定义", flush=True)
        print("=" * 70 + "\n", flush=True)
        # === END DEBUG ===

        params: dict = {
            "model": self.config.model,
            "messages": safe_messages,
            "stream": True,
            "temperature": self.config.temperature,
            **self.extra,
        }

        if self.config.provider == ProviderType.MIMO:
            thinking = self.config.thinking_enabled
            if thinking is None:
                thinking = self.config.model_info.is_reasoning_model
            extra_body = {"max_completion_tokens": min(self.config.max_tokens, self.config.model_info.max_tokens)}
            if thinking:
                extra_body["thinking"] = {"type": "enabled"}
            else:
                extra_body["thinking"] = {"type": "disabled"}
            if thinking and self.config.model in ("mimo-v2.5-pro", "mimo-v2.5"):
                params.pop("temperature", None)
        else:
            params["max_tokens"] = self.config.max_tokens
            extra_body = None
        if tools:
            params["tools"] = tools

        try:
            params["stream_options"] = {"include_usage": True}
            stream = self._call_with_retry(params, extra_body=extra_body)
        except Exception:
            params.pop("stream_options", None)
            stream = self._call_with_retry(params, extra_body=extra_body)

        return self._process_stream(stream, on_token)

    def _process_stream(self, stream, on_token) -> LLMResponse:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_map: dict[int, dict] = {}
        prompt_tok = 0
        completion_tok = 0
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            if chunk is None:
                continue
            usage = getattr(chunk, "usage", None)
            if usage:
                prompt_tok = getattr(usage, "prompt_tokens", 0) or 0
                completion_tok = getattr(usage, "completion_tokens", 0) or 0
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            if delta is None:
                continue
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                reasoning_parts.append(delta.reasoning_content)
                if on_token:
                    on_token(delta.reasoning_content)
            if delta.content is not None:
                content_parts.append(delta.content)
                if on_token:
                    on_token(delta.content)
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    if tc_delta is None:
                        continue
                    idx = getattr(tc_delta, "index", None)
                    if idx is None:
                        idx = len(tc_map)
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    if tc_delta.id:
                        tc_map[idx]["id"] = tc_delta.id
                    func = getattr(tc_delta, "function", None)
                    if func:
                        if getattr(func, "name", None):
                            tc_map[idx]["name"] = func.name
                        if getattr(func, "arguments", None):
                            tc_map[idx]["args"] += func.arguments

        if chunk_count == 0:
            logger.warning("[LLM._process_stream] stream produced 0 chunks")
            return LLMResponse(content="", tool_calls=[])

        parsed: list[ToolCall] = []
        for idx in sorted(tc_map):
            raw = tc_map[idx]
            args = _safe_parse_args(raw.get("args", ""))
            tool_id = _safe_tool_id(raw.get("id", ""))
            tool_name = _safe_tool_name(raw.get("name", ""))
            parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))

        self.total_prompt_tokens += prompt_tok
        self.total_completion_tokens += completion_tok

        return LLMResponse(
            content="".join(content_parts),
            reasoning_content="".join(reasoning_parts),
            tool_calls=parsed,
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
        )

    def _call_with_retry(self, params: dict, max_retries: int = 3, extra_body: dict = None):
        for attempt in range(max_retries):
            try:
                if extra_body:
                    return self.client.chat.completions.create(**params, extra_body=extra_body)
                return self.client.chat.completions.create(**params)
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"Transient error, retrying in {wait}s ({attempt+1}/{max_retries})")
                time.sleep(wait)
            except APIError as e:
                if e.status_code and e.status_code >= 500 and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Server error, retrying in {wait}s ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                else:
                    raise

    def _simulate_response(self, messages: list[dict]) -> LLMResponse:
        time.sleep(0.3)
        last_msg = messages[-1].get("content", "") if messages else "Hello!"
        return LLMResponse(
            content=f"WS2 Agent (simulator)\n\n收到消息: {last_msg}\n\n提示: 配置真实 API 以使用完整功能",
            tool_calls=[], prompt_tokens=0, completion_tokens=0,
        )


class SimulatorLLM(LLM):
    """Simulator LLM for testing."""

    def __init__(self):
        super().__init__(model="simulator", api_key="demo")
        self._counter = 0

    def generate(self, prompt: str, system_prompt: str = None) -> str:
        """模拟的文本生成"""
        self._counter += 1
        responses = [
            f"WS2 Agent 已就绪！\n\n你问: {prompt}\n\n这是模拟响应 #{self._counter}。",
            f"👋 你好！\n\n我可以帮你:\n- 查询课程进度\n- 管理学习内容\n- 分析科研论文\n\n试试问我: '查看总览'",
            f"好的，让我想想...\n\n你的问题很有趣: {prompt}\n\n在真实模式下我会调用工具帮你！",
        ]
        return responses[(self._counter - 1) % len(responses)]

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_token: Callable[[str], Any] | None = None,
    ) -> LLMResponse:
        self._counter += 1
        last_msg = messages[-1].get("content", "") if messages else "Hello!"
        responses = [
            f"WS2 Agent 已就绪！\n\n你问: {last_msg}\n\n这是模拟响应 #{self._counter}。",
            f"👋 你好！\n\n我可以帮你:\n- 查询课程进度\n- 管理学习内容\n- 分析科研论文\n\n试试问我: '查看总览'",
            f"好的，让我想想...\n\n你的问题很有趣: {last_msg}\n\n在真实模式下我会调用工具帮你！",
        ]
        response = responses[(self._counter - 1) % len(responses)]
        if on_token:
            on_token("思考中...")
            time.sleep(0.1)
            on_token(response)
            time.sleep(0.01)
        return LLMResponse(content=response, reasoning_content="思考中...", prompt_tokens=0, completion_tokens=len(response))


class LiteLLM(BaseLLMProvider):
    """LLM backend via LiteLLM, supporting 100+ providers."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ):
        config = ProviderConfig(
            provider=ProviderType.LITELLM,
            api_key=api_key or "",
            base_url=base_url,
            model=model,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        super().__init__(config)
        self.extra = kwargs
        self._check_litellm()

    def _check_litellm(self):
        try:
            import litellm
            self._litellm_available = True
        except ImportError:
            logger.warning("LiteLLM 未安装")
            self._litellm_available = False

    def is_available(self) -> bool:
        return self._litellm_available

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_token: Callable[[str], Any] | None = None,
    ) -> LLMResponse:
        if not self._litellm_available:
            return LLMResponse(content="LiteLLM not installed. Install with: pip install litellm")

        import litellm

        safe_messages = _sanitize_messages(messages)

        # === DEBUG: 打印即将发送的消息 ===
        print("\n" + "=" * 70, flush=True)
        print(f"[LiteLLM.chat] >>> 发送给 {self.config.model} ({self.config.provider.value})", flush=True)
        print(f"[LiteLLM.chat] >>> 消息数: {len(safe_messages)}", flush=True)
        for i, msg in enumerate(safe_messages):
            role = msg.get("role", "?")
            content_preview = str(msg.get("content", ""))[:120]
            has_tc = "tool_calls" in msg
            tc_id = msg.get("tool_call_id", "")
            print(f"  [{i}] role={role} content={content_preview!r} tc={has_tc} tcid={tc_id!r}", flush=True)
        if tools:
            print(f"[LiteLLM.chat] >>> tools: {len(tools)} 个工具定义", flush=True)
        print("=" * 70 + "\n", flush=True)
        # === END DEBUG ===

        params: dict = {
            "model": self.config.model,
            "messages": safe_messages,
            "stream": True,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            **self.extra,
        }
        if self.config.api_key:
            params["api_key"] = self.config.api_key
        if self.config.base_url:
            params["api_base"] = self.config.base_url
        if tools:
            params["tools"] = tools

        try:
            stream = litellm.completion(**params)
            return self._process_stream(stream, on_token)
        except Exception as e:
            logger.error(f"LiteLLM 调用失败: {e}")
            return LLMResponse(content=f"LiteLLM 错误: {e}")

    def _process_stream(self, stream, on_token) -> LLMResponse:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_map: dict[int, dict] = {}
        prompt_tok = 0
        completion_tok = 0
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            if chunk is None:
                continue
            usage = getattr(chunk, "usage", None)
            if usage:
                prompt_tok = getattr(usage, "prompt_tokens", 0) or 0
                completion_tok = getattr(usage, "completion_tokens", 0) or 0
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            if delta is None:
                continue
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                reasoning_parts.append(delta.reasoning_content)
                if on_token:
                    on_token(delta.reasoning_content)
            if getattr(delta, "content", None) is not None:
                content_parts.append(delta.content)
                if on_token:
                    on_token(delta.content)
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    if tc_delta is None:
                        continue
                    idx = getattr(tc_delta, "index", None)
                    if idx is None:
                        idx = len(tc_map)
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    if tc_delta.id:
                        tc_map[idx]["id"] = tc_delta.id
                    func = getattr(tc_delta, "function", None)
                    if func:
                        if getattr(func, "name", None):
                            tc_map[idx]["name"] = func.name
                        if getattr(func, "arguments", None):
                            tc_map[idx]["args"] += func.arguments

        if chunk_count == 0:
            logger.warning("[LiteLLM._process_stream] stream produced 0 chunks")
            return LLMResponse(content="", tool_calls=[])

        parsed: list[ToolCall] = []
        for idx in sorted(tc_map):
            raw = tc_map[idx]
            args = _safe_parse_args(raw.get("args", ""))
            tool_id = _safe_tool_id(raw.get("id", ""))
            tool_name = _safe_tool_name(raw.get("name", ""))
            parsed.append(ToolCall(id=tool_id, name=tool_name, arguments=args))

        self.total_prompt_tokens += prompt_tok
        self.total_completion_tokens += completion_tok

        return LLMResponse(
            content="".join(content_parts),
            reasoning_content="".join(reasoning_parts),
            tool_calls=parsed,
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
        )


class MultiProviderManager:
    """多提供商管理器 - 管理多个 LLM 提供商，支持故障转移"""

    def __init__(self, configs: List[ProviderConfig]):
        self.providers: List[BaseLLMProvider] = []
        self.total_cost = 0.0
        self._init_providers(configs)

    def _init_providers(self, configs: List[ProviderConfig]):
        sorted_configs = sorted(configs, key=lambda c: c.priority)
        for config in sorted_configs:
            if not config.enabled:
                continue
            provider = self._create_provider(config)
            if provider:
                self.providers.append(provider)
                logger.info(f"已添加提供商: {config.name} (优先级: {config.priority})")

    def _create_provider(self, config: ProviderConfig) -> Optional[BaseLLMProvider]:
        if config.provider == ProviderType.SIMULATOR:
            return SimulatorLLM()
        elif config.provider == ProviderType.LITELLM:
            return LiteLLM(config.model, config.api_key, config.base_url)
        else:
            llm = LLM(config.model, config.api_key, config.base_url,
                       temperature=config.temperature, max_tokens=config.max_tokens,
                       timeout=config.timeout)
            llm.config.provider = config.provider
            llm.config.thinking_enabled = config.thinking_enabled
            if config.provider == ProviderType.MIMO:
                llm._init_client()
            return llm

    def get_provider(self) -> Optional[BaseLLMProvider]:
        for provider in self.providers:
            if provider.is_available():
                return provider
        return None

    def list_available_providers(self) -> List[str]:
        return [p.config.name for p in self.providers if p.is_available()]

    def chat_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_token: Optional[Callable[[str], Any]] = None,
    ) -> LLMResponse:
        errors = []
        for provider in self.providers:
            if not provider.is_available():
                continue
            try:
                logger.info(f"尝试使用提供商: {provider.config.name}")
                response = provider.chat(messages, tools, on_token)
                cost = provider.estimated_cost
                if cost:
                    self.total_cost += cost
                return response
            except Exception as e:
                logger.warning(f"提供商 {provider.config.name} 失败: {e}")
                errors.append(f"{provider.config.name}: {e}")
                continue

        error_msg = "; ".join(errors) if errors else "没有可用的提供商"
        logger.error(f"所有提供商都失败: {error_msg}")
        return LLMResponse(content=f"所有 API 提供商都不可用: {error_msg}", tool_calls=[], prompt_tokens=0, completion_tokens=0)

    def reset(self):
        self.total_cost = 0.0
        for provider in self.providers:
            provider.total_prompt_tokens = 0
            provider.total_completion_tokens = 0
