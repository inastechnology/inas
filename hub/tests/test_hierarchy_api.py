import gzip
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOCAL_STORAGE_BASE_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "local")
os.environ.setdefault("TURSO_AUTH_TOKEN", "local")
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

from ina_device_hub import hierarchy_api, web_server  # noqa: E402
from ina_device_hub.hierarchy_repository import HierarchyRepository  # noqa: E402
from ina_device_hub.hierarchy_service import HierarchyService  # noqa: E402
from ina_device_hub.local_edge_runtime import LocalEdgeRuntime  # noqa: E402

CHILD_EDGE_ID = "INAEG-223e4567-e89b-42d3-a456-426614174001"
OTHER_EDGE_ID = "INAEG-323e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


def new_id() -> str:
    return str(uuid.uuid4())


class HierarchyApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.runtime = LocalEdgeRuntime.open(self.root)
        self.repository = HierarchyRepository(
            self.root / "edge-runtime" / "hierarchy.db",
            parent_node_id=self.runtime.node_id,
        )
        self.service = HierarchyService(repository=self.repository, runtime=self.runtime)
        self.client = web_server.app.test_client()
        self.service_patch = patch.object(hierarchy_api, "hierarchy_service", return_value=self.service)
        self.service_patch.start()
        self.environment = {"HUB_AUTH_MODE": "local"}

    def tearDown(self):
        self.service_patch.stop()
        self.repository.close()
        self.runtime.close()
        self.temporary_directory.cleanup()

    def test_admin_enrollment_returns_one_time_token_and_lists_only_public_node_data(self):
        with patch.dict(os.environ, self.environment, clear=False):
            enrolled = self.client.post(
                "/local/api/hierarchy/children/enrollments",
                json={"node_id": CHILD_EDGE_ID, "display_name": "North field"},
            )
            listed = self.client.get("/local/api/hierarchy/nodes")

        self.assertEqual(enrolled.status_code, 201)
        token = enrolled.get_json()["bearer_token"]
        self.assertTrue(token.startswith("inas_sync_v1_"))
        serialized = json.dumps(listed.get_json())
        self.assertNotIn(token, serialized)
        self.assertNotIn("credential_digest", serialized)
        self.assertEqual(listed.get_json()["children"][0]["parent_node_id"], self.runtime.node_id)
        self.assertEqual(enrolled.headers["Cache-Control"], "no-store")

    def test_node_authentication_happens_before_body_and_gzip_exchange_succeeds(self):
        enrollment = self.repository.enroll_child(CHILD_EDGE_ID)
        oversized = gzip.compress(b"x" * ((1024 * 1024) + 1))
        with patch.dict(os.environ, self.environment, clear=False):
            unauthenticated = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                data=oversized,
                headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
            )
            valid = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                data=gzip.compress(json.dumps(self._request()).encode()),
                headers={
                    "Authorization": f"Bearer {enrollment['bearer_token']}",
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.get_json()["correlation_request_id"], self.request_id)
        self.assertEqual(valid.get_json()["ack_event_ids"], [self.event_id])

    def test_sync_rejects_decompressed_oversize_mismatch_and_routing_override(self):
        enrollment = self.repository.enroll_child(CHILD_EDGE_ID)
        headers = {
            "Authorization": f"Bearer {enrollment['bearer_token']}",
            "Content-Type": "application/json",
        }
        request_document = self._request()
        with patch.dict(os.environ, self.environment, clear=False):
            oversized = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                data=gzip.compress(b"x" * ((1024 * 1024) + 1)),
                headers={**headers, "Content-Encoding": "gzip"},
            )
            mismatch = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                json={**request_document, "node_id": OTHER_EDGE_ID},
                headers=headers,
            )
            routing = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                json={**request_document, "tenant_id": "caller-must-not-route"},
                headers=headers,
            )

        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(routing.status_code, 400)
        self.assertEqual(self.repository.list_events(), [])

    def test_browser_identity_cannot_replace_node_bearer_and_revocation_is_immediate(self):
        enrollment = self.repository.enroll_child(CHILD_EDGE_ID)
        with patch.dict(os.environ, self.environment, clear=False):
            browser_only = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                json=self._request(),
                headers={"CF-Access-Jwt-Assertion": "browser-token"},
            )
            self.repository.revoke_child(CHILD_EDGE_ID)
            revoked = self.client.post(
                f"/sync/v1/nodes/{CHILD_EDGE_ID}/exchange",
                json=self._request(),
                headers={"Authorization": f"Bearer {enrollment['bearer_token']}"},
            )

        self.assertEqual(browser_only.status_code, 401)
        self.assertEqual(revoked.status_code, 401)

    def _request(self):
        self.request_id = new_id()
        self.event_id = new_id()
        return {
            "protocol_version": "1.0",
            "request_id": self.request_id,
            "node_id": CHILD_EDGE_ID,
            "node_type": "edge_gateway",
            "sent_at": "2026-07-23T02:15:00Z",
            "cursor": None,
            "events": [
                {
                    "event_id": self.event_id,
                    "origin_node_id": CHILD_EDGE_ID,
                    "sequence": 1,
                    "schema_version": 1,
                    "event_type": "device.telemetry",
                    "occurred_at": "2026-07-23T02:14:58Z",
                    "device_id": DEVICE_ID,
                    "payload": {"soil_moisture": 41},
                }
            ],
            "command_results": [],
            "health": {
                "status": "ok",
                "software_version": "0.1.0",
                "outbox_depth": 1,
                "mqtt_connected": True,
                "storage_free_bytes": 1000,
                "capabilities": ["mqtt"],
            },
        }


if __name__ == "__main__":
    unittest.main()
