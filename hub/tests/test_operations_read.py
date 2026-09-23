import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOCAL_STORAGE_BASE_DIR", tempfile.mkdtemp())
for env_key, env_value in {
    "TURSO_DATABASE_URL": "local",
    "TURSO_AUTH_TOKEN": "local",
    "S3_ENDPOINT_URL": "x",
    "S3_BUCKET_NAME": "x",
    "S3_BUCKET_REGION": "auto",
    "S3_ACCESS_KEY": "x",
    "S3_SECRET_KEY": "x",
    "MQTT_BROKER_URL": "localhost",
    "MQTT_BROKER_PORT": "1883",
    "TIMELAPSE_INTERVAL": "600",
}.items():
    os.environ.setdefault(env_key, env_value)

from ina_device_hub import operations_api, user_context, web_server  # noqa: E402
from ina_device_hub.field_record_media_service import FieldRecordMediaStorageError  # noqa: E402
from ina_device_hub.field_repository import FieldRepository  # noqa: E402
from ina_device_hub.operations_read_service import OperationsReadService  # noqa: E402
from ina_device_hub.timelapse_media_service import TimelapseMediaService  # noqa: E402


class OperationsReadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.fields = FieldRepository.__new__(FieldRepository)
        self.attachment = {
            "id": "photo-a",
            "object_key": "field-records/field-a/2026-09-22/photo-a.png",
            "content_type": "image/png",
            "size_bytes": 12,
            "original_filename": "leaf.png",
            "url": "/local/api/secret",
            "private": "hidden",
        }
        self.fields.fields = {
            "field-a": {
                "id": "field-a",
                "name": "Field A",
                "memo": "not in inventory",
                "camera_device_ids": ["camera-a"],
                "notes": [
                    {"id": "note-a", "text": "葉の色", "created_at": "2026-09-22T09:00:00+00:00", "attachments": [self.attachment]},
                    {"id": "note-b", "text": "潅水後", "created_at": "2026-09-22T09:00:00+00:00"},
                ],
                "events": [
                    {"id": "event-a", "title": "Earlier observation entered later", "occurred_at": "2026-09-01T08:00:00", "created_at": "2026-09-23T10:00:00Z"}
                ],
            },
            "field-b": {"id": "field-b", "name": "Private", "camera_device_ids": ["camera-b"], "notes": [{"id": "secret"}]},
        }
        self.layouts = Mock()
        self.layouts.get.return_value = {"spaces": []}
        self.frames = TimelapseMediaService.__new__(TimelapseMediaService)
        self.frames.local_storage_base_dir = str(self.base)
        self._frame("camera-a", "20260922_080000")
        self._frame("camera-a", "20260922_090000")
        self._frame("camera-b", "20260922_080000")
        self.attachments = Mock()
        self.attachments.fetch_image.return_value = b"\x89PNG\r\n\x1a\nleaf"
        self.service = OperationsReadService(self.fields, self.layouts, self.frames, self.attachments)
        self.environment = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
            "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
            "HUB_OPERATIONS_SERVICE_IDS": "legacy.access",
            "HUB_OPERATIONS_READ_GRANTS": self._grants(),
        }
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.environment).start()
        self.auth = patch.object(user_context, "_verify_access_token", return_value={"common_name": "collector.access"}).start()
        patch.object(operations_api, "OperationsReadService", return_value=self.service).start()
        self.ota = patch.object(operations_api, "ota_update_service").start()
        self.client = web_server.app.test_client()
        self.headers = {user_context.ACCESS_JWT_HEADER: "test-jwt"}

    @staticmethod
    def _grants(scopes=None, fields=None):
        return json.dumps(
            {"collector.access": {"scopes": scopes if scopes is not None else ["records:read", "images:read"], "field_ids": fields or ["field-a"]}}
        )

    def _frame(self, camera, image_id):
        path = self.base / "timelapse_frames" / camera / image_id[:8] / f"{image_id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xffframe")
        return path

    def get(self, path, **kwargs):
        return self.client.get(f"/operations/api/v1/{path}", headers=self.headers, **kwargs)

    def test_field_list_contains_only_allowed_metadata(self):
        response = self.get("fields")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json["items"]], ["field-a"])
        self.assertNotIn("memo", response.json["items"][0])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_collector_cannot_publish_rollout_or_read_devices(self):
        for path in ("devices/firmware-artifacts/WTR/1.0.0", "devices/firmware-rollouts"):
            with self.subTest(path=path):
                response = self.client.post(f"/operations/api/v1/{path}", headers=self.headers, json={"dry_run": False})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.get("devices").status_code, 403)
        self.ota.assert_not_called()

    def test_legacy_service_has_no_implicit_field_access(self):
        self.auth.return_value = {"common_name": "legacy.access"}
        self.assertEqual(self.get("fields").status_code, 403)
        self.assertEqual(self.get("health").status_code, 200)

    def test_browser_token_is_not_a_collector_identity(self):
        self.auth.return_value = {"email": "person@example.com"}
        with patch.object(web_server, "discord_notification_service"):
            self.assertEqual(self.get("fields").status_code, 401)

    def test_removing_read_grant_revokes_access_instead_of_enabling_writes(self):
        with patch.dict(os.environ, {"HUB_OPERATIONS_READ_GRANTS": "{}"}), patch.object(web_server, "discord_notification_service"):
            self.assertEqual(self.get("fields").status_code, 401)
            response = self.client.post("/operations/api/v1/devices/firmware-rollouts", headers=self.headers, json={})
            self.assertEqual(response.status_code, 401)
        self.ota.assert_not_called()

    def test_identity_cannot_be_both_reader_and_writer(self):
        with patch.dict(os.environ, {"HUB_OPERATIONS_SERVICE_IDS": "collector.access,legacy.access"}), patch.object(web_server, "discord_notification_service"):
            self.assertEqual(self.get("health").status_code, 401)

    def test_collector_cannot_use_browser_api(self):
        self.assertEqual(self.client.get("/local/api/fields", headers=self.headers).status_code, 401)

    def test_invalid_grants_fail_closed_for_legacy_writes(self):
        self.auth.return_value = {"common_name": "legacy.access"}
        for value in ("broken", "[]", '{"collector.access":null}', self._grants(scopes=["admin"]), self._grants(scopes=[])):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"HUB_OPERATIONS_READ_GRANTS": value}),
                patch.object(web_server, "discord_notification_service"),
            ):
                response = self.client.post("/operations/api/v1/devices/firmware-rollouts", headers=self.headers, json={})
                self.assertEqual(response.status_code, 401)
        self.ota.assert_not_called()

    def test_scopes_and_field_membership_are_checked_on_every_route(self):
        for path in ("fields/field-b/records", "fields/field-b/cameras", "fields/field-b/record-images/photo-a", "fields/field-b/cameras/camera-b/images"):
            self.assertEqual(self.get(path).status_code, 403, path)
        with patch.dict(os.environ, {"HUB_OPERATIONS_READ_GRANTS": self._grants(scopes=["records:read"])}):
            self.assertEqual(self.get("fields/field-a/cameras").status_code, 403)
            self.assertEqual(self.get("fields/field-a/record-images/photo-a").status_code, 403)
        with patch.dict(os.environ, {"HUB_OPERATIONS_READ_GRANTS": self._grants(scopes=["images:read"])}):
            self.assertEqual(self.get("fields/field-a/records").status_code, 403)
        self.attachments.fetch_image.assert_not_called()

    def test_search_pagination_preserves_ties_and_sanitizes_attachments(self):
        first = self.get("fields/field-a/records", query_string={"limit": 1}).json
        second = self.get("fields/field-a/records", query_string={"limit": 1, "cursor": first["next_cursor"]}).json
        third = self.get("fields/field-a/records", query_string={"limit": 1, "cursor": second["next_cursor"]}).json
        self.assertEqual([page["items"][0]["id"] for page in (first, second, third)], ["note-a", "note-b", "event-a"])
        self.assertFalse(third["has_more"])
        attachment = first["items"][0]["attachments"][0]
        self.assertNotIn("object_key", attachment)
        self.assertNotIn("private", attachment)
        self.assertTrue(attachment["url"].startswith("/operations/api/v1/"))
        self.assertEqual(self.get("fields/field-a/records", query_string={"q": "different", "cursor": first["next_cursor"]}).status_code, 400)

    def test_incremental_filter_uses_ingestion_time_for_backdated_events(self):
        response = self.get("fields/field-a/records", query_string={"since": "2026-09-23T00:00:00Z"})
        self.assertEqual([item["id"] for item in response.json["items"]], ["event-a"])
        response = self.get("fields/field-a/records", query_string={"q": "葉", "source": "note"})
        self.assertEqual([item["id"] for item in response.json["items"]], ["note-a"])

    def test_invalid_filters_return_bad_request(self):
        for query in (
            {"limit": 101},
            {"cursor": "!"},
            {"date_from": "yesterday"},
            {"date_from": "2026-09-23", "date_to": "2026-09-22"},
            {"source": "unknown"},
            {"since": "2026-09-23"},
        ):
            self.assertEqual(self.get("fields/field-a/records", query_string=query).status_code, 400, query)

    def test_actual_attachment_bytes_and_storage_errors(self):
        response = self.get("fields/field-a/record-images/photo-a")
        self.assertEqual(response.data, self.attachments.fetch_image.return_value)
        self.assertEqual(response.mimetype, "image/png")
        self.attachments.fetch_image.side_effect = FieldRecordMediaStorageError("private object storage endpoint")
        response = self.get("fields/field-a/record-images/photo-a")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b"private object", response.data)

    def test_unknown_or_cross_field_attachment_never_reads_storage(self):
        self.assertEqual(self.get("fields/field-a/record-images/unknown").status_code, 404)
        self.attachment["object_key"] = "field-records/field-b/2026-09-22/photo-a.png"
        self.assertEqual(self.get("fields/field-a/record-images/photo-a").status_code, 404)
        self.attachments.fetch_image.assert_not_called()

    def test_camera_list_and_paginated_saved_images(self):
        self.assertEqual(self.get("fields/field-a/cameras").json["items"], [{"id": "camera-a", "field_id": "field-a"}])
        first = self.get("fields/field-a/cameras/camera-a/images", query_string={"limit": 1}).json
        second = self.get("fields/field-a/cameras/camera-a/images", query_string={"limit": 1, "cursor": first["next_cursor"]}).json
        self.assertEqual(first["items"][0]["id"], "20260922_080000")
        self.assertEqual(second["items"][0]["id"], "20260922_090000")
        self.assertNotIn("relative_path", first["items"][0])
        response = self.client.get(first["items"][0]["url"], headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"\xff\xd8\xffframe")

    def test_camera_from_other_field_and_traversal_are_rejected(self):
        self.assertEqual(self.get("fields/field-a/cameras/camera-b/images").status_code, 404)
        self.assertEqual(self.get("fields/field-a/cameras/camera-b/images/20260922_080000").status_code, 404)
        self.assertEqual(self.get("fields/field-a/cameras/camera-a/images/..%2fsecret").status_code, 404)

    def test_frame_symlinks_cannot_escape_camera_directory(self):
        path = self._frame("camera-a", "20260922_100000")
        path.unlink()
        path.symlink_to(self.base / "timelapse_frames/camera-b/20260922/20260922_080000.jpg")
        self.assertEqual(self.get("fields/field-a/cameras/camera-a/images/20260922_100000").status_code, 404)
        self.assertEqual(self.get("fields/field-a/cameras/camera-a/images").json["count"], 2)

    def test_layout_assignments_supersede_stale_legacy_camera_list(self):
        self.layouts.get.return_value = {"spaces": [{"placements": [{"binding": {"device_id": "camera-c", "resource_type": "camera"}}]}]}
        self.assertEqual(self.get("fields/field-a/cameras").json["items"][0]["id"], "camera-c")
        self.assertEqual(self.get("fields/field-a/cameras/camera-a/images").status_code, 404)


if __name__ == "__main__":
    unittest.main()
