import copy
import re

from ina_device_hub.device_definition_registry import get_device_definition

_EQUIPMENT_TYPES = {
    "irrigation": (
        {"value": "pump", "label": "ポンプ", "description": "水をくみ上げて送る"},
        {"value": "valve", "label": "バルブ", "description": "水の通り道を開け閉めする"},
        {"value": "drip_line", "label": "点滴チューブ", "description": "株元へ少しずつ届ける"},
        {"value": "sprinkler", "label": "スプリンクラー", "description": "広い範囲へ散水する"},
    ),
    "sensor_power": (
        {"value": "soil_sensor", "label": "土壌センサー", "description": "土の状態を計測する"},
        {"value": "light_sensor", "label": "光センサー", "description": "日射や明るさを計測する"},
        {"value": "sensor", "label": "複合センサー", "description": "複数の環境値を計測する"},
    ),
}

_EQUIPMENT_TYPE_TOKEN = re.compile(r"(?:^|\n)equipment_type=([a-z_]+)(?=\n|$)")

_DEVICE_OUTPUT_CAPABILITIES = {
    "WTR": (
        {
            "number": 1,
            "switch_id": "irr1",
            "terminal": "IRR1",
            "channel_mask": 1,
            "role": "irrigation",
            "role_label": "潅水",
            "default_name": "潅水1系",
            "equipment_presets": ("ポンプ", "電磁弁", "点滴ライン", "スプリンクラー"),
        },
        {
            "number": 2,
            "switch_id": "irr2",
            "terminal": "IRR2",
            "channel_mask": 2,
            "role": "irrigation",
            "role_label": "潅水",
            "default_name": "潅水2系",
            "equipment_presets": ("ポンプ", "電磁弁", "点滴ライン", "スプリンクラー"),
        },
    ),
    "WRS": (
        {
            "number": 1,
            "switch_id": "irr1",
            "terminal": "IRR1",
            "channel_mask": 1,
            "role": "irrigation",
            "role_label": "潅水",
            "default_name": "潅水1系",
            "equipment_presets": ("ポンプ", "電磁弁", "点滴ライン", "スプリンクラー"),
        },
        {
            "number": 2,
            "switch_id": "irr2",
            "terminal": "IRR2",
            "channel_mask": 2,
            "role": "irrigation",
            "role_label": "潅水",
            "default_name": "潅水2系",
            "equipment_presets": ("ポンプ", "電磁弁", "点滴ライン", "スプリンクラー"),
        },
        {
            "number": 3,
            "switch_id": "sensor_power",
            "terminal": "SENSOR_12V_SW",
            "channel_mask": 0,
            "role": "sensor_power",
            "role_label": "センサー電源",
            "default_name": "センサー電源",
            "equipment_presets": ("土壌センサー", "光量センサー", "土壌・光量センサー"),
        },
    ),
}


def device_output_capabilities(device_kind: str | None):
    definition_slots = get_device_definition(device_kind).get("output_slots") or []
    if definition_slots:
        capabilities = []
        for slot in definition_slots:
            role = str(slot.get("role") or "")
            equipment_types = _EQUIPMENT_TYPES.get(role, ())
            allowed = set(slot.get("allowed_load_types") or [])
            presets = tuple(item["label"] for item in equipment_types if not allowed or item["value"] in allowed)
            capabilities.append(
                {
                    "number": slot.get("number"),
                    "switch_id": slot.get("id"),
                    "terminal": slot.get("terminal") or "",
                    "channel_mask": slot.get("channel_mask") or 0,
                    "role": role,
                    "role_label": slot.get("role_label") or "設備",
                    "default_name": slot.get("default_name") or slot.get("role_label") or "設備",
                    "equipment_presets": presets,
                    "assignable": slot.get("assignable") is True,
                    "fixed": slot.get("assignable") is not True,
                }
            )
        return capabilities
    return copy.deepcopy(list(_DEVICE_OUTPUT_CAPABILITIES.get(str(device_kind or "").upper(), ())))


def supported_output_ids(device_kind: str | None):
    return {item["switch_id"] for item in device_output_capabilities(device_kind)}


def equipment_types_for_role(role: str | None):
    return copy.deepcopy(list(_EQUIPMENT_TYPES.get(str(role or ""), ())))


def equipment_type_from_notes(notes: str | None):
    match = _EQUIPMENT_TYPE_TOKEN.search(str(notes or ""))
    return match.group(1) if match else ""


def infer_equipment_type(value: str | None, *, preset: str | None = None, role: str | None = None):
    normalized = f"{preset or ''} {value or ''}".casefold()
    if any(token in normalized for token in ("drip", "irrigation_line", "点滴", "チューブ", "ライン")):
        return "drip_line"
    if any(token in normalized for token in ("sprinkler", "スプリンクラー", "散水")):
        return "sprinkler"
    if any(token in normalized for token in ("valve", "バルブ", "電磁弁")):
        return "valve"
    if any(token in normalized for token in ("pump", "ポンプ")):
        return "pump"
    if any(token in normalized for token in ("soil", "土壌")):
        return "soil_sensor"
    if any(token in normalized for token in ("light", "par", "光量", "光センサー")):
        return "light_sensor"
    if role == "sensor_power" or "sensor" in normalized or "センサー" in normalized:
        return "sensor"
    return "pump" if role == "irrigation" else "sensor" if role == "sensor_power" else "other"
