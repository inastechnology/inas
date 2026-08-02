from __future__ import annotations

import unittest
from pathlib import Path

from shipping_tool.domain.diagnostic_profile import DiagnosticEngine, DiagnosticProfile


class DiagnosticProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = DiagnosticProfile.load(
            Path("../../rs485-debug-device/shipping/diagnostic-profile.json")
        )

    def test_detects_rs485_devices_and_scan_count(self) -> None:
        engine = DiagnosticEngine(self.profile)
        engine.feed(
            '[DETECTED] model="ComWinTop CWT-SOIL" id=1 baud=4800 8N1 '
            "reason=cwt_configuration_signature confidence=high\n"
            '[DETECTED] model="DFRobot SEN0641 PAR" id=3 baud=4800 8N1 '
            "reason=no_soil_signature confidence=heuristic\n"
            "[SCAN] Complete: 2 supported device(s)\n"
        )
        self.assertEqual(len(engine.devices), 2)
        self.assertEqual(engine.statuses["device_count"].value, "2台")

    def test_detects_rs485_error(self) -> None:
        engine = DiagnosticEngine(self.profile)
        engine.feed(
            '[ERROR] model="ComWinTop CWT-SOIL" id=1 baud=4800 '
            "status=timeout received=0 failure=1/3\n"
        )
        self.assertEqual(len(engine.errors), 1)

    def test_detects_rs485_detailed_result_error(self) -> None:
        engine = DiagnosticEngine(self.profile)
        engine.feed(
            '[RESULT] profile="ComWinTop CWT-SOIL" baud=4800 id=1 '
            "status=crc_error calculated=0x1234 received=0x5678\n"
        )
        self.assertEqual(len(engine.errors), 1)

    def test_common_profile_reads_status_json(self) -> None:
        profile = DiagnosticProfile.load(
            Path("../../watering-rs485-device/shipping/diagnostic-profile.json")
        )
        engine = DiagnosticEngine(profile)
        engine.feed_line(
            'Sending WRS status: {"network_connected":true,"soil_rs485_ok":false,'
            '"par_ok":true,"soil_moisture_percent":31.5}'
        )
        self.assertEqual(engine.statuses["wifi"].value, "接続")
        self.assertEqual(engine.statuses["soil_rs485"].severity, "error")
        self.assertEqual(engine.statuses["moisture"].value, "31.5%")


if __name__ == "__main__":
    unittest.main()
