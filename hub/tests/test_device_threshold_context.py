import copy
import unittest

from ina_device_hub.device_definition_registry import get_device_definition
from ina_device_hub.device_threshold_context import build_threshold_contexts, validate_threshold_rules


class ThresholdContextTest(unittest.TestCase):
    def setUp(self):
        self.definition = get_device_definition("FGT")
        self.payload = {
            "rs485_registry_saved": True,
            "moisture_guard_source_supported": True,
            "rs485_devices": [
                {"type": "par", "name": "光", "enabled": True, "ok": True, "moisture_percent": 100},
                {"type": "soil", "name": "北", "location": "1番畝", "baud": 4800, "modbus_slave_id": 1, "enabled": True, "ok": True, "moisture_percent": 20.0},
                {"type": "soil", "name": "南", "location": "2番畝", "baud": 4800, "modbus_slave_id": 2, "enabled": True, "ok": True, "moisture_percent": 100.0},
                {"type": "soil", "name": "停止", "baud": 4800, "modbus_slave_id": 3, "enabled": False, "ok": True, "moisture_percent": 90.0},
            ],
        }

    def context(self, payload=None, statuses=None, config=None):
        return build_threshold_contexts(self.definition, self.payload if payload is None else payload, "2026-09-13T12:00:00Z", statuses or [], config)[0]

    def test_separate_sensors_and_all_enabled_average(self):
        options = {item["key"]: item for item in self.context()["options"]}
        self.assertEqual(options["first"]["percent"], 20)
        self.assertEqual(options["sensor:4800:2"]["percent"], 100)
        self.assertEqual(options["average"]["percent"], 60)
        self.assertEqual([member["name"] for member in options["average"]["members"]], ["北", "南"])
        self.assertIsNone(options["sensor:4800:3"]["percent"])

    def test_failed_sensor_never_substitutes_another_or_partial_average(self):
        for value in (None, float("nan"), float("inf"), -1, 101, True, "20"):
            with self.subTest(value=value):
                self.payload["rs485_devices"][1]["moisture_percent"] = value
                options = {item["key"]: item for item in self.context()["options"]}
                self.assertIsNone(options["first"]["percent"])
                self.assertIsNone(options["average"]["percent"])
                self.assertEqual(options["sensor:4800:2"]["percent"], 100)
        self.payload["rs485_devices"][1].update(moisture_percent=0, ok=False)
        self.assertIsNone(self.context()["options"][0]["percent"])

    def test_zero_is_a_valid_value_and_disabled_sensor_is_excluded(self):
        self.payload["rs485_devices"][1]["moisture_percent"] = 0
        self.assertEqual(self.context()["options"][0]["percent"], 0)
        self.payload["rs485_devices"][1]["enabled"] = False
        self.assertEqual(self.context()["options"][0]["percent"], 100)
        self.assertEqual(self.context()["options"][1]["percent"], 100)

    def test_missing_source_and_old_firmware_do_not_claim_confirmation(self):
        context = self.context({}, config={"fgt": {"moisture_guard": {"source": "sensor:9600:10"}}})
        self.assertFalse(context["supported"])
        self.assertIsNone(context["options"][-1]["percent"])
        self.assertEqual(context["options"][-1]["key"], "sensor:9600:10")
        self.assertEqual(context["options"][0]["members"], [])

    def test_runtime_sensor_fallback_is_only_used_without_saved_registry(self):
        payload = {
            "rs485_registry_saved": False,
            "soil_rs485_enabled": True,
            "soil_rs485_ok": True,
            "soil_rs485_modbus_slave_id": 1,
            "soil_moisture_percent": 45,
        }
        self.assertEqual(self.context(payload)["options"][0]["percent"], 45)
        payload["rs485_registry_saved"] = True
        self.assertIsNone(self.context(payload)["options"][0]["percent"])

    def test_previous_decision_keeps_its_source_value_and_threshold(self):
        previous = copy.deepcopy(self.payload)
        previous.update(
            moisture_guard_checked=True,
            moisture_guard_source="average",
            moisture_guard_sample_ok=False,
            moisture_guard_sample_percent=None,
            moisture_guard_threshold_percent=65,
            moisture_guard_result="allow_unavailable",
        )
        previous["rs485_devices"][1]["name"] = "以前の北側"
        context = self.context(statuses=[{"received_at": "2026-09-13T06:00:00Z", "payload": previous}])
        decision = context["last_decision"]
        self.assertEqual(decision["source"]["members"][0]["name"], "以前の北側")
        self.assertEqual(decision["threshold"], 65)
        self.assertIsNone(decision["value"])
        self.assertIn("読めない", decision["result"])

    def test_rejects_invalid_rule_definitions(self):
        validate_threshold_rules(self.definition["ui"])
        for change in ({"id": "../bad"}, {"threshold_path": "missing.field"}, {"script": "alert(1)"}, {"source_path": "fgt.enabled"}):
            ui = copy.deepcopy(self.definition["ui"])
            ui["threshold_rules"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_threshold_rules(ui)
