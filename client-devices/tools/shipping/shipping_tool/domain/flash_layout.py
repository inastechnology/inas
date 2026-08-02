from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LayoutError(ValueError):
    pass


def parse_int(value: int | str, field_name: str) -> int:
    if isinstance(value, bool):
        raise LayoutError(f"{field_name} must be an integer or hexadecimal string")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip(), 0)
        except ValueError as exc:
            raise LayoutError(f"{field_name} is invalid: {value}") from exc
    else:
        raise LayoutError(f"{field_name} must be an integer or hexadecimal string")
    if parsed < 0:
        raise LayoutError(f"{field_name} must not be negative")
    return parsed


@dataclass(frozen=True)
class FlashRegion:
    region_id: str
    label: str
    address: int
    max_size: int | None
    required: bool
    default_enabled: bool
    accepted_names: tuple[str, ...]
    description: str
    sensitive: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "FlashRegion":
        prefix = f"regions[{index}]"
        region_id = str(value.get("id", "")).strip()
        label = str(value.get("label", "")).strip()
        if not region_id or not label:
            raise LayoutError(f"{prefix} requires id and label")
        accepted_names_value = value.get("accepted_names", [])
        if not isinstance(accepted_names_value, list):
            raise LayoutError(f"{prefix}.accepted_names must be a list")
        max_size_value = value.get("max_size")
        return cls(
            region_id=region_id,
            label=label,
            address=parse_int(value.get("address"), f"{prefix}.address"),
            max_size=(
                parse_int(max_size_value, f"{prefix}.max_size")
                if max_size_value is not None
                else None
            ),
            required=bool(value.get("required", False)),
            default_enabled=bool(value.get("default_enabled", value.get("required", False))),
            accepted_names=tuple(str(item) for item in accepted_names_value),
            description=str(value.get("description", "")).strip(),
            sensitive=bool(value.get("sensitive", False)),
        )


@dataclass(frozen=True)
class FlashLayout:
    schema_version: int
    name: str
    chip: str
    flash_size: str
    regions: tuple[FlashRegion, ...]
    source_path: Path

    @classmethod
    def load(cls, path: Path) -> "FlashLayout":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LayoutError(f"Could not read layout: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LayoutError(f"Invalid JSON at line {exc.lineno}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise LayoutError("Layout root must be an object")

        regions_value = value.get("regions")
        if not isinstance(regions_value, list) or not regions_value:
            raise LayoutError("Layout requires at least one region")
        regions = tuple(
            FlashRegion.from_dict(item, index)
            for index, item in enumerate(regions_value)
            if isinstance(item, dict)
        )
        if len(regions) != len(regions_value):
            raise LayoutError("Every region must be an object")
        if len({region.region_id for region in regions}) != len(regions):
            raise LayoutError("Region IDs must be unique")

        layout = cls(
            schema_version=parse_int(value.get("schema_version", 1), "schema_version"),
            name=str(value.get("name", "")).strip(),
            chip=str(value.get("chip", "")).strip(),
            flash_size=str(value.get("flash_size", "keep")).strip(),
            regions=regions,
            source_path=path.resolve(),
        )
        if layout.schema_version != 1:
            raise LayoutError(f"Unsupported schema_version: {layout.schema_version}")
        if not layout.name or not layout.chip:
            raise LayoutError("Layout requires name and chip")
        layout.validate_overlaps()
        return layout

    def validate_overlaps(self) -> None:
        sized = sorted(
            (region for region in self.regions if region.max_size is not None),
            key=lambda region: region.address,
        )
        for previous, current in zip(sized, sized[1:]):
            assert previous.max_size is not None
            if previous.address + previous.max_size > current.address:
                raise LayoutError(
                    f"Regions overlap: {previous.region_id} and {current.region_id}"
                )

    def matching_regions(self, file_name: str) -> tuple[FlashRegion, ...]:
        normalized = file_name.casefold()
        return tuple(
            region
            for region in self.regions
            if normalized in {name.casefold() for name in region.accepted_names}
        )


@dataclass(frozen=True)
class FlashSelection:
    region: FlashRegion
    file_path: Path

    def validate(self) -> None:
        if not self.file_path.is_file():
            raise LayoutError(f"File not found: {self.file_path}")
        if self.file_path.suffix.lower() != ".bin":
            raise LayoutError(f"Only .bin files are supported: {self.file_path.name}")
        size = self.file_path.stat().st_size
        if size <= 0:
            raise LayoutError(f"File is empty: {self.file_path.name}")
        if self.region.max_size is not None and size > self.region.max_size:
            raise LayoutError(
                f"{self.file_path.name} ({size} bytes) exceeds "
                f"{self.region.label} ({self.region.max_size} bytes)"
            )
