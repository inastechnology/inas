"""Build template-ready plant calendar TODO data without Flask dependencies."""

from urllib.parse import urlencode

from ina_device_hub.plant_action_catalog import plant_action_type


TIMING_LABELS = {"overdue": "期限超過", "due": "今やる", "upcoming": "そろそろ"}
TIMING_PHRASES = {"overdue": "期限を過ぎています。", "due": "今、", "upcoming": "そろそろ"}
PRIORITY_LABELS = {"required": "必須", "should": "やった方がよい", "recommended": "おすすめ", "optional": "好みで"}


def build_calendar_todo_items(field_id: str, plant_bundle: dict, limit: int = 20):
    return [
        _calendar_todo_item(field_id, suggestion)
        for suggestion in (plant_bundle.get("suggestions") or [])[:limit]
    ]


def _calendar_todo_item(field_id: str, suggestion: dict):
    action = suggestion.get("action") if isinstance(suggestion.get("action"), dict) else {}
    timing_state = suggestion.get("timing_state") or "upcoming"
    crop_name = suggestion.get("crop_name") or "作物"
    action_type_view = plant_action_type(action.get("action_type"))
    action_label = action_type_view["todo_label"] or action.get("title") or "作業確認"

    return {
        "planting_id": suggestion.get("planting_id"),
        "placement_name": suggestion.get("placement_name"),
        "title": _todo_title(crop_name, action_label, timing_state),
        "original_title": action.get("title") or action_label,
        "reason": action.get("reason") or "栽培カレンダーの予定時期に入りました。",
        "timing_state": timing_state,
        "timing_label": TIMING_LABELS.get(timing_state, "そろそろ"),
        "priority": action.get("priority") or "recommended",
        "priority_label": PRIORITY_LABELS.get(action.get("priority"), "おすすめ"),
        "action_type": action_type_view["code"],
        "action_type_label": action_type_view["label"],
        "illustration_url": action_type_view["illustration_url"],
        "accent": action_type_view["accent"],
        "window_start": action.get("window_start"),
        "window_end": action.get("window_end"),
        "calendar_url": f"/fields/{field_id}/calendar?{urlencode({'planting': suggestion.get('planting_id') or '', 'action': action.get('id') or ''})}",
    }


def _todo_title(crop_name: str, action_label: str, timing_state: str):
    phrase = TIMING_PHRASES.get(timing_state, "そろそろ")
    if timing_state == "overdue":
        return f"{crop_name}の{action_label}は{phrase}"
    return f"{crop_name}に{phrase}{action_label}が必要です"
