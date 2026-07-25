import json
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ina_edge_runtime.protocol import content_hash
from ina_edge_runtime.store import EdgeStore
from ina_edge_runtime.sync import apply_sync_response, build_sync_request, normalize_sync_request, normalize_sync_response

EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174001"
LOCAL_HUB_ID = "INALH-223e4567-e89b-42d3-a456-426614174001"
DESCENDANT_EDGE_ID = "INAEG-323e4567-e89b-42d3-a456-426614174001"
OTHER_EDGE_ID = "INAEG-423e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"
SENT_AT = datetime(2026, 7, 23, 2, 15, tzinfo=UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class SyncRequestTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = EdgeStore(Path(self.temporary_directory.name) / "edge.db")

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_builds_schema_conformant_batch_from_durable_state(self):
        event_id = new_id()
        result_id = new_id()
        self.store.enqueue_event(
            event_id=event_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        self.store.record_command_result(
            result_id=result_id,
            command_id=new_id(),
            origin_node_id=EDGE_ID,
            status="succeeded",
            occurred_at="2026-07-23T02:14:59Z",
        )
        self.store.set_sync_cursor("cursor-1")
        request_id = new_id()

        batch = build_sync_request(
            self.store,
            node_id=EDGE_ID,
            request_id=request_id,
            sent_at=SENT_AT,
            health={
                "status": "ok",
                "software_version": "0.1.0",
                "hardware_profile_id": "egw-cm4-cellular-r1",
                "mqtt_connected": True,
                "storage_total_bytes": 32_000_000_000,
                "storage_free_bytes": 24_000_000_000,
                "capabilities": ["cellular", "mqtt", "wifi_ap"],
            },
        )

        self.assertEqual(batch.event_ids, (event_id,))
        self.assertEqual(batch.command_result_ids, (result_id,))
        self.assertEqual(batch.document["request_id"], request_id)
        self.assertEqual(batch.document["node_type"], "edge_gateway")
        self.assertEqual(batch.document["cursor"], "cursor-1")
        self.assertEqual(batch.document["health"]["outbox_depth"], 2)
        self.assertEqual(batch.document["sent_at"], "2026-07-23T02:15:00.000Z")
        self._assert_schema_valid(batch.document)

    def test_rejects_unknown_inconsistent_and_non_json_health(self):
        baseline = {
            "status": "ok",
            "software_version": "0.1.0",
            "mqtt_connected": True,
            "storage_total_bytes": 10,
            "storage_free_bytes": 5,
            "capabilities": ["mqtt"],
        }
        invalid_values = (
            {**baseline, "tenant_id": "must-not-be-sent"},
            {**baseline, "storage_free_bytes": 11},
            {**baseline, "capabilities": ["mqtt", "mqtt"]},
            {**baseline, "details": {"invalid": float("nan")}},
        )
        for health in invalid_values:
            with self.subTest(health=health), self.assertRaises(ValueError):
                build_sync_request(self.store, node_id=EDGE_ID, health=health, sent_at=SENT_AT)

    def test_normalizes_registered_subtree_request_and_rejects_untrusted_origin(self):
        event_id = new_id()
        self.store.enqueue_event(
            event_id=event_id,
            origin_node_id=DESCENDANT_EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
            sequence=7,
        )
        batch = build_sync_request(
            self.store,
            node_id=LOCAL_HUB_ID,
            request_id=new_id(),
            sent_at=SENT_AT,
            health=self._health(),
        )

        normalized = normalize_sync_request(
            batch.document,
            authenticated_node_id=LOCAL_HUB_ID,
            allowed_origin_node_ids={LOCAL_HUB_ID, DESCENDANT_EDGE_ID},
        )

        self.assertEqual(normalized["events"][0]["origin_node_id"], DESCENDANT_EDGE_ID)
        self.assertEqual(normalized["events"][0]["sequence"], 7)
        with self.assertRaisesRegex(ValueError, "outside"):
            normalize_sync_request(batch.document, authenticated_node_id=LOCAL_HUB_ID)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            normalize_sync_request(
                {**batch.document, "tenant_id": "caller-must-not-route"},
                authenticated_node_id=LOCAL_HUB_ID,
                allowed_origin_node_ids={LOCAL_HUB_ID, DESCENDANT_EDGE_ID},
            )

    def test_local_hub_can_validate_descendant_targets_without_weakening_default(self):
        batch = build_sync_request(
            self.store,
            node_id=LOCAL_HUB_ID,
            request_id=new_id(),
            sent_at=SENT_AT,
            health=self._health(),
        )
        response = self._response(
            batch,
            desired_resources=[
                {
                    "resource_type": "device.runtime_config",
                    "resource_id": DEVICE_ID,
                    "target_node_id": DESCENDANT_EDGE_ID,
                    "revision": 1,
                    "operation": "upsert",
                    "content_sha256": content_hash({"moisture_threshold": 42}),
                    "updated_at": "2026-07-23T02:14:00Z",
                    "payload": {"moisture_threshold": 42},
                }
            ],
            commands=[
                {
                    "command_id": new_id(),
                    "idempotency_key": "route-descendant-1",
                    "command_type": "device.runtime_config_push",
                    "target_node_id": DESCENDANT_EDGE_ID,
                    "device_id": DEVICE_ID,
                    "issued_at": "2026-07-23T02:15:00Z",
                    "expires_at": "2026-07-23T02:20:00Z",
                    "payload": {},
                }
            ],
        )

        normalized = normalize_sync_response(
            response,
            node_id=LOCAL_HUB_ID,
            batch=batch,
            allowed_target_node_ids={LOCAL_HUB_ID, DESCENDANT_EDGE_ID},
        )

        self.assertEqual(normalized["desired_resources"][0]["target_node_id"], DESCENDANT_EDGE_ID)
        self.assertEqual(normalized["commands"][0]["target_node_id"], DESCENDANT_EDGE_ID)
        with self.assertRaisesRegex(ValueError, "outside"):
            normalize_sync_response(response, node_id=LOCAL_HUB_ID, batch=batch)
        with self.assertRaisesRegex(ValueError, "outside"):
            normalize_sync_response(
                {
                    **response,
                    "commands": [
                        {
                            **response["commands"][0],
                            "target_node_id": OTHER_EDGE_ID,
                        }
                    ],
                },
                node_id=LOCAL_HUB_ID,
                batch=batch,
                allowed_target_node_ids={LOCAL_HUB_ID, DESCENDANT_EDGE_ID},
            )

    def test_applies_correlated_response_and_only_acknowledges_named_items(self):
        first_event_id = new_id()
        second_event_id = new_id()
        for event_id, value in ((first_event_id, 1), (second_event_id, 2)):
            self.store.enqueue_event(
                event_id=event_id,
                origin_node_id=EDGE_ID,
                event_type="device.status",
                occurred_at="2026-07-23T02:14:58Z",
                device_id=DEVICE_ID,
                payload={"value": value},
            )
        batch = build_sync_request(
            self.store,
            node_id=EDGE_ID,
            request_id=new_id(),
            sent_at=SENT_AT,
            event_limit=2,
            health=self._health(),
        )
        command_id = new_id()
        response = self._response(
            batch,
            ack_event_ids=[first_event_id],
            desired_resources=[
                {
                    "resource_type": "device.runtime_config",
                    "resource_id": DEVICE_ID,
                    "target_node_id": EDGE_ID,
                    "revision": 3,
                    "operation": "upsert",
                    "content_sha256": content_hash({"moisture_threshold": 42}),
                    "updated_at": "2026-07-23T02:14:00Z",
                    "payload": {"moisture_threshold": 42},
                }
            ],
            commands=[
                {
                    "command_id": command_id,
                    "idempotency_key": "operator-request-1",
                    "command_type": "device.runtime_config_push",
                    "target_node_id": EDGE_ID,
                    "device_id": DEVICE_ID,
                    "issued_at": "2026-07-23T02:15:00Z",
                    "expires_at": "2026-07-23T02:20:00Z",
                    "payload": {},
                }
            ],
        )

        applied = apply_sync_response(self.store, node_id=EDGE_ID, batch=batch, response=response, now=SENT_AT)

        self.assertEqual(applied.acknowledged_event_count, 1)
        self.assertEqual([event.event_id for event in self.store.pending_events()], [second_event_id])
        self.assertEqual(self.store.get_sync_cursor(), "cursor-2")
        self.assertEqual(self.store.get_desired_resource("device.runtime_config", DEVICE_ID).revision, 3)
        self.assertEqual([command.command_id for command in applied.commands], [command_id])
        self.assertEqual([command.command_id for command in self.store.pending_commands(now=SENT_AT)], [command_id])
        self.assertEqual(applied.next_poll_seconds, 15)

        replayed = apply_sync_response(self.store, node_id=EDGE_ID, batch=batch, response=response, now=SENT_AT)
        self.assertEqual(replayed.acknowledged_event_count, 0)
        self.assertEqual(replayed.desired_results[0].status, "unchanged")
        self.assertEqual([command.command_id for command in replayed.commands], [command_id])

    def test_rejects_untrusted_routing_and_acknowledgements_before_mutation(self):
        event_id = new_id()
        self.store.enqueue_event(
            event_id=event_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        batch = build_sync_request(
            self.store,
            node_id=EDGE_ID,
            request_id=new_id(),
            sent_at=SENT_AT,
            health=self._health(),
        )
        baseline = self._response(batch, ack_event_ids=[event_id])
        invalid_responses = (
            {**baseline, "correlation_request_id": new_id()},
            {**baseline, "ack_event_ids": [new_id()]},
            {
                **baseline,
                "desired_resources": [
                    {
                        "resource_type": "device.runtime_config",
                        "resource_id": DEVICE_ID,
                        "target_node_id": "INAEG-223e4567-e89b-42d3-a456-426614174001",
                        "revision": 1,
                        "operation": "upsert",
                        "content_sha256": content_hash({}),
                        "updated_at": "2026-07-23T02:14:00Z",
                        "payload": {},
                    }
                ],
            },
            {**baseline, "tenant_id": "must-not-be-accepted"},
        )

        for response in invalid_responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                apply_sync_response(self.store, node_id=EDGE_ID, batch=batch, response=response, now=SENT_AT)
            self.assertEqual([event.event_id for event in self.store.pending_events()], [event_id])
            self.assertIsNone(self.store.get_sync_cursor())

    def _health(self):
        return {
            "status": "ok",
            "software_version": "0.1.0",
            "mqtt_connected": True,
            "storage_total_bytes": 10,
            "storage_free_bytes": 5,
            "capabilities": ["mqtt"],
        }

    def _response(self, batch, **overrides):
        return {
            "protocol_version": "1.0",
            "correlation_request_id": batch.document["request_id"],
            "server_time": "2026-07-23T02:15:01Z",
            "next_cursor": "cursor-2",
            "ack_event_ids": [],
            "ack_command_result_ids": [],
            "desired_resources": [],
            "commands": [],
            "next_poll_seconds": 15,
            **overrides,
        }

    def _assert_schema_valid(self, document):
        contract_dir = Path(__file__).resolve().parents[2] / "contracts" / "sync" / "v1"
        schema = json.loads((contract_dir / "sync.schema.json").read_text(encoding="utf-8"))
        wrapper = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/syncRequest",
        }
        validator = Draft202012Validator(wrapper, format_checker=FormatChecker())
        self.assertEqual(list(validator.iter_errors(document)), [])


if __name__ == "__main__":
    unittest.main()
