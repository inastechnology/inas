import copy
from datetime import datetime, timedelta
from urllib.parse import quote

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.camera_growth_assessment_repository import camera_growth_assessment_repository
from ina_device_hub.camera_management_service import camera_management_service
from ina_device_hub.field_layout_repository import field_layout_repository
from ina_device_hub.field_repository import field_repository
from ina_device_hub.general_log import logger
from ina_device_hub.plant_action_catalog import normalize_plant_action_type
from ina_device_hub.plant_management_repository import plant_management_repository
from ina_device_hub.sensor_measurement_repository import sensor_measurement_repository
from ina_device_hub.timelapse_media_service import timelapse_media_service

MAX_CAPTURE_BYTES = 10 * 1024 * 1024
MIN_COMPARISON_AGE = timedelta(hours=12)
MAX_COMPARISON_AGE = timedelta(days=14)
VALID_OVERALL_STATUSES = {"healthy", "attention", "concern", "insufficient_evidence"}
VALID_OBSERVATION_CATEGORIES = {"growth", "leaf", "flower", "fruit", "pest", "disease", "water", "environment", "other"}
VALID_OBSERVATION_SEVERITIES = {"info", "watch", "warning"}
VALID_CONCERN_SEVERITIES = {"watch", "warning"}
VALID_ACTION_PRIORITIES = {"required", "should", "recommended", "optional"}


class CameraGrowthMonitoringNotFoundError(LookupError):
    pass


class CameraGrowthMonitoringValidationError(ValueError):
    pass


class CameraGrowthCaptureError(RuntimeError):
    pass


class CameraGrowthAIUnavailableError(RuntimeError):
    pass


class CameraGrowthAnalysisError(RuntimeError):
    pass


class CameraGrowthMonitoringService:
    def __init__(
        self,
        *,
        field_repo=None,
        layout_repo=None,
        plant_repo=None,
        camera_service=None,
        connector=None,
        media_service=None,
        measurement_repo=None,
        ai_service=None,
        assessment_repo=None,
        now_provider=None,
    ):
        self.field_repository = field_repo or field_repository()
        self.layout_repository = layout_repo or field_layout_repository()
        self.plant_repository = plant_repo or plant_management_repository()
        self.camera_service = camera_service or camera_management_service()
        self.connector = connector or camera_connector()
        self.media_service = media_service or timelapse_media_service()
        self.measurement_repository = measurement_repo or sensor_measurement_repository()
        self.ai_service = ai_service or ai_content_service()
        self.assessment_repository = assessment_repo or camera_growth_assessment_repository()
        self.now_provider = now_provider or datetime.now

    def dashboard(self, field_id: str, *, limit: int = 30):
        field, layout, plantings = self._field_state(field_id)
        assessments = self.assessment_repository.list(field_id=field_id, limit=limit)
        return {
            "field": {"id": field["id"], "name": field.get("name") or field["id"]},
            "image_ai_configured": self.ai_service.image_analysis_available(),
            "sources": self._build_sources(field, layout, plantings, assessments),
            "assessments": assessments,
        }

    def list_assessments(self, field_id: str, *, camera_id: str = "", limit: int = 50):
        self._field_state(field_id)
        return self.assessment_repository.list(field_id=field_id, camera_id=camera_id, limit=limit)

    def create_assessment(self, field_id: str, camera_id: str, *, created_by: str, audience: dict | None = None):
        field, layout, plantings = self._field_state(field_id)
        assessments = self.assessment_repository.list(field_id=field_id, limit=200)
        source = next(
            (item for item in self._build_sources(field, layout, plantings, assessments) if item["camera_id"] == camera_id),
            None,
        )
        if source is None:
            raise CameraGrowthMonitoringNotFoundError("設置ビューにこのカメラがありません")
        if source["blocking_reasons"]:
            reason = source["blocking_reasons"][0]
            if reason["code"] == "ai_not_configured":
                raise CameraGrowthAIUnavailableError(reason["message"])
            raise CameraGrowthMonitoringValidationError(reason["message"])

        captured_at = self._local_now()
        previous_frame, previous_bytes = self._previous_frame(camera_id, captured_at)
        image_bytes = self.connector.take_picture(camera_id, timeout_seconds=20)
        if not self._valid_jpeg(image_bytes):
            raise CameraGrowthCaptureError("カメラから有効なJPEG画像を取得できませんでした。接続と映像を確認してください")
        if len(image_bytes) > MAX_CAPTURE_BYTES:
            raise CameraGrowthCaptureError("取得した画像が大きすぎるため解析できませんでした")

        saved_path = self.media_service.save_frame(camera_id, image_bytes, captured_at=captured_at)
        if not saved_path:
            raise CameraGrowthCaptureError("撮影画像を保存できませんでした")
        current_frame = self._frame_record(camera_id, captured_at)
        context = self._analysis_context(field, layout, source, audience or {})
        images = [
            {
                "label": "現在画像",
                "captured_at": current_frame["captured_at"],
                "bytes": image_bytes,
            }
        ]
        if previous_frame and previous_bytes:
            images.append(
                {
                    "label": "比較画像（過去）",
                    "captured_at": previous_frame["captured_at"],
                    "bytes": previous_bytes,
                }
            )
        try:
            raw_result = self.ai_service.assess_plant_growth(context, images)
        except RuntimeError as exc:
            logger.warning("Camera growth analysis failed for camera_id=%s", camera_id)
            raise CameraGrowthAnalysisError("AIによる画像評価を完了できませんでした。AI設定と接続を確認して再実行してください") from exc

        result = normalize_growth_assessment_result(raw_result, comparison_available=bool(previous_frame and previous_bytes))
        return self.assessment_repository.create(
            {
                "field_id": field_id,
                "camera_id": camera_id,
                "camera_name": source["camera_name"],
                "camera_placement_id": source["camera_placement_id"],
                "target_placement_ids": source["target_placement_ids"],
                "planting_ids": [item["id"] for item in source["plantings"]],
                "crop_labels": [item["crop_label"] for item in source["plantings"]],
                "current_frame": current_frame,
                "previous_frame": previous_frame,
                "result": result,
                "context_snapshot": context,
                "created_by": created_by,
            }
        )

    def _field_state(self, field_id: str):
        field = self.field_repository.get(field_id)
        if field is None:
            raise CameraGrowthMonitoringNotFoundError("圃場が見つかりません")
        layout = self.layout_repository.get(field_id, field_name=field.get("name", ""))
        bundle = self.plant_repository.field_bundle(field_id, statuses={"active"}, include_work_logs=False)
        plantings = [item for item in bundle.get("plantings", []) if item.get("status") == "active"]
        return field, layout, plantings

    def _build_sources(self, field: dict, layout: dict, plantings: list, assessments: list):
        placements, spaces = _layout_indexes(layout)
        latest_by_camera = {}
        for assessment in assessments:
            latest_by_camera.setdefault(assessment.get("camera_id"), assessment)
        sources = []
        for space in layout.get("spaces") or []:
            for placement in space.get("placements") or []:
                binding = placement.get("binding") or {}
                if placement.get("preset") != "camera" or binding.get("resource_type") != "camera":
                    continue
                camera_id = binding.get("device_id") or ""
                camera = self.camera_service.get(camera_id) if camera_id else None
                target_ids = [item for item in binding.get("target_placement_ids") or [] if item in placements]
                expanded_ids = _expand_target_placement_ids(target_ids, placements, spaces)
                source_plantings = [_planting_summary(item) for item in plantings if item.get("placement_id") in expanded_ids]
                areas = [
                    {
                        "id": target_id,
                        "name": placements[target_id].get("name") or target_id,
                        "preset": placements[target_id].get("preset") or "",
                    }
                    for target_id in target_ids
                ]
                blocking_reasons = []
                if camera is None:
                    blocking_reasons.append({"code": "camera_not_registered", "message": "登録済みカメラを設置ビューに割り当て直してください"})
                if not target_ids:
                    blocking_reasons.append({"code": "targets_missing", "message": "設置ビューでカメラの監視対象を選択してください"})
                if target_ids and not source_plantings:
                    blocking_reasons.append({"code": "planting_missing", "message": "監視対象の場所に定植中の作物を登録してください"})
                if not self.ai_service.image_analysis_available():
                    blocking_reasons.append({"code": "ai_not_configured", "message": "アプリ設定で画像AIのAPIキーとモデルを設定してください"})
                frames = self.media_service.list_frame_records(camera_id, limit=1) if camera else []
                sources.append(
                    {
                        "camera_id": camera_id,
                        "camera_name": (camera or {}).get("name") or placement.get("name") or camera_id,
                        "camera_placement_id": placement.get("id") or "",
                        "camera_placement_name": placement.get("name") or "",
                        "space_id": space.get("id") or "",
                        "space_name": space.get("name") or "",
                        "target_placement_ids": target_ids,
                        "monitored_areas": areas,
                        "plantings": source_plantings,
                        "latest_frame": frames[0] if frames else None,
                        "latest_assessment": latest_by_camera.get(camera_id),
                        "detail_url": f"/camera/{quote(camera_id, safe='')}" if camera_id else "",
                        "preview_url": f"/camera/{quote(camera_id, safe='')}#live" if camera_id else "",
                        "images_url": f"/camera/{quote(camera_id, safe='')}#captures" if camera_id else "",
                        "ready": not blocking_reasons,
                        "blocking_reasons": blocking_reasons,
                        "_expanded_target_ids": sorted(expanded_ids),
                    }
                )
        sources.sort(key=lambda item: ((item.get("camera_name") or item.get("camera_id") or "").casefold(), item.get("camera_id") or ""))
        return sources

    def _analysis_context(self, field: dict, layout: dict, source: dict, audience: dict):
        environment_type = ((field.get("location") or {}).get("environment_type") or "")[:80]
        sensor_readings = self._sensor_readings(layout, set(source["_expanded_target_ids"]))
        return {
            "field": {"id": field["id"], "name": field.get("name") or field["id"], "environment_type": environment_type},
            "monitored_areas": copy.deepcopy(source["monitored_areas"]),
            "plantings": [
                {
                    key: item.get(key)
                    for key in (
                        "id",
                        "placement_id",
                        "placement_name",
                        "crop_name",
                        "cultivar",
                        "crop_category",
                        "tree_age_years",
                        "planted_on",
                        "plant_count",
                        "cultivation_method",
                        "conditions",
                        "growth_targets",
                    )
                }
                for item in source["plantings"]
            ],
            "sensor_readings": sensor_readings,
            "audience": {"experience_level": str(audience.get("experience_level") or "standard")[:40]},
        }

    def _sensor_readings(self, layout: dict, target_ids: set[str]):
        device_ids = []
        for space in layout.get("spaces") or []:
            for placement in space.get("placements") or []:
                binding = placement.get("binding") or {}
                if binding.get("resource_type") == "camera":
                    continue
                binding_targets = set(binding.get("target_placement_ids") or [])
                if binding.get("device_id") and binding_targets & target_ids:
                    device_ids.append(binding["device_id"])
        readings = []
        for device_id in list(dict.fromkeys(device_ids))[:10]:
            try:
                measurements = self.measurement_repository.latest_for_device(device_id, limit=20)
            except Exception:
                logger.warning("Could not load camera-growth sensor context for device_id=%s", device_id)
                continue
            seen_metrics = set()
            for measurement in measurements:
                metric = str(measurement.get("metric") or "")
                if not metric or metric in seen_metrics:
                    continue
                seen_metrics.add(metric)
                readings.append(
                    {
                        "device_id": device_id,
                        "metric": metric[:100],
                        "value": measurement.get("value"),
                        "unit": str(measurement.get("unit") or "")[:40],
                        "measured_at": str(measurement.get("measured_at") or "")[:80],
                    }
                )
                if len(readings) >= 30:
                    return readings
        return readings

    def _previous_frame(self, camera_id: str, captured_at: datetime):
        frames = self.media_service.list_frame_records(
            camera_id,
            start_at=captured_at - MAX_COMPARISON_AGE,
            end_at=captured_at - MIN_COMPARISON_AGE,
            limit=1,
        )
        if not frames:
            return None, None
        frame = frames[0]
        path = self.media_service.resolve_frame_path(frame.get("relative_path") or "")
        if not path:
            return None, None
        try:
            with open(path, "rb") as file:
                image_bytes = file.read(MAX_CAPTURE_BYTES + 1)
        except OSError:
            return None, None
        if len(image_bytes) > MAX_CAPTURE_BYTES or not self._valid_jpeg(image_bytes):
            return None, None
        return frame, image_bytes

    def _frame_record(self, camera_id: str, captured_at: datetime):
        relative_path = self.media_service.get_frame_relative_path(camera_id, captured_at)
        return {
            "camera_id": camera_id,
            "captured_at": captured_at.isoformat(),
            "relative_path": relative_path,
            "url": f"/local/api/camera-images/{quote(relative_path, safe='/')}",
        }

    def _local_now(self):
        value = self.now_provider()
        if value.tzinfo is not None:
            value = value.astimezone().replace(tzinfo=None)
        return value

    @staticmethod
    def _valid_jpeg(value):
        return isinstance(value, bytes) and len(value) >= 4 and value.startswith(b"\xff\xd8") and value.endswith(b"\xff\xd9")


def normalize_growth_assessment_result(value: dict, *, comparison_available: bool):
    value = value if isinstance(value, dict) else {}
    overall_status = _clean_choice(value.get("overall_status"), VALID_OVERALL_STATUSES, "insufficient_evidence")
    confidence = _bounded_float(value.get("confidence"), 0.0, 0.0, 1.0)
    observations = []
    for item in _object_list(value.get("observations"), 12):
        finding = _clean_text(item.get("finding"), 600)
        if not finding:
            continue
        observations.append(
            {
                "category": _clean_choice(item.get("category"), VALID_OBSERVATION_CATEGORIES, "other"),
                "finding": finding,
                "evidence": _clean_text(item.get("evidence"), 600),
                "severity": _clean_choice(item.get("severity"), VALID_OBSERVATION_SEVERITIES, "info"),
            }
        )
    comparison = value.get("comparison") if isinstance(value.get("comparison"), dict) else {}
    normalized_comparison = {
        "available": comparison_available and _clean_bool(comparison.get("available"), True),
        "summary": _clean_text(comparison.get("summary"), 800) if comparison_available else "比較できる過去画像がありません。",
        "changes": _string_list(comparison.get("changes"), 10, 500) if comparison_available else [],
    }
    concerns = []
    for item in _object_list(value.get("concerns"), 10):
        title = _clean_text(item.get("title"), 240)
        if title:
            concerns.append(
                {
                    "title": title,
                    "severity": _clean_choice(item.get("severity"), VALID_CONCERN_SEVERITIES, "watch"),
                    "evidence": _clean_text(item.get("evidence"), 600),
                }
            )
    actions = []
    for item in _object_list(value.get("suggested_actions"), 10):
        title = _clean_text(item.get("title"), 240)
        if not title:
            continue
        action_type = normalize_plant_action_type(item.get("action_type"), "other")
        checks = _string_list(item.get("checks_before_action"), 10, 500)
        skips = _string_list(item.get("skip_conditions"), 10, 500)
        if action_type in {"fertilization", "pest_control", "gibberellin_treatment"}:
            _append_unique(checks, "使用する資材・薬剤が対象作物と用途に登録されているか製品ラベルで確認する")
            _append_unique(skips, "登録内容、使用量、使用時期を製品ラベルで確認できない場合は実施しない")
        actions.append(
            {
                "title": title,
                "action_type": action_type,
                "priority": _clean_choice(item.get("priority"), VALID_ACTION_PRIORITIES, "recommended"),
                "timing": _clean_text(item.get("timing"), 300),
                "reason": _clean_text(item.get("reason"), 800),
                "checks_before_action": checks,
                "instructions": _string_list(item.get("instructions"), 10, 500),
                "skip_conditions": skips,
            }
        )
    if not actions and overall_status == "insufficient_evidence":
        actions.append(
            {
                "title": "現物を観察して追加記録を残す",
                "action_type": "observation",
                "priority": "recommended",
                "timing": "次回の作業前",
                "reason": "画像だけでは生育状態を十分に判断できないため",
                "checks_before_action": ["葉の表裏、茎、果実、培地の状態を現物で確認する"],
                "instructions": ["同じ位置と明るさで写真を撮り、変化を記録する"],
                "skip_conditions": [],
            }
        )
    needs_human_review = (
        confidence < 0.65
        or overall_status in {"concern", "insufficient_evidence"}
        or any(item["severity"] == "warning" for item in concerns)
        or any(item["action_type"] in {"fertilization", "pest_control", "pruning", "harvest", "gibberellin_treatment"} for item in actions)
    )
    limitations = _string_list(value.get("limitations"), 10, 500)
    _append_unique(limitations, "カメラ画像だけでは、根・培地内部・葉裏・臭い・触感を確認できません。")
    return {
        "schema_version": 1,
        "overall_status": overall_status,
        "confidence": confidence,
        "summary": _clean_text(value.get("summary"), 1000) or "画像から十分な評価結果を得られませんでした。",
        "observations": observations,
        "comparison": normalized_comparison,
        "concerns": concerns,
        "suggested_actions": actions,
        "limitations": limitations,
        "needs_human_review": needs_human_review,
    }


def _layout_indexes(layout: dict):
    placements = {}
    spaces = {}
    for space in layout.get("spaces") or []:
        spaces[space.get("id")] = space
        for placement in space.get("placements") or []:
            placements[placement.get("id")] = placement
    return placements, spaces


def _expand_target_placement_ids(target_ids: list[str], placements: dict, spaces: dict):
    expanded = set()
    visited_spaces = set()

    def add_space(space_id):
        if not space_id or space_id in visited_spaces:
            return
        visited_spaces.add(space_id)
        for child in (spaces.get(space_id) or {}).get("placements") or []:
            child_id = child.get("id")
            if child_id:
                expanded.add(child_id)
            add_space(child.get("child_space_id"))

    for target_id in target_ids:
        target = placements.get(target_id)
        if not target:
            continue
        expanded.add(target_id)
        add_space(target.get("child_space_id"))
    return expanded


def _planting_summary(value: dict):
    crop_label = " / ".join(item for item in (value.get("crop_name"), value.get("cultivar")) if item)
    return {**copy.deepcopy(value), "crop_label": crop_label or value.get("id") or "作物"}


def _object_list(value, limit):
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def _string_list(value, limit, item_length):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        text = _clean_text(item, item_length)
        if text and text not in result:
            result.append(text)
    return result


def _clean_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _clean_choice(value, choices, default):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in choices else default


def _bounded_float(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, number))


def _clean_bool(value, default):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _append_unique(values, value):
    if value not in values:
        values.append(value)


__instance = None


def camera_growth_monitoring_service():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = CameraGrowthMonitoringService()
    return __instance
