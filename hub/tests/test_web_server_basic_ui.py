import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import UTC, datetime
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

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.field_layout_repository import FieldLayoutRepository  # noqa: E402
from ina_device_hub.field_repository import FieldRepository  # noqa: E402
from ina_device_hub.plant_management_repository import PlantManagementRepository  # noqa: E402
from ina_device_hub.sensor_device_repository import SensorDeviceRepository  # noqa: E402


class FakeTimelapseMediaService:
    def __init__(self):
        self.calls = []

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


class FakeAIContentService:
    def __init__(self):
        self.connection_overrides = None
        self.calendar_contexts = []
        self.follow_up_contexts = []

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

    def between_for_devices(self, device_ids, start_at, end_at, limit=5000):
        return [item for item in reversed(self.measurements) if item["device_id"] in device_ids and start_at <= item["measured_at"] < end_at][:limit]


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
        return deepcopy(self.records.get(user_email.lower(), {
            "user_email": user_email.lower(),
            "locale": "ja",
            "timezone": "Asia/Tokyo",
            "date_format": "yyyy-MM-dd",
            "preferences": {"cultivation_experience": "standard"},
            "version": 0,
            "created_at": "",
            "updated_at": "",
        }))

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
        self.plant_management_repository = PlantManagementRepository()
        self.plant_management_repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.plant_management_repository.data = {
            "schema_version": 1,
            "plantings": {},
            "calendars": {},
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
        web_server.plant_management_repository = self.original_plant_management_repository
        web_server.ai_content_service = self.original_ai_content_service
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
        self.assertIn("初心者 - 手順を詳しく", html)

        saved = self.client.patch(
            "/local/api/me/preferences",
            headers=headers,
            json={
                "version": 0,
                "locale": "en",
                "timezone": "UTC",
                "date_format": "MM/dd/yyyy",
                "preferences": {"cultivation_experience": "beginner"},
            },
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["preferences"]["version"], 1)
        self.assertEqual(saved.get_json()["preferences"]["locale"], "ja")
        self.assertEqual(saved.get_json()["preferences"]["preferences"]["cultivation_experience"], "beginner")
        self.assertNotIn("Set-Cookie", saved.headers)

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
        response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("アプリ設定", html)
        self.assertIn('id="settings-search"', html)
        self.assertNotIn('name="default_language"', html)
        self.assertNotIn("システム既定言語", html)
        self.assertIn('name="text_analyze_model"', html)
        self.assertIn('name="image_analyze_model"', html)
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
        self.assertIn('name="camera_id"', html)
        self.assertIn('id="instagram-camera-select"', html)
        self.assertIn('data-searchable-select', html)
        self.assertIn('/static/searchable-select.css', html)
        self.assertIn('name="plant_position_prompt"', html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("接続を確認", html)

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

    def test_instagram_settings_reject_invalid_post_schedule_before_saving(self):
        response = self.client.post("/settings", data={"settings_section": "instagram", "post_schedule_start": "invalid"})

        self.assertEqual(response.status_code, 400)

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

    def test_field_status_dashboard_uses_latest_value_and_flags_target_miss(self):
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
                    "values": {"soil_moisture_percent": 48, "soil_ph": 6.0},
                },
                {
                    "device_id": "SOI-new",
                    "scope_label": "2番畝",
                    "updated_at": "2026-07-14T02:00:00+00:00",
                    "values": {"last_soil_moisture": 29, "soil_ph": 6.2},
                },
            ],
        )

        metrics = {metric["metric"]: metric for metric in dashboard["metrics"]}
        moisture = metrics["soil_moisture_percent"]
        self.assertEqual(dashboard["overall_state"], "attention")
        self.assertEqual(dashboard["counts"]["attention"], 1)
        self.assertEqual(moisture["value"], 29)
        self.assertEqual(moisture["device_id"], "SOI-new")
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
        self.assertIn('aria-label="INADS-soiの動作設定"', html)
        self.assertNotIn("<h3>監視単位</h3>", html)
        self.assertNotIn("東ベッド", html)

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

    def test_planting_calendar_edit_completion_and_question_flow(self):
        self.fake_user_preference_repository.records["local-user@ina.local"] = {
            **self.fake_user_preference_repository.get("local-user@ina.local"),
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

        self.assertEqual(created.status_code, 201)
        planting = created.get_json()["planting"]
        action = created.get_json()["calendar"]["actions"][0]
        self.assertEqual(planting["placement_name"], "鉢A")
        self.assertEqual(planting["crop_category"], "fruit_tree")
        self.assertEqual(planting["tree_age_years"], 3)
        self.assertEqual(planting["conditions"]["region"], "")
        self.assertEqual(planting["growth_targets"]["soil_moisture_percent"], {"min": 32.0, "max": 62.0})
        self.assertEqual(action["priority"], "recommended")
        self.assertEqual(self.fake_ai_content_service.calendar_contexts[-1]["audience"]["experience_level"], "beginner")

        target_update = self.client.patch(
            f"/local/api/plantings/{planting['id']}",
            json={"growth_targets": {"soil_moisture_percent": {"min": 35, "max": 65}}},
        )
        self.assertEqual(target_update.status_code, 200)
        self.assertEqual(target_update.get_json()["growth_targets"]["soil_moisture_percent"]["max"], 65.0)

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
                "use_as_guidance": True,
            },
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["priority"], "should")
        self.assertEqual(edited.get_json()["status"], "in_progress")
        self.assertEqual(edited.get_json()["required_people"], 2)
        self.assertEqual(edited.get_json()["estimated_minutes"], 45)

        action_search = self.client.get(
            f"/local/api/plantings/{planting['id']}/calendar/actions?q=葉色&status=in_progress&page_size=1"
        )
        self.assertEqual(action_search.status_code, 200)
        self.assertEqual(action_search.get_json()["total"], 1)
        self.assertEqual(action_search.get_json()["items"][0]["id"], action["id"])

        completed = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/actions/{action['id']}/complete",
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
        self.assertEqual(completed.get_json()["rating"], 4)
        self.assertEqual(completed.get_json()["work_details"]["execution"]["follow_up_days"], 10)
        self.assertEqual(completed.get_json()["work_details"]["execution"]["material_name"], "液肥A")
        self.assertEqual(completed.get_json()["attachments"][0]["storage"], "r2")
        self.assertEqual(completed.get_json()["follow_up"]["actions"][0]["title"], "次回の追肥要否を確認")
        self.assertEqual(self.fake_ai_content_service.follow_up_contexts[-1]["audience"]["experience_level"], "beginner")
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

        regenerated = self.client.post(
            f"/local/api/plantings/{planting['id']}/calendar/regenerate",
            json={"start_date": "2026-07-21", "planning_notes": "週末だけ作業する"},
        )
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(self.fake_ai_content_service.calendar_contexts[-1]["audience"]["experience_level"], "beginner")
        self.assertTrue(any(item["status"] == "completed" for item in regenerated.get_json()["calendar"]["actions"]))

        detail = self.client.get(f"/fields/{field['id']}?planting={planting['id']}#cultivation")
        html = detail.get_data(as_text=True)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('data-field-tab="monitoring"', html)
        self.assertIn(f'data-planting-form="{planting["id"]}"', html)
        self.assertIn("年間カレンダーを開く", html)
        self.assertIn("直近の履歴", html)
        self.assertIn("少量施肥", html)
        self.assertIn('/static/plant-actions/fertilization.webp', html)
        self.assertIn(f'/fields/{field["id"]}/calendar?planting={planting["id"]}', html)

    def test_planting_generation_rejects_missing_ai_context_before_creating_record(self):
        field = self.field_repository.upsert(None, {"name": "入力確認圃場"})
        layout = self.field_layout_repository.get(field["id"], field_name=field["name"])
        layout["spaces"][0]["placements"].append(
            {"id": "pot-a", "preset": "pot", "name": "鉢A", "x": 2, "y": 3, "width": 2, "height": 2}
        )
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
                ]
            ),
        )

        self.assertEqual(created.status_code, 302)
        event = self.field_repository.get(field["id"])["events"][0]
        self.assertEqual(event["target_placement_id"], "pot-a")
        self.assertEqual(event["target_name"], "ブルーベリー鉢A")
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


if __name__ == "__main__":
    unittest.main()
