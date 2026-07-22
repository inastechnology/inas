"""Build the field record calendar view model from domain records."""

import calendar
from datetime import datetime, timedelta

RECORD_KIND_LABELS = {
    "event": "作業・観察",
    "note": "メモ",
    "decision": "判断候補",
    "work": "栽培作業",
    "planting": "定植",
}
RATING_EMOJIS = {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "😄"}


def record_month_start(month_value: str):
    try:
        return datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        return datetime.now().astimezone().date().replace(day=1)


def build_field_record_calendar(field: dict, plant_bundle: dict, month_value: str, automatic_measurements=None):
    month_start = record_month_start(month_value)
    items_by_date = _collect_record_items(field, plant_bundle)
    measurements_by_date = _group_measurements_by_date(automatic_measurements or [])
    today_value = datetime.now().astimezone().date().isoformat()
    weeks = _calendar_weeks(month_start, today_value, items_by_date, measurements_by_date)
    previous_month = month_start - timedelta(days=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)

    return {
        "label": f"{month_start.year}年{month_start.month}月",
        "value": month_start.strftime("%Y-%m"),
        "previous": previous_month.strftime("%Y-%m"),
        "next": next_month.strftime("%Y-%m"),
        "weeks": weeks,
        "items_by_date": items_by_date,
        "measurements_by_date": measurements_by_date,
        "today": today_value,
        "today_items": items_by_date.get(today_value, []),
        "today_measurement_count": len(measurements_by_date.get(today_value, [])),
    }


def _collect_record_items(field: dict, plant_bundle: dict):
    items_by_date = {}

    def add_item(value, label, kind, detail="", *, item_id="", rating=None, attachments=None, record_values=None, target_name="", tags=None):
        day_value = str(value or "")[:10]
        try:
            datetime.fromisoformat(day_value)
        except ValueError:
            return
        normalized_rating = rating if rating in RATING_EMOJIS else None
        items_by_date.setdefault(day_value, []).append(
            {
                "id": item_id,
                "label": label,
                "kind": kind,
                "kind_label": RECORD_KIND_LABELS.get(kind, "記録"),
                "detail": detail,
                "time": str(value or "")[11:16] if len(str(value or "")) >= 16 else "",
                "rating": normalized_rating,
                "rating_emoji": RATING_EMOJIS.get(normalized_rating, ""),
                "attachments": _browser_attachments(attachments),
                "record_values": record_values or [],
                "target_name": target_name,
                "tags": tags or [],
            }
        )

    for event in field.get("events") or []:
        add_item(
            event.get("occurred_at") or event.get("created_at"),
            event.get("title") or "圃場イベント",
            "event",
            event.get("description") or event.get("human_evaluation") or "",
            item_id=event.get("id") or "",
            rating=event.get("rating"),
            attachments=event.get("attachments"),
            record_values=event.get("record_values"),
            target_name=event.get("target_name") or "",
            tags=event.get("tags") or [],
        )
    for note in field.get("notes") or []:
        add_item(
            note.get("created_at"),
            note.get("text") or "メモ",
            "note",
            note.get("human_evaluation") or "",
            item_id=note.get("id") or "",
            rating=note.get("rating"),
            attachments=note.get("attachments"),
        )
    for plan in field.get("action_plans") or []:
        add_item(
            plan.get("created_at"),
            plan.get("title") or "判断候補",
            "decision",
            plan.get("scientific_reason") or plan.get("status") or "",
            item_id=plan.get("id") or "",
            rating=plan.get("rating"),
        )

    event_work_log_ids = {event.get("source_work_log_id") for event in field.get("events") or [] if event.get("source_work_log_id")}
    for work_log in plant_bundle.get("work_logs") or []:
        if work_log.get("review_status", "approved") != "approved" or work_log.get("id") in event_work_log_ids:
            continue
        add_item(
            work_log.get("performed_on"),
            work_log.get("title") or "栽培作業",
            "work",
            work_log.get("note") or "",
            item_id=work_log.get("id") or "",
            rating=work_log.get("rating"),
            attachments=work_log.get("attachments"),
        )
    for planting in plant_bundle.get("plantings") or []:
        add_item(
            planting.get("planted_on"),
            f"{planting.get('crop_name') or '作物'}を定植",
            "planting",
            planting.get("placement_name") or "",
            item_id=planting.get("id") or "",
        )
    return items_by_date


def _browser_attachments(attachments):
    return [
        {
            "id": attachment.get("id") or "",
            "url": attachment.get("url") or "",
            "content_type": attachment.get("content_type") or "",
            "original_filename": attachment.get("original_filename") or "image",
        }
        for attachment in attachments or []
        if isinstance(attachment, dict) and attachment.get("url")
    ]


def _group_measurements_by_date(measurements):
    grouped = {}
    for measurement in measurements:
        grouped.setdefault(measurement["date"], []).append(measurement)
    return grouped


def _calendar_weeks(month_start, today_value, items_by_date, measurements_by_date):
    return [
        [
            {
                "date": day.isoformat(),
                "day": day.day,
                "in_month": day.month == month_start.month,
                "is_today": day.isoformat() == today_value,
                "items": items_by_date.get(day.isoformat(), []),
                "measurement_count": len(measurements_by_date.get(day.isoformat(), [])),
            }
            for day in week
        ]
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    ]
