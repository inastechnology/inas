from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

INAS_FIRMWARE_MODULE_TYPE = "inas-device-firmware"
INAS_FIRMWARE_MODULE_SCHEMA_VERSION = 1
MAX_RELEASE_MANIFEST_BYTES = 256 * 1024
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class FirmwareUploadValidationError(ValueError):
    pass


class FirmwareUploadTooLargeError(FirmwareUploadValidationError):
    pass


@dataclass(frozen=True)
class NormalizedFirmwareUpload:
    firmware_binary: bytes
    source_format: str
    release_module: dict | None = None

    def validate_embedded_manifest(self, embedded_manifest: dict) -> None:
        if self.release_module is None:
            return

        release_device_kind = self.release_module["device_kind"]
        embedded_device_kind = embedded_manifest.get("device_kind")
        if release_device_kind != embedded_device_kind:
            raise FirmwareUploadValidationError(f"release module device_kind mismatch: release={release_device_kind} embedded={embedded_device_kind}")

        release_version = self.release_module["firmware_version"]
        embedded_version = embedded_manifest.get("version")
        if release_version != embedded_version:
            raise FirmwareUploadValidationError(f"release module version mismatch: release={release_version} embedded={embedded_version}")


def normalize_firmware_upload(content: bytes | bytearray, *, max_upload_bytes: int) -> NormalizedFirmwareUpload:
    if not isinstance(content, bytes | bytearray) or not content:
        raise FirmwareUploadValidationError("firmware upload must not be empty")
    if max_upload_bytes <= 0:
        raise FirmwareUploadValidationError("firmware upload limit must be greater than zero")

    payload = bytes(content)
    if len(payload) > max_upload_bytes:
        raise FirmwareUploadTooLargeError(f"firmware upload exceeds the {max_upload_bytes}-byte limit")
    if not payload.startswith(ZIP_SIGNATURES):
        return NormalizedFirmwareUpload(firmware_binary=payload, source_format="bin")

    return _extract_inas_firmware(payload, max_upload_bytes=max_upload_bytes)


def _extract_inas_firmware(payload: bytes, *, max_upload_bytes: int) -> NormalizedFirmwareUpload:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            _validate_archive_paths(members)
            manifest_info = _single_member_named(members, "release-module.json")
            if manifest_info.file_size > MAX_RELEASE_MANIFEST_BYTES:
                raise FirmwareUploadValidationError("release-module.json is too large")
            release_module = _read_release_manifest(archive, manifest_info)
            firmware_info = _firmware_member(members, manifest_info, release_module)
            if firmware_info.file_size > max_upload_bytes:
                raise FirmwareUploadTooLargeError(f"firmware.bin exceeds the {max_upload_bytes}-byte limit")
            if firmware_info.file_size == 0:
                raise FirmwareUploadValidationError("firmware.bin in the release module is empty")
            if firmware_info.flag_bits & 0x1:
                raise FirmwareUploadValidationError("encrypted .inasfw files are not supported")
            firmware_binary = archive.read(firmware_info)
    except FirmwareUploadValidationError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise FirmwareUploadValidationError(f"invalid .inasfw release module: {exc}") from exc

    expected_checksum = release_module["checksums"]["firmware.bin"].lower()
    actual_checksum = hashlib.sha256(firmware_binary).hexdigest()
    if actual_checksum != expected_checksum:
        raise FirmwareUploadValidationError(f"firmware.bin checksum mismatch: release={expected_checksum} actual={actual_checksum}")

    return NormalizedFirmwareUpload(firmware_binary=firmware_binary, source_format="inasfw", release_module=release_module)


def _validate_archive_paths(members: list[zipfile.ZipInfo]) -> None:
    names = [member.filename for member in members]
    if len(names) != len(set(names)):
        raise FirmwareUploadValidationError(".inasfw contains duplicate archive paths")
    for name in names:
        path = PurePosixPath(name)
        if "\\" in name or path.is_absolute() or ".." in path.parts:
            raise FirmwareUploadValidationError(f".inasfw contains an unsafe archive path: {name}")


def _single_member_named(members: list[zipfile.ZipInfo], filename: str) -> zipfile.ZipInfo:
    matches = [member for member in members if not member.is_dir() and PurePosixPath(member.filename).name == filename]
    if len(matches) != 1:
        raise FirmwareUploadValidationError(f".inasfw must contain exactly one {filename}")
    return matches[0]


def _read_release_manifest(archive: zipfile.ZipFile, manifest_info: zipfile.ZipInfo) -> dict:
    if manifest_info.flag_bits & 0x1:
        raise FirmwareUploadValidationError("encrypted .inasfw files are not supported")
    value = json.loads(archive.read(manifest_info).decode("utf-8"))
    if not isinstance(value, dict):
        raise FirmwareUploadValidationError("release-module.json must contain a JSON object")
    if value.get("schema_version") != INAS_FIRMWARE_MODULE_SCHEMA_VERSION:
        raise FirmwareUploadValidationError("unsupported release-module.json schema_version")
    if value.get("module_type") != INAS_FIRMWARE_MODULE_TYPE:
        raise FirmwareUploadValidationError("release-module.json is not an INAS device firmware module")
    for key in ("device_kind", "firmware_version"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise FirmwareUploadValidationError(f"release-module.json {key} must be a non-empty string")
    if not isinstance(value.get("checksums"), dict):
        raise FirmwareUploadValidationError("release-module.json checksums must be an object")
    checksum = value["checksums"].get("firmware.bin")
    if not isinstance(checksum, str) or len(checksum) != 64 or any(character not in "0123456789abcdefABCDEF" for character in checksum):
        raise FirmwareUploadValidationError("release-module.json must contain a valid firmware.bin SHA-256 checksum")
    return value


def _firmware_member(members: list[zipfile.ZipInfo], manifest_info: zipfile.ZipInfo, release_module: dict) -> zipfile.ZipInfo:
    regions = release_module.get("regions")
    if not isinstance(regions, list):
        raise FirmwareUploadValidationError("release-module.json regions must be an array")
    app_regions = [region for region in regions if isinstance(region, dict) and region.get("id") == "app0"]
    if len(app_regions) != 1:
        raise FirmwareUploadValidationError("release-module.json must contain exactly one app0 region")
    if app_regions[0].get("file") != "firmware.bin":
        raise FirmwareUploadValidationError("the app0 region must reference firmware.bin")

    manifest_parent = PurePosixPath(manifest_info.filename).parent
    firmware_path = str(manifest_parent / "firmware.bin") if str(manifest_parent) != "." else "firmware.bin"
    matches = [member for member in members if not member.is_dir() and member.filename == firmware_path]
    if len(matches) != 1:
        raise FirmwareUploadValidationError("firmware.bin must be next to release-module.json in the .inasfw file")
    return matches[0]
