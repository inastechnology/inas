import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import UTC, date, datetime
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")
os.environ["HUB_AUTH_MODE"] = "local"

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.field_layout_collaboration_service import FieldLayoutCollaborationService  # noqa: E402
from ina_device_hub.field_layout_repository import FieldLayoutRepository  # noqa: E402
from ina_device_hub.field_repository import FieldRepository  # noqa: E402
from ina_device_hub.plant_calendar_generation_task import PlantCalendarGenerationTask  # noqa: E402
from ina_device_hub.plant_management_repository import PlantManagementRepository  # noqa: E402
from ina_device_hub.sensor_device_repository import SensorDeviceRepository  # noqa: E402


class FakeTimelapseMediaService:
    def __init__(self):
        self.calls = []
        self.video_calls = []

    def list_frame_records(self, device_id, start_at=None, end_at=None, limit=100):
        self.calls.append((device_id, start_at, end_at, limit))
        return [
            {
                "camera_id": device_id,
                "captured_at": "2026-07-04T06:30:00",
                "relative_path": "timelapse_frames/camera-1/20260704/20260704_063000.jpg",
                "url": "/local/api/camera-images/timelapse_frames/camera-1/20260704/20260704_063000.jpg",
            }
        ]

    def list_video_records(self, device_id, limit=20):
        del device_id, limit
        return []

    def ensure_recent_video(self, device_id, *, start_at, end_at, fps=8, max_frames=96):
        self.video_calls.append((device_id, start_at, end_at, fps, max_frames))
        return {
            "camera_id": device_id,
            "captured_at": "2026-07-04T06:30:00",
            "frame_count": 12,
            "relative_path": f"timelapse_videos/{device_id}/20260704/20260704_063000.mp4",
            "url": f"/local/api/camera-videos/timelapse_videos/{device_id}/20260704/20260704_063000.mp4",
        }


class FakeAIContentService:
    def __init__(self):
        self.connection_overrides = None
        self.calendar_contexts = []
        self.follow_up_contexts = []
        self.question_contexts = []

    def reload_settings(self):
        return None

    def test_connection(self, channel, overrides=None):
        self.connection_overrides = overrides
        return {"ok": True, "model": overrides.get("model"), "response": "OK"}

    def generate_plant_calendar(self, context, guidance_examples=None):
        self.calendar_contexts.append(deepcopy(context))
        planted_on = context["planting"]["planted_on"]
        return {
            "growth_targets": {
                "soil_moisture_percent": {"min": 32, "max": 62},
                "soil_ec_us_cm": {"min": 400, "max": 1200},
            },
            "actions": [
                {
                    "action_type": "fertilization",
                    "title": "追肥要否を確認",
                    "priority": "recommended",
                    "window_start": planted_on,
                    "window_end": "2026-07-31",
                    "timing_label": "活着後",
                    "reason": "樹勢を確認するため",
                    "instructions": "葉色を確認する",
                    "tags": ["追肥", "樹勢維持"],
                    "rule_id": "rule-fertilization",
                }
            ],
            "care_profile": {
                "summary": "ブルーベリーの栽培基準",
                "fertilization": {"strategy": "葉色とECで判断する"},
            },
            "task_rules": [
                {
                    "rule_id": "rule-fertilization",
                    "action_type": "fertilization",
                    "title": "追肥要否を確認",
                    "recurrence_type": "interval_after_completion",
                    "anchor": "completion_date",
                    "interval_days": {"min": 30, "preferred": 45, "max": 60},
                    "active_months": list(range(1, 13)),
                }
            ],
            "generation": {"source": "test", "guidance_count": len(guidance_examples or [])},
        }

    def generate_follow_up_tasks(self, context):
        self.follow_up_contexts.append(deepcopy(context))
        return {
            "source": "test",
            "decision_summary": "実施日から次回を計算",
            "actions": [
                {
                    "rule_id": context["task_rule"]["rule_id"],
                    "action_type": "fertilization",
                    "title": "次回の追肥要否を確認",
                    "priority": "recommended",
                    "window_start": "2026-08-20",
                    "window_end": "2026-09-05",
                }
            ],
        }

    def answer_plant_question(self, context, question):
        self.question_contexts.append({"context": deepcopy(context), "question": question})
        return f"{context['planting']['crop_name']}について回答: {question}"


class FakeDeviceConfigService:
    def __init__(self):
        self.records = {}
        self.get_all_calls = 0

    def get_all_records(self):
        self.get_all_calls += 1
        return self.records

    def find_record(self, device_id):
        return self.records.get(device_id)

    def list_statuses(self, device_id, limit=100):
        return deepcopy((self.records.get(device_id) or {}).get("status_history") or [])[-limit:]

    def search_records(self, *, query="", states=None, device_kinds=None, page=1, page_size=50):
        items = {
            device_id: record
            for device_id, record in self.records.items()
            if not query or query.casefold() in " ".join((device_id, record.get("name", ""), record.get("location", ""))).casefold()
        }
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": page_size,
            "page_count": 1,
            "has_previous": False,
            "has_next": False,
        }


class FakeSensorMeasurementRepository:
    def __init__(self):
        self.measurements = []

    def latest_for_device(self, device_id, limit=100):
        return [item for item in reversed(self.measurements) if item["device_id"] == device_id][:limit]

    def between_for_devices(self, device_ids, start_at, end_at, limit=5000, metric=None):
        return [
            item
            for item in reversed(self.measurements)
            if item["device_id"] in device_ids and (not metric or item.get("metric") == metric) and start_at <= item["measured_at"] < end_at
        ][:limit]


class FakeFieldRecordMediaService:
    def __init__(self):
        self.objects = {}

    def upload_images(self, field_id, occurred_at, files):
        attachments = []
        for index, image in enumerate(file for file in files if file.filename):
            image_bytes = image.read()
            attachment_id = f"attachment-{len(self.objects) + index + 1}"
            attachment = {
                "id": attachment_id,
                "storage": "r2",
                "object_key": f"field-records/{field_id}/{str(occurred_at)[:10]}/{attachment_id}.png",
                "content_type": "image/png",
                "size_bytes": len(image_bytes),
                "original_filename": image.filename,
                "url": f"/local/api/fields/{field_id}/record-images/{attachment_id}",
            }
            self.objects[attachment_id] = image_bytes
            attachments.append(attachment)
        return attachments

    def fetch_image(self, attachment):
        return self.objects[attachment["id"]]


class FakeUserPreferenceRepository:
    def __init__(self):
        self.records = {}

    def get(self, user_email):
        return deepcopy(
            self.records.get(
                user_email.lower(),
                {
                    "user_email": user_email.lower(),
                    "locale": "ja",
                    "timezone": "Asia/Tokyo",
                    "date_format": "yyyy-MM-dd",
                    "preferences": {"cultivation_experience": "standard", "font_size": "standard", "contrast": "standard"},
                    "version": 0,
                    "created_at": "",
                    "updated_at": "",
                },
            )
        )

    def update(self, user_email, value, expected_version):
        current = self.get(user_email)
        if current["version"] != expected_version:
            raise web_server.UserPreferenceConflictError(current)
        saved = {
            **current,
            "locale": "ja",
            "timezone": value.get("timezone", "Asia/Tokyo"),
            "date_format": value.get("date_format", "yyyy-MM-dd"),
            "preferences": {
                **deepcopy(value.get("preferences") or {}),
                "cultivation_experience": (value.get("preferences") or {}).get("cultivation_experience", "standard"),
                "font_size": (value.get("preferences") or {}).get("font_size", "standard"),
                "contrast": (value.get("preferences") or {}).get("contrast", "standard"),
            },
            "version": expected_version + 1,
            "updated_at": "2026-07-15 12:00:00",
        }
        self.records[user_email.lower()] = saved
        return deepcopy(saved)


class WebServerBasicUITest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sensor_device_repository = SensorDeviceRepository()
        self.sensor_device_repository.device_repo_path = os.path.join(self.tmp_dir.name, ".device_list.json")
        self.sensor_device_repository.device_dict = {}
        self.sensor_device_repository.save()

        self.original_sensor_device_repository = web_server.sensor_device_repository
        web_server.sensor_device_repository = lambda: self.sensor_device_repository
        self.fake_timelapse_media_service = FakeTimelapseMediaService()
        self.original_timelapse_media_service = web_server.timelapse_media_service
        web_server.timelapse_media_service = lambda: self.fake_timelapse_media_service
        self.field_repository = FieldRepository()
        self.field_repository.field_repo_path = os.path.join(self.tmp_dir.name, ".fields.json")
        self.field_repository.fields = {}
        self.field_repository.save()
        self.original_field_repository = web_server.field_repository
        web_server.field_repository = lambda: self.field_repository
        self.field_layout_repository = FieldLayoutRepository()
        self.field_layout_repository.layout_repo_path = os.path.join(self.tmp_dir.name, ".field_layouts.json")
        self.field_layout_repository.layouts = {}
        self.field_layout_repository.save()
        self.original_field_layout_repository = web_server.field_layout_repository
        web_server.field_layout_repository = lambda: self.field_layout_repository
        self.field_layout_collaboration_service = FieldLayoutCollaborationService()
        self.original_field_layout_collaboration_service = web_server.field_layout_collaboration_service
        web_server.field_layout_collaboration_service = lambda: self.field_layout_collaboration_service
        self.plant_management_repository = PlantManagementRepository()
        self.plant_management_repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.plant_management_repository.data = {
            "schema_version": 2,
            "plantings": {},
            "calendars": {},
            "generation_tasks": [],
            "feedback": [],
            "work_logs": [],
            "questions": [],
        }
        self.plant_management_repository.save()
        self.original_plant_management_repository = web_server.plant_management_repository
        web_server.plant_management_repository = lambda: self.plant_management_repository
        self.original_ai_content_service = web_server.ai_content_service
        self.fake_ai_content_service = FakeAIContentService()
        web_server.ai_content_service = lambda: self.fake_ai_content_service
        self.plant_calendar_generation_task = PlantCalendarGenerationTask(
            plant_repository=self.plant_management_repository,
            field_repository=self.field_repository,
            layout_repository=self.field_layout_repository,
            ai_service=self.fake_ai_content_service,
        )
        self.original_plant_calendar_generation_task = web_server.plant_calendar_generation_task
        web_server.plant_calendar_generation_task = lambda: self.plant_calendar_generation_task
        self.fake_device_config_service = FakeDeviceConfigService()
        self.original_device_config_service = web_server.device_config_service
        web_server.device_config_service = lambda: self.fake_device_config_service
        self.fake_sensor_measurement_repository = FakeSensorMeasurementRepository()
        self.original_sensor_measurement_repository = web_server.sensor_measurement_repository
        web_server.sensor_measurement_repository = lambda: self.fake_sensor_measurement_repository
        self.fake_field_record_media_service = FakeFieldRecordMediaService()
        self.original_field_record_media_service = web_server.field_record_media_service
        web_server.field_record_media_service = lambda: self.fake_field_record_media_service
        self.fake_user_preference_repository = FakeUserPreferenceRepository()
        self.original_user_preference_repository = web_server.user_preference_repository
        web_server.user_preference_repository = lambda: self.fake_user_preference_repository
        self.client = web_server.app.test_client()

    def tearDown(self):
        web_server.sensor_device_repository = self.original_sensor_device_repository
        web_server.timelapse_media_service = self.original_timelapse_media_service
        web_server.field_repository = self.original_field_repository
        web_server.field_layout_repository = self.original_field_layout_repository
        web_server.field_layout_collaboration_service = self.original_field_layout_collaboration_service
        web_server.plant_management_repository = self.original_plant_management_repository
        web_server.ai_content_service = self.original_ai_content_service
        web_server.plant_calendar_generation_task = self.original_plant_calendar_generation_task
        web_server.device_config_service = self.original_device_config_service
        web_server.sensor_measurement_repository = self.original_sensor_measurement_repository
        web_server.field_record_media_service = self.original_field_record_media_service
        web_server.user_preference_repository = self.original_user_preference_repository
        self.tmp_dir.cleanup()

    def test_personal_preferences_are_separate_from_app_settings_without_language_control(self):
        headers = {"Cf-Access-Authenticated-User-Email": "worker@example.com"}
        page = self.client.get("/preferences", headers=headers)

        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("個人設定", html)
        self.assertIn("worker@example.com", html)
        self.assertNotIn("AIテキストAPI", html)
        self.assertNotIn('name="locale"', html)
        self.assertNotIn("表示言語", html)
        self.assertIn('name="cultivation_experience"', html)
        self.assertIn('name="font_size"', html)
        self.assertIn('value="standard"', html)
        self.assertIn('value="large"', html)
        self.assertIn('value="extra_large"', html)
        self.assertIn("本文18px目安", html)
        self.assertIn("a11y-font-standard", html)
        self.assertIn('name="contrast"', html)
        self.assertIn("くっきり", html)
        self.assertIn("a11y-contrast-standard", html)
        self.assertIn("初心者 - 手順を詳しく", html)
        self.assertIn('id="advice-help-open"', html)
        self.assertIn('id="advice-help-dialog"', html)
        self.assertIn("同じ「トマトの追肥」", html)
        self.assertIn("初心者 — 小学生でも分かる言葉", html)
        self.assertIn("標準 — 大人向けの一般的な説明", html)
        self.assertIn("プロ — 専門用語と判断根拠", html)
        self.assertIn("つぶの肥料", html)
        self.assertIn("下の葉の色が薄くなったり、育つ速さが遅くなった場合は追肥が必要です", html)
        self.assertIn("実際に葉の色と育つ速さを確認してください", html)
        self.assertIn("固形肥料", html)
        self.assertIn("培地EC・pH、原水EC、排液率", html)

        saved = self.client.patch(
            "/local/api/me/preferences",
            headers=headers,
            json={
                "version": 0,
                "locale": "en",
                "timezone": "UTC",
                "date_format": "MM/dd/yyyy",
                "preferences": {"cultivation_experience": "beginner", "font_size": "extra_large", "contrast": "high"},
            },
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["preferences"]["version"], 1)
        self.assertEqual(saved.get_json()["preferences"]["locale"], "ja")
        self.assertEqual(saved.get_json()["preferences"]["preferences"]["cultivation_experience"], "beginner")
        self.assertEqual(saved.get_json()["preferences"]["preferences"]["font_size"], "extra_large")
        self.assertEqual(saved.get_json()["preferences"]["preferences"]["contrast"], "high")
        self.assertNotIn("Set-Cookie", saved.headers)

    def test_saved_font_size_class_is_applied_to_server_and_react_pages(self):
        self.fake_user_preference_repository.records["local-user@ina.local"] = {
            "user_email": "local-user@ina.local",
            "locale": "ja",
            "timezone": "Asia/Tokyo",
            "date_format": "yyyy-MM-dd",
            "preferences": {"cultivation_experience": "standard", "font_size": "extra_large", "contrast": "high"},
            "version": 1,
            "created_at": "",
            "updated_at": "2026-07-20 00:00:00",
        }

        for path in ("/preferences", "/fields", "/settings", "/demo/mqtt-devices", "/cameras/new"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("a11y-font-extra-large", response.get_data(as_text=True))
                self.assertIn("a11y-contrast-high", response.get_data(as_text=True))

    def test_personal_preferences_return_latest_value_on_concurrent_edit(self):
        headers = {"Cf-Access-Authenticated-User-Email": "worker@example.com"}
        first = self.client.patch(
            "/local/api/me/preferences",
            headers=headers,
            json={"version": 0, "locale": "ja", "timezone": "Asia/Tokyo", "date_format": "yyyy-MM-dd"},
        )
        stale = self.client.patch(
            "/local/api/me/preferences",
            headers=headers,
            json={"version": 0, "locale": "en", "timezone": "UTC", "date_format": "MM/dd/yyyy"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["code"], "revision_conflict")
        self.assertEqual(stale.get_json()["current"]["version"], 1)

    def test_operator_can_open_personal_settings_but_not_app_settings(self):
        headers = {"Cf-Access-Authenticated-User-Email": "worker@example.com"}
        with patch.dict(os.environ, {"HUB_ADMIN_EMAILS": ""}):
            preferences = self.client.get("/preferences", headers=headers)
            settings = self.client.get("/settings", headers=headers)

        self.assertEqual(preferences.status_code, 200)
        self.assertEqual(settings.status_code, 403)
        self.assertIn("アプリ設定を開く権限がありません", settings.get_data(as_text=True))

    def test_configured_access_admin_can_open_app_settings(self):
        headers = {"Cf-Access-Authenticated-User-Email": "admin@example.com"}
        with patch.dict(os.environ, {"HUB_ADMIN_EMAILS": "admin@example.com"}):
            settings = self.client.get("/settings", headers=headers)

        self.assertEqual(settings.status_code, 200)

    def test_app_settings_page_renders_secret_write_only_inputs_and_instagram_settings(self):
        with patch.dict(os.environ, {"CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME": "hub.example.com"}):
            response = self.client.get("/settings?section=notifications")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("アプリ設定", html)
        self.assertIn('id="settings-search"', html)
        self.assertNotIn('name="default_language"', html)
        self.assertNotIn("システム既定言語", html)
        self.assertIn('name="text_analyze_model"', html)
        self.assertIn('name="image_analyze_model"', html)
        self.assertIn('name="text_analyze_temperature_mode"', html)
        self.assertIn('name="text_analyze_temperature"', html)
        self.assertIn('name="text_analyze_reasoning_effort"', html)
        self.assertIn("接続先とモデル特性を調整（上級者向け）", html)
        self.assertIn('id="ai-test-dialog"', html)
        self.assertIn("次に行うこと", html)
        self.assertIn('name="plant_calendar_prompt_template"', html)
        self.assertIn('name="plant_calendar_web_knowledge_enabled"', html)
        self.assertIn('name="plant_calendar_web_knowledge_cache_days"', html)
        self.assertIn("栽培情報を自動で調べる", html)
        self.assertIn("プロンプトフォーマットを編集", html)
        self.assertIn("{default_instructions}", html)
        self.assertIn('type="password" name="text_analyze_api_key" value=""', html)
        self.assertIn('type="password" name="image_analyze_api_key" value=""', html)
        for secret in (
            web_server.setting().get("ai").get("text_analyze_api_key"),
            web_server.setting().get("ai").get("image_analyze_api_key"),
            web_server.setting().get("instagram").get("access_token"),
        ):
            if secret:
                self.assertNotIn(secret, html)
        self.assertIn('name="post_schedule_start"', html)
        self.assertIn('name="posting_paused"', html)
        self.assertIn("Instagramへの自動投稿を一時停止する", html)
        self.assertIn('name="camera_id"', html)
        self.assertIn('id="instagram-camera-select"', html)
        self.assertIn("data-searchable-select", html)
        self.assertIn("/static/searchable-select.css", html)
        self.assertIn('name="plant_position_prompt"', html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("接続を確認", html)
        self.assertIn('id="notification-settings-form"', html)
        self.assertIn("今日の栽培作業", html)
        self.assertIn('name="plant_task_reminder_days_before"', html)
        self.assertIn('id="disable-all-notifications-dialog"', html)
        self.assertIn('role="switch" name="enabled"', html)
        self.assertIn('class="notification-switch-control"', html)
        self.assertIn("https://hub.example.com", html)
        self.assertNotIn("127.0.0.1", html)
        self.assertIn("土壌水分の未到達チェック", html)
        self.assertIn('href="/settings/post-watering-moisture"', html)

    def test_post_watering_moisture_wizard_selects_sensor_and_saves_rule(self):
        current_rules = deepcopy(web_server.setting().get("post_watering_moisture"))
        self.fake_device_config_service.records = {
            "WTR-001": {
                "name": "北畝の潅水機",
                "location": "1号ハウス",
                "state": "active",
                "device_kind": "WTR",
                "last_status": {"last_soil_moisture": 31},
            },
            "SOI-001": {
                "name": "北畝の水分計",
                "location": "1号ハウス 北畝",
                "state": "active",
                "device_kind": "SOI",
                "last_status": {"soil_moisture_percent": 44},
            },
            "SOI-002": {
                "name": "南畝の水分計",
                "location": "1号ハウス 南畝",
                "state": "active",
                "device_kind": "SOI",
                "last_status": {"soil_moisture_percent": 61},
            },
        }
        self.fake_sensor_measurement_repository.measurements = [
            {
                "device_id": "SOI-001",
                "device_kind": "SOI",
                "measured_at": "2026-08-24T01:00:00+00:00",
                "metric": "soil_moisture_percent",
                "value": 41.0,
            },
            {
                "device_id": "SOI-001",
                "device_kind": "SOI",
                "measured_at": "2026-08-25T01:00:00+00:00",
                "metric": "soil_moisture_percent",
                "value": 46.0,
            },
        ]
        try:
            page = self.client.get("/settings/post-watering-moisture?sensor_device_id=SOI-001")

            self.assertEqual(page.status_code, 200)
            html = page.get_data(as_text=True)
            self.assertIn("水分が回復していない状態を知らせる", html)
            self.assertIn("北畝の水分計", html)
            self.assertIn("南畝の水分計", html)
            self.assertIn('name="sensor_device_id" value="SOI-001"', html)
            self.assertIn('name="sensor_device_id" value="SOI-002"', html)
            self.assertIn("現在 44.0%", html)
            self.assertIn('id="post-watering-sensor-trend"', html)
            self.assertIn("選択センサーの直近3日", html)

            trend = self.client.get("/local/api/settings/post-watering-moisture/trend?sensor_device_id=SOI-001&days=7")
            self.assertEqual(trend.status_code, 200)
            self.assertEqual([point["value"] for point in trend.get_json()["points"]], [41.0, 46.0])
            self.assertEqual(trend.get_json()["latest"], 46.0)
            self.assertEqual(trend.get_json()["days"], 7)

            saved = self.client.post(
                "/settings/post-watering-moisture",
                data={
                    "sensor_device_id": "SOI-002",
                    "minimum_percent": "53.5",
                    "window_days": "7",
                    "enabled": "on",
                },
            )

            self.assertEqual(saved.status_code, 302)
            self.assertEqual(saved.headers["Location"], "/settings/post-watering-moisture?sensor_device_id=SOI-002&saved=1")
            rules = web_server.setting().get("post_watering_moisture")["rules"]
            self.assertEqual(rules[0]["sensor_device_id"], "SOI-002")
            self.assertEqual(rules[0]["minimum_percent"], 53.5)
            self.assertEqual(rules[0]["window_days"], 7)
            self.assertTrue(rules[0]["enabled"])

            reloaded = self.client.get(saved.headers["Location"])
            self.assertEqual(reloaded.status_code, 200)
            reloaded_html = reloaded.get_data(as_text=True)
            self.assertIn("土壌水分の未到達通知設定を保存しました", reloaded_html)
            self.assertIn("南畝の水分計", reloaded_html)
            self.assertIn("直近7日で53.5%未到達 / 使用中", reloaded_html)
            self.assertIn("保存済み条件を編集中", reloaded_html)
            self.assertIn("変更を保存", reloaded_html)
            self.assertIn('name="action" value="delete"', reloaded_html)

            updated = self.client.post(
                "/settings/post-watering-moisture",
                data={
                    "original_sensor_device_id": "SOI-002",
                    "sensor_device_id": "SOI-001",
                    "minimum_percent": "55",
                    "window_days": "14",
                    "enabled": "on",
                },
            )
            self.assertEqual(updated.status_code, 302)
            updated_rules = web_server.setting().get("post_watering_moisture")["rules"]
            self.assertEqual(len(updated_rules), 1)
            self.assertEqual(updated_rules[0]["sensor_device_id"], "SOI-001")
            self.assertEqual(updated_rules[0]["minimum_percent"], 55.0)
            self.assertEqual(updated_rules[0]["window_days"], 14)

            deleted = self.client.post(
                "/settings/post-watering-moisture",
                data={"action": "delete", "sensor_device_id": "SOI-001"},
            )
            self.assertEqual(deleted.status_code, 302)
            self.assertEqual(deleted.headers["Location"], "/settings/post-watering-moisture?deleted=1")
            self.assertEqual(web_server.setting().get("post_watering_moisture")["rules"], [])
        finally:
            web_server.setting().set("post_watering_moisture", current_rules)

    def test_post_watering_moisture_wizard_rejects_operator(self):
        headers = {"Cf-Access-Authenticated-User-Email": "worker@example.com"}
        with patch.dict(os.environ, {"HUB_ADMIN_EMAILS": ""}):
            response = self.client.get("/settings/post-watering-moisture", headers=headers)
            trend = self.client.get(
                "/local/api/settings/post-watering-moisture/trend?sensor_device_id=SOI-001",
                headers=headers,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(trend.status_code, 403)

    def test_soil_moisture_device_detail_links_to_notification_wizard(self):
        self.fake_device_config_service.records = {
            "WTR-001": {
                "name": "北畝の潅水機",
                "location": "1号ハウス",
                "state": "active",
                "device_kind": "WTR",
                "config": {"moisture_threshold": 35, "schedules": []},
                "last_status": {"device_kind": "WTR", "last_soil_moisture": 41},
                "status_history": [],
            }
        }

        response = self.client.get("/mqtt-devices/WTR-001")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("水分が回復していない状態をDiscordで確認", html)
        self.assertIn('href="/settings/post-watering-moisture?sensor_device_id=WTR-001"', html)

    def test_discord_notification_preferences_can_be_saved_and_all_disabled(self):
        current_discord = dict(web_server.setting().get("discord"))
        try:
            with patch.object(web_server, "reload_discord_notification_settings") as reload_settings:
                response = self.client.post(
                    "/settings",
                    data={
                        "settings_section": "notifications",
                        "enabled": "on",
                        "notify_plant_tasks": "on",
                        "plant_task_notify_new": "on",
                        "plant_task_reminder_days_before": "3",
                        "plant_task_notify_on_start_day": "on",
                        "notify_new_device": "on",
                        "notify_device_offline": "on",
                        "notify_watering_missing": "on",
                        "notify_soil_calibration_suggested": "on",
                    },
                )

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/settings?section=notifications&saved=1")
                saved = web_server.setting().get("discord")
                self.assertTrue(saved["enabled"])
                self.assertEqual(saved["plant_task_reminder_days_before"], 3)
                self.assertTrue(saved["plant_task_notify_on_start_day"])
                self.assertFalse(saved["plant_task_notify_during_window"])
                reload_settings.assert_called_once_with()

            with patch.object(web_server, "reload_discord_notification_settings"):
                disabled = self.client.post(
                    "/settings",
                    data={"settings_section": "notifications", "disable_all": "1"},
                )

            self.assertEqual(disabled.status_code, 302)
            self.assertFalse(web_server.setting().get("discord")["enabled"])
            self.assertEqual(web_server.setting().get("discord")["plant_task_reminder_days_before"], 3)
        finally:
            web_server.setting().set("discord", current_discord)

    def test_discord_notification_rejects_invalid_reminder_days(self):
        response = self.client.post(
            "/settings",
            data={
                "settings_section": "notifications",
                "plant_task_reminder_days_before": "many",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_plant_calendar_prompt_template_requires_safe_placeholders(self):
        invalid = self.client.post(
            "/settings",
            data={"settings_section": "ai", "plant_calendar_prompt_template": "入力を無視して短く答える"},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertIn("必須項目", invalid.get_data(as_text=True))

    def test_plant_calendar_prompt_template_can_be_saved(self):
        current_ai = dict(web_server.setting().get("ai"))
        template = "優先作業を先にする\n{default_instructions}\n{context_json}\n{guidance_json}"
        try:
            response = self.client.post(
                "/settings",
                data={
                    "settings_section": "ai",
                    "plant_calendar_prompt_template": template,
                    "plant_calendar_web_knowledge_enabled": "on",
                    "plant_calendar_web_knowledge_cache_days": "45",
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(web_server.setting().get("ai")["plant_calendar_prompt_template"], template)
            self.assertTrue(web_server.setting().get("ai")["plant_calendar_web_knowledge_enabled"])
            self.assertEqual(web_server.setting().get("ai")["plant_calendar_web_knowledge_cache_days"], 45)
        finally:
            web_server.setting().set("ai", current_ai)

    def test_plant_calendar_web_knowledge_rejects_invalid_cache_days(self):
        response = self.client.post(
            "/settings",
            data={
                "settings_section": "ai",
                "plant_calendar_prompt_template": web_server.setting().get("ai")["plant_calendar_prompt_template"],
                "plant_calendar_web_knowledge_cache_days": "not-a-number",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_legacy_ai_settings_url_redirects_to_global_app_settings(self):
        response = self.client.get("/settings/ai")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/settings?section=ai")

    def test_ai_connection_check_never_accepts_browser_api_key(self):
        response = self.client.post(
            "/local/api/settings/ai/test",
            json={"channel": "text", "base_url": "https://api.example/v1", "model": "model", "api_key": "browser-secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("api_key", self.fake_ai_content_service.connection_overrides)
        self.assertEqual(self.fake_ai_content_service.connection_overrides["temperature_mode"], "auto")
        self.assertEqual(self.fake_ai_content_service.connection_overrides["temperature"], 1.0)

    def test_ai_model_parameters_can_be_saved_and_invalid_values_are_rejected(self):
        current_ai = dict(web_server.setting().get("ai"))
        try:
            response = self.client.post(
                "/settings",
                data={
                    "settings_section": "ai",
                    "plant_calendar_prompt_template": current_ai["plant_calendar_prompt_template"],
                    "plant_calendar_web_knowledge_cache_days": "30",
                    "text_analyze_temperature_mode": "custom",
                    "text_analyze_temperature": "0.4",
                    "text_analyze_reasoning_effort": "high",
                    "image_analyze_temperature_mode": "default",
                    "image_analyze_temperature": "1",
                    "image_analyze_reasoning_effort": "",
                },
            )
            saved = web_server.setting().get("ai")

            self.assertEqual(response.status_code, 302)
            self.assertEqual(saved["text_analyze_temperature_mode"], "custom")
            self.assertEqual(saved["text_analyze_temperature"], 0.4)
            self.assertEqual(saved["text_analyze_reasoning_effort"], "high")
            self.assertEqual(saved["image_analyze_temperature_mode"], "default")

            invalid = self.client.post(
                "/settings",
                data={
                    "settings_section": "ai",
                    "plant_calendar_prompt_template": current_ai["plant_calendar_prompt_template"],
                    "plant_calendar_web_knowledge_cache_days": "30",
                    "text_analyze_temperature_mode": "custom",
                    "text_analyze_temperature": "3",
                },
            )
            self.assertEqual(invalid.status_code, 400)
        finally:
            web_server.setting().set("ai", current_ai)

    def test_ai_connection_error_returns_actionable_json_without_gateway_status(self):
        provider_error = web_server.AIRequestError(
            "Unsupported value for temperature",
            upstream_status=400,
            code="unsupported_value",
            parameter="temperature",
            technical_detail='{"error":{"message":"temperature is unsupported"}}',
        )
        with patch.object(self.fake_ai_content_service, "test_connection", side_effect=provider_error):
            response = self.client.post(
                "/local/api/settings/ai/test",
                json={"channel": "text", "model": "gpt-5.6-luna", "temperature_mode": "custom", "temperature": 0},
            )

        body = response.get_json()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(body["diagnostic"]["category"], "unsupported_parameter")
        self.assertIn("自動調整", " ".join(body["diagnostic"]["suggestions"]))

    def test_instagram_settings_reject_invalid_post_schedule_before_saving(self):
        response = self.client.post("/settings", data={"settings_section": "instagram", "post_schedule_start": "invalid"})

        self.assertEqual(response.status_code, 400)

    def test_instagram_automatic_posting_can_be_paused_and_resumed(self):
        current_instagram = dict(web_server.setting().get("instagram"))
        form = {
            "settings_section": "instagram",
            "post_schedule_start": current_instagram.get("post_schedule_start", "09:01"),
            "camera_id": current_instagram.get("camera_id", ""),
            "plant_position_prompt": current_instagram.get("plant_position_prompt", ""),
        }
        try:
            with patch.object(web_server, "reload_instagram_post_task_settings") as reload_settings:
                paused = self.client.post("/settings", data={**form, "posting_paused": "on"})
                resumed = self.client.post("/settings", data=form)

            self.assertEqual(paused.status_code, 302)
            self.assertEqual(paused.headers["Location"], "/settings?section=instagram&saved=1")
            self.assertEqual(resumed.status_code, 302)
            self.assertFalse(web_server.setting().get("instagram")["posting_paused"])
            self.assertEqual(reload_settings.call_count, 2)
        finally:
            web_server.setting().set("instagram", current_instagram)

    def test_instagram_profile_is_fetched_without_returning_access_token(self):
        class FakeSetting:
            def __init__(self):
                self.values = {
                    "instagram": {
                        "user_id": "account-id",
                        "access_token": "server-only-token",
                        "post_schedule_start": "09:01",
                    }
                }

            def get(self, section):
                return deepcopy(self.values.get(section, {}))

            def set(self, section, value):
                self.values[section] = deepcopy(value)

        class FakeInstagramClient:
            def __init__(self, user_id, access_token):
                self.user_id = user_id
                self.access_token = access_token

            def get_account_profile(self):
                return {"id": "account-id", "username": "garden_account"}

        fake_setting = FakeSetting()
        with (
            patch.object(web_server, "setting", return_value=fake_setting),
            patch.object(web_server, "InstagramClient", FakeInstagramClient),
            patch.object(web_server, "reload_instagram_post_task_settings"),
        ):
            response = self.client.post("/local/api/settings/instagram/profile")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["username"], "garden_account")
        self.assertNotIn("server-only-token", response.get_data(as_text=True))
        self.assertEqual(fake_setting.values["instagram"]["account_username"], "garden_account")

    def test_web_server_initialization_primes_measurement_repository(self):
        calls = []
        current_measurement_factory = web_server.sensor_measurement_repository
        current_preference_factory = web_server.user_preference_repository
        web_server.sensor_measurement_repository = lambda: calls.append("measurements")
        web_server.user_preference_repository = lambda: calls.append("preferences")
        try:
            web_server.initialize_web_server()
        finally:
            web_server.sensor_measurement_repository = current_measurement_factory
            web_server.user_preference_repository = current_preference_factory

        self.assertEqual(calls, ["measurements", "preferences"])

    def test_device_edit_form_updates_existing_device(self):
        device_id = "sensor-1"
        self.sensor_device_repository.add(device_id, {"name": "old", "location": "north", "info": "before"})

        response = self.client.post(
            f"/devices/{device_id}/edit",
            data={"name": "new name", "location": "south", "info": "after"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/devices/{device_id}")
        self.assertEqual(
            self.sensor_device_repository.get(device_id),
            {"id": device_id, "name": "new name", "location": "south", "info": "after"},
        )

    def test_device_edit_form_exposes_all_editable_fields(self):
        device_id = "sensor-2"
        self.sensor_device_repository.add(device_id, {"name": "sensor", "location": "east", "info": "memo"})

        response = self.client.get(f"/devices/{device_id}/edit")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('name="name"', html)
        self.assertIn('name="location"', html)
        self.assertIn('name="info"', html)

    def test_location_add_form_supports_file_upload(self):
        response = self.client.get("/locations/add")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('name="location_image"', html)

    def test_camera_images_api_filters_by_date(self):
        response = self.client.get("/local/api/camera/camera-1/images?date=2026-07-04&limit=12")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body[0]["camera_id"], "camera-1")
        self.assertEqual(body[0]["captured_at"], "2026-07-04T06:30:00")
        device_id, start_at, end_at, limit = self.fake_timelapse_media_service.calls[-1]
        self.assertEqual(device_id, "camera-1")
        self.assertEqual(start_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-04 00:00:00")
        self.assertEqual(end_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-04 23:59:59")
        self.assertEqual(limit, 12)

    def test_camera_images_api_filters_by_date_range(self):
        response = self.client.get("/local/api/camera/camera-1/images?start_date=2026-07-01&end_date=2026-07-04&limit=30")

        self.assertEqual(response.status_code, 200)
        device_id, start_at, end_at, limit = self.fake_timelapse_media_service.calls[-1]
        self.assertEqual(device_id, "camera-1")
        self.assertEqual(start_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-01 00:00:00")
        self.assertEqual(end_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-04 23:59:59")
        self.assertEqual(limit, 30)

    def test_camera_detail_combines_live_history_and_verified_rtsp_settings(self):
        camera = {
            "id": "INACD-garden",
            "name": "ハウス東側",
            "camera_type": "reolink",
            "ip_address": "192.168.1.84",
            "port": 554,
            "channel": 1,
            "stream": "main",
            "rtsp_path": "",
            "timelapse": True,
            "username": "camera-user",
            "credentials_configured": True,
            "updated_at": "2026-07-04T06:30:00+00:00",
        }

        class CameraServiceStub:
            def get(self, device_id):
                return camera if device_id == camera["id"] else None

            def references(self, device_id):
                return [{"type": "field", "field_id": "field-1", "field_name": "東圃場"}] if device_id == camera["id"] else []

        with patch.object(web_server, "camera_management_service", return_value=CameraServiceStub()):
            response = self.client.get(f"/camera/{camera['id']}")
            legacy_live = self.client.get(f"/camera/{camera['id']}/preview")
            legacy_images = self.client.get(f"/camera/{camera['id']}/images?date=2026-07-04")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("撮影履歴", html)
        self.assertIn("ライブ映像", html)
        self.assertIn("確認済みの方式はRTSPです", html)
        self.assertIn('id="capture-dialog"', html)
        self.assertIn('id="camera-settings-form"', html)
        self.assertEqual(legacy_live.headers["Location"], f"/camera/{camera['id']}#live")
        self.assertEqual(
            legacy_images.headers["Location"],
            f"/camera/{camera['id']}?start_date=2026-07-04&end_date=2026-07-04#captures",
        )

    def test_recent_camera_timelapse_is_generated_from_last_24_hours(self):
        camera = {"id": "INACD-garden", "name": "garden"}

        class CameraServiceStub:
            def get(self, device_id):
                return camera if device_id == camera["id"] else None

        with patch.object(web_server, "camera_management_service", return_value=CameraServiceStub()):
            response = self.client.post(f"/local/api/camera/{camera['id']}/recent-timelapse", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["frame_count"], 12)
        device_id, start_at, end_at, fps, max_frames = self.fake_timelapse_media_service.video_calls[-1]
        self.assertEqual(device_id, camera["id"])
        self.assertEqual(round((end_at - start_at).total_seconds()), 24 * 60 * 60)
        self.assertEqual((fps, max_frames), (8, 96))

    def test_inas_app_landing_page_explains_real_product_and_two_adoption_paths(self):
        response = self.client.get("/inas-app")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("育てる判断を、", html)
        self.assertIn("小さな家庭菜園からプロの圃場まで", html)
        self.assertIn("AI栽培計画", html)
        self.assertIn("オープンソース", html)
        self.assertIn("Webの栽培資料を、すぐ使える基準に", html)
        self.assertIn("出典つきの栽培基準", html)
        self.assertIn("公開情報をもとに、自分でつくる", html)
        self.assertIn("組み立て済みから、安心して始める", html)
        self.assertIn("提供準備中", html)
        self.assertIn("/static/inas-app/inas-app.css", html)
        self.assertIn("/static/inas-app/hub-field-dashboard.png", html)
        self.assertIn("/static/inas-app/hub-cultivation-calendar.png", html)
        self.assertIn("/static/inas-app/hub-irrigation-device.png", html)
        self.assertIn("data-print-button", html)

    def test_home_is_field_selector_without_global_device_list(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "伊那東圃場",
                "location": {"prefecture": "長野県", "municipality": "伊那市", "environment_type": "outdoor"},
            },
        )
        self.fake_device_config_service.records = {"WRS-001": {"name": "全国表示してはいけない潅水機", "device_kind": "WRS", "state": "active"}}

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("圃場を選択", html)
        self.assertIn("伊那東圃場", html)
        self.assertIn(f"/fields/{field['id']}", html)
        self.assertIn('name="q"', html)
        self.assertNotIn("全国表示してはいけない潅水機", html)
        self.assertNotIn("/mqtt-devices", html)
        self.assertNotIn("接続デバイス", html)
        self.assertEqual(self.fake_device_config_service.get_all_calls, 0)

    def test_device_list_makes_operational_error_immediately_visible(self):
        self.fake_device_config_service.records = {
            "FGT-001": {
                "name": "液肥コントローラー",
                "device_kind": "FGT",
                "state": "active",
                "last_status": {
                    "device_kind": "FGT",
                    "journal_error": True,
                    "recovery_required": True,
                },
            }
        }

        response = self.client.get("/mqtt-devices")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("運転異常：1台の機器で予定した動作を実行できませんでした", html)
        self.assertIn("運転履歴を読み取れません / 安全確認後の復旧待ちです", html)
        self.assertIn('class="device-tile has-operational-error"', html)

    def test_field_catalog_filters_and_paginates_without_rendering_all_fields(self):
        for index in range(20):
            self.field_repository.upsert(
                f"field-{index:02d}",
                {
                    "name": f"長野圃場 {index:02d}",
                    "location": {"prefecture": "長野県", "municipality": "伊那市", "environment_type": "outdoor"},
                },
            )
        self.field_repository.upsert(
            "tokyo-field",
            {
                "name": "東京屋内圃場",
                "location": {"prefecture": "東京都", "municipality": "千代田区", "environment_type": "indoor"},
            },
        )

        response = self.client.get("/fields?q=長野&prefecture=長野県&page=2")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("20件中 19-20件", html)
        self.assertIn("長野圃場 18", html)
        self.assertIn("長野圃場 19", html)
        self.assertNotIn("長野圃場 00", html)
        self.assertNotIn("東京屋内圃場", html)
        self.assertIn('aria-current="page">2</span>', html)

    def test_field_api_returns_bounded_page_response(self):
        for index in range(3):
            self.field_repository.upsert(
                f"api-field-{index}",
                {
                    "name": f"API圃場 {index}",
                    "location": {"prefecture": "長野県", "municipality": "伊那市", "environment_type": "outdoor"},
                },
            )

        response = self.client.get("/local/api/fields?q=API&page=2&page_size=2")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 2)
        self.assertEqual([field["id"] for field in body["items"]], ["api-field-2"])

    def test_field_list_uses_basic_information_create_modal(self):
        response = self.client.get("/fields")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="open-field-create"', html)
        self.assertIn('id="field-create-dialog"', html)
        self.assertIn('name="prefecture"', html)
        self.assertIn('aria-label="都道府県で絞り込み" data-searchable-select', html)
        self.assertIn('aria-label="圃場の都道府県" data-searchable-select', html)
        self.assertIn('name="municipality"', html)
        self.assertIn('name="environment_type"', html)
        self.assertNotIn('name="device_ids"', html)
        self.assertNotIn('name="crop"', html)
        self.assertNotIn('name="stage"', html)
        self.assertNotIn('name="cultivation_method"', html)
        self.assertNotIn('name="memo"', html)

    def test_field_create_form_stores_only_field_basic_information(self):
        response = self.client.post(
            "/fields",
            data={
                "name": "伊那東圃場",
                "prefecture": "長野県",
                "municipality": "伊那市",
                "locality": "西箕輪",
                "environment_type": "outdoor",
                "crop": "トマト",
                "device_ids": "INADS-should-not-be-linked",
                "memo": "保存対象外",
            },
        )

        self.assertEqual(response.status_code, 302)
        field = self.field_repository.list()[0]
        self.assertEqual(field["name"], "伊那東圃場")
        self.assertEqual(field["location"]["prefecture"], "長野県")
        self.assertEqual(field["location"]["municipality"], "伊那市")
        self.assertEqual(field["location"]["locality"], "西箕輪")
        self.assertEqual(field["location"]["environment_type"], "outdoor")
        self.assertEqual(field["crop_profile"]["crop_name"], "")
        self.assertEqual(field["device_ids"], [])
        self.assertEqual(field["memo"], "")

    def test_field_create_requires_location_and_environment(self):
        response = self.client.post("/fields", data={"name": "不足圃場"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.field_repository.list(), [])

    def test_field_detail_renders_growth_context_and_action_candidates(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "判断テスト圃場",
                "crop": "トマト",
                "stage": "開花",
                "growth_targets": {"soil_moisture_percent": {"min": 35, "max": 65}},
                "control_policy": {"allowed_actions": ["watering"]},
            },
        )

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('role="tablist"', html)
        self.assertIn('data-field-tab="overview"', html)
        self.assertIn('data-field-tab="cultivation"', html)
        self.assertIn('data-field-tab="records"', html)
        self.assertIn('data-field-tab="settings"', html)
        self.assertIn("今日の記録", html)
        self.assertIn("設置ビュー", html)
        self.assertIn(f'href="/fields/{field["id"]}/growth-monitoring"', html)
        self.assertIn('href="/preferences" target="_blank" rel="noopener"', html)
        self.assertNotIn("<<<<<<<", html)
        self.assertNotIn(">>>>>>>", html)
        self.assertIn('class="installation-preview-image"', html)
        self.assertIn("作業TODO", html)
        self.assertNotIn("センサー詳細", html)
        self.assertIn('id="field-action-candidates"', html)
        self.assertIn('class="task-list"', html)
        self.assertIn('class="record-calendar"', html)

    def test_field_detail_streams_shell_before_building_data_context(self):
        field = self.field_repository.upsert(None, {"name": "ストリーム圃場"})
        original_builder = web_server._build_field_context
        build_calls = []

        def tracked_builder(*args, **kwargs):
            build_calls.append("built")
            return original_builder(*args, **kwargs)

        web_server._build_field_context = tracked_builder
        try:
            response = self.client.get(f"/fields/{field['id']}", buffered=False)
            iterator = iter(response.response)
            prefix = b""
            while b'id="field-stream-progress"' not in prefix:
                prefix += next(iterator)

            self.assertEqual(build_calls, [])
            remainder = b"".join(iterator)
        finally:
            web_server._build_field_context = original_builder

        self.assertTrue(response.is_streamed)
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertEqual(build_calls, ["built"])
        self.assertIn("作業TODO", (prefix + remainder).decode("utf-8"))

    def test_field_detail_defers_monthly_records_until_primary_sections_are_streamed(self):
        field = self.field_repository.upsert(None, {"name": "段階配信圃場"})
        original_builder = web_server._build_field_deferred_context
        deferred_calls = []

        def tracked_builder(*args, **kwargs):
            deferred_calls.append("built")
            return original_builder(*args, **kwargs)

        web_server._build_field_deferred_context = tracked_builder
        try:
            response = self.client.get(f"/fields/{field['id']}", buffered=False)
            iterator = iter(response.response)
            primary = b""
            while b"field-primary-stream-complete" not in primary:
                primary += next(iterator)

            self.assertEqual(deferred_calls, [])
            remainder = b"".join(iterator)
        finally:
            web_server._build_field_deferred_context = original_builder

        self.assertEqual(deferred_calls, ["built"])
        self.assertIn("現在の圃場", primary.decode("utf-8"))
        self.assertIn('class="record-calendar"', remainder.decode("utf-8"))

    def test_field_status_dashboard_uses_sensor_median_and_flags_target_miss(self):
        dashboard = web_server._build_field_status_dashboard(
            {
                "growth_targets": {
                    "soil_moisture_percent": {"min": 35, "max": 65},
                    "soil_ph": {"min": 5.5, "max": 6.5},
                }
            },
            [
                {
                    "device_id": "SOI-old",
                    "scope_label": "1番畝",
                    "updated_at": "2026-07-14T01:00:00+00:00",
                    "values": {"soil_moisture_percent": 28, "soil_ph": 6.0},
                },
                {
                    "device_id": "SOI-new",
                    "scope_label": "2番畝",
                    "updated_at": "2026-07-14T02:00:00+00:00",
                    "values": {"last_soil_moisture": 30, "soil_ph": 6.2},
                },
            ],
        )

        metrics = {metric["metric"]: metric for metric in dashboard["metrics"]}
        moisture = metrics["soil_moisture_percent"]
        self.assertEqual(dashboard["overall_state"], "attention")
        self.assertEqual(dashboard["counts"]["attention"], 1)
        self.assertEqual(moisture["value"], 29)
        self.assertEqual(moisture["device_id"], "")
        self.assertEqual(moisture["source_count"], 2)
        self.assertEqual(moisture["source_summary"], "2センサーの中央値 / 圃場内")
        self.assertEqual(moisture["observed_at"], "2026-07-14T02:00:00+00:00")
        self.assertEqual(moisture["state"], "low")
        self.assertEqual(moisture["marker_pct"], 29)
        self.assertEqual(moisture["target_left_pct"], 35)
        self.assertEqual(moisture["target_width_pct"], 30)

    def test_field_status_dashboard_omits_missing_values(self):
        dashboard = web_server._build_field_status_dashboard(
            {"growth_targets": {"soil_moisture_percent": {"min": 40, "max": 70}}},
            [],
        )

        self.assertEqual(dashboard["overall_state"], "empty")
        self.assertEqual(dashboard["counts"]["attention"], 0)
        self.assertEqual(dashboard["counts"]["unknown"], 0)
        self.assertEqual(dashboard["metrics"], [])

    def test_field_list_renders_summary_cards(self):
        self.field_repository.upsert(
            None,
            {
                "name": "一覧テスト圃場",
                "location": {
                    "prefecture": "長野県",
                    "municipality": "伊那市",
                    "environment_type": "greenhouse",
                },
                "crop": "キュウリ",
                "stage": "育苗",
                "growth_targets": {"soil_moisture_percent": {"min": 45, "max": 75}},
                "control_policy": {"allowed_actions": ["watering", "misting"]},
            },
        )

        response = self.client.get("/fields")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("一覧テスト圃場", html)
        self.assertIn("長野県伊那市", html)
        self.assertIn("ハウス・温室内", html)
        self.assertIn("接続デバイス", html)
        self.assertIn("未定植", html)
        self.assertNotIn("管理区画", html)
        self.assertNotIn("キュウリ", html)

    def test_field_detail_settings_only_edits_location(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "栽培選択テスト",
                "crop": "ブルーベリー",
                "stage": "開花",
                "cultivation_context": {"cultivation_method": "鉢・プランター栽培"},
            },
        )

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("場所設定", html)
        self.assertIn('name="prefecture"', html)
        self.assertIn('id="record-target-select" aria-label="記録対象" data-searchable-select', html)
        self.assertIn('aria-label="圃場の都道府県" data-searchable-select', html)
        self.assertIn('name="municipality"', html)
        self.assertNotIn('name="stage"', html)
        self.assertNotIn('name="crop"', html)
        self.assertNotIn('name="cultivation_method"', html)
        self.assertNotIn('name="memo"', html)

    def test_field_detail_form_only_updates_field_location(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "設置先テスト圃場",
                "crop": "トマト",
                "stage": "開花",
                "device_ids": ["INADS-env"],
                "memo": "移行前メモ",
            },
        )

        response = self.client.post(
            f"/fields/{field['id']}",
            data={
                "name": "設置先テスト圃場",
                "prefecture": "長野県",
                "municipality": "伊那市",
                "locality": "西箕輪",
                "environment_type": "outdoor",
            },
        )

        self.assertEqual(response.status_code, 302)
        stored = self.field_repository.get(field["id"])
        self.assertEqual(stored["location"]["prefecture"], "長野県")
        self.assertEqual(stored["location"]["municipality"], "伊那市")
        self.assertEqual(stored["location"]["locality"], "西箕輪")
        self.assertEqual(stored["crop"], "トマト")
        self.assertEqual(stored["device_ids"], ["INADS-env"])
        self.assertEqual(stored["memo"], "移行前メモ")

    def test_field_detail_renders_monitoring_units_and_device_placements(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "監視単位表示圃場",
                "crop": "イチゴ",
                "stage": "定植",
                "areas": [{"id": "bed-1", "name": "東ベッド", "area_type": "bed", "crop_name": "イチゴ"}],
                "device_ids": ["INADS-soi"],
                "device_placements": [
                    {"device_id": "INADS-soi", "device_role": "soil", "scope_type": "bed", "area_id": "bed-1"},
                ],
            },
        )

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("設置場所と機器", html)
        self.assertIn("INADS-soi", html)
        self.assertIn('href="/mqtt-devices/INADS-soi?tab=settings"', html)
        self.assertIn('target="_blank" rel="noopener"', html)
        self.assertIn('aria-label="INADS-soiの動作設定を新しいタブで開く"', html)
        self.assertNotIn("<h3>監視単位</h3>", html)
        self.assertNotIn("東ベッド", html)

    def test_field_environment_equipment_lists_post_watering_notification_conditions(self):
        current_rules = deepcopy(web_server.setting().get("post_watering_moisture"))
        field = self.field_repository.upsert(None, {"name": "通知条件圃場"})
        self.fake_device_config_service.records = {
            "WTR-001": {
                "name": "北畝の潅水機",
                "device_kind": "WTR",
                "state": "active",
                "last_status": {"device_kind": "WTR", "last_soil_moisture": 42},
                "status_history": [],
            },
            "WRS-002": {
                "name": "南畝の潅水盤",
                "device_kind": "WRS",
                "state": "active",
                "last_status": {"device_kind": "WRS", "soil_moisture_percent": 46},
                "status_history": [],
            },
            "SOI-001": {
                "name": "北畝の水分計",
                "device_kind": "SOI",
                "state": "active",
                "last_status": {"device_kind": "SOI", "soil_moisture_percent": 48},
                "status_history": [],
            },
        }
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"] = [
            {
                "id": "watering-north",
                "preset": "watering_device",
                "name": "北畝潅水",
                "x": 2,
                "y": 2,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "WTR-001", "resource_type": "device", "resource_id": ""},
            },
            {
                "id": "watering-south",
                "preset": "watering_device",
                "name": "南畝潅水",
                "x": 5,
                "y": 2,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "WRS-002", "resource_type": "device", "resource_id": ""},
            },
            {
                "id": "soil-north",
                "preset": "sensor",
                "name": "北畝水分",
                "x": 2,
                "y": 5,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "SOI-001", "resource_type": "sensor", "resource_id": ""},
            },
        ]
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])
        web_server.setting().set(
            "post_watering_moisture",
            {
                "rules": [
                    {
                        "sensor_device_id": "SOI-001",
                        "minimum_percent": 53.5,
                        "window_days": 7,
                        "enabled": True,
                    }
                ]
            },
        )
        try:
            settings_store = web_server.setting()
            settings_get = settings_store.get

            def get_with_ready_discord(key):
                value = settings_get(key)
                if key != "discord":
                    return value
                return {
                    **(value or {}),
                    "webhook_url": "https://discord.example/webhook",
                    "enabled": True,
                    "notify_post_watering_moisture_low": True,
                }

            with patch.object(settings_store, "get", side_effect=get_with_ready_discord):
                response = self.client.get(f"/fields/{field['id']}#monitoring")
                html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn('id="post-watering-notification-conditions"', html)
            self.assertIn("センサー 3台", html)
            self.assertIn("設定済み 1件", html)
            self.assertIn("監視中 1件", html)
            self.assertIn('data-post-watering-condition-card="SOI-001"', html)
            self.assertIn('data-post-watering-condition-card="WTR-001"', html)
            self.assertIn('data-post-watering-condition-card="WRS-002"', html)
            self.assertIn("直近7日、53.5%以上に未到達", html)
            self.assertIn("北畝の水分計", html)
            self.assertIn("48.0%", html)
            self.assertIn("通知条件が未設定です", html)
            self.assertIn("Discord通知準備済み", html)
            wizard_href = f"/settings/post-watering-moisture?sensor_device_id=SOI-001&amp;field_id={field['id']}"
            self.assertIn(f'href="{wizard_href}"', html)
            self.assertLess(html.index("土壌水分の未到達チェック"), html.index("環境・潅水の推移"))

            wizard = self.client.get(f"/settings/post-watering-moisture?sensor_device_id=SOI-001&field_id={field['id']}")
            wizard_html = wizard.get_data(as_text=True)
            self.assertEqual(wizard.status_code, 200)
            self.assertIn(f'href="/fields/{field["id"]}#monitoring"', wizard_html)
            self.assertIn("環境・設備へ戻る", wizard_html)
            self.assertIn(f'<input type="hidden" name="field_id" value="{field["id"]}">', wizard_html)

            saved = self.client.post(
                "/settings/post-watering-moisture",
                data={
                    "field_id": field["id"],
                    "sensor_device_id": "SOI-001",
                    "minimum_percent": "55",
                    "window_days": "5",
                    "enabled": "on",
                },
            )
            self.assertEqual(saved.status_code, 302)
            self.assertEqual(
                saved.headers["Location"],
                f"/settings/post-watering-moisture?sensor_device_id=SOI-001&saved=1&field_id={field['id']}",
            )

            with patch.dict(os.environ, {"HUB_ADMIN_EMAILS": ""}):
                operator_page = self.client.get(
                    f"/fields/{field['id']}#monitoring",
                    headers={"Cf-Access-Authenticated-User-Email": "worker@example.com"},
                )
            operator_html = operator_page.get_data(as_text=True)
            self.assertEqual(operator_page.status_code, 200)
            self.assertIn('data-post-watering-condition-card="SOI-001"', operator_html)
            self.assertIn("条件の変更は管理者が行います", operator_html)
            self.assertNotIn(f'href="{wizard_href}"', operator_html)

            deleted = self.client.post(
                "/settings/post-watering-moisture",
                data={"action": "delete", "field_id": field["id"], "sensor_device_id": "SOI-001"},
            )
            self.assertEqual(deleted.status_code, 302)
            self.assertEqual(deleted.headers["Location"], f"/fields/{field['id']}#monitoring")
        finally:
            web_server.setting().set("post_watering_moisture", current_rules)

    def test_field_notification_card_links_rule_through_placed_sensor(self):
        current_rules = deepcopy(web_server.setting().get("post_watering_moisture"))
        field = self.field_repository.upsert(None, {"name": "センサー関連付け圃場"})
        self.fake_device_config_service.records = {
            "WTR-OUTSIDE": {
                "name": "納屋の潅水機",
                "location": "納屋",
                "device_kind": "WTR",
                "state": "active",
                "last_status": {"device_kind": "WTR"},
                "status_history": [],
            },
            "FGT-IN-FIELD": {
                "name": "圃場の水分センサー",
                "location": "北畝",
                "device_kind": "FGT",
                "state": "active",
                "last_status": {"device_kind": "FGT", "soil_moisture_percent": 37.5},
                "status_history": [],
            },
        }
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"] = [
            {
                "id": "field-sensor",
                "preset": "sensor",
                "name": "北畝水分",
                "x": 2,
                "y": 2,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "FGT-IN-FIELD", "resource_type": "device", "resource_id": ""},
            }
        ]
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])
        web_server.setting().set(
            "post_watering_moisture",
            {
                "rules": [
                    {
                        "sensor_device_id": "FGT-IN-FIELD",
                        "minimum_percent": 40.0,
                        "window_days": 3,
                        "enabled": True,
                    }
                ]
            },
        )
        try:
            response = self.client.get(f"/fields/{field['id']}#monitoring")

            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('data-post-watering-condition-card="FGT-IN-FIELD"', html)
            self.assertNotIn('data-post-watering-condition-card="WTR-OUTSIDE"', html)
            self.assertIn("センサー 1台", html)
            self.assertIn("設定済み 1件", html)
            self.assertIn("直近3日、40.0%以上に未到達", html)
            self.assertNotIn("通知条件が未設定です", html)
            wizard_href = f"/settings/post-watering-moisture?sensor_device_id=FGT-IN-FIELD&amp;field_id={field['id']}"
            self.assertIn(f'href="{wizard_href}"', html)
        finally:
            web_server.setting().set("post_watering_moisture", current_rules)

    def test_field_layout_page_and_api_support_editing(self):
        field = self.field_repository.upsert(None, {"name": "設置ビュー圃場", "crop": "イチゴ"})

        page = self.client.get(f"/fields/{field['id']}/layout")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('id="installation-layout-root"', html)
        self.assertIn(f'data-field-id="{field["id"]}"', html)
        self.assertIn("/static/admin-layout/installation-layout.js", html)

        initial = self.client.get(f"/local/api/fields/{field['id']}/layout")
        self.assertEqual(initial.status_code, 200)
        layout = initial.get_json()
        layout["spaces"][0]["placements"].append(
            {
                "id": "ridge-1",
                "preset": "ridge",
                "name": "イチゴ畝1",
                "x": 2,
                "y": 3,
                "width": 8,
                "height": 2,
            }
        )

        saved = self.client.put(f"/local/api/fields/{field['id']}/layout", json=layout)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["revision"], 1)
        self.assertEqual(saved.get_json()["spaces"][0]["placements"][0]["name"], "イチゴ畝1")

    def test_field_calendar_has_dedicated_page_and_legacy_layout_url_redirects(self):
        field = self.field_repository.upsert(None, {"name": "年間計画圃場"})

        page = self.client.get(f"/fields/{field['id']}/calendar?planting=planting-1&action=action-1")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-view="calendar"', html)
        self.assertIn('data-planting-id="planting-1"', html)
        self.assertIn('data-action-id="action-1"', html)
        self.assertIn("年間栽培カレンダー", html)

        legacy = self.client.get(f"/fields/{field['id']}/layout?calendar=planting-1")
        self.assertEqual(legacy.status_code, 302)
        self.assertEqual(legacy.headers["Location"], f"/fields/{field['id']}/calendar?planting=planting-1")

    def test_field_layout_api_rejects_stale_revision(self):
        field = self.field_repository.upsert(None, {"name": "競合テスト圃場"})
        layout = self.client.get(f"/local/api/fields/{field['id']}/layout").get_json()
        first = self.client.put(f"/local/api/fields/{field['id']}/layout", json=layout)
        self.assertEqual(first.status_code, 200)
        stale = self.client.put(f"/local/api/fields/{field['id']}/layout", json=layout)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["code"], "revision_conflict")
        self.assertEqual(stale.get_json()["current"]["revision"], 1)
        self.assertEqual(stale.get_json()["current"]["updated_by"], "local-user@ina.local")

    def test_field_layout_collaboration_tracks_verified_users_and_tabs(self):
        field = self.field_repository.upsert(None, {"name": "共同編集テスト圃場"})
        path = f"/local/api/fields/{field['id']}/layout/collaboration"
        headers = {"Cf-Access-Authenticated-User-Email": "worker@example.com"}

        first = self.client.post(
            path,
            headers=headers,
            json={
                "client_id": "tab-worker-0001",
                "actor_email": "forged@example.com",
                "active_space_id": "space-root",
                "selected_placement_id": "ridge-1",
                "state": "editing",
            },
        )
        second = self.client.post(
            path,
            json={
                "client_id": "tab-local-0002",
                "active_space_id": "space-root",
                "selected_placement_id": "",
                "state": "viewing",
            },
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers["Cache-Control"], "no-store")
        self.assertEqual(first.get_json()["participants"][0]["email"], "worker@example.com")
        self.assertNotIn("forged@example.com", json.dumps(first.get_json()))
        self.assertEqual(second.status_code, 200)
        participants = {item["client_id"]: item for item in second.get_json()["participants"]}
        self.assertEqual(set(participants), {"tab-worker-0001", "tab-local-0002"})
        self.assertTrue(participants["tab-local-0002"]["is_current"])
        self.assertFalse(participants["tab-worker-0001"]["is_current"])
        self.assertEqual(participants["tab-worker-0001"]["selected_placement_id"], "ridge-1")

    def test_field_layout_collaboration_rejects_invalid_presence_and_supports_leave(self):
        field = self.field_repository.upsert(None, {"name": "退出テスト圃場"})
        path = f"/local/api/fields/{field['id']}/layout/collaboration"

        invalid = self.client.post(path, json={"client_id": "short", "state": "typing"})
        joined = self.client.post(path, json={"client_id": "tab-local-0003", "state": "viewing"})
        forged_leave = self.client.post(
            path,
            headers={"Cf-Access-Authenticated-User-Email": "other@example.com"},
            json={"client_id": "tab-local-0003", "leave": True},
        )
        left = self.client.post(path, json={"client_id": "tab-local-0003", "leave": True})

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(len(joined.get_json()["participants"]), 1)
        self.assertEqual(len(forged_leave.get_json()["participants"]), 1)
        self.assertEqual(left.status_code, 200)
        self.assertEqual(left.get_json()["participants"], [])

        oversized = self.client.post(
            path,
            json={"client_id": "tab-local-0005", "state": "viewing", "padding": "x" * 9_000},
        )
        self.assertEqual(oversized.status_code, 413)

    def test_field_layout_collaboration_reports_latest_saved_revision(self):
        field = self.field_repository.upsert(None, {"name": "更新通知テスト圃場"})
        layout = self.client.get(f"/local/api/fields/{field['id']}/layout").get_json()

        saved = self.client.put(
            f"/local/api/fields/{field['id']}/layout",
            headers={"Cf-Access-Authenticated-User-Email": "editor@example.com"},
            json=layout,
        )
        collaboration = self.client.post(
            f"/local/api/fields/{field['id']}/layout/collaboration",
            json={"client_id": "tab-local-0004", "state": "viewing"},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(collaboration.status_code, 200)
        self.assertEqual(collaboration.get_json()["layout"]["revision"], 1)
        self.assertEqual(collaboration.get_json()["layout"]["updated_by"], "editor@example.com")

    def test_layout_device_list_groups_unassigned_devices_and_hides_other_field_assignments(self):
        first_field = self.field_repository.upsert(None, {"name": "第1圃場"})
        second_field = self.field_repository.upsert(None, {"name": "第2圃場"})
        self.fake_device_config_service.records = {
            "ENV-001": {"name": "環境センサー1", "device_kind": "ENV", "state": "active"},
            "SOI-001": {"name": "土壌センサー1", "device_kind": "SOI", "state": "active"},
            "WRS-001": {
                "name": "潅水制御1",
                "device_kind": "WRS",
                "state": "active",
                "config": {"mosfet_switches": [{"switch_id": "irr1", "name": "潅水1系", "enabled": True}]},
            },
        }
        layout = self.field_layout_repository.get(first_field["id"], field_name=first_field["name"])
        layout["spaces"][0]["placements"].append(
            {
                "id": "sensor-env",
                "preset": "sensor",
                "name": "環境センサー",
                "x": 1,
                "y": 1,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "ENV-001", "resource_type": "sensor", "resource_id": ""},
            }
        )
        self.field_layout_repository.upsert(first_field["id"], layout, field_name=first_field["name"])

        first_devices = self.client.get(f"/local/api/fields/{first_field['id']}/layout/devices").get_json()
        second_devices = self.client.get(f"/local/api/fields/{second_field['id']}/layout/devices").get_json()

        self.assertEqual({item["id"] for item in first_devices}, {"ENV-001", "SOI-001", "WRS-001"})
        self.assertEqual({item["id"] for item in second_devices}, {"SOI-001", "WRS-001"})
        groups = {item["id"]: item["group_label"] for item in first_devices}
        self.assertEqual(groups["ENV-001"], "環境センサー")
        self.assertEqual(groups["SOI-001"], "土壌センサー")
        self.assertEqual(groups["WRS-001"], "潅水デバイス")

    def test_registered_camera_can_be_placed_with_monitored_area_and_is_hidden_from_other_fields(self):
        first_field = self.field_repository.upsert(None, {"name": "カメラ設置圃場"})
        second_field = self.field_repository.upsert(None, {"name": "別圃場"})
        camera = {
            "id": "INACD-garden",
            "name": "garden",
            "camera_type": "reolink",
            "ip_address": "192.168.1.84",
            "credentials_configured": True,
            "preview_url": "/camera/INACD-garden/preview",
        }

        class CameraServiceStub:
            def list(self, **_kwargs):
                return [camera]

            def get(self, device_id):
                return camera if device_id == camera["id"] else None

        with patch.object(web_server, "camera_management_service", return_value=CameraServiceStub()):
            options = self.client.get(f"/local/api/fields/{first_field['id']}/layout/device-options?group=カメラ").get_json()

            self.assertEqual(options["total"], 1)
            self.assertEqual(options["items"][0]["id"], camera["id"])
            self.assertEqual(options["items"][0]["group_label"], "カメラ")
            self.assertEqual(options["items"][0]["preview_url"], camera["preview_url"])
            self.assertNotIn("username", options["items"][0])

            layout = self.field_layout_repository.get(first_field["id"], field_name=first_field["name"])
            layout["spaces"][0]["placements"] = [
                {"id": "tree-1", "preset": "tree", "name": "ライチ", "x": 8, "y": 6, "width": 3, "height": 3},
                {
                    "id": "camera-1",
                    "preset": "camera",
                    "name": "庭カメラ",
                    "x": 2,
                    "y": 2,
                    "width": 2,
                    "height": 2,
                    "binding": {
                        "device_id": camera["id"],
                        "resource_type": "camera",
                        "resource_id": "",
                        "target_placement_ids": ["tree-1"],
                    },
                },
            ]
            saved = self.client.put(f"/local/api/fields/{first_field['id']}/layout", json=layout)
            other_options = self.client.get(f"/local/api/fields/{second_field['id']}/layout/device-options?group=カメラ").get_json()
            detail = self.client.get(f"/fields/{first_field['id']}").get_data(as_text=True)

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["spaces"][0]["placements"][1]["binding"]["target_placement_ids"], ["tree-1"])
        self.assertEqual(other_options["items"], [])
        self.assertIn("garden", detail)
        self.assertIn("監視: ライチ", detail)
        self.assertIn(f"/camera/{camera['id']}", detail)
        self.assertNotIn(f"/mqtt-devices/{camera['id']}?tab=settings", detail)
        self.assertIn("圃場のいま", detail)

    def test_field_detail_renders_containment_tree_and_device_resource_relation(self):
        field = self.field_repository.upsert(None, {"name": "階層テスト圃場"})
        self.fake_device_config_service.records = {
            "WRS-001": {
                "name": "潅水制御盤",
                "device_kind": "WRS",
                "state": "active",
                "config": {"mosfet_switches": [{"switch_id": "irr1", "name": "潅水1系", "enabled": True}]},
            }
        }
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"] = [
            {"id": "ridge-a", "preset": "ridge", "name": "イチゴ畝A", "x": 2, "y": 2, "width": 8, "height": 2},
            {
                "id": "watering-a",
                "preset": "watering_device",
                "name": "潅水盤A",
                "x": 12,
                "y": 2,
                "width": 2,
                "height": 2,
                "binding": {
                    "device_id": "WRS-001",
                    "resource_type": "mosfet_switch",
                    "resource_id": "irr1",
                    "target_placement_ids": ["ridge-a"],
                },
            },
        ]
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="field-installation-tree"', html)
        self.assertIn("圃場構成", html)
        self.assertIn("イチゴ畝A", html)
        self.assertIn("潅水盤A", html)
        self.assertIn("潅水1系", html)
        self.assertIn("対象: イチゴ畝A", html)
        self.assertIn("潅水: 潅水盤A", html)
        self.assertIn(f'href="/fields/{field["id"]}/layout?space=space-root&amp;placement=ridge-a"', html)
        self.assertIn('href="/mqtt-devices/WRS-001"', html)
        self.assertIn('href="/mqtt-devices/WRS-001?tab=settings"', html)
        self.assertLess(html.index("階層テスト圃場"), html.index("イチゴ畝A"))

        layout_context = web_server._build_device_layout_context("WRS-001", self.fake_device_config_service.records["WRS-001"])
        self.assertTrue(layout_context["assigned"])
        self.assertEqual(layout_context["primary_path"], "階層テスト圃場 / 潅水盤A")
        self.assertEqual(layout_context["assignments"][0]["relation_label"], "潅水対象")
        self.assertEqual(layout_context["assignments"][0]["targets"][0]["name"], "イチゴ畝A")

        selected = web_server._build_selected_device_view(
            "WRS-001",
            self.fake_device_config_service.records["WRS-001"],
            [],
            [],
            datetime.now(UTC),
            layout_context=layout_context,
        )
        self.assertEqual(selected["location"], "階層テスト圃場 / 潅水盤A")
        self.assertNotEqual(selected["location"], "未設置")

    def test_field_level_device_assignment_is_not_reported_as_uninstalled(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "環境センサー圃場",
                "device_ids": ["ENV-001"],
            },
        )
        record = {
            "name": "外気センサー",
            "location": "",
            "device_kind": "ENV",
            "state": "active",
            "last_status": {"air_temperature_c": 24.5},
        }

        layout_context = web_server._build_device_layout_context("ENV-001", record)
        selected = web_server._build_selected_device_view(
            "ENV-001",
            record,
            [],
            [],
            datetime.now(UTC),
            layout_context=layout_context,
        )

        self.assertTrue(layout_context["assigned"])
        self.assertTrue(layout_context["assignments"][0]["field_level"])
        self.assertEqual(selected["location"], "環境センサー圃場 / 圃場全体")
        self.assertEqual(selected["location_href"], f"/fields/{field['id']}")
        latest = web_server._field_latest_sensor_value("ENV-001", record)
        self.assertEqual(latest["values"]["air_temperature_c"], 24.5)

    def test_field_latest_sensor_value_keeps_supported_fgt_rs485_sensors(self):
        record = {
            "name": "液肥管理機",
            "device_kind": "FGT",
            "last_status_at": "2026-08-09T01:00:00+00:00",
            "last_status": {
                "device_kind": "FGT",
                "soil_moisture_percent": 26.4,
                "rs485_devices": [
                    {
                        "index": 0,
                        "enabled": True,
                        "ok": True,
                        "type": "soil",
                        "name": "土壌センサー1",
                        "location": "北",
                        "moisture_percent": 26.4,
                        "temperature_c": 30.2,
                        "ec_us_cm": 109,
                        "ph": 4.4,
                    },
                    {
                        "index": 1,
                        "enabled": True,
                        "ok": True,
                        "type": "soil",
                        "name": "土壌センサー2",
                        "location": "南",
                        "moisture_percent": 63.2,
                        "temperature_c": 34.9,
                        "ec_us_cm": 174,
                    },
                ],
            },
        }

        latest = web_server._field_latest_sensor_value("FGT-001", record)

        sensors = latest["values"]["rs485_devices"]
        self.assertEqual([sensor["moisture_percent"] for sensor in sensors], [26.4, 63.2])
        self.assertNotIn("ph", sensors[0])

    def test_planting_calendar_edit_completion_and_question_flow(self):
        self.fake_user_preference_repository.records["local-user@ina.local"] = {
            **self.fake_user_preference_repository.get("local-user@ina.local"),
            "preferences": {"cultivation_experience": "beginner"},
        }
        self.fake_user_preference_repository.records["worker@example.com"] = {
            **self.fake_user_preference_repository.get("worker@example.com"),
            "preferences": {"cultivation_experience": "beginner"},
        }
        field = self.field_repository.upsert(None, {"name": "果樹圃場", "crop": "ブルーベリー"})
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"].append(
            {
                "id": "pot-a",
                "preset": "pot",
                "name": "鉢A",
                "x": 2,
                "y": 3,
                "width": 2,
                "height": 2,
            }
        )
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])

        created = self.client.post(
            f"/local/api/fields/{field['id']}/plantings",
            json={
                "space_id": "space-root",
                "placement_id": "pot-a",
                "crop_name": "ブルーベリー",
                "cultivar": "ティフブルー",
                "crop_category": "fruit_tree",
                "tree_age_years": 3,
                "planted_on": "2026-07-14",
                "plant_count": 1,
                "cultivation_method": "container",
                "conditions": {"environment": "屋外", "soil_or_substrate": "酸性培養土", "sunlight": "日なた", "region": "重複地域"},
            },
        )

        self.assertEqual(created.status_code, 202)
        planting = created.get_json()["planting"]
        self.assertEqual(created.get_json()["generation_task"]["status"], "queued")
        self.assertEqual(created.get_json()["generation_task"]["start_date"], date.today().isoformat())
        self.assertEqual(self.fake_ai_content_service.calendar_contexts, [])
        self.assertEqual(planting["placement_name"], "鉢A")
        self.assertEqual(planting["crop_category"], "fruit_tree")
        self.assertEqual(planting["tree_age_years"], 3)
        self.assertEqual(planting["conditions"]["region"], "")
        self.assertEqual(planting["calendar_id"], "")
        queued_bundle = self.client.get(f"/local/api/fields/{field['id']}/plantings?compact=1")
        self.assertEqual(queued_bundle.get_json()["generation_tasks"][0]["status"], "queued")
        duplicate = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/regenerate",
            json={"start_date": "2026-07-20", "planning_notes": "重複"},
        )
        self.assertEqual(duplicate.status_code, 409)

        self.plant_calendar_generation_task.process_next()
        planting = self.plant_management_repository.get_planting(planting["id"])
        action = self.plant_management_repository.get_calendar(planting["id"])["actions"][0]
        self.assertEqual(planting["growth_targets"]["soil_moisture_percent"], {"min": 32.0, "max": 62.0})
        self.assertEqual(action["priority"], "recommended")
        self.assertEqual(self.fake_ai_content_service.calendar_contexts[-1]["audience"]["experience_level"], "beginner")
        generated_bundle = self.client.get(
            f"/local/api/fields/{field['id']}/plantings",
            headers={"Cf-Access-Authenticated-User-Email": "worker@example.com"},
        ).get_json()
        self.assertEqual(generated_bundle["viewer"], {"email": "worker@example.com", "role": "operator"})
        self.assertIn(action["id"], generated_bundle["operation_readiness"])
        self.assertEqual(generated_bundle["operation_readiness"][action["id"]]["executor_mode"], "human")

        target_update = self.client.patch(
            f"/local/api/plantings/{planting['id']}",
            json={"growth_targets": {"soil_moisture_percent": {"min": 35, "max": 65}}},
        )
        self.assertEqual(target_update.status_code, 200)
        self.assertEqual(target_update.get_json()["growth_targets"]["soil_moisture_percent"]["max"], 65.0)

        catalog = self.client.get("/local/api/fertilizer-materials")
        self.assertEqual(catalog.status_code, 200)
        self.assertIn("builtin:poultry-manure-reference", {item["id"] for item in catalog.get_json()["materials"]})
        custom_material = self.client.post(
            "/local/api/fertilizer-materials",
            json={
                "label": "園芸店の有機配合",
                "material_kind": "organic_fertilizer",
                "material_name": "有機配合 6-4-3",
                "nutrient_percent": {"n": 6, "p2o5": 4, "k2o": 3},
                "annual_available_percent": 50,
                "effect_years": 1,
                "start_delay_days": 7,
                "analysis_source": "製品ラベル",
            },
        )
        self.assertEqual(custom_material.status_code, 201)
        custom_material_id = custom_material.get_json()["id"]

        fertilizer = self.client.post(
            f"/local/api/plantings/{planting['id']}/fertilizer-applications",
            json={
                "material_id": custom_material_id,
                "applied_on": "2026-07-14",
                "material_kind": "cattle_manure",
                "material_name": "牛ふん堆肥",
                "amount_kg": 25,
                "nutrient_percent": {"n": 2, "p2o5": 1, "k2o": 1.5, "mgo": 0.5},
                "annual_available_percent": 10,
                "effect_years": 2,
                "start_delay_days": 0,
                "analysis_source": "製品分析表",
            },
        )
        self.assertEqual(fertilizer.status_code, 201)
        self.assertEqual(fertilizer.get_json()["application"]["placement_id"], "pot-a")
        self.assertEqual(fertilizer.get_json()["application"]["material_snapshot"]["label"], "園芸店の有機配合")
        self.assertGreater(fertilizer.get_json()["effect_summary"]["nutrients"]["n"]["remaining_kg"], 0)
        self.assertGreater(fertilizer.get_json()["effect_summary"]["nutrients"]["mgo"]["remaining_kg"], 0)
        fertilizer_list = self.client.get(f"/local/api/plantings/{planting['id']}/fertilizer-applications?as_of=2026-07-14")
        self.assertEqual(fertilizer_list.status_code, 200)
        self.assertEqual(fertilizer_list.get_json()["applications"][0]["material_name"], "牛ふん堆肥")
        self.assertEqual(self.client.delete(f"/local/api/fertilizer-materials/{custom_material_id}").status_code, 204)

        blocked_completion = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}/complete",
            json={"performed_on": "2026-07-20", "rating": 4},
        )
        self.assertEqual(blocked_completion.status_code, 409)
        self.assertIn("作業を開始", blocked_completion.get_json()["error"])

        edited = self.client.patch(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}",
            json={
                "priority": "should",
                "reason": "葉色が薄くなりやすいため",
                "status": "in_progress",
                "required_people": 2,
                "estimated_minutes": 45,
                "assigned_to": "worker@example.com",
                "use_as_guidance": True,
            },
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["priority"], "should")
        self.assertEqual(edited.get_json()["status"], "in_progress")
        self.assertEqual(edited.get_json()["required_people"], 2)
        self.assertEqual(edited.get_json()["estimated_minutes"], 45)
        self.assertEqual(edited.get_json()["assigned_to"], "worker@example.com")

        another_worker = self.client.patch(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}",
            headers={"Cf-Access-Authenticated-User-Email": "other@example.com"},
            json={"reason": "別担当者による変更"},
        )
        self.assertEqual(another_worker.status_code, 403)

        action_search = self.client.get(f"/local/api/plantings/{planting['id']}/calendar/actions?q=葉色&status=in_progress&page_size=1")
        self.assertEqual(action_search.status_code, 200)
        self.assertEqual(action_search.get_json()["total"], 1)
        self.assertEqual(action_search.get_json()["items"][0]["id"], action["id"])

        rich_action = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions",
            data={
                "payload": json.dumps(
                    {
                        "title": "画像付きの葉色確認",
                        "action_type": "observation",
                        "priority": "recommended",
                        "window_start": "2026-07-21",
                        "window_end": "2026-07-22",
                        "reason": "葉色を比較するため",
                        "instructions": "葉を撮影して比較する",
                        "instructions_html": "<p><strong>同じ葉</strong>を撮影します。</p>{{image:0}}",
                        "required_people": 1,
                        "estimated_minutes": 15,
                    },
                    ensure_ascii=False,
                ),
                "images": (io.BytesIO(b"calendar-action-image"), "leaf.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(rich_action.status_code, 201)
        self.assertEqual(rich_action.get_json()["attachments"][0]["original_filename"], "leaf.png")
        self.assertIn("<figure><img", rich_action.get_json()["instructions_html"])
        self.assertNotIn("{{image:0}}", rich_action.get_json()["instructions_html"])
        rich_image = self.client.get(rich_action.get_json()["attachments"][0]["url"])
        self.assertEqual(rich_image.status_code, 200)
        self.assertEqual(rich_image.data, b"calendar-action-image")

        completed = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}/complete",
            headers={"Cf-Access-Authenticated-User-Email": "worker@example.com"},
            data={
                "performed_on": "2026-07-20",
                "note": "少量施肥",
                "rating": "4",
                "work_details": json.dumps(
                    {
                        "execution": {
                            "target": "鉢Aの根域",
                            "method_id": "custom",
                            "method_label": "手入力した施肥方法",
                            "method_type": "material_application",
                            "material_name": "液肥A",
                            "custom_method": "手入力した施肥方法",
                            "follow_up_days": 10,
                        }
                    },
                    ensure_ascii=False,
                ),
                "images": (io.BytesIO(b"\x89PNG\r\n\x1a\nwork-image"), "work.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(completed.status_code, 201)
        self.assertEqual(completed.get_json()["performed_on"], "2026-07-20")
        self.assertEqual(completed.get_json()["performed_by"], "worker@example.com")
        self.assertEqual(completed.get_json()["rating"], 4)
        self.assertEqual(completed.get_json()["work_details"]["execution"]["follow_up_days"], 10)
        self.assertEqual(completed.get_json()["work_details"]["execution"]["material_name"], "液肥A")
        self.assertEqual(completed.get_json()["attachments"][0]["storage"], "r2")
        self.assertEqual(completed.get_json()["review_status"], "pending")
        self.assertEqual(completed.get_json()["action"]["status"], "awaiting_review")
        self.assertEqual(self.fake_ai_content_service.follow_up_contexts, [])
        self.assertEqual(self.field_repository.get(field["id"])["events"], [])
        pending_field_detail = self.client.get(f"/fields/{field['id']}?planting={planting['id']}#cultivation")
        self.assertNotIn("少量施肥", pending_field_detail.get_data(as_text=True))

        operator_review = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}/review",
            headers={"Cf-Access-Authenticated-User-Email": "worker@example.com"},
            json={"decision": "approved", "note": ""},
        )
        self.assertEqual(operator_review.status_code, 403)
        with patch.dict(os.environ, {"HUB_ADMIN_EMAILS": "manager@example.com"}):
            reviewed = self.client.post(
                f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}/review",
                headers={"Cf-Access-Authenticated-User-Email": "manager@example.com"},
                json={"decision": "approved", "note": "写真と使用量を確認"},
            )
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.get_json()["action"]["status"], "completed")
        self.assertEqual(reviewed.get_json()["work_log"]["reviewed_by"], "manager@example.com")
        self.assertEqual(reviewed.get_json()["follow_up"]["actions"][0]["title"], "次回の追肥要否を確認")
        self.assertEqual(self.fake_ai_content_service.follow_up_contexts[-1]["audience"]["experience_level"], "standard")
        self.assertEqual(self.field_repository.get(field["id"])["events"][0]["occurred_at"], "2026-07-20")

        record_search = self.client.get(f"/local/api/fields/{field['id']}/records?q=少量施肥&page_size=1")
        self.assertEqual(record_search.status_code, 200)
        self.assertEqual(record_search.get_json()["total"], 1)
        self.assertEqual(record_search.get_json()["items"][0]["source"], "event")

        question = self.client.post(
            f"/local/api/plantings/{planting['id']}/questions",
            json={"question": "次の追肥はいつですか"},
        )
        self.assertEqual(question.status_code, 201)
        self.assertIn("ブルーベリーについて回答", question.get_json()["answer"])
        question_history = self.client.get(f"/local/api/plantings/{planting['id']}/questions?q=追肥")
        self.assertEqual(question_history.status_code, 200)
        self.assertEqual(question_history.get_json()["total"], 1)
        ai_calls_before_rejection = len(self.fake_ai_content_service.question_contexts)
        rejected_question = self.client.post(
            f"/local/api/plantings/{planting['id']}/questions",
            json={"question": "おすすめの映画を教えて"},
        )
        self.assertEqual(rejected_question.status_code, 422)
        self.assertEqual(rejected_question.get_json()["code"], "question_out_of_scope")
        self.assertFalse(rejected_question.get_json()["saved"])
        self.assertEqual(len(self.fake_ai_content_service.question_contexts), ai_calls_before_rejection)
        self.assertEqual(self.client.get(f"/local/api/plantings/{planting['id']}/questions").get_json()["total"], 1)
        for index in range(1, 7):
            self.plant_management_repository.record_question(planting["id"], f"第{index}回の葉を確認", f"第{index}回の回答")
        latest_questions = self.client.get(f"/local/api/plantings/{planting['id']}/questions?page=1&page_size=5").get_json()
        older_questions = self.client.get(f"/local/api/plantings/{planting['id']}/questions?page=2&page_size=5").get_json()
        self.assertEqual(latest_questions["total"], 7)
        self.assertEqual(len(latest_questions["items"]), 5)
        self.assertTrue(latest_questions["has_next"])
        self.assertEqual(len(older_questions["items"]), 2)
        self.assertFalse(older_questions["has_next"])

        regenerated = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/regenerate",
            json={"start_date": "2026-07-21", "planning_notes": "週末だけ作業する", "mode": "review"},
        )
        self.assertEqual(regenerated.status_code, 202)
        self.assertEqual(regenerated.get_json()["generation_task"]["status"], "queued")
        locked_action = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions",
            json={"action_type": "observation", "title": "生成中の追加", "window_start": "2026-07-21", "window_end": "2026-07-22"},
        )
        self.assertEqual(locked_action.status_code, 409)
        self.assertIn("AI栽培計画を作成中", locked_action.get_json()["error"])
        locked_fertilizer = self.client.delete(f"/local/api/plantings/{planting['id']}/fertilizer-applications/{fertilizer.get_json()['application']['id']}")
        self.assertEqual(locked_fertilizer.status_code, 409)
        previous_context_count = len(self.fake_ai_content_service.calendar_contexts)
        self.plant_calendar_generation_task.process_next()
        self.assertEqual(self.fake_ai_content_service.calendar_contexts[-1]["audience"]["experience_level"], "beginner")
        self.assertGreater(len(self.fake_ai_content_service.calendar_contexts[-1]["existing_calendar"]["actions"]), 0)
        self.assertEqual(len(self.fake_ai_content_service.calendar_contexts), previous_context_count + 1)
        review_task = self.plant_management_repository.field_bundle(field["id"])["generation_tasks"][0]
        self.assertEqual(review_task["status"], "awaiting_review")
        self.assertTrue(review_task["proposals"])
        decision = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/regeneration-proposals/{review_task['id']}/decisions",
            json={"decisions": [{"proposal_id": proposal["id"], "decision": "approved"} for proposal in review_task["proposals"]]},
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.get_json()["task"]["status"], "succeeded")
        self.assertEqual(decision.get_json()["bundle"]["generation_tasks"][0]["status"], "succeeded")
        self.assertTrue(any(item["status"] == "completed" for item in self.plant_management_repository.get_calendar(planting["id"])["actions"]))

        detail = self.client.get(f"/fields/{field['id']}?planting={planting['id']}#cultivation")
        html = detail.get_data(as_text=True)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('data-field-tab="monitoring"', html)
        self.assertIn(f'data-planting-form="{planting["id"]}"', html)
        self.assertIn("年間カレンダーを開く", html)
        self.assertIn("直近の履歴", html)
        self.assertIn("少量施肥", html)
        self.assertIn("/static/plant-actions/fertilization.webp", html)
        self.assertIn(f"/fields/{field['id']}/calendar?planting={planting['id']}", html)

    def test_plant_action_can_be_checked_and_skipped_with_a_field_history_record(self):
        field = self.field_repository.upsert(None, {"name": "見送り判断圃場", "crop": "ブルーベリー"})
        planting = self.plant_management_repository.create_planting(
            field["id"],
            {
                "space_id": "space-root",
                "placement_id": "pot-a",
                "placement_name": "鉢A",
                "crop_name": "ブルーベリー",
                "planted_on": "2026-07-14",
                "plant_count": 1,
            },
        )
        calendar = self.plant_management_repository.create_calendar(
            planting["id"],
            [
                {
                    "action_type": "fertilization",
                    "title": "追肥する",
                    "window_start": "2026-07-15",
                    "window_end": "2026-07-18",
                }
            ],
        )
        action_id = calendar["actions"][0]["id"]

        direct_status_change = self.client.patch(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action_id}",
            json={"status": "skipped"},
        )
        skipped = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action_id}/skip",
            data={
                "decided_on": "2026-07-19",
                "reason_code": "generated_in_error",
                "observed_facts": "葉色と新梢は良好。排液EC 1.2 mS/cmで追肥不要",
                "note": "期限切れで残った自動作業を確認した",
                "next_review_on": "2026-07-26",
                "use_as_guidance": "true",
                "images": (io.BytesIO(b"\x89PNG\r\n\x1a\nskip-image"), "skip.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(direct_status_change.status_code, 400)
        self.assertEqual(skipped.status_code, 201)
        action = skipped.get_json()["action"]
        self.assertEqual(action["status"], "skipped")
        self.assertEqual(action["skip_decision"]["decided_by"], "local-user@ina.local")
        self.assertEqual(action["skip_decision"]["attachments"][0]["original_filename"], "skip.png")
        event = self.field_repository.get(field["id"])["events"][0]
        self.assertEqual(event["occurred_at"], "2026-07-19")
        self.assertEqual(event["target_placement_id"], "pot-a")
        self.assertIn("自動計画で誤って生成された", event["description"])
        self.assertEqual(self.plant_management_repository.guidance_examples("ブルーベリー")[0]["decision_type"], "skip_action")

        reopened = self.client.patch(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action_id}",
            json={"status": "planned"},
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertIsNone(reopened.get_json()["skip_decision"])
        self.assertEqual(len(self.field_repository.get(field["id"])["events"]), 1)

    def test_planting_generation_rejects_missing_ai_context_before_creating_record(self):
        field = self.field_repository.upsert(None, {"name": "入力確認圃場"})
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"].append({"id": "pot-a", "preset": "pot", "name": "鉢A", "x": 2, "y": 3, "width": 2, "height": 2})
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])

        response = self.client.post(
            f"/local/api/fields/{field['id']}/plantings",
            json={
                "space_id": "space-root",
                "placement_id": "pot-a",
                "crop_name": "ブルーベリー",
                "crop_category": "fruit_tree",
                "planted_on": "2026-07-14",
                "plant_count": 1,
                "cultivation_method": "container",
                "conditions": {"environment": "屋外"},
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("用土・培地", response.get_json()["error"])
        self.assertIn("日当たり", response.get_json()["error"])
        self.assertIn("樹齢", response.get_json()["error"])
        self.assertEqual(self.plant_management_repository.data["plantings"], {})

    def test_record_calendar_opens_daily_records_with_r2_image_and_emoji_rating(self):
        field = self.field_repository.upsert(None, {"name": "記録圃場"})
        image_bytes = b"\x89PNG\r\n\x1a\nfield-image"

        created = self.client.post(
            f"/fields/{field['id']}/events",
            data={
                "event_type": "observation",
                "occurred_at": "2026-07-18T08:30",
                "title": "葉色を確認",
                "description": "新葉の色は安定",
                "rating": "5",
                "images": (io.BytesIO(image_bytes), "leaf.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(created.status_code, 302)
        event = self.field_repository.get(field["id"])["events"][0]
        self.assertEqual(event["rating"], 5)
        self.assertEqual(event["attachments"][0]["storage"], "r2")

        detail = self.client.get(f"/fields/{field['id']}?record_month=2026-07#records")
        html = detail.get_data(as_text=True)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('data-record-date="2026-07-18"', html)
        self.assertIn('id="record-day-modal"', html)
        self.assertIn('id="record-image-dropzone"', html)
        self.assertIn("画像を選択・貼り付け", html)
        self.assertIn("葉色を確認", html)
        self.assertIn("😄", html)

        attachment_id = event["attachments"][0]["id"]
        image = self.client.get(f"/local/api/fields/{field['id']}/record-images/{attachment_id}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content_type, "image/png")
        self.assertEqual(image.data, image_bytes)

        api_created = self.client.post(
            f"/local/api/fields/{field['id']}/events",
            data={
                "event_type": "harvest",
                "occurred_at": "2026-07-19T10:00",
                "title": "収穫を確認",
                "rating": "4",
                "images": (io.BytesIO(b"\x89PNG\r\n\x1a\napi-image"), "harvest.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(api_created.status_code, 201)
        self.assertEqual(api_created.get_json()["rating"], 4)
        self.assertEqual(api_created.get_json()["attachments"][0]["storage"], "r2")

    def test_device_free_field_records_selected_values_for_a_pot_and_reuses_recent_items(self):
        field = self.field_repository.upsert(None, {"name": "手入力圃場"})
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"].append({"id": "pot-a", "preset": "pot", "name": "ブルーベリー鉢A", "x": 2, "y": 2, "width": 2, "height": 2})
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])

        initial = self.client.get(f"/fields/{field['id']}?record_month=2026-07#records")
        initial_html = initial.get_data(as_text=True)
        self.assertEqual(initial.status_code, 200)
        self.assertIn("記録することを検索", initial_html)
        self.assertIn("記録項目を追加", initial_html)
        self.assertIn("ブルーベリー鉢A", initial_html)
        self.assertNotIn("センサー詳細", initial_html)

        created = self.client.post(
            f"/fields/{field['id']}/events",
            data=MultiDict(
                [
                    ("event_type", "daily_record"),
                    ("occurred_at", "2026-07-18T07:15"),
                    ("target_placement_id", "pot-a"),
                    ("record_item_key", "watering_duration_min"),
                    ("record_item_value", "12"),
                    ("record_item_key", "soil_ec_us_cm"),
                    ("record_item_value", "850"),
                    ("description", "朝の手潅水"),
                    ("tags", "潅水"),
                    ("tags", "ブルーベリー"),
                ]
            ),
        )

        self.assertEqual(created.status_code, 302)
        event = self.field_repository.get(field["id"])["events"][0]
        self.assertEqual(event["target_placement_id"], "pot-a")
        self.assertEqual(event["target_name"], "ブルーベリー鉢A")
        self.assertEqual(event["tags"], ["潅水", "ブルーベリー"])
        self.assertEqual(
            [(item["key"], item["value"], item["unit"]) for item in event["record_values"]],
            [("watering_duration_min", 12, "分"), ("soil_ec_us_cm", 850, "uS/cm")],
        )

        detail = self.client.get(f"/fields/{field['id']}?record_month=2026-07#records")
        html = detail.get_data(as_text=True)
        self.assertIn("過去に選択", html)
        self.assertIn('data-add-record-item="watering_duration_min"', html)
        self.assertIn('data-add-record-item="soil_ec_us_cm"', html)
        self.assertIn("朝の手潅水", html)
        self.assertIn('id="record-tag-input"', html)
        self.assertIn('<option value="潅水">', html)
        self.assertIn('<span class="timeline-tag">ブルーベリー</span>', html)

    def test_record_calendar_includes_multiple_automatic_device_values_with_times(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "自動記録圃場",
                "device_ids": ["ENV-001", "SOI-001", "UNBOUND-001"],
            },
        )
        self.fake_device_config_service.records = {
            "ENV-001": {"name": "ハウス環境", "device_kind": "ENV", "state": "active", "status_history": []},
            "SOI-001": {"name": "鉢水分", "device_kind": "SOI", "state": "active", "status_history": []},
            "UNBOUND-001": {"name": "未配置センサー", "device_kind": "SOI", "state": "active", "status_history": []},
        }
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"] = [
            {
                "id": "sensor-env",
                "preset": "sensor",
                "name": "環境センサー",
                "x": 1,
                "y": 1,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "ENV-001", "resource_type": "sensor", "resource_id": ""},
            },
            {
                "id": "sensor-soil",
                "preset": "sensor",
                "name": "土壌センサー",
                "x": 4,
                "y": 1,
                "width": 2,
                "height": 2,
                "binding": {"device_id": "SOI-001", "resource_type": "sensor", "resource_id": ""},
            },
        ]
        self.field_layout_repository.upsert(field["id"], layout, field_name=field["name"])
        self.fake_sensor_measurement_repository.measurements = [
            {
                "device_id": "ENV-001",
                "device_kind": "ENV",
                "measured_at": "2026-07-18T00:30:00+00:00",
                "metric": "soil_ec_us_cm",
                "value": 780,
                "unit": "uS/cm",
                "source": "mqtt_status",
            },
            {
                "device_id": "ENV-001",
                "device_kind": "ENV",
                "measured_at": "2026-07-18T02:30:00+00:00",
                "metric": "soil_ec_us_cm",
                "value": 810,
                "unit": "uS/cm",
                "source": "mqtt_status",
            },
            {
                "device_id": "SOI-001",
                "device_kind": "SOI",
                "measured_at": "2026-07-18T01:00:00+00:00",
                "metric": "soil_moisture_percent",
                "value": 44,
                "unit": "%",
                "source": "mqtt_status",
            },
            {
                "device_id": "UNBOUND-001",
                "device_kind": "SOI",
                "measured_at": "2026-07-18T01:30:00+00:00",
                "metric": "soil_moisture_percent",
                "value": 51,
                "unit": "%",
                "source": "mqtt_status",
            },
        ]

        detail = self.client.get(f"/fields/{field['id']}?record_month=2026-07#records")
        html = detail.get_data(as_text=True)

        self.assertEqual(detail.status_code, 200)
        self.assertIn("自動 3", html)
        self.assertIn("ハウス環境", html)
        self.assertIn("鉢水分", html)
        self.assertNotIn("未配置センサー", html)
        self.assertIn('"time": "09:30"', html)
        self.assertIn('"time": "11:30"', html)

        self.fake_user_preference_repository.records["local-user@ina.local"] = {
            "user_email": "local-user@ina.local",
            "locale": "ja",
            "timezone": "UTC",
            "date_format": "yyyy-MM-dd",
            "preferences": {"cultivation_experience": "standard"},
            "version": 1,
            "created_at": "",
            "updated_at": "2026-07-18 00:00:00",
        }
        utc_detail = self.client.get(f"/fields/{field['id']}?record_month=2026-07#records")
        utc_html = utc_detail.get_data(as_text=True)

        self.assertEqual(utc_detail.status_code, 200)
        self.assertIn('"time": "00:30"', utc_html)
        self.assertIn('"time": "02:30"', utc_html)
        self.assertNotIn('"time": "09:30"', utc_html)


if __name__ == "__main__":
    unittest.main()
