import json
from datetime import date

from ina_device_hub.plant_management_repository import (
    PlantManagementConflictError,
    PlantManagementNotFoundError,
    PlantManagementValidationError,
)


class PlantActionAuthorizationError(PermissionError):
    pass


class PlantActionReviewService:
    def __init__(self, *, plant_repository, field_repository, media_service, ai_content_service):
        self.plant_repository = plant_repository
        self.field_repository = field_repository
        self.media_service = media_service
        self.ai_content_service = ai_content_service

    def submit_completion(self, planting_id: str, action_id: str, payload: dict, images: list, *, actor_email: str, actor_role: str):
        if not isinstance(payload, dict):
            raise PlantManagementValidationError("request body must be an object")
        planting, _calendar, action = self._action_context(planting_id, action_id)
        if action.get("status") != "in_progress":
            raise PlantManagementConflictError("作業を開始してから実績を記録してください")
        self.assert_actor_can_work(action, actor_email=actor_email, actor_role=actor_role)

        performed_on = _required_date(payload.get("performed_on"), "performed_on")
        if date.fromisoformat(performed_on) > date.today():
            raise PlantManagementValidationError("performed_on must not be in the future")
        rating = _required_rating(payload.get("rating"))
        work_details = _work_details(payload.get("work_details"))
        attachments = self.media_service.upload_images(planting["field_id"], performed_on, images)
        work_log = self.plant_repository.complete_action(
            planting_id,
            action_id,
            performed_on,
            payload.get("note", ""),
            rating=rating,
            attachments=attachments,
            work_details=work_details,
            performed_by=actor_email,
        )
        updated_action = self._action_context(planting_id, action_id)[2]
        return {"work_log": work_log, "action": updated_action}

    def review_completion(
        self,
        planting_id: str,
        action_id: str,
        payload: dict,
        *,
        reviewer_email: str,
        reviewer_role: str,
        audience: dict | None = None,
    ):
        if reviewer_role != "admin":
            raise PlantActionAuthorizationError("administrator role is required")
        if not isinstance(payload, dict):
            raise PlantManagementValidationError("request body must be an object")
        planting, calendar, action = self._action_context(planting_id, action_id)
        if action.get("status") != "awaiting_review":
            raise PlantManagementConflictError("action must be awaiting review")
        decision = str(payload.get("decision") or "").strip()
        note = str(payload.get("note") or "").strip()
        result = self.plant_repository.review_action_completion(
            planting_id,
            action_id,
            decision,
            reviewed_by=reviewer_email,
            note=note,
        )
        if decision != "approved":
            return {**result, "event": None, "follow_up": _empty_follow_up("管理者から差し戻されました。")}

        work_log = result["work_log"]
        approved_action = result["action"]
        event = self.field_repository.add_event(
            work_log["field_id"],
            {
                "event_type": _plant_action_event_type(work_log["action_type"]),
                "occurred_at": work_log["performed_on"],
                "title": work_log["title"],
                "description": work_log["note"],
                "rating": work_log["rating"],
                "attachments": work_log["attachments"],
                "target_placement_id": planting["placement_id"],
                "target_name": planting["placement_name"],
                "source_work_log_id": work_log["id"],
                "tags": ["plant-calendar", work_log["action_type"], work_log["crop_name"], "manager-approved"],
            },
        )
        follow_up = _empty_follow_up("次回を自動生成しない作業です。")
        task_rule = next((rule for rule in calendar.get("task_rules", []) if rule.get("rule_id") == approved_action.get("rule_id")), None)
        if task_rule:
            current_calendar = self.plant_repository.get_calendar(planting_id) or {}
            follow_up_field = self.field_repository.get(planting["field_id"]) or {}
            follow_up_context = {
                "planting": self.plant_repository.get_planting(planting_id) or planting,
                "field": {"id": follow_up_field.get("id"), "location": follow_up_field.get("location", {})},
                "care_profile": current_calendar.get("care_profile", {}),
                "growth_targets": planting.get("growth_targets", {}),
                "task_rule": task_rule,
                "completed_action": approved_action,
                "completion_event": work_log,
                "planned_actions": [item for item in current_calendar.get("actions", []) if item.get("status") == "planned"],
                "recent_work_logs": self.plant_repository.recent_work_logs(planting_id, limit=12),
                "fertilizer_history": self.plant_repository.fertilizer_effect_context(planting_id, as_of=work_log["performed_on"]),
                "audience": audience or {},
            }
            generated = self.ai_content_service.generate_follow_up_tasks(follow_up_context)
            appended_actions = self.plant_repository.append_generated_actions(planting_id, generated.get("actions") or [])
            follow_up = {**generated, "actions": appended_actions}
        return {**result, "event": event, "follow_up": follow_up}

    @staticmethod
    def assert_actor_can_work(action: dict, *, actor_email: str, actor_role: str):
        assigned_to = str(action.get("assigned_to") or "").strip().lower()
        actor_email = str(actor_email or "").strip().lower()
        if actor_role != "admin" and assigned_to and assigned_to != actor_email:
            raise PlantActionAuthorizationError("この作業は別の担当者に割り当てられています")

    def _action_context(self, planting_id: str, action_id: str):
        planting = self.plant_repository.get_planting(planting_id)
        if planting is None:
            raise PlantManagementNotFoundError("planting not found")
        calendar = self.plant_repository.get_calendar(planting_id)
        action = next((item for item in (calendar or {}).get("actions", []) if item.get("id") == action_id), None)
        if calendar is None or action is None:
            raise PlantManagementNotFoundError("calendar action not found")
        return planting, calendar, action


def _required_date(value, path: str):
    try:
        return date.fromisoformat(str(value or "").strip()).isoformat()
    except ValueError as exc:
        raise PlantManagementValidationError(f"{path} must be YYYY-MM-DD") from exc


def _required_rating(value):
    try:
        rating = int(value)
    except (TypeError, ValueError) as exc:
        raise PlantManagementValidationError("rating must be an integer from 1 to 5") from exc
    if rating < 1 or rating > 5:
        raise PlantManagementValidationError("rating must be an integer from 1 to 5")
    return rating


def _work_details(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PlantManagementValidationError("work_details must be valid JSON") from exc
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise PlantManagementValidationError("work_details must be an object")
    return value


def _empty_follow_up(summary: str):
    return {"actions": [], "decision_summary": summary, "source": "rule"}


def _plant_action_event_type(action_type):
    return {
        "fertilization": "fertilizer",
        "pest_control": "pest",
        "harvest": "harvest",
        "watering": "watering",
    }.get(action_type, "other")
