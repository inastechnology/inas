import tempfile
import threading
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ina_edge_runtime.protocol import content_hash
from ina_edge_runtime.store import CommandConflictError, CommandExpiredError, CommandStateError, EdgeStore, EventConflictError, RevisionConflictError

EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174001"
CHILD_EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174003"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"
NOW = datetime(2026, 7, 23, 2, 15, tzinfo=UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class EdgeStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "edge.db"
        self.store = EdgeStore(self.database_path)

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_outbox_is_durable_ordered_idempotent_and_partially_acknowledged(self):
        first_id = new_id()
        second_id = new_id()
        first = self.store.enqueue_event(
            event_id=first_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        duplicate = self.store.enqueue_event(
            event_id=first_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        second = self.store.enqueue_event(
            event_id=second_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:59Z",
            device_id=DEVICE_ID,
            payload={"value": 2},
        )

        self.assertEqual(first, duplicate)
        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(self.store.outbox_depth(), 2)
        self.store.close()
        self.store = EdgeStore(self.database_path)
        self.assertEqual([event.event_id for event in self.store.pending_events()], [first_id, second_id])

        self.assertEqual(self.store.ack_events([first_id]), 1)
        self.assertEqual([event.event_id for event in self.store.pending_events()], [second_id])
        self.assertEqual(self.store.ack_events([first_id]), 0)

    def test_store_serializes_access_from_mqtt_and_sync_threads(self):
        failures = []

        def enqueue(index):
            try:
                self.store.enqueue_event(
                    event_id=new_id(),
                    origin_node_id=EDGE_ID,
                    event_type="device.status",
                    occurred_at="2026-07-23T02:14:58Z",
                    payload={"index": index},
                )
            except Exception as exc:  # pragma: no cover - assertion captures worker failures
                failures.append(exc)

        workers = [threading.Thread(target=enqueue, args=(index,)) for index in range(20)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        self.assertEqual(failures, [])
        events = self.store.pending_events()
        self.assertEqual(len(events), 20)
        self.assertEqual([event.sequence for event in events], list(range(1, 21)))

    def test_event_id_and_forwarded_origin_sequence_conflicts_fail_closed(self):
        event_id = new_id()
        self.store.enqueue_event(
            event_id=event_id,
            origin_node_id=CHILD_EDGE_ID,
            sequence=42,
            event_type="gateway.health",
            occurred_at="2026-07-23T02:14:58Z",
            payload={"status": "ok"},
        )
        next_event = self.store.enqueue_event(
            event_id=new_id(),
            origin_node_id=CHILD_EDGE_ID,
            event_type="gateway.health",
            occurred_at="2026-07-23T02:14:59Z",
            payload={"status": "ok"},
        )
        self.assertEqual(next_event.sequence, 43)

        with self.assertRaises(EventConflictError):
            self.store.enqueue_event(
                event_id=event_id,
                origin_node_id=CHILD_EDGE_ID,
                sequence=42,
                event_type="gateway.health",
                occurred_at="2026-07-23T02:14:58Z",
                payload={"status": "critical"},
            )

        with self.assertRaises(EventConflictError):
            self.store.enqueue_event(
                event_id=new_id(),
                origin_node_id=CHILD_EDGE_ID,
                sequence=42,
                event_type="gateway.health",
                occurred_at="2026-07-23T02:15:00Z",
                payload={"status": "ok"},
            )

    def test_desired_resource_uses_monotonic_revision_and_detects_split_brain(self):
        payload = {"moisture_threshold": 42}
        first = self.store.apply_desired_resource(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=EDGE_ID,
            revision=3,
            operation="upsert",
            content_sha256=content_hash(payload),
            updated_at="2026-07-23T02:14:00Z",
            payload=payload,
        )
        self.assertEqual(first.status, "applied")
        same = self.store.apply_desired_resource(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=EDGE_ID,
            revision=3,
            operation="upsert",
            content_sha256=content_hash(payload),
            updated_at="2026-07-23T02:14:00Z",
            payload=payload,
        )
        self.assertEqual(same.status, "unchanged")
        stale = self.store.apply_desired_resource(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=EDGE_ID,
            revision=2,
            operation="upsert",
            content_sha256=content_hash({"moisture_threshold": 30}),
            updated_at="2026-07-23T02:13:00Z",
            payload={"moisture_threshold": 30},
        )
        self.assertEqual(stale.status, "stale")
        self.assertEqual(stale.resource.revision, 3)

        with self.assertRaises(RevisionConflictError):
            self.store.apply_desired_resource(
                resource_type="device.runtime_config",
                resource_id=DEVICE_ID,
                target_node_id=EDGE_ID,
                revision=3,
                operation="upsert",
                content_sha256=content_hash({"moisture_threshold": 99}),
                updated_at="2026-07-23T02:14:00Z",
                payload={"moisture_threshold": 99},
            )

        newer = self.store.apply_desired_resource(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=EDGE_ID,
            revision=4,
            operation="upsert",
            content_sha256=content_hash({"moisture_threshold": 43}),
            updated_at="2026-07-23T02:16:00Z",
            payload={"moisture_threshold": 43},
        )
        self.assertEqual(newer.status, "applied")
        self.assertEqual(self.store.get_desired_resource("device.runtime_config", DEVICE_ID).revision, 4)

    def test_commands_are_deduplicated_expired_and_transitioned_safely(self):
        command_id = new_id()
        values = {
            "command_id": command_id,
            "idempotency_key": "operator-request-1",
            "command_type": "device.action",
            "target_node_id": EDGE_ID,
            "device_id": DEVICE_ID,
            "issued_at": "2026-07-23T02:15:00Z",
            "expires_at": "2026-07-23T02:20:00Z",
            "payload": {"action": "water", "duration_sec": 5},
        }
        command = self.store.receive_command(**values, now=NOW)
        duplicate = self.store.receive_command(**values, now=NOW)
        self.assertEqual(command, duplicate)
        self.assertEqual([item.command_id for item in self.store.pending_commands(now=NOW)], [command_id])

        accepted = self.store.set_command_status(command_id, "accepted", now=NOW)
        self.assertEqual(accepted.status, "accepted")
        self.store.close()
        self.store = EdgeStore(self.database_path)
        self.assertEqual([item.command_id for item in self.store.pending_commands(now=NOW)], [command_id])
        succeeded = self.store.set_command_status(command_id, "succeeded", now=NOW + timedelta(seconds=1))
        self.assertEqual(succeeded.status, "succeeded")
        with self.assertRaises(CommandStateError):
            self.store.set_command_status(command_id, "running", now=NOW + timedelta(seconds=2))

        with self.assertRaises(CommandConflictError):
            self.store.receive_command(**{**values, "command_id": new_id()}, now=NOW)

        expired_id = new_id()
        expired = self.store.receive_command(
            command_id=expired_id,
            idempotency_key="expired-command",
            command_type="device.action",
            target_node_id=EDGE_ID,
            issued_at="2026-07-23T02:00:00Z",
            expires_at="2026-07-23T02:01:00Z",
            payload={"action": "water"},
            now=NOW,
        )
        self.assertEqual(expired.status, "expired")
        self.assertNotIn(expired_id, [item.command_id for item in self.store.pending_commands(now=NOW)])

    def test_command_cannot_be_activated_at_or_after_expiry(self):
        values = {
            "command_id": new_id(),
            "idempotency_key": "activation-expiry-guard",
            "command_type": "device.action",
            "target_node_id": EDGE_ID,
            "device_id": DEVICE_ID,
            "issued_at": "2026-07-23T02:15:00Z",
            "expires_at": "2026-07-23T02:20:00Z",
            "payload": {"action": "water"},
        }
        self.store.receive_command(**values, now=NOW)

        with self.assertRaises(CommandExpiredError) as raised:
            self.store.set_command_status(values["command_id"], "accepted", now=NOW + timedelta(minutes=5))

        self.assertEqual(raised.exception.command.status, "expired")
        self.assertEqual(self.store.get_command(values["command_id"]).status, "expired")

    def test_desired_resource_ids_must_match_their_entity_type(self):
        with self.assertRaises(ValueError):
            self.store.apply_desired_resource(
                resource_type="device.runtime_config",
                resource_id=EDGE_ID,
                target_node_id=EDGE_ID,
                revision=1,
                operation="upsert",
                content_sha256=content_hash({}),
                updated_at="2026-07-23T02:14:00Z",
                payload={},
            )
        with self.assertRaises(ValueError):
            self.store.apply_desired_resource(
                resource_type="node.policy",
                resource_id=CHILD_EDGE_ID,
                target_node_id=EDGE_ID,
                revision=1,
                operation="upsert",
                content_sha256=content_hash({}),
                updated_at="2026-07-23T02:14:00Z",
                payload={},
            )

    def test_command_result_and_cursor_survive_restart_until_acknowledged(self):
        result_id = new_id()
        command_id = new_id()
        result = self.store.record_command_result(
            result_id=result_id,
            command_id=command_id,
            origin_node_id=EDGE_ID,
            status="succeeded",
            occurred_at="2026-07-23T02:15:01Z",
            payload={"mqtt_rc": 0},
        )
        duplicate = self.store.record_command_result(
            result_id=result_id,
            command_id=command_id,
            origin_node_id=EDGE_ID,
            status="succeeded",
            occurred_at="2026-07-23T02:15:01Z",
            payload={"mqtt_rc": 0},
        )
        self.assertEqual(result, duplicate)
        self.store.set_sync_cursor("cursor-1")

        self.store.close()
        self.store = EdgeStore(self.database_path)
        self.assertEqual(self.store.get_sync_cursor(), "cursor-1")
        self.assertEqual([item.result_id for item in self.store.pending_command_results()], [result_id])
        self.assertEqual(self.store.ack_command_results([result_id]), 1)
        self.assertEqual(self.store.pending_command_results(), [])

    def test_command_completion_and_terminal_result_are_atomic_and_idempotent(self):
        command_id = new_id()
        self.store.receive_command(
            command_id=command_id,
            idempotency_key="complete-once",
            command_type="device.runtime_config_push",
            target_node_id=EDGE_ID,
            device_id=DEVICE_ID,
            issued_at="2026-07-23T02:15:00Z",
            expires_at="2026-07-23T02:20:00Z",
            payload={},
            now=NOW,
        )
        self.store.set_command_status(command_id, "accepted", now=NOW)
        self.store.set_command_status(command_id, "running", now=NOW)
        self.assertEqual([command.command_id for command in self.store.commands_with_status(["running"])], [command_id])

        first = self.store.complete_command(
            command_id,
            "succeeded",
            origin_node_id=EDGE_ID,
            payload={"mqtt_rc": 0},
            now=NOW,
        )
        duplicate = self.store.complete_command(
            command_id,
            "succeeded",
            origin_node_id=EDGE_ID,
            payload={"ignored_on_idempotent_retry": True},
            now=NOW + timedelta(seconds=1),
        )

        self.assertEqual(first.result_id, duplicate.result_id)
        self.assertEqual(self.store.get_command(command_id).status, "succeeded")
        self.assertEqual(len(self.store.pending_command_results()), 1)
        self.assertEqual(self.store.ack_command_results([first.result_id]), 1)

        after_ack = self.store.complete_command(
            command_id,
            "succeeded",
            origin_node_id=EDGE_ID,
            now=NOW + timedelta(seconds=2),
        )
        self.assertEqual(after_ack.result_id, first.result_id)
        self.assertEqual(self.store.pending_command_results(), [])


if __name__ == "__main__":
    unittest.main()
