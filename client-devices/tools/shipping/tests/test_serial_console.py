from __future__ import annotations

import unittest

from shipping_tool.services.serial_console import encode_console_command


class SerialConsoleCommandTest(unittest.TestCase):
    def test_text_command_appends_crlf(self) -> None:
        self.assertEqual(
            encode_console_command("scan", hex_mode=False, append_newline=True),
            b"scan\r\n",
        )

    def test_text_command_can_be_sent_without_newline(self) -> None:
        self.assertEqual(
            encode_console_command("?", hex_mode=False, append_newline=False),
            b"?",
        )

    def test_hex_command_accepts_plain_and_prefixed_tokens(self) -> None:
        self.assertEqual(
            encode_console_command(
                "01 0x03,00 00 00 07 04 08",
                hex_mode=True,
                append_newline=True,
            ),
            bytes((0x01, 0x03, 0x00, 0x00, 0x00, 0x07, 0x04, 0x08)),
        )

    def test_hex_command_rejects_invalid_token(self) -> None:
        with self.assertRaises(ValueError):
            encode_console_command("01 XYZ", hex_mode=True, append_newline=False)


if __name__ == "__main__":
    unittest.main()
