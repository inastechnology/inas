from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "create_release_module.py"
SPEC = importlib.util.spec_from_file_location("create_release_module", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CreateReleaseModuleTest(unittest.TestCase):
    def test_builds_self_contained_deterministic_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_dir = root / "build"
            build_dir.mkdir()
            for name in ("bootloader.bin", "partitions.bin", "firmware.bin"):
                (build_dir / name).write_bytes(name.encode("ascii"))
            boot_app0 = root / "boot_app0.bin"
            boot_app0.write_bytes(b"ota")
            filesystem = root / "littlefs.bin"
            filesystem.write_bytes(b"filesystem")
            profile = root / "diagnostic-profile.json"
            profile.write_text(
                json.dumps({"id": "test-device"}),
                encoding="utf-8",
            )
            output = root / "test-device-1.0.0.zip"

            first_checksum = MODULE.build_release_module(
                build_dir=build_dir,
                boot_app0=boot_app0,
                output=output,
                module_id="test-device",
                device_kind="TST",
                display_name="Test Device",
                firmware_version="1.0.0",
                target="seeed_xiao_esp32s3",
                chip="esp32s3",
                flash_size="8MB",
                filesystem=filesystem,
                diagnostic_profile=profile,
            )
            second_checksum = MODULE.build_release_module(
                build_dir=build_dir,
                boot_app0=boot_app0,
                output=output,
                module_id="test-device",
                device_kind="TST",
                display_name="Test Device",
                firmware_version="1.0.0",
                target="seeed_xiao_esp32s3",
                chip="esp32s3",
                flash_size="8MB",
                filesystem=filesystem,
                diagnostic_profile=profile,
            )
            self.assertEqual(first_checksum, second_checksum)

            with zipfile.ZipFile(output) as archive:
                root_name = output.stem
                manifest = json.loads(
                    archive.read(f"{root_name}/release-module.json")
                )
                self.assertEqual(
                    manifest["module_type"],
                    "inas-device-firmware",
                )
                self.assertEqual(
                    manifest["diagnostic_profile_id"],
                    "test-device",
                )
                self.assertFalse(
                    next(
                        region
                        for region in manifest["regions"]
                        if region["id"] == "storage"
                    )["default_enabled"]
                )
                self.assertIn(
                    f"{root_name}/bootloader.bin",
                    archive.namelist(),
                )
                self.assertIn(
                    f"{root_name}/firmware.bin",
                    archive.namelist(),
                )


if __name__ == "__main__":
    unittest.main()
