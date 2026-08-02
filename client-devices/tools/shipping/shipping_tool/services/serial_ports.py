from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str
    hwid: str

    @property
    def display_name(self) -> str:
        return f"{self.device} — {self.description}" if self.description else self.device


def list_serial_ports() -> list[SerialPortInfo]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    return [
        SerialPortInfo(
            device=port.device,
            description=port.description or "",
            hwid=port.hwid or "",
        )
        for port in sorted(list_ports.comports(), key=lambda item: item.device)
    ]
