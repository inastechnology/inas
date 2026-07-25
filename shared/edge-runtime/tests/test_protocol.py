import math
import unittest
from datetime import UTC, datetime

from ina_edge_runtime.protocol import canonical_json, content_hash, format_timestamp, normalize_timestamp


class ProtocolUtilityTest(unittest.TestCase):
    def test_normalizes_timestamp_to_utc_milliseconds(self):
        self.assertEqual(normalize_timestamp("2026-07-23T11:00:00+09:00", field_name="timestamp"), "2026-07-23T02:00:00.000Z")
        self.assertEqual(format_timestamp(datetime(2026, 7, 23, 2, 0, tzinfo=UTC)), "2026-07-23T02:00:00.000Z")

    def test_canonical_json_is_stable_and_rejects_non_finite_numbers(self):
        self.assertEqual(canonical_json({"b": 2, "a": "日本"}), '{"a":"日本","b":2}')
        self.assertEqual(content_hash({"b": 2, "a": 1}), content_hash({"a": 1, "b": 2}))
        with self.assertRaises(ValueError):
            canonical_json({"invalid": math.nan})


if __name__ == "__main__":
    unittest.main()
