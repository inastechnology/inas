from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shipping_tool.domain.flash_layout import FlashLayout, FlashSelection, LayoutError


class FlashLayoutTest(unittest.TestCase):
    def write_layout(self, directory: Path, regions: list[dict]) -> Path:
        path = directory / "layout.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "test",
                    "chip": "esp32s3",
                    "flash_size": "8MB",
                    "regions": regions,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_loads_hexadecimal_addresses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_layout(
                Path(temporary),
                [
                    {
                        "id": "app",
                        "label": "App",
                        "address": "0x10000",
                        "max_size": "0x20000",
                    }
                ],
            )
            layout = FlashLayout.load(path)
            self.assertEqual(layout.regions[0].address, 0x10000)
            self.assertEqual(layout.regions[0].max_size, 0x20000)

    def test_rejects_overlapping_regions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_layout(
                Path(temporary),
                [
                    {
                        "id": "first",
                        "label": "First",
                        "address": "0x0",
                        "max_size": "0x2000",
                    },
                    {
                        "id": "second",
                        "label": "Second",
                        "address": "0x1000",
                        "max_size": "0x1000",
                    },
                ],
            )
            with self.assertRaises(LayoutError):
                FlashLayout.load(path)

    def test_rejects_image_larger_than_region(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = self.write_layout(
                directory,
                [
                    {
                        "id": "app",
                        "label": "App",
                        "address": 0,
                        "max_size": 4,
                    }
                ],
            )
            image = directory / "firmware.bin"
            image.write_bytes(b"12345")
            layout = FlashLayout.load(path)
            with self.assertRaises(LayoutError):
                FlashSelection(layout.regions[0], image).validate()

    def test_matches_same_firmware_to_both_ota_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_layout(
                Path(temporary),
                [
                    {
                        "id": "app0",
                        "label": "App 0",
                        "address": "0x10000",
                        "max_size": "0x1000",
                        "accepted_names": ["firmware.bin"],
                    },
                    {
                        "id": "app1",
                        "label": "App 1",
                        "address": "0x11000",
                        "max_size": "0x1000",
                        "accepted_names": ["firmware.bin"],
                    },
                ],
            )
            layout = FlashLayout.load(path)
            self.assertEqual(
                [region.region_id for region in layout.matching_regions("FIRMWARE.BIN")],
                ["app0", "app1"],
            )


if __name__ == "__main__":
    unittest.main()
