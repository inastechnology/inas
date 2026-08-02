from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from shipping_tool.domain.flash_layout import (
    FlashLayout,
    FlashSelection,
    LayoutError,
)


MODULE_TYPE = "inas-device-firmware"
SCHEMA_VERSION = 1
MANIFEST_NAME = "release-module.json"
MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_MEMBER_SIZE = 16 * 1024 * 1024


class ReleaseModuleError(ValueError):
    pass


@dataclass
class LoadedReleaseModule:
    module_id: str
    device_kind: str
    display_name: str
    firmware_version: str
    target: str
    layout: FlashLayout
    files_by_region: dict[str, Path]
    diagnostic_profile_path: Path | None
    diagnostic_profile_id: str | None
    source_archive: Path
    archive_sha256: str
    _temporary_directory: tempfile.TemporaryDirectory

    def close(self) -> None:
        self._temporary_directory.cleanup()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ReleaseModuleError(f"Unsafe ZIP member path: {name}")
    return path


def find_manifest(infos: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    matches = [
        info
        for info in infos
        if not info.is_dir() and PurePosixPath(info.filename).name == MANIFEST_NAME
    ]
    if len(matches) != 1:
        raise ReleaseModuleError(
            f"Release module must contain exactly one {MANIFEST_NAME}"
        )
    return matches[0]


def require_text(value: dict[str, Any], key: str) -> str:
    text = str(value.get(key, "")).strip()
    if not text:
        raise ReleaseModuleError(f"Release module requires {key}")
    return text


def load_release_module(path: Path) -> LoadedReleaseModule:
    archive_path = path.resolve()
    if not archive_path.is_file():
        raise ReleaseModuleError(f"Release module not found: {archive_path}")
    if archive_path.suffix.casefold() != ".zip":
        raise ReleaseModuleError("Release module must be a ZIP file")
    if archive_path.stat().st_size > MAX_ARCHIVE_SIZE:
        raise ReleaseModuleError("Release module ZIP is too large")

    temporary = tempfile.TemporaryDirectory(prefix="inas-release-module-")
    temporary_root = Path(temporary.name)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            seen_names: set[str] = set()
            for info in infos:
                safe_member_name(info.filename)
                if info.filename in seen_names:
                    raise ReleaseModuleError(
                        f"Duplicate ZIP member: {info.filename}"
                    )
                seen_names.add(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ReleaseModuleError(
                        f"Symbolic links are not allowed: {info.filename}"
                    )
                if info.file_size > MAX_MEMBER_SIZE:
                    raise ReleaseModuleError(
                        f"ZIP member is too large: {info.filename}"
                    )

            manifest_info = find_manifest(infos)
            manifest_root = PurePosixPath(manifest_info.filename).parent
            try:
                manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReleaseModuleError(f"Invalid {MANIFEST_NAME}: {exc}") from exc
            if not isinstance(manifest, dict):
                raise ReleaseModuleError("Release module manifest must be an object")
            if manifest.get("schema_version") != SCHEMA_VERSION:
                raise ReleaseModuleError("Unsupported release module schema")
            if manifest.get("module_type") != MODULE_TYPE:
                raise ReleaseModuleError("Unsupported release module type")

            regions = manifest.get("regions")
            checksums = manifest.get("checksums")
            if not isinstance(regions, list) or not regions:
                raise ReleaseModuleError("Release module requires regions")
            if not isinstance(checksums, dict):
                raise ReleaseModuleError("Release module requires checksums")

            archive_infos = {info.filename: info for info in infos}
            extracted_files: dict[str, Path] = {}

            def extract_verified(relative_name: str) -> Path:
                relative = safe_member_name(relative_name)
                if len(relative.parts) != 1:
                    raise ReleaseModuleError(
                        f"Module file must be at module root: {relative_name}"
                    )
                archive_name = str(manifest_root / relative)
                info = archive_infos.get(archive_name)
                if info is None or info.is_dir():
                    raise ReleaseModuleError(
                        f"Release module file not found: {relative_name}"
                    )
                content = archive.read(info)
                expected = str(checksums.get(relative_name, "")).casefold()
                actual = sha256_bytes(content)
                if len(expected) != 64 or actual != expected:
                    raise ReleaseModuleError(
                        f"SHA-256 mismatch: {relative_name}"
                    )
                output_path = temporary_root / relative.name
                output_path.write_bytes(content)
                return output_path

            layout_regions: list[dict[str, Any]] = []
            files_by_region: dict[str, Path] = {}
            for index, raw_region in enumerate(regions):
                if not isinstance(raw_region, dict):
                    raise ReleaseModuleError(
                        f"regions[{index}] must be an object"
                    )
                region_id = require_text(raw_region, "id")
                relative_name = require_text(raw_region, "file")
                if region_id in files_by_region:
                    raise ReleaseModuleError(
                        f"Duplicate release module region: {region_id}"
                    )
                image_path = extracted_files.get(relative_name)
                if image_path is None:
                    image_path = extract_verified(relative_name)
                    extracted_files[relative_name] = image_path
                files_by_region[region_id] = image_path
                layout_region = dict(raw_region)
                layout_region.pop("file", None)
                layout_region["accepted_names"] = [image_path.name]
                layout_regions.append(layout_region)

            layout_value = {
                "schema_version": SCHEMA_VERSION,
                "name": require_text(manifest, "name"),
                "chip": require_text(manifest, "chip"),
                "flash_size": require_text(manifest, "flash_size"),
                "regions": layout_regions,
            }
            layout_path = temporary_root / "flash-layout.json"
            layout_path.write_text(
                json.dumps(layout_value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            try:
                layout = FlashLayout.load(layout_path)
                for region in layout.regions:
                    FlashSelection(region, files_by_region[region.region_id]).validate()
            except LayoutError as exc:
                raise ReleaseModuleError(str(exc)) from exc

            diagnostic_profile_path: Path | None = None
            diagnostic_profile_name = manifest.get("diagnostic_profile")
            if diagnostic_profile_name:
                diagnostic_profile_path = extract_verified(
                    str(diagnostic_profile_name)
                )

        return LoadedReleaseModule(
            module_id=require_text(manifest, "module_id"),
            device_kind=require_text(manifest, "device_kind"),
            display_name=require_text(manifest, "display_name"),
            firmware_version=require_text(manifest, "firmware_version"),
            target=require_text(manifest, "target"),
            layout=layout,
            files_by_region=files_by_region,
            diagnostic_profile_path=diagnostic_profile_path,
            diagnostic_profile_id=(
                str(manifest["diagnostic_profile_id"])
                if manifest.get("diagnostic_profile_id")
                else None
            ),
            source_archive=archive_path,
            archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            _temporary_directory=temporary,
        )
    except ReleaseModuleError:
        temporary.cleanup()
        raise
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        temporary.cleanup()
        raise ReleaseModuleError(f"Could not load release module: {exc}") from exc
    except Exception:
        temporary.cleanup()
        raise
