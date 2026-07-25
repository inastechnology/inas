import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

DEVICE_PREFIX = "INADS"
EDGE_GATEWAY_PREFIX = "INAEG"
LOCAL_HUB_PREFIX = "INALH"

_DEMO_DEVICE_RE = re.compile(r"^INADS-DEMO-[A-Z0-9]+(?:-[A-Z0-9]+)*$")


class IdentityValidationError(ValueError):
    pass


_UUID_VERSION = 4


class NodeType(StrEnum):
    EDGE_GATEWAY = "edge_gateway"
    LOCAL_HUB = "local_hub"


_NODE_PREFIX_BY_TYPE = {
    NodeType.EDGE_GATEWAY: EDGE_GATEWAY_PREFIX,
    NodeType.LOCAL_HUB: LOCAL_HUB_PREFIX,
}
_NODE_TYPE_BY_PREFIX = {prefix: node_type for node_type, prefix in _NODE_PREFIX_BY_TYPE.items()}


@dataclass(frozen=True)
class NodeIdentity:
    value: str
    node_type: NodeType
    unique_id: uuid.UUID


def generate_node_id(node_type: NodeType | str) -> str:
    normalized_type = _coerce_node_type(node_type)
    return f"{_NODE_PREFIX_BY_TYPE[normalized_type]}-{uuid.uuid4()}"


def parse_node_id(value: str) -> NodeIdentity:
    prefix, unique_id = _split_prefixed_uuid(value, allowed_prefixes=set(_NODE_TYPE_BY_PREFIX))
    return NodeIdentity(value=value, node_type=_NODE_TYPE_BY_PREFIX[prefix], unique_id=unique_id)


def validate_device_id(value: str, *, allow_demo: bool = False) -> str:
    if allow_demo and isinstance(value, str) and _DEMO_DEVICE_RE.fullmatch(value):
        return value
    _split_prefixed_uuid(value, allowed_prefixes={DEVICE_PREFIX})
    return value


def validate_uuid_v4(value: str, *, field_name: str = "id") -> str:
    if not isinstance(value, str):
        raise IdentityValidationError(f"{field_name} must be a string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise IdentityValidationError(f"{field_name} must be a canonical lowercase UUIDv4") from exc
    if parsed.version != _UUID_VERSION or parsed.variant != uuid.RFC_4122 or str(parsed) != value:
        raise IdentityValidationError(f"{field_name} must be a canonical lowercase UUIDv4")
    return value


def _coerce_node_type(value: NodeType | str) -> NodeType:
    if isinstance(value, NodeType):
        return value
    try:
        return NodeType(value)
    except (TypeError, ValueError) as exc:
        supported = ", ".join(item.value for item in NodeType)
        raise IdentityValidationError(f"node_type must be one of: {supported}") from exc


def _split_prefixed_uuid(value: str, *, allowed_prefixes: set[str]) -> tuple[str, uuid.UUID]:
    if not isinstance(value, str):
        raise IdentityValidationError("identity must be a string")
    prefix, separator, suffix = value.partition("-")
    if separator != "-" or prefix not in allowed_prefixes:
        supported = ", ".join(sorted(allowed_prefixes))
        raise IdentityValidationError(f"identity prefix must be one of: {supported}")
    validate_uuid_v4(suffix, field_name="identity UUID")
    return prefix, uuid.UUID(suffix)
