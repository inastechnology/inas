import copy
import os
import tempfile
import unittest
from datetime import UTC, datetime

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

from ina_device_hub.device_definition_registry import (
    get_device_definition,
    list_device_definitions,
    project_runtime_config,
)
from ina_device_hub.web_server import _build_device_operational_metrics, _build_device_output_settings, _build_scheduled_operation_state


class DeviceDefinitionRegistryTest(unittest.TestCase):
    def test_all_firmware_projects_are_registered(self):
        definitions = {item["device"]["kind"]: item for item in list_device_definitions()}
        self.assertEqual(set(definitions), {"WTR", "WRS", "ENV", "SOI", "FGT"})
        for kind, definition in definitions.items():
            self.assertEqual(definition["schema_version"], 1, kind)
            self.assertTrue(definition["runtime_config"]["send_keys"], kind)
            self.assertEqual(definition["status"]["metrics"], definition["sensor_slots"], kind)

    def test_runtime_projection_preserves_database_source(self):
        stored = {
            "ntp_server": "pool.ntp.org",
            "timezone_offset_sec": 32400,
            "sleep_sec": 300,
            "ota_check_interval_sec": 21600,
            "soil_calibration": {"calibrated": True},
            "env_sensors": {"par": {"enabled": True}},
            "legacy_value": {"must": "remain"},
        }
        before = copy.deepcopy(stored)

        payload = project_runtime_config("SOI", stored)

        self.assertEqual(stored, before)
        self.assertEqual(
            payload,
            {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "sleep_sec": 300,
                "ota_check_interval_sec": 21600,
                "soil_calibration": {"calibrated": True},
            },
        )

    def test_fgt_outputs_are_fixed_and_named_by_farming_role(self):
        definition = get_device_definition("FGT")
        outputs = _build_device_output_settings("FGT", {}, {"assignments": []})["outputs"]

        self.assertEqual(len(outputs), 5)
        self.assertTrue(all(output["fixed"] for output in outputs))
        self.assertTrue(all(not output["assignable"] for output in outputs))
        self.assertEqual(
            [output["name"] for output in outputs],
            ["水を入れる", "A液を量る", "B液を量る", "タンクを混ぜる", "植物へ送る"],
        )
        self.assertEqual(len(definition["output_slots"]), 5)

    def test_fgt_timed_output_fields_use_seconds_and_1800_second_limit(self):
        definition = get_device_definition("FGT")
        fields = {field["path"]: field for field in definition["ui"]["configuration_fields"]}

        self.assertNotIn("fgt.enabled", fields)
        self.assertNotIn("fgt.recipe.nutrient_a_ml", fields)
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.on_sec"]["unit"], "秒")
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.on_sec"]["min"], 1)
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.on_sec"]["max"], 1800)
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.repeat_count"]["min"], 1)
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.repeat_count"]["max"], 99)
        self.assertEqual(fields["fgt.timed_outputs.nutrient_a.repeat_count"]["output_id"], "nutrient_a")
        self.assertEqual(fields["sleep_sec"]["max"], 86400)

    def test_fgt_runtime_projection_always_enables_scheduled_operation(self):
        stored = {
            "fgt": {
                "enabled": False,
                "timed_outputs": {"enabled": True},
                "sensors": {"soil": {"modbus_slave_id": 2, "modbus_function": 4, "start_register": 10}},
            },
            "schedules": [{"enabled": True, "hour": 6, "minute": 30}],
        }

        payload = project_runtime_config("FGT", stored)

        self.assertIs(payload["fgt"]["enabled"], True)
        self.assertEqual(
            payload["fgt"]["sensors"]["soil"],
            {"modbus_slave_id": 1, "modbus_function": 3, "start_register": 0},
        )
        self.assertIs(stored["fgt"]["enabled"], False)
        self.assertEqual(stored["fgt"]["sensors"]["soil"]["modbus_slave_id"], 2)

    def test_fgt_declares_only_supported_three_in_one_soil_metrics(self):
        definition = get_device_definition("FGT")
        metric_ids = {item["id"] for item in definition["status"]["metrics"]}

        self.assertTrue({"soil_moisture", "soil_temperature", "soil_ec"} <= metric_ids)
        self.assertTrue({"soil_ph", "soil_n", "soil_p", "soil_k"}.isdisjoint(metric_ids))

    def test_fgt_scheduled_operation_warns_when_irrigation_output_is_zero(self):
        definition = get_device_definition("FGT")
        config = {
            "fgt": {
                "enabled": False,
                "timed_outputs": {
                    "enabled": True,
                    "irrigation": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
                },
            },
            "schedules": [{"enabled": True, "hour": 6, "minute": 30}],
        }

        state = _build_scheduled_operation_state(definition, config)

        self.assertTrue(state["enabled"])
        self.assertFalse(state["ready"])
        self.assertEqual(state["value"], "設定不足")
        self.assertIn("irrigation", state["missing_output_ids"])
        self.assertIn("A液ポンプなどは設定どおり動作", state["warning"])
        self.assertIn("予約時刻に植物へ送水されません", state["warning"])
        self.assertFalse(state["enable_control_available"])

    def test_fgt_output_cards_distinguish_programmed_and_zero_second_outputs(self):
        config = {
            "fgt": {
                "timed_outputs": {
                    "enabled": True,
                    "water_inlet": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
                    "nutrient_a": {"on_sec": 120, "off_sec": 0, "repeat_count": 1},
                    "nutrient_b": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
                    "mixer": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
                    "irrigation": {"on_sec": 0, "off_sec": 0, "repeat_count": 0},
                }
            }
        }

        outputs = {output["switch_id"]: output for output in _build_device_output_settings("FGT", config, {"assignments": []})["outputs"]}

        self.assertTrue(outputs["nutrient_a"]["enabled"])
        self.assertEqual(outputs["nutrient_a"]["program_summary"], "120秒 × 1回")
        self.assertFalse(outputs["irrigation"]["enabled"])
        self.assertEqual(outputs["irrigation"]["program_summary"], "動作しません")

    def test_supported_but_missing_metrics_remain_visible(self):
        config = {"env_sensors": {"soil": {"enabled": False}, "par": {"enabled": True}}}
        metrics = _build_device_operational_metrics(
            {"device_kind": "ENV", "state": "active"},
            {"device_kind": "ENV", "par_umol_m2_s": 820},
            config,
            datetime.now(UTC),
            {"label": "未取得", "class": "muted"},
        )
        by_label = {item["label"]: item for item in metrics}

        self.assertEqual(by_label["土壌水分"]["value"], "未接続")
        self.assertEqual(by_label["気温"]["value"], "未取得")
        self.assertEqual(by_label["光合成に使える光"]["value"], "820 µmol/m²/s")


if __name__ == "__main__":
    unittest.main()
