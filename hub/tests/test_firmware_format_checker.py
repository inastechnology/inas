import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ina_device_hub.firmware_format_checker import check_firmware_file, main
from ina_device_hub.firmware_manifest import FirmwareManifestValidationError


class FirmwareFormatCheckerTest(unittest.TestCase):
    def test_check_firmware_file_returns_embedded_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            firmware_path = Path(tmp_dir) / "firmware.bin"
            firmware_path.write_bytes(_firmware_binary(device_kind="WTR", version="1.1.0"))

            manifest = check_firmware_file(firmware_path)

        self.assertEqual(manifest["device_kind"], "WTR")
        self.assertEqual(manifest["version"], "1.1.0")
        self.assertEqual(manifest["build_id"], "2026-07-01T00:00:00Z+abcdef0")

    def test_check_firmware_file_rejects_binary_without_manifest_marker(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            firmware_path = Path(tmp_dir) / "firmware.bin"
            firmware_path.write_bytes(b"\xe9ESP32BIN\x00firmware-body")

            with self.assertRaisesRegex(FirmwareManifestValidationError, "firmware manifest marker not found"):
                check_firmware_file(firmware_path)

    def test_main_returns_success_and_prints_json_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            firmware_path = Path(tmp_dir) / "firmware.bin"
            firmware_path.write_bytes(_firmware_binary(device_kind="WTR", version="1.2.0"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                rc = main(["--json", str(firmware_path)])

        self.assertEqual(rc, 0)
        manifest = json.loads(stdout.getvalue())
        self.assertEqual(manifest["device_kind"], "WTR")
        self.assertEqual(manifest["version"], "1.2.0")

    def test_main_returns_failure_when_manifest_marker_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            firmware_path = Path(tmp_dir) / "firmware.bin"
            firmware_path.write_bytes(b"firmware-body")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                rc = main([str(firmware_path)])

        self.assertEqual(rc, 1)
        self.assertIn("NG: firmware manifest marker not found", stdout.getvalue())


def _firmware_binary(
    *,
    device_kind: str,
    version: str,
    build_id: str = "2026-07-01T00:00:00Z+abcdef0",
    project: str = "watering-device",
    target: str = "seeed_xiao_esp32s3",
    framework: str = "arduino",
):
    manifest = (
        "INAS_FW_MANIFEST_V1_BEGIN\n"
        "schema=1\n"
        f"project={project}\n"
        f"device_kind={device_kind}\n"
        f"version={version}\n"
        f"build_id={build_id}\n"
        f"target={target}\n"
        f"framework={framework}\n"
        "INAS_FW_MANIFEST_V1_END\n"
    ).encode("ascii")
    return b"\xe9ESP32BIN" + manifest + b"\x00firmware-body"
