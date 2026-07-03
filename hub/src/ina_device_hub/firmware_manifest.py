import re

FIRMWARE_MANIFEST_BEGIN = b"INAS_FW_MANIFEST_V1_BEGIN\n"
FIRMWARE_MANIFEST_END = b"INAS_FW_MANIFEST_V1_END"
FIRMWARE_MANIFEST_REQUIRED_KEYS = {"schema", "project", "device_kind", "version", "build_id", "target", "framework"}

_DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:+-]+$")


class FirmwareManifestValidationError(ValueError):
    pass


def extract_firmware_manifest(binary: bytes | bytearray):
    if not isinstance(binary, bytes | bytearray) or not binary:
        raise FirmwareManifestValidationError("firmware binary must not be empty")

    data = bytes(binary)
    start = data.find(FIRMWARE_MANIFEST_BEGIN)
    if start < 0:
        raise FirmwareManifestValidationError("firmware manifest marker not found")
    manifest_start = start + len(FIRMWARE_MANIFEST_BEGIN)
    end = data.find(FIRMWARE_MANIFEST_END, manifest_start)
    if end < 0:
        raise FirmwareManifestValidationError("firmware manifest end marker not found")
    if end - manifest_start > 1024:
        raise FirmwareManifestValidationError("firmware manifest is too large")

    try:
        manifest_text = data[manifest_start:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise FirmwareManifestValidationError("firmware manifest must be ASCII") from exc

    metadata = {}
    for line in manifest_text.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise FirmwareManifestValidationError("firmware manifest contains malformed line")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in metadata:
            raise FirmwareManifestValidationError("firmware manifest contains duplicate or empty key")
        metadata[key] = value

    return validate_firmware_manifest(metadata)


def validate_firmware_manifest(metadata: dict):
    if not isinstance(metadata, dict):
        raise FirmwareManifestValidationError("firmware manifest must be an object")

    missing = sorted(FIRMWARE_MANIFEST_REQUIRED_KEYS - set(metadata))
    if missing:
        raise FirmwareManifestValidationError(f"firmware manifest missing keys: {', '.join(missing)}")

    schema = metadata.get("schema")
    if schema != "1":
        raise FirmwareManifestValidationError("firmware manifest schema must be 1")

    return {
        "schema": schema,
        "project": _normalize_manifest_token("project", metadata.get("project"), max_len=64),
        "device_kind": _normalize_device_kind(metadata.get("device_kind")),
        "version": _normalize_version(metadata.get("version")),
        "build_id": _normalize_manifest_token("build_id", metadata.get("build_id"), max_len=64),
        "target": _normalize_manifest_token("target", metadata.get("target"), max_len=64),
        "framework": _normalize_manifest_token("framework", metadata.get("framework"), max_len=32),
    }


def _normalize_manifest_token(name: str, value, *, max_len: int):
    if not isinstance(value, str) or not value:
        raise FirmwareManifestValidationError(f"firmware manifest {name} must be a non-empty string")
    if _SAFE_TOKEN_RE.match(value) is None:
        raise FirmwareManifestValidationError(f"firmware manifest {name} contains unsupported characters")
    if len(value) >= max_len:
        raise FirmwareManifestValidationError(f"firmware manifest {name} must be shorter than {max_len} characters")
    return value


def _normalize_device_kind(value):
    if not isinstance(value, str) or _DEVICE_KIND_RE.match(value) is None:
        raise FirmwareManifestValidationError("device_kind must be exactly three uppercase letters")
    return value


def _normalize_version(version: str):
    if not isinstance(version, str) or not version.strip():
        raise FirmwareManifestValidationError("version must be a non-empty string")
    version = version.strip()
    if _SAFE_TOKEN_RE.match(version) is None:
        raise FirmwareManifestValidationError("version contains unsupported characters")
    if len(version) >= 32:
        raise FirmwareManifestValidationError("version must be shorter than 32 characters")
    return version
