#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path


MODULE_TYPE = "inas-device-firmware"
SCHEMA_VERSION = 1
FIXED_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReleaseImage:
    region_id: str
    label: str
    address: str
    max_size: str
    source: Path
    archive_name: str
    required: bool
    default_enabled: bool
    description: str
    sensitive: bool = False

    def manifest_region(self) -> dict[str, object]:
        return {
            "id": self.region_id,
            "label": self.label,
            "address": self.address,
            "max_size": self.max_size,
            "required": self.required,
            "default_enabled": self.default_enabled,
            "accepted_names": [self.archive_name],
            "file": self.archive_name,
            "description": self.description,
            "sensitive": self.sensitive,
        }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_required_file(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    content = path.read_bytes()
    if not content:
        raise ValueError(f"{label} is empty: {path}")
    return content


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def build_release_module(
    *,
    build_dir: Path,
    boot_app0: Path,
    output: Path,
    module_id: str,
    device_kind: str,
    display_name: str,
    firmware_version: str,
    target: str,
    chip: str,
    flash_size: str,
    app_max_size: str = "0x330000",
    filesystem_offset: str = "0x670000",
    filesystem_max_size: str = "0x180000",
    filesystem: Path | None = None,
    diagnostic_profile: Path | None = None,
) -> str:
    images = [
        ReleaseImage(
            region_id="bootloader",
            label="Bootloader",
            address="0x0",
            max_size="0x8000",
            source=build_dir / "bootloader.bin",
            archive_name="bootloader.bin",
            required=True,
            default_enabled=True,
            description="起動プログラム",
        ),
        ReleaseImage(
            region_id="partition_table",
            label="Partition table",
            address="0x8000",
            max_size="0x1000",
            source=build_dir / "partitions.bin",
            archive_name="partitions.bin",
            required=True,
            default_enabled=True,
            description="フラッシュ領域の区切り",
        ),
        ReleaseImage(
            region_id="ota_boot_metadata",
            label="OTA boot metadata",
            address="0xE000",
            max_size="0x2000",
            source=boot_app0,
            archive_name="boot_app0.bin",
            required=True,
            default_enabled=True,
            description="初回起動するOTAスロットの情報",
        ),
        ReleaseImage(
            region_id="app0",
            label="Application app0",
            address="0x10000",
            max_size=app_max_size,
            source=build_dir / "firmware.bin",
            archive_name="firmware.bin",
            required=True,
            default_enabled=True,
            description="メインF/W",
        ),
    ]
    if filesystem is not None:
        images.append(
            ReleaseImage(
                region_id="storage",
                label="LittleFS storage",
                address=filesystem_offset,
                max_size=filesystem_max_size,
                source=filesystem,
                archive_name="littlefs.bin",
                required=False,
                default_enabled=False,
                description="初期ファイルシステム（通常は既存設定を保持）",
                sensitive=True,
            )
        )

    archive_files: dict[str, bytes] = {}
    for image in images:
        archive_files[image.archive_name] = read_required_file(
            image.source, image.label
        )

    diagnostic_profile_name: str | None = None
    diagnostic_profile_id: str | None = None
    if diagnostic_profile is not None:
        profile_content = read_required_file(
            diagnostic_profile, "Diagnostic profile"
        )
        try:
            profile_value = json.loads(profile_content.decode("utf-8"))
            diagnostic_profile_id = str(profile_value["id"])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
            raise ValueError(
                f"Invalid diagnostic profile: {diagnostic_profile}"
            ) from exc
        diagnostic_profile_name = "diagnostic-profile.json"
        archive_files[diagnostic_profile_name] = profile_content

    checksums = {
        name: sha256_bytes(content)
        for name, content in sorted(archive_files.items())
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "module_type": MODULE_TYPE,
        "module_id": module_id,
        "device_kind": device_kind,
        "display_name": display_name,
        "firmware_version": firmware_version,
        "target": target,
        "name": f"{display_name} {firmware_version}",
        "chip": chip,
        "flash_size": flash_size,
        "regions": [image.manifest_region() for image in images],
        "diagnostic_profile": diagnostic_profile_name,
        "diagnostic_profile_id": diagnostic_profile_id,
        "checksums": checksums,
    }
    manifest_content = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    checksum_content = "".join(
        f"{digest}  {name}\n" for name, digest in checksums.items()
    ).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    root_name = output.stem
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            zip_info(f"{root_name}/release-module.json"),
            manifest_content,
        )
        archive.writestr(
            zip_info(f"{root_name}/SHA256SUMS.txt"),
            checksum_content,
        )
        for name, content in sorted(archive_files.items()):
            archive.writestr(zip_info(f"{root_name}/{name}"), content)

    module_checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    return module_checksum


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an INAS .inasfw firmware release package"
    )
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--boot-app0", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--module-id", required=True)
    parser.add_argument("--device-kind", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--firmware-version", required=True)
    parser.add_argument("--target", default="seeed_xiao_esp32s3")
    parser.add_argument("--chip", default="esp32s3")
    parser.add_argument("--flash-size", default="8MB")
    parser.add_argument("--app-max-size", default="0x330000")
    parser.add_argument("--filesystem-offset", default="0x670000")
    parser.add_argument("--filesystem-max-size", default="0x180000")
    parser.add_argument("--filesystem", type=Path)
    parser.add_argument("--diagnostic-profile", type=Path)
    args = parser.parse_args()

    try:
        checksum = build_release_module(
            build_dir=args.build_dir.resolve(),
            boot_app0=args.boot_app0.resolve(),
            output=args.output.resolve(),
            module_id=args.module_id,
            device_kind=args.device_kind,
            display_name=args.display_name,
            firmware_version=args.firmware_version,
            target=args.target,
            chip=args.chip,
            flash_size=args.flash_size,
            app_max_size=args.app_max_size,
            filesystem_offset=args.filesystem_offset,
            filesystem_max_size=args.filesystem_max_size,
            filesystem=args.filesystem.resolve() if args.filesystem else None,
            diagnostic_profile=(
                args.diagnostic_profile.resolve()
                if args.diagnostic_profile
                else None
            ),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Created release module: {args.output}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
