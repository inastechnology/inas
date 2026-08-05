import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

from ina_device_hub import extension_registry
from ina_device_hub.extension_registry import build_device_detail_extensions, list_extensions

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_extension_registry.py"
SPEC = importlib.util.spec_from_file_location("build_extension_registry", SCRIPT_PATH)
build_extension_registry = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build_extension_registry)


class ExtensionRegistryTest(unittest.TestCase):
    def test_fgt_extension_is_registered_without_core_specific_code(self):
        extensions = list_extensions()

        self.assertEqual(
            [item["id"] for item in extensions],
            ["jp.inas.development.operation-check", "jp.inas.device.fgt-operation-guide"],
        )
        self.assertEqual(extensions[1]["source"], "extensions/fgt-operation-guide")

    def test_operation_check_extension_resolves_wtr_values_without_actions(self):
        contributions = build_device_detail_extensions(
            "WTR",
            device={"name": "デモ潅水機1"},
            status={"last_soil_moisture": 42, "watering_started": False},
            config={"moisture_threshold": 35},
        )

        self.assertEqual([item["id"] for item in contributions], ["jp.inas.development.operation-check"])
        self.assertEqual(contributions[0]["overview_cards"][0]["title"], "プラグインが動作しています")
        metrics = next(block for block in contributions[0]["tabs"][0]["blocks"] if block["type"] == "metric_grid")
        self.assertEqual(
            [item["display_value"] for item in metrics["items"]],
            ["デモ潅水機1", "42 %", "無効", "35 %"],
        )

    def test_device_detail_contributions_apply_only_to_declared_kind(self):
        fgt = build_device_detail_extensions(
            "FGT",
            config={
                "fgt": {
                    "timed_outputs": {
                        "nutrient_a": {
                            "on_sec": 120,
                            "off_sec": 30,
                            "repeat_count": 2,
                        }
                    }
                },
                "sleep_sec": 3600,
            },
        )

        self.assertEqual(len(fgt), 1)
        self.assertEqual(fgt[0]["tabs"][0]["label"], "時間指定運転")
        metrics = next(block for block in fgt[0]["tabs"][0]["blocks"] if block["type"] == "metric_grid")
        self.assertEqual(
            [item["display_value"] for item in metrics["items"]],
            ["120 秒", "30 秒", "2 回", "3600 秒"],
        )
        self.assertEqual([item["id"] for item in build_device_detail_extensions("WTR", config={})], ["jp.inas.development.operation-check"])

    def test_missing_extension_value_is_presented_as_unset(self):
        fgt = build_device_detail_extensions("FGT", config={})
        metrics = next(block for block in fgt[0]["tabs"][0]["blocks"] if block["type"] == "metric_grid")

        self.assertTrue(all(item["display_value"] == "未設定" for item in metrics["items"]))

    def test_build_rejects_executable_or_unknown_ui_blocks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            extension_root = Path(temporary_directory)
            manifest_directory = extension_root / "unsafe"
            manifest_directory.mkdir()
            (manifest_directory / "extension.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "jp.example.unsafe",
                        "name": "Unsafe",
                        "version": "1.0.0",
                        "description": "Unsafe test",
                        "compatibility": {"hub_extension_api": 1},
                        "ui": {
                            "device_detail": {
                                "device_kinds": ["FGT"],
                                "tabs": [
                                    {
                                        "id": "unsafe",
                                        "label": "Unsafe",
                                        "title": "Unsafe",
                                        "description": "Unsafe",
                                        "blocks": [{"type": "html", "title": "Unsafe", "html": "<script></script>"}],
                                    }
                                ],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(build_extension_registry, "EXTENSION_ROOT", extension_root):
                with self.assertRaisesRegex(ValueError, "unsupported UI block"):
                    build_extension_registry.build_registry()

    def test_runtime_merges_valid_installed_manifest_from_work_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "extensions" / "installed" / "com.example.runtime" / "1.0.0" / "extension.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "com.example.runtime",
                        "name": "Runtime guide",
                        "version": "1.0.0",
                        "description": "Installed at runtime",
                        "compatibility": {"hub_extension_api": 1},
                        "ui": {
                            "device_detail": {
                                "device_kinds": ["FGT"],
                                "overview_cards": [
                                    {
                                        "id": "runtime-guide",
                                        "type": "callout",
                                        "title": "Runtime",
                                        "description": "Visible after installation",
                                        "tone": "leaf",
                                    }
                                ],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            class FakeSetting:
                @staticmethod
                def get_work_dir():
                    return temporary_directory

            with patch.object(extension_registry, "setting", return_value=FakeSetting()):
                extension_registry.reload_extension_registry()
                extensions = extension_registry.list_extensions()
                contribution = extension_registry.build_device_detail_extensions("FGT")
            extension_registry.reload_extension_registry()

        self.assertEqual(
            [item["id"] for item in extensions],
            ["com.example.runtime", "jp.inas.development.operation-check", "jp.inas.device.fgt-operation-guide"],
        )
        self.assertTrue(any(item["id"] == "com.example.runtime" for item in contribution))


if __name__ == "__main__":
    unittest.main()
