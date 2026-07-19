from datetime import date

from ina_device_hub.plant_management_repository import (
    VALID_ACTION_SKIP_REASON_CODES,
    PlantManagementNotFoundError,
    PlantManagementValidationError,
)

ACTION_SKIP_REASON_LABELS = {
    "already_satisfied": "既に作業の目的を満たしている",
    "start_conditions_not_met": "実施条件を満たしていない",
    "timing_passed": "適期を過ぎた",
    "duplicate": "他の作業と重複している",
    "generated_in_error": "自動計画で誤って生成された",
    "not_applicable": "現在の作物・区画には不要",
    "other": "その他",
}


class PlantActionDecisionService:
    def __init__(self, *, plant_repository, field_repository, media_service):
        self.plant_repository = plant_repository
        self.field_repository = field_repository
        self.media_service = media_service

    def skip_action(self, planting_id: str, action_id: str, payload: dict, images: list, *, decided_by: str):
        if not isinstance(payload, dict):
            raise PlantManagementValidationError("request body must be an object")
        planting = self.plant_repository.get_planting(planting_id)
        if planting is None:
            raise PlantManagementNotFoundError("planting not found")
        calendar = self.plant_repository.get_calendar(planting_id)
        action = next((item for item in (calendar or {}).get("actions", []) if item.get("id") == action_id), None)
        if action is None:
            raise PlantManagementNotFoundError("calendar action not found")
        if action.get("status") not in {"planned", "in_progress"}:
            raise PlantManagementValidationError("only planned or in-progress actions can be skipped")

        decided_on = _required_date(payload.get("decided_on"), "decided_on")
        if date.fromisoformat(decided_on) > date.today():
            raise PlantManagementValidationError("decided_on must not be in the future")
        reason_code = str(payload.get("reason_code") or "").strip()
        if reason_code not in VALID_ACTION_SKIP_REASON_CODES:
            raise PlantManagementValidationError("unsupported skip reason")
        observed_facts = str(payload.get("observed_facts") or "").strip()
        if not observed_facts:
            raise PlantManagementValidationError("observed_facts is required")
        if len(observed_facts) > 2000:
            raise PlantManagementValidationError("observed_facts must be 2000 characters or less")
        next_review_on = str(payload.get("next_review_on") or "").strip() or None
        if next_review_on:
            next_review_on = _required_date(next_review_on, "next_review_on")
            if next_review_on < decided_on:
                raise PlantManagementValidationError("next_review_on must be on or after decided_on")

        attachments = self.media_service.upload_images(planting["field_id"], decided_on, images)
        skipped_action = self.plant_repository.skip_action(
            planting_id,
            action_id,
            decided_on,
            reason_code,
            observed_facts,
            str(payload.get("note") or ""),
            next_review_on=next_review_on,
            attachments=attachments,
            decided_by=decided_by,
            use_as_guidance=_boolean_value(payload.get("use_as_guidance"), default=True),
        )
        decision = skipped_action["skip_decision"]
        reason_label = ACTION_SKIP_REASON_LABELS[reason_code]
        description = "\n".join(
            part
            for part in (
                f"見送り理由: {reason_label}",
                f"確認内容: {decision['observed_facts']}",
                f"判断メモ: {decision['note']}" if decision["note"] else "",
                f"次回確認日: {decision['next_review_on']}" if decision["next_review_on"] else "",
            )
            if part
        )
        event = self.field_repository.add_event(
            planting["field_id"],
            {
                "event_type": "observation",
                "occurred_at": decided_on,
                "title": f"{skipped_action['title']}を見送り",
                "description": description,
                "target_placement_id": planting["placement_id"],
                "target_name": planting["placement_name"],
                "human_evaluation": decision["note"] or decision["observed_facts"],
                "attachments": decision["attachments"],
                "tags": ["plant-calendar", "skip-decision", skipped_action["action_type"], planting["crop_name"]],
            },
        )
        return {"action": skipped_action, "event": event}


def _required_date(value, path: str):
    try:
        return date.fromisoformat(str(value or "").strip()).isoformat()
    except ValueError as exc:
        raise PlantManagementValidationError(f"{path} must be YYYY-MM-DD") from exc


def _boolean_value(value, *, default: bool):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
