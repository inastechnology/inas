import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ina_device_hub.hierarchy_repository import (
    HierarchyAuthenticationError,
    HierarchyConflictError,
    HierarchyRepository,
)

LOCAL_HUB_ID = "INALH-123e4567-e89b-42d3-a456-426614174001"
CHILD_EDGE_ID = "INAEG-223e4567-e89b-42d3-a456-426614174001"
CHILD_HUB_ID = "INALH-323e4567-e89b-42d3-a456-426614174001"
DESCENDANT_EDGE_ID = "INAEG-423e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


def new_id() -> str:
    return str(uuid.uuid4())


class HierarchyRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "hierarchy.db"
        self.repository = HierarchyRepository(self.database_path, parent_node_id=LOCAL_HUB_ID)

    def tearDown(self):
        self.repository.close()
        self.temporary_directory.cleanup()

    def test_enrollment_returns_token_once_rotates_and_revokes_without_public_secret(self):
        enrolled = self.repository.enroll_child(CHILD_EDGE_ID, display_name="North field")
        first_token = enrolled["bearer_token"]

        authenticated = self.repository.authenticate_child(CHILD_EDGE_ID, first_token)

        self.assertEqual(authenticated["parent_node_id"], LOCAL_HUB_ID)
        self.assertNotIn("bearer_token", authenticated)
        self.assertFalse(any("credential" in key for key in authenticated))
        self.assertNotIn(first_token.encode(), self.database_path.read_bytes())

        rotated = self.repository.enroll_child(CHILD_EDGE_ID, display_name="North field")
        with self.assertRaises(HierarchyAuthenticationError):
            self.repository.authenticate_child(CHILD_EDGE_ID, first_token)
        self.repository.authenticate_child(CHILD_EDGE_ID, rotated["bearer_token"])

        self.repository.revoke_child(CHILD_EDGE_ID)
        with self.assertRaises(HierarchyAuthenticationError):
            self.repository.authenticate_child(CHILD_EDGE_ID, rotated["bearer_token"])

    def test_registered_subtree_persists_idempotent_events_and_rejects_conflicts(self):
        self.repository.enroll_child(CHILD_HUB_ID, descendant_node_ids=[DESCENDANT_EDGE_ID])
        event = self._event(origin_node_id=DESCENDANT_EDGE_ID, sequence=9)
        request = self._request(CHILD_HUB_ID, events=[event])

        first = self.repository.ingest_exchange(CHILD_HUB_ID, request)
        replay = self.repository.ingest_exchange(CHILD_HUB_ID, request)

        self.assertEqual(first["ack_event_ids"], [event["event_id"]])
        self.assertEqual(replay["ack_event_ids"], [event["event_id"]])
        stored = self.repository.list_events()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["event_id"], event["event_id"])
        self.assertEqual(stored[0]["origin_node_id"], DESCENDANT_EDGE_ID)
        self.assertEqual(stored[0]["sequence"], 9)

        conflicting = {**event, "payload": {"soil_moisture": 99}}
        with self.assertRaises(HierarchyConflictError):
            self.repository.ingest_exchange(CHILD_HUB_ID, self._request(CHILD_HUB_ID, events=[conflicting]))
        self.assertEqual(len(self.repository.list_events()), 1)

    def test_desired_and_commands_follow_next_hop_and_expired_commands_are_omitted(self):
        self.repository.enroll_child(CHILD_HUB_ID, descendant_node_ids=[DESCENDANT_EDGE_ID])
        desired = self.repository.set_downstream_desired(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=DESCENDANT_EDGE_ID,
            operation="upsert",
            payload={"moisture_threshold": 42},
        )
        active_command = self.repository.create_command(
            target_node_id=DESCENDANT_EDGE_ID,
            command_type="device.runtime_config_push",
            device_id=DEVICE_ID,
            expires_at="2099-01-01T00:05:00Z",
            payload={},
        )
        self.repository.create_command(
            target_node_id=DESCENDANT_EDGE_ID,
            command_type="device.runtime_config_push",
            device_id=DEVICE_ID,
            expires_at="2098-01-01T00:05:00Z",
            payload={},
        )

        resources = self.repository.desired_for_child(CHILD_HUB_ID)
        commands = self.repository.commands_for_child(
            CHILD_HUB_ID,
            now=datetime(2098, 6, 23, 2, 15, tzinfo=UTC),
        )

        self.assertEqual(resources, [desired])
        self.assertEqual([command["command_id"] for command in commands], [active_command["command_id"]])
        self.assertEqual(commands[0]["target_node_id"], DESCENDANT_EDGE_ID)

        result = {
            "result_id": new_id(),
            "command_id": active_command["command_id"],
            "origin_node_id": DESCENDANT_EDGE_ID,
            "status": "succeeded",
            "occurred_at": "2026-07-23T02:16:00.000Z",
        }
        response = self.repository.ingest_exchange(
            CHILD_HUB_ID,
            self._request(CHILD_HUB_ID, command_results=[result]),
        )
        self.assertEqual(response["ack_command_result_ids"], [result["result_id"]])
        self.assertEqual(self.repository.commands_for_child(CHILD_HUB_ID), [])

    def test_child_records_are_marked_forwarded_only_after_durable_upstream_enqueue(self):
        self.repository.enroll_child(CHILD_EDGE_ID)
        event = self._event(origin_node_id=CHILD_EDGE_ID, sequence=1)
        self.repository.ingest_exchange(CHILD_EDGE_ID, self._request(CHILD_EDGE_ID, events=[event]))

        pending = self.repository.unforwarded_events()
        self.assertEqual(pending, [event])
        self.assertEqual(self.repository.mark_events_forwarded([event["event_id"]]), 1)
        self.assertEqual(self.repository.unforwarded_events(), [])
        self.assertEqual(self.repository.list_events(), [event])

    def _request(self, node_id, *, events=None, command_results=None):
        return {
            "protocol_version": "1.0",
            "request_id": new_id(),
            "node_id": node_id,
            "node_type": "local_hub" if node_id.startswith("INALH-") else "edge_gateway",
            "sent_at": "2026-07-23T02:15:00.000Z",
            "cursor": None,
            "events": events or [],
            "command_results": command_results or [],
            "health": {
                "status": "ok",
                "software_version": "0.1.0",
                "outbox_depth": len(events or []) + len(command_results or []),
                "mqtt_connected": True,
                "storage_free_bytes": 1000,
                "capabilities": ["mqtt"],
            },
        }

    def _event(self, *, origin_node_id, sequence):
        return {
            "event_id": new_id(),
            "origin_node_id": origin_node_id,
            "sequence": sequence,
            "schema_version": 1,
            "event_type": "device.telemetry",
            "occurred_at": "2026-07-23T02:14:58.000Z",
            "device_id": DEVICE_ID,
            "payload": {"soil_moisture": 41},
        }


if __name__ == "__main__":
    unittest.main()
