import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class LlmTrustConfig:
    allow_provider_override: bool = False
    allow_model_override: bool = False
    allowed_providers: List[str] = field(default_factory=list)
    allowed_models: List[str] = field(default_factory=list)
    allow_agent_id_override: bool = False
    allow_profile_override: bool = False


class TrustGate:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._llm_gates: Dict[str, LlmTrustConfig] = {}

    def configure_llm_gate(self, plugin_name: str, config: LlmTrustConfig):
        self._llm_gates[plugin_name] = config

    def check_llm_access(self, plugin_name: str, provider: str = "", model: str = "") -> bool:
        gate = self._llm_gates.get(plugin_name)
        if gate is None:
            logger.warning(f"TrustGate: no LLM config for plugin {plugin_name}, denying")
            return False

        if provider and gate.allowed_providers:
            if provider not in gate.allowed_providers:
                if not gate.allow_provider_override:
                    logger.warning(f"TrustGate: plugin {plugin_name} denied provider {provider}")
                    return False

        if model and gate.allowed_models:
            if model not in gate.allowed_models:
                if not gate.allow_model_override:
                    logger.warning(f"TrustGate: plugin {plugin_name} denied model {model}")
                    return False

        return True

    def check_tool_access(self, plugin_name: str, tool_name: str) -> bool:
        plugin_config = self._config.get("plugins", {}).get("entries", {}).get(plugin_name, {})
        allowed_tools = plugin_config.get("allowed_tools", None)
        if allowed_tools is None:
            return True
        return tool_name in allowed_tools

    def check_env_access(self, plugin_name: str, env_var: str) -> bool:
        plugin_config = self._config.get("plugins", {}).get("entries", {}).get(plugin_name, {})
        allowed_env = plugin_config.get("allowed_env", None)
        if allowed_env is None:
            return False
        return env_var in allowed_env


class LlmTrustGate:
    def __init__(self, trust_gate: TrustGate, plugin_name: str):
        self._gate = trust_gate
        self._plugin_name = plugin_name

    def complete(self, messages, **kwargs) -> Any:
        provider = kwargs.get("provider", "")
        model = kwargs.get("model", "")

        if not self._gate.check_llm_access(self._plugin_name, provider, model):
            raise PermissionError(
                f"Plugin {self._plugin_name} LLM access denied "
                f"(provider={provider}, model={model})"
            )

        return None

    def complete_structured(self, instructions, input_data, json_schema, **kwargs) -> Any:
        provider = kwargs.get("provider", "")
        model = kwargs.get("model", "")

        if not self._gate.check_llm_access(self._plugin_name, provider, model):
            raise PermissionError(
                f"Plugin {self._plugin_name} structured LLM access denied"
            )

        return None
