import unittest
import uuid

from ina_edge_runtime.identity import IdentityValidationError, NodeType, generate_node_id, parse_node_id, validate_device_id, validate_uuid_v4

EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174001"
LOCAL_HUB_ID = "INALH-123e4567-e89b-42d3-a456-426614174002"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


class IdentityTest(unittest.TestCase):
    def test_generates_offline_uuid_v4_node_ids(self):
        edge_id = generate_node_id(NodeType.EDGE_GATEWAY)
        local_hub_id = generate_node_id("local_hub")

        self.assertEqual(parse_node_id(edge_id).node_type, NodeType.EDGE_GATEWAY)
        self.assertEqual(parse_node_id(local_hub_id).node_type, NodeType.LOCAL_HUB)
        self.assertEqual(parse_node_id(edge_id).unique_id.version, 4)

    def test_parses_canonical_node_identity(self):
        parsed = parse_node_id(EDGE_ID)

        self.assertEqual(parsed.value, EDGE_ID)
        self.assertEqual(parsed.node_type, NodeType.EDGE_GATEWAY)
        self.assertEqual(str(parsed.unique_id), EDGE_ID.removeprefix("INAEG-"))

    def test_rejects_wrong_prefix_non_v4_and_noncanonical_uuid(self):
        invalid_values = (
            "INAGW-123e4567-e89b-42d3-a456-426614174001",
            "INAEG-123e4567-e89b-12d3-a456-426614174001",
            "INAEG-123E4567-E89B-42D3-A456-426614174001",
            "INAEG-not-a-uuid",
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(IdentityValidationError):
                parse_node_id(value)

    def test_preserves_existing_device_namespace_and_isolates_demo_ids(self):
        self.assertEqual(validate_device_id(DEVICE_ID), DEVICE_ID)
        with self.assertRaises(IdentityValidationError):
            validate_device_id("INADS-DEMO-WTR-001")
        self.assertEqual(validate_device_id("INADS-DEMO-WTR-001", allow_demo=True), "INADS-DEMO-WTR-001")

    def test_uuid_validator_rejects_uuid_object_and_uuid_v1(self):
        with self.assertRaises(IdentityValidationError):
            validate_uuid_v4(uuid.uuid4())
        with self.assertRaises(IdentityValidationError):
            validate_uuid_v4(str(uuid.uuid1()))


if __name__ == "__main__":
    unittest.main()
