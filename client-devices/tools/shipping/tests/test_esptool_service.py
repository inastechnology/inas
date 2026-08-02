from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shipping_tool.domain.flash_layout import FlashLayout, FlashRegion, FlashSelection
from shipping_tool.services.esptool_service import EsptoolService


class EsptoolServiceTest(unittest.TestCase):
    def test_write_command_contains_only_selected_regions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            app = directory / "firmware.bin"
            app.write_bytes(b"app")
            storage = directory / "littlefs.bin"
            storage.write_bytes(b"fs")
            app_region = FlashRegion(
                "app", "App", 0x10000, 0x1000, False, False, (), "", False
            )
            storage_region = FlashRegion(
                "storage", "Storage", 0x670000, 0x1000, False, False, (), "", True
            )
            layout = FlashLayout(
                1, "test", "esp32s3", "8MB", (app_region, storage_region), directory
            )
            service = EsptoolService("python")
            command = service.build_write_command(
                layout,
                "COM44",
                460800,
                [FlashSelection(app_region, app)],
                erase_all=False,
            )
            self.assertIn("0x10000", command)
            self.assertNotIn("0x670000", command)
            self.assertNotIn(str(storage), command)

    def test_merged_image_is_written_at_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "flash_merged.bin"
            image.write_bytes(b"merged")
            region = FlashRegion(
                "merged", "Merged", 0, None, True, True, (), "", False
            )
            layout = FlashLayout(
                1, "merged", "esp32s3", "keep", (region,), Path(temporary)
            )
            command = EsptoolService("python").build_write_command(
                layout,
                "COM3",
                921600,
                [FlashSelection(region, image)],
                erase_all=False,
            )
            self.assertEqual(command[-2:], ["0x0", str(image)])


if __name__ == "__main__":
    unittest.main()
