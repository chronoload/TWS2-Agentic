from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ChainNode:
    name: str                      # 调用目标（函数名 / 类.方法）
    kind: str = ""                 # helper | class_method | module | builtin | unknown | cross_file | broken | recursive | depth_limit
    file: str = ""
    line: int = 0
    detail: str = ""
    children: list = field(default_factory=list)


@dataclass
class Endpoint:
    method: str
    path: str
    func: str
    file: str
    line: int
    doc: str = ""
    params: list = field(default_factory=list)   # 函数参数
    request_model: str = ""                      # 使用的 Pydantic 模型名
    response_keys: list = field(default_factory=list)  # ok(data={...}) 顶层键
    note: str = ""


@dataclass
class ModelField:
    name: str
    type: str
    default: str
    required: bool


@dataclass
class RequestModel:
    name: str
    file: str
    line: int
    doc: str = ""
    fields: list = field(default_factory=list)


# ─── 前端/契约 ───

@dataclass
class ClientMethod:
    name: str
    line: int = 0
    endpoint: str = ""
    http_method: str = ""
    payload_keys: list = field(default_factory=list)


@dataclass
class Drift:
    kind: str
    client: str
    endpoint: str
    detail: str


@dataclass
class DataclassDef:
    name: str
    file: str
    line: int
    kind: str = "dataclass"
    fields: list = field(default_factory=list)


# ─── def-use ───

@dataclass
class DefUseRead:
    file: str
    line: int
    obj: str
    attr: str
    default: str


@dataclass
class DefUseWrite:
    file: str
    line: int
    obj: str
    attr: str
    expr: str


@dataclass
class DefUseIssue:
    kind: str          # no_assignment | loose_match | external_contract
    attr: str
    file: str
    line: int
    obj: str
    default: str
    writes: list = field(default_factory=list)
    detail: str = ""


# ─── 行为/链路 ───

@dataclass
class BehaviorIssue:
    entry: str
    missing: list = field(default_factory=list)
    file: str = ""
    detail: str = ""


@dataclass
class ChainBreakIssue:
    entry: str
    fallback: str
    file: str
    line: int
    detail: str = ""


# ─── 状态标志 / 合并仲裁 / 命名空间 ───

@dataclass
class FlagLifecycleIssue:
    kind: str          # clear_without_set | stale_cache
    attr: str
    file: str
    line: int
    detail: str = ""


@dataclass
class MergeDirectionIssue:
    kind: str          # count_only_arbitration | arbiter_without_source
    fn: str
    file: str
    line: int
    detail: str = ""


@dataclass
class IdSourceIssue:
    kind: str          # cross_namespace_key | unguarded_key_consumer
    consumer: str
    key_arg: str
    file: str
    line: int
    detail: str = ""


# ─── 4 维扫描项 ───

@dataclass
class HardcodedItem:
    file: str
    line: int
    kind: str
    value: str
    context: str = ""


@dataclass
class EnvVarItem:
    file: str
    line: int
    name: str
    default: str = ""
    context: str = ""


@dataclass
class DataPoolItem:
    file: str
    line: int
    name: str
    kind: str
    size_hint: str = ""
    context: str = ""


@dataclass
class StaticResourceItem:
    file: str
    line: int
    path: str
    kind: str
    context: str = ""
