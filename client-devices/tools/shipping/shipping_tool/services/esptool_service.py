from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from shipping_tool.domain.flash_layout import FlashLayout, FlashSelection


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class EsptoolResult:
    returncode: int
    command: tuple[str, ...]


class EsptoolService:
    def __init__(self, python_executable: str | None = None) -> None:
        self.python_executable = python_executable or sys.executable

    def base_command(self) -> list[str]:
        return [self.python_executable, "-m", "esptool"]

    def build_write_command(
        self,
        layout: FlashLayout,
        port: str,
        baud: int,
        selections: Iterable[FlashSelection],
        erase_all: bool,
    ) -> list[str]:
        selected = sorted(selections, key=lambda item: item.region.address)
        if not selected:
            raise ValueError("No flash region is selected")
        for item in selected:
            item.validate()

        command = self.base_command() + [
            "--chip",
            layout.chip,
            "--port",
            port,
            "--baud",
            str(baud),
            "--before",
            "default-reset",
            "--after",
            "hard-reset",
        ]
        if erase_all:
            command.append("erase-flash")
            return command
        command += [
            "write-flash",
            "-z",
            "--flash-mode",
            "keep",
            "--flash-freq",
            "keep",
            "--flash-size",
            layout.flash_size,
        ]
        for item in selected:
            command.extend([hex(item.region.address), str(item.file_path)])
        return command

    def build_verify_command(
        self,
        layout: FlashLayout,
        port: str,
        baud: int,
        selections: Iterable[FlashSelection],
    ) -> list[str]:
        selected = sorted(selections, key=lambda item: item.region.address)
        if not selected:
            raise ValueError("No flash region is selected")
        for item in selected:
            item.validate()
        command = self.base_command() + [
            "--chip",
            layout.chip,
            "--port",
            port,
            "--baud",
            str(baud),
            "verify-flash",
        ]
        for item in selected:
            command.extend([hex(item.region.address), str(item.file_path)])
        return command

    def build_chip_id_command(self, chip: str, port: str, baud: int) -> list[str]:
        return self.base_command() + [
            "--chip",
            chip,
            "--port",
            port,
            "--baud",
            str(baud),
            "chip-id",
        ]

    def build_reset_command(self, chip: str, port: str) -> list[str]:
        return self.base_command() + [
            "--chip",
            chip,
            "--port",
            port,
            "run",
        ]

    def run(self, command: list[str], log: LogCallback) -> EsptoolResult:
        log("$ " + subprocess.list2cmdline(command))
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log(line.rstrip())
        returncode = process.wait()
        return EsptoolResult(returncode=returncode, command=tuple(command))
