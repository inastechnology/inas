"""Resolve declared threshold inputs for display, without making device decisions."""

import math
import re

from ina_device_hub.device_definition_registry import value_at_path

_RULE_KEYS = {
    "id",
    "title",
    "enabled_path",
    "threshold_path",
    "selection_hint",
    "timing_hint",
    "missing_hint",
    "source",
    "device_enabled_path",
    "device_threshold_path",
    "decision",
    "source_path",
    "device_source_path",
    "capability_path",
    "unsupported_hint",
}
_SOURCE_KEYS = {
    "registry_flag_path",
    "collection_path",
    "filter_key",
    "filter_value",
    "enabled_key",
    "valid_key",
    "value_key",
    "name_key",
    "location_key",
    "fallback_name",
    "fallback_enabled_path",
    "fallback_valid_path",
    "fallback_value_path",
    "baud_key",
    "address_key",
    "fallback_baud",
    "fallback_address_path",
}
_DECISION_KEYS = {"checked_path", "valid_path", "value_path", "threshold_path", "reason_path", "labels"}


def validate_threshold_rules(ui):
    rules = ui.get("threshold_rules", [])
    if not isinstance(rules, list) or len(rules) > 8:
        raise ValueError("ui.threshold_rules must be an array of at most eight rules")
    fields = {field["path"]: field for field in ui.get("configuration_fields", [])}
    ids, used_paths = set(), set()
    for rule in rules:
        _validate_object(rule, _RULE_KEYS, {"source", "decision"})
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", rule["id"]) or rule["id"] in ids:
            raise ValueError("threshold rule IDs must be unique kebab-case names")
        ids.add(rule["id"])
        for key, expected_type in (("enabled_path", "boolean"), ("threshold_path", "number"), ("source_path", "measurement_source")):
            path = rule[key]
            if path in used_paths or fields.get(path, {}).get("type") != expected_type:
                raise ValueError("threshold rules must reference distinct existing boolean and number fields")
            used_paths.add(path)
        field = fields[rule["threshold_path"]]
        if not all(_finite_number(field.get(key)) for key in ("min", "max")) or field["min"] > field["max"]:
            raise ValueError("threshold fields require finite, ordered bounds")
        _validate_object(rule["source"], _SOURCE_KEYS, {"fallback_baud"})
        if rule["source"]["fallback_baud"] not in (2400, 4800, 9600):
            raise ValueError("unsupported fallback sensor baud")
        _validate_object(rule["decision"], _DECISION_KEYS, {"labels"})
        labels = rule["decision"]["labels"]
        if not isinstance(labels, dict) or not labels or not all(isinstance(k, str) and isinstance(v, str) and 0 < len(v) <= 500 for k, v in labels.items()):
            raise ValueError("threshold decision labels must be plain text")


def _validate_object(value, keys, objects=frozenset()):
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("unknown or missing threshold rule fields")
    for key in keys - objects:
        if not isinstance(value[key], str) or not 0 < len(value[key]) <= 1000:
            raise ValueError("threshold rule values must be non-empty text")
        if (key.endswith("_path") or key.endswith("_key")) and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", value[key]):
            raise ValueError("threshold paths must be dotted object keys")


def _finite_number(value):
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _measurement(value, field):
    return value if _finite_number(value) and field["min"] <= value <= field["max"] else None


def _sensor_options(rule, payload, field):
    spec = rule["source"]
    registry_flag = value_at_path(payload, spec["registry_flag_path"])
    members = []
    known = registry_flag is False
    if registry_flag is True:
        collection = value_at_path(payload, spec["collection_path"])
        known = isinstance(collection, list)
        for position, item in enumerate(collection if known else []):
            if not isinstance(item, dict) or value_at_path(item, spec["filter_key"]) != spec["filter_value"]:
                continue
            baud, address = value_at_path(item, spec["baud_key"]), value_at_path(item, spec["address_key"])
            identity = f"sensor:{baud}:{address}" if type(baud) is int and type(address) is int else None
            members.append(
                {
                    "key": identity,
                    "name": str(value_at_path(item, spec["name_key"]) or f"{spec['fallback_name']}（登録{position + 1}番目）"),
                    "location": str(value_at_path(item, spec["location_key"]) or "設置場所未設定"),
                    "position": position,
                    "enabled": value_at_path(item, spec["enabled_key"]) is True,
                    "percent": _measurement(value_at_path(item, spec["value_key"]), field) if value_at_path(item, spec["valid_key"]) is True else None,
                }
            )
    elif registry_flag is False:
        address = value_at_path(payload, spec["fallback_address_path"])
        members.append(
            {
                "key": f"sensor:{spec['fallback_baud']}:{address}" if type(address) is int else None,
                "name": spec["fallback_name"],
                "location": "",
                "position": None,
                "enabled": value_at_path(payload, spec["fallback_enabled_path"]) is True,
                "percent": _measurement(value_at_path(payload, spec["fallback_value_path"]), field)
                if value_at_path(payload, spec["fallback_valid_path"]) is True
                else None,
            }
        )
    active = [member for member in members if member["enabled"]]
    options = [_option("first", "自動（登録順で最初の有効なセンサー）", active[:1], known), _option("average", "有効なセンサーすべての平均", active, known)]
    for member in members:
        if member["key"]:
            label = member["name"] + (f" — {member['location']}" if member["location"] else "")
            if not member["enabled"]:
                label += "（停止中）"
            options.append(_option(member["key"], label, [member], True))
    return options


def _option(key, label, members, known):
    valid = bool(members) and all(member["enabled"] and member["percent"] is not None for member in members)
    return {
        "key": key,
        "label": label,
        "members": members,
        "percent": sum(member["percent"] for member in members) / len(members) if valid else None,
        "state": "測定値あり" if valid else "読み取れません" if members else "対象なし" if known else "対象情報を受信していません",
    }


def build_threshold_contexts(definition, payload, received_at, statuses, config=None):
    ui = definition.get("ui", {})
    fields = {field["path"]: field for field in ui.get("configuration_fields", [])}
    contexts = []
    for rule in ui.get("threshold_rules", []):
        field = fields[rule["threshold_path"]]
        options = _sensor_options(rule, payload, field)
        selected = value_at_path(config, rule["source_path"]) or "first"
        if not any(option["key"] == selected for option in options):
            options.append(_option(selected, "保存済みのセンサー（現在の一覧にありません）", [], False))
        decision_spec = rule["decision"]
        candidates = [*statuses, {"received_at": received_at, "payload": payload}]
        last_decision = None
        for entry in reversed(candidates):
            previous = entry.get("payload") if isinstance(entry, dict) else None
            if not isinstance(previous, dict) or value_at_path(previous, decision_spec["checked_path"]) is not True:
                continue
            value = (
                _measurement(value_at_path(previous, decision_spec["value_path"]), field)
                if value_at_path(previous, decision_spec["valid_path"]) is True
                else None
            )
            selected = value_at_path(previous, rule["device_source_path"]) or "first"
            old_options = _sensor_options(rule, previous, field)
            source = next((option for option in old_options if option["key"] == selected), _option(selected, "以前選択したセンサー", [], False))
            last_decision = {
                "source": source,
                "value": value,
                "threshold": _measurement(value_at_path(previous, decision_spec["threshold_path"]), field),
                "received_at": entry.get("received_at"),
                "result": decision_spec["labels"].get(value_at_path(previous, decision_spec["reason_path"]), "判断結果を確認できません"),
            }
            break
        contexts.append(
            {
                "rule": rule,
                "enabled_field": fields[rule["enabled_path"]],
                "source_field": fields[rule["source_path"]],
                "threshold_field": field,
                "options": options,
                "received_at": received_at,
                "supported": value_at_path(payload, rule["capability_path"]) is True,
                "device_source": value_at_path(payload, rule["device_source_path"]),
                "device_enabled": value_at_path(payload, rule["device_enabled_path"]),
                "device_threshold": _measurement(value_at_path(payload, rule["device_threshold_path"]), field),
                "last_decision": last_decision,
            }
        )
    return contexts
