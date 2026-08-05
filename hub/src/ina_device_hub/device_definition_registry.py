import copy
import json
from functools import lru_cache
from pathlib import Path

_REGISTRY_PATH = Path(__file__).with_name("device_definitions") / "generated" / "registry.json"
_FALLBACK = {
    "schema_version": 1,
    "definition_version": "fallback",
    "device": {"kind": "", "product_name": "未登録の機器", "category": "unknown", "icon": "📟"},
    "sensor_slots": [],
    "output_slots": [],
    "runtime_sections": ["advanced"],
    "runtime_config": {"schema_version": 1, "send_keys": []},
    "status": {"schema_version": 1, "metrics": []},
    "ui": {"schema_version": 1, "sections": ["overview", "monitoring", "advanced"], "configuration_fields": []},
    "actions": {"schema_version": 1, "actions": []},
}


@lru_cache(maxsize=1)
def _registry():
    value = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not isinstance(value.get("definitions"), dict):
        raise RuntimeError("generated Device Definition registry is invalid")
    return value["definitions"]


def get_device_definition(device_kind):
    kind = str(device_kind or "").strip().upper()
    definition = _registry().get(kind)
    if definition is None:
        fallback = copy.deepcopy(_FALLBACK)
        fallback["device"]["kind"] = kind
        fallback["device"]["product_name"] = f"{kind} デバイス" if kind else "種別未取得"
        return fallback
    return copy.deepcopy(definition)


def list_device_definitions():
    return [copy.deepcopy(value) for _, value in sorted(_registry().items())]


def device_kind_label(device_kind):
    return get_device_definition(device_kind)["device"]["product_name"]


def project_runtime_config(device_kind, stored_config):
    """Build the exact JSON sent to firmware without mutating stored legacy data."""
    if not isinstance(stored_config, dict):
        return {}
    definition = get_device_definition(device_kind)
    send_keys = definition.get("runtime_config", {}).get("send_keys") or []
    projected = copy.deepcopy(stored_config) if not send_keys else {key: copy.deepcopy(stored_config[key]) for key in send_keys if key in stored_config}
    for path, fixed_value in (definition.get("runtime_config", {}).get("fixed_values") or {}).items():
        _set_value_at_path(projected, path, copy.deepcopy(fixed_value))
    return projected


def value_at_path(value, path):
    current = value
    for token in str(path or "").split("."):
        if not token or not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _set_value_at_path(value, path, next_value):
    tokens = [token for token in str(path or "").split(".") if token]
    current = value
    for token in tokens[:-1]:
        child = current.get(token)
        if not isinstance(child, dict):
            child = {}
            current[token] = child
        current = child
    if tokens:
        current[tokens[-1]] = next_value
