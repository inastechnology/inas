from __future__ import annotations

import codecs
import threading
from collections.abc import Callable


ConsoleDataCallback = Callable[[str], None]
ConsoleStateCallback = Callable[[bool, str], None]


def encode_console_command(value: str, hex_mode: bool, append_newline: bool) -> bytes:
    if hex_mode:
        normalized = value.replace(",", " ").replace("\t", " ")
        tokens = [token for token in normalized.split(" ") if token]
        if not tokens:
            raise ValueError("16進バイト列を入力してください")
        result = bytearray()
        for token in tokens:
            cleaned = token[2:] if token.lower().startswith("0x") else token
            if len(cleaned) == 0 or len(cleaned) > 2:
                raise ValueError(f"不正な16進バイトです: {token}")
            try:
                result.append(int(cleaned, 16))
            except ValueError as exc:
                raise ValueError(f"不正な16進バイトです: {token}") from exc
        return bytes(result)

    payload = value.encode("utf-8")
    if append_newline:
        payload += b"\r\n"
    return payload


class SerialConsoleService:
    def __init__(
        self,
        on_data: ConsoleDataCallback,
        on_state: ConsoleStateCallback,
    ) -> None:
        self._on_data = on_data
        self._on_state = on_state
        self._serial = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._write_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._serial is not None and bool(self._serial.is_open)

    def connect(self, port: str, baud: int) -> None:
        if self.connected:
            self.disconnect()
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserialがインストールされていません") from exc

        self._serial = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1.0,
        )
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="shipping-serial-console",
            daemon=True,
        )
        self._thread.start()
        self._on_state(True, f"{port} / {baud}bps")

    def disconnect(self) -> None:
        self._stop_event.set()
        serial_port = self._serial
        self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self._on_state(False, "切断")

    def write(self, payload: bytes) -> None:
        serial_port = self._serial
        if serial_port is None or not serial_port.is_open:
            raise RuntimeError("コンソールが接続されていません")
        with self._write_lock:
            serial_port.write(payload)
            serial_port.flush()

    def _read_loop(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while not self._stop_event.is_set():
                serial_port = self._serial
                if serial_port is None or not serial_port.is_open:
                    break
                waiting = serial_port.in_waiting
                data = serial_port.read(waiting if waiting > 0 else 1)
                if data:
                    text = decoder.decode(data)
                    if text:
                        self._on_data(text)
        except Exception as exc:
            serial_port = self._serial
            self._serial = None
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception:
                    pass
            self._on_state(False, f"通信エラー: {exc}")
        finally:
            remaining = decoder.decode(b"", final=True)
            if remaining:
                self._on_data(remaining)
