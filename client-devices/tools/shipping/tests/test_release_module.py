from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from shipping_tool.domain.release_module import (
    ReleaseModuleError,
    load_release_module,
)


class ReleaseModuleTest(unittest.TestCase):
    def create_module(
        self,
        directory: Path,
        *,
        firmware_checksum: str | None = None,
    ) -> Path:
        files = {
            "bootloader.bin": b"boot",
            "firmware.bin": b"firmware",
        }
        checksums = {
            name: hashlib.sha256(content).hexdigest()
            for name, content in files.items()
        }
        if firmware_checksum is not None:
            checksums["firmware.bin"] = firmware_checksum
        manifest = {
            "schema_version": 1,
            "module_type": "inas-device-firmware",
            "module_id": "test-device",
            "device_kind": "TST",
            "display_name": "Test Device",
            "firmware_version": "1.2.3",
            "target": "seeed_xiao_esp32s3",
            "name": "Test Device 1.2.3",
            "chip": "esp32s3",
            "flash_size": "8MB",
            "regions": [
                {
                    "id": "bootloader",
                    "label": "Bootloader",
                    "address": "0x0",
                    "max_size": "0x8000",
                    "required": True,
                    "file": "bootloader.bin",
                },
                {
                    "id": "app0",
                    "label": "Application",
                    "address": "0x10000",
                    "max_size": "0x330000",
                    "required": True,
                    "file": "firmware.bin",
                },
            ],
            "checksums": checksums,
        }
        output = directory / "test-release.zip"
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "test-release/release-module.json",
                json.dumps(manifest),
            )
            for name, content in files.items():
                archive.writestr(f"test-release/{name}", content)
        return output

    def test_loads_layout_and_verified_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self.create_module(Path(temporary))
            module = load_release_module(archive)
            try:
                self.assertEqual(module.module_id, "test-device")
                self.assertEqual(module.firmware_version, "1.2.3")
                self.assertEqual(module.layout.chip, "esp32s3")
                self.assertEqual(
                    module.files_by_region["app0"].read_bytes(),
                    b"firmware",
                )
            finally:
                module.close()

    def test_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self.create_module(
                Path(temporary),
                firmware_checksum="0" * 64,
            )
            with self.assertRaisesRegex(ReleaseModuleError, "SHA-256 mismatch"):
                load_release_module(archive)

    def test_rejects_path_traversal_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self.create_module(Path(temporary))
            with zipfile.ZipFile(archive, "a") as output:
                output.writestr("../outside.bin", b"unsafe")
            with self.assertRaisesRegex(ReleaseModuleError, "Unsafe ZIP member"):
                load_release_module(archive)


if __name__ == "__main__":
    unittest.main()
