from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_tool_input(
    value: Any,
    context: Any = None,
    step_outputs: Optional[Dict[str, Any]] = None,
    input_data: Optional[Dict[str, Any]] = None,
    node_outputs: Optional[Dict[str, Any]] = None,
) -> Any:
    if not isinstance(value, str):
        if isinstance(value, dict):
            return {k: resolve_tool_input(v, context, step_outputs, input_data, node_outputs) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve_tool_input(v, context, step_outputs, input_data, node_outputs) for v in value]
        return value

    val = value.strip()
    if not (val.startswith("{") and val.endswith("}")):
        return value

    inner = val[1:-1].strip()
    if not inner:
        return value

    try:
        from .param_chain import _is_param_ref
        ref = _is_param_ref(val)
        if ref:
            return _lookup(ref, context, step_outputs, input_data, node_outputs)
    except ImportError:
        pass

    if inner.startswith("$input."):
        path = inner[len("$input."):]
        return _dig(input_data or {}, path)
    if inner.startswith("$step."):
        path = inner[len("$step."):]
        return _dig(step_outputs or {}, path)
    if inner.startswith("$node."):
        path = inner[len("$node."):]
        return _dig(node_outputs or {}, path)
    if inner.startswith("$var."):
        path = inner[len("$var."):]
        if context and hasattr(context, "variables"):
            return _dig(context.variables, path)
        return _dig(input_data or {}, path)
    if step_outputs is not None and inner in step_outputs:
        return step_outputs[inner]
    if input_data is not None and inner in input_data:
        return input_data[inner]
    if context and hasattr(context, "variables") and inner in context.variables:
        return context.variables[inner]

    return value


def _dig(data: Any, path: str) -> Any:
    if not path:
        return data
    cur = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _lookup(
    ref: str,
    context: Any,
    step_outputs: Optional[Dict[str, Any]],
    input_data: Optional[Dict[str, Any]],
    node_outputs: Optional[Dict[str, Any]],
) -> Any:
    if ref.startswith("$input."):
        return _dig(input_data or {}, ref[len("$input."):])
    if ref.startswith("$step."):
        return _dig(step_outputs or {}, ref[len("$step."):])
    if ref.startswith("$node."):
        return _dig(node_outputs or {}, ref[len("$node."):])
    if ref.startswith("$var."):
        if context and hasattr(context, "variables"):
            return _dig(context.variables, ref[len("$var."):])
        return _dig(input_data or {}, ref[len("$var."):])
    if step_outputs is not None and ref in step_outputs:
        return step_outputs[ref]
    if node_outputs is not None and ref in node_outputs:
        return node_outputs[ref]
    if input_data is not None and ref in input_data:
        return input_data[ref]
    if context and hasattr(context, "variables") and ref in context.variables:
        return context.variables[ref]
    return None


def build_param_chain(
    steps: List[Any],
    name: str = "workflow_chain",
) -> Any:
    try:
        from .param_chain import ParamChain, ParamBinding, ParamOutput
    except ImportError:
        return None

    chain = ParamChain(name=name)
    for step in steps:
        step_id = getattr(step, "step_id", None) or (step.get("step_id", "") if isinstance(step, dict) else "")
        if not step_id:
            continue
        config = getattr(step, "config", None) or (step.get("config", {}) if isinstance(step, dict) else {})
        args = config.get("args", {})

        inputs = []
        for arg_name, arg_val in (args.items() if isinstance(args, dict) else []):
            if isinstance(arg_val, str) and arg_val.startswith("{") and arg_val.endswith("}"):
                ref = arg_val[1:-1].strip()
                inputs.append(ParamBinding(target=arg_name, source=ref, required=False))

        outputs = [ParamOutput(name=arg_name) for arg_name in (args.keys() if isinstance(args, dict) else [])]

        chain.add_node(step_id, name=step_id, inputs=inputs, outputs=outputs)

    return chain


def safe_parse_output(output: Any) -> Dict[str, Any]:
    if output is None:
        return {}
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        try:
            data = json.loads(output)
            return data if isinstance(data, dict) else {"_raw": data}
        except (json.JSONDecodeError, TypeError):
            return {"_raw": output[:5000]}
    return {"_raw": str(output)}


def extract_param(
    output: Any,
    name: str,
    default: Any = None,
) -> Any:
    data = safe_parse_output(output)
    if name in data:
        return data[name]
    for key, val in data.items():
        if isinstance(val, dict) and name in val:
            return val[name]
    return default


class ParamChainBuilder:
    def __init__(self, name: str = "chain"):
        self.name = name
        self._bindings: List[Tuple[str, str, str, Optional[str], Any]] = []

    def bind(
        self,
        target: str,
        source: str,
        transform: Optional[str] = None,
        default: Any = None,
    ) -> "ParamChainBuilder":
        self._bindings.append((target, source, "", transform, default))
        return self

    def from_step(self, step_id: str, output_name: str) -> "ParamChainBuilder":
        pass

    def build(self) -> List[Dict[str, Any]]:
        return [
            {"target": t, "source": s, "transform": tf, "default": df}
            for t, s, _, tf, df in self._bindings
        ]