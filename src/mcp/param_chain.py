from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


class ParamChainError(Exception):
    pass


class ParamNotFoundError(ParamChainError):
    pass


class ParamTransformError(ParamChainError):
    pass


class ParamTypeError(ParamChainError):
    pass


@dataclass
class ParamSpec:
    name: str
    type: str = "string"
    required: bool = False
    default: Any = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
        }


@dataclass
class ParamBinding:
    target: str
    source: str
    transform: Optional[str] = None
    default: Any = None
    required: bool = False

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "source": self.source,
            "transform": self.transform,
            "default": self.default,
            "required": self.required,
        }


@dataclass
class ParamOutput:
    name: str
    path: str = ""
    type: str = "auto"

    def to_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "type": self.type}


class ParamChainNode:
    def __init__(
        self,
        node_id: str,
        name: str = "",
        inputs: Optional[List[ParamBinding]] = None,
        outputs: Optional[List[ParamOutput]] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.node_id = node_id
        self.name = name or node_id
        self.inputs: List[ParamBinding] = inputs or []
        self.outputs: List[ParamOutput] = outputs or []
        self.transform = transform
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "inputs": [b.to_dict() for b in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "metadata": self.metadata,
        }


_TYPE_CASTS: Dict[str, Callable[[Any], Any]] = {
    "string": str,
    "str": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": lambda v: v if isinstance(v, bool) else (str(v).lower() in ("true", "1", "yes", "y") if v else False),
    "boolean": lambda v: v if isinstance(v, bool) else (str(v).lower() in ("true", "1", "yes", "y") if v else False),
    "list": list,
    "array": list,
    "dict": dict,
    "object": dict,
    "json": json.loads if isinstance(v := "", str) else (lambda x: x),
}


def _cast_type(value: Any, target_type: str) -> Any:
    if not target_type or target_type == "auto" or target_type == "any":
        return value
    target = target_type.lower()
    if target not in _TYPE_CASTS:
        return value
    if value is None:
        return None
    try:
        return _TYPE_CASTS[target](value)
    except (ValueError, TypeError) as e:
        raise ParamTypeError(f"cannot cast {type(value).__name__} to {target_type}: {e}")


_BUILTIN_TRANSFORMS: Dict[str, Callable[[Any, Any], Any]] = {}


def register_transform(name: str, fn: Callable[[Any, Any], Any]):
    _BUILTIN_TRANSFORMS[name] = fn


def _apply_transform(value: Any, transform: str, context: Dict[str, Any]) -> Any:
    if not transform:
        return value
    if transform in _BUILTIN_TRANSFORMS:
        return _BUILTIN_TRANSFORMS[transform](value, context)

    safe_globals = {
        "__builtins__": {},
        "value": value,
        "context": context,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "json": json,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "abs": abs,
        "round": round,
    }
    # 预处理 JSON 风格字面量 → Python 风格（避免 NameError: name 'false' is not defined）
    _preprocessed = transform
    _preprocessed = re.sub(r'\bfalse\b', 'False', _preprocessed)
    _preprocessed = re.sub(r'\btrue\b', 'True', _preprocessed)
    _preprocessed = re.sub(r'\bnull\b', 'None', _preprocessed)
    try:
        return eval(_preprocessed, safe_globals)
    except Exception as e:
        raise ParamTransformError(f"transform '{transform}' failed: {e}")


def _t_length(value, _ctx):
    return len(value) if hasattr(value, "__len__") else 0


def _t_upper(value, _ctx):
    return str(value).upper()


def _t_lower(value, _ctx):
    return str(value).lower()


def _t_strip(value, _ctx):
    return str(value).strip()


def _t_first(value, _ctx):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    if isinstance(value, str) and value:
        return value[0]
    return value


def _t_last(value, _ctx):
    if isinstance(value, (list, tuple)) and value:
        return value[-1]
    if isinstance(value, str) and value:
        return value[-1]
    return value


def _t_join(value, _ctx):
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def _t_lines(value, _ctx):
    if isinstance(value, str):
        return [ln for ln in value.splitlines() if ln.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _t_keys(value, _ctx):
    if isinstance(value, dict):
        return list(value.keys())
    return []


def _t_values(value, _ctx):
    if isinstance(value, dict):
        return list(value.values())
    return []


def _t_unique(value, _ctx):
    if isinstance(value, (list, tuple)):
        seen = []
        for v in value:
            if v not in seen:
                seen.append(v)
        return seen
    return value


def _t_truncate(value, _ctx):
    s = str(value)
    if len(s) > 200:
        return s[:200] + "..."
    return s


def _t_to_json(value, _ctx):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _t_from_json(value, _ctx):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _t_dedup_strings(value, _ctx):
    if isinstance(value, (list, tuple)):
        seen = set()
        out = []
        for v in value:
            k = str(v)
            if k not in seen:
                seen.add(k)
                out.append(v)
        return out
    return value


def _t_default_if_empty(value, _ctx):
    if value is None or value == "" or value == [] or value == {}:
        return None
    return value


def _t_path_get(value, _ctx):
    if not isinstance(value, dict):
        return value
    return value


def _t_negate(value, _ctx):
    if isinstance(value, bool):
        return not value
    return not value


def _t_round3(value, _ctx):
    try:
        return round(float(value), 3)
    except (ValueError, TypeError):
        return value


for _name, _fn in list(globals().items()):
    if _name.startswith("_t_") and callable(_fn):
        register_transform(_name[3:], _fn)


class ParamChain:
    def __init__(self, name: str = ""):
        self.name = name
        self.nodes: Dict[str, ParamChainNode] = {}
        self._topo_cache: Optional[List[str]] = None

    def add_node(
        self,
        node_id: str,
        name: str = "",
        inputs: Optional[List[ParamBinding]] = None,
        outputs: Optional[List[ParamOutput]] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ParamChain":
        node = ParamChainNode(
            node_id=node_id,
            name=name,
            inputs=inputs,
            outputs=outputs,
            transform=transform,
            metadata=metadata,
        )
        self.nodes[node_id] = node
        self._topo_cache = None
        return self

    def add_binding(
        self,
        node_id: str,
        target: str,
        source: str,
        transform: Optional[str] = None,
        default: Any = None,
        required: bool = False,
    ) -> "ParamChain":
        if node_id not in self.nodes:
            raise ParamChainError(f"node '{node_id}' not in chain")
        self.nodes[node_id].inputs.append(ParamBinding(
            target=target, source=source, transform=transform,
            default=default, required=required,
        ))
        return self

    def _extract_source_node(self, source: str) -> str:
        """从 source 中提取 source node id（如果 source 引用了其他 node）。

        支持的语法:
          - $input.X / $node.X / $step.X / $var.X: 命名空间引用，提取 X 的第一段作为 source_node
          - bare_name: 没有路径分隔符时不视为节点引用（返回空字符串）
          - bare.path: 直接返回第一段
        """
        if not source:
            return ""
        for prefix in ("$input.", "$node.", "$step.", "$var."):
            if source.startswith(prefix):
                path = source[len(prefix):]
                if "." in path:
                    return path.split(".", 1)[0]
                return ""
        if "." in source:
            return source.split(".", 1)[0]
        return ""

    def _topo_sort(self) -> List[str]:
        if self._topo_cache is not None:
            return self._topo_cache

        incoming: Dict[str, Set[str]] = {nid: set() for nid in self.nodes}
        for node in self.nodes.values():
            for binding in node.inputs:
                source_node = self._extract_source_node(binding.source)
                if source_node and source_node in self.nodes:
                    incoming[node.node_id].add(source_node)

        result: List[str] = []
        visited: Set[str] = set()
        temp_mark: Set[str] = set()

        def visit(nid: str):
            if nid in visited:
                return
            if nid in temp_mark:
                raise ParamChainError(f"cycle detected at node '{nid}'")
            temp_mark.add(nid)
            for dep in incoming.get(nid, set()):
                visit(dep)
            temp_mark.discard(nid)
            visited.add(nid)
            result.append(nid)

        for nid in self.nodes:
            visit(nid)

        self._topo_cache = result
        return result

    def _resolve_source(self, source: str, node_outputs: Dict[str, Any], step_outputs: Dict[str, Any], input_data: Dict[str, Any]) -> Any:
        if not source:
            return None
        if source.startswith("$input."):
            path = source[len("$input."):]
            return self._dig(input_data, path)
        if source.startswith("$step."):
            path = source[len("$step."):]
            return self._dig(step_outputs, path)
        if source.startswith("$node."):
            path = source[len("$node."):]
            return self._dig(node_outputs, path)
        if source in node_outputs:
            return node_outputs[source]
        if source in step_outputs:
            return step_outputs[source]
        if source in input_data:
            return input_data[source]
        return self._dig(input_data, source)

    def _dig(self, data: Any, path: str) -> Any:
        if not path:
            return data
        cur = data
        for part in re.split(r"\.(?![^\[]*\])", path):
            if cur is None:
                return None
            m = re.match(r"^([^\[]+)(\[(\d+|\*)\])?$", part)
            if not m:
                continue
            key = m.group(1)
            idx = m.group(3)
            if isinstance(cur, dict):
                cur = cur.get(key)
            elif isinstance(cur, (list, tuple)):
                try:
                    cur = cur[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
            if idx is not None:
                if idx == "*":
                    return cur
                if isinstance(cur, (list, tuple)):
                    try:
                        cur = cur[int(idx)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
        return cur

    def resolve(
        self,
        input_data: Dict[str, Any],
        step_outputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        step_outputs = step_outputs or {}
        node_outputs: Dict[str, Any] = {}
        node_resolved: Dict[str, Dict[str, Any]] = {}

        for nid in self._topo_sort():
            node = self.nodes[nid]
            resolved: Dict[str, Any] = {}

            for binding in node.inputs:
                source = binding.source
                if not source and binding.default is not None:
                    resolved[binding.target] = binding.default
                    continue

                try:
                    value = self._resolve_source(source, node_outputs, step_outputs, input_data)
                except Exception as e:
                    if binding.required:
                        raise ParamNotFoundError(
                            f"node '{nid}': required input '{binding.target}' (source='{source}') not found: {e}"
                        )
                    value = binding.default

                if value is None and binding.default is not None:
                    value = binding.default

                if value is None and binding.required:
                    raise ParamNotFoundError(
                        f"node '{nid}': required input '{binding.target}' (source='{source}') resolved to None"
                    )

                if binding.transform:
                    try:
                        value = _apply_transform(value, binding.transform, {
                            "node": nid, "input": input_data, "node_outputs": node_outputs,
                            "step_outputs": step_outputs,
                        })
                    except ParamTransformError as e:
                        if binding.required:
                            raise
                        logger.warning(f"node '{nid}' transform failed for '{binding.target}': {e}")
                        value = binding.default

                resolved[binding.target] = value

            if node.transform:
                try:
                    custom_result = node.transform(resolved)
                    if custom_result:
                        resolved.update(custom_result)
                except Exception as e:
                    logger.warning(f"node '{nid}' custom transform failed: {e}")

            for output in node.outputs:
                if output.path:
                    value = self._dig(resolved, output.path)
                else:
                    value = resolved.get(output.name, resolved)
                if output.type and output.type != "auto":
                    try:
                        value = _cast_type(value, output.type)
                    except ParamTypeError:
                        pass
                if not output.path:
                    resolved[output.name] = value
                nid_output_key = f"{nid}.{output.name}"
                node_outputs[nid_output_key] = value
                if nid not in node_outputs:
                    node_outputs[nid] = {}
                if isinstance(node_outputs[nid], dict):
                    node_outputs[nid][output.name] = value

            node_resolved[nid] = resolved

        return node_resolved

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }


_PARAM_REF_RE = re.compile(r"^\{([\$\w\.\[\]\*][\w\.\[\]\$]*)\}$")


def _is_param_ref(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    m = _PARAM_REF_RE.match(value.strip())
    return m.group(1) if m else None


def chain_from_bindings(
    name: str,
    bindings: Dict[str, str],
    default_required: bool = False,
) -> ParamChain:
    chain = ParamChain(name=name)
    for target, source in bindings.items():
        if not source:
            continue
        chain.add_node(
            node_id=target,
            name=target,
            inputs=[ParamBinding(
                target="value", source=source, required=default_required,
            )],
            outputs=[ParamOutput(name=target, path="value")],
        )
    return chain


def resolve_step_params(
    step_def_config: Dict[str, Any],
    input_data: Dict[str, Any],
    step_outputs: Dict[str, Any],
    node_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    node_outputs = node_outputs or {}
    args = step_def_config.get("args", {})
    if not isinstance(args, dict):
        return args
    resolved = {}
    for key, val in args.items():
        ref = _is_param_ref(val)
        if ref:
            if ref.startswith("$input."):
                cur = input_data
                for part in ref[len("$input."):].split("."):
                    cur = cur.get(part, {}) if isinstance(cur, dict) else None
            elif ref.startswith("$step."):
                cur = step_outputs
                for part in ref[len("$step."):].split("."):
                    cur = cur.get(part, {}) if isinstance(cur, dict) else None
            elif ref.startswith("$node."):
                cur = node_outputs
                for part in ref[len("$node."):].split("."):
                    cur = cur.get(part, {}) if isinstance(cur, dict) else None
            else:
                cur = step_outputs.get(ref, input_data.get(ref))
                if cur is None and ref in node_outputs:
                    cur = node_outputs[ref]
            resolved[key] = cur
        elif isinstance(val, dict):
            resolved[key] = resolve_step_params({"args": val}, input_data, step_outputs, node_outputs)
        elif isinstance(val, list):
            resolved[key] = [
                resolve_step_params({"args": {"_x": v}}, input_data, step_outputs, node_outputs).get("_x", v)
                if _is_param_ref(v) else v
                for v in val
            ]
        else:
            resolved[key] = val
    return resolved


def build_chain_from_step_defs(
    steps: List[Any],
    name: str = "step_chain",
) -> ParamChain:
    chain = ParamChain(name=name)
    for step in steps:
        step_id = getattr(step, "step_id", None) or step.get("step_id", "")
        if not step_id:
            continue
        config = getattr(step, "config", None) or step.get("config", {}) or {}
        args = config.get("args", {})
        inputs = []
        for arg_name, arg_val in (args.items() if isinstance(args, dict) else []):
            ref = _is_param_ref(arg_val)
            if ref:
                inputs.append(ParamBinding(target=arg_name, source=ref, required=False))
        chain.add_node(
            node_id=step_id,
            name=getattr(step, "name", step_id),
            inputs=inputs,
            outputs=[ParamOutput(name=arg_name) for arg_name in (args.keys() if isinstance(args, dict) else [])],
        )
    return chain


__all__ = [
    "ParamChain",
    "ParamBinding",
    "ParamOutput",
    "ParamSpec",
    "ParamChainError",
    "ParamNotFoundError",
    "ParamTransformError",
    "ParamTypeError",
    "chain_from_bindings",
    "resolve_step_params",
    "build_chain_from_step_defs",
    "register_transform",
    "_apply_transform",
    "_cast_type",
    "_BUILTIN_TRANSFORMS",
]