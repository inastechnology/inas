from __future__ import annotations

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path


TOOL_FILES = (
    ".gitignore",
    "README.md",
    "requirements.txt",
    "run.py",
    "setup-windows.bat",
    "setup-windows.ps1",
    "setup-linux.sh",
    "start-windows.bat",
    "start-linux.sh",
)
TOOL_DIRECTORIES = ("configs", "shipping_tool")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_release_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    for relative_name in TOOL_FILES:
        shutil.copy2(source / relative_name, target / relative_name)
    for relative_name in TOOL_DIRECTORIES:
        shutil.copytree(
            source / relative_name,
            target / relative_name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    profiles_dir = target / "profiles"
    profiles_dir.mkdir()
    client_devices_dir = source.parents[1]
    for profile in sorted(
        client_devices_dir.glob("*-device/shipping/diagnostic-profile.json")
    ):
        output_name = f"{profile.parents[1].name}.json"
        shutil.copy2(profile, profiles_dir / output_name)

def create_zip(source_tree: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_tree.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_tree.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the portable shipping tool ZIP")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = Path(__file__).resolve().parents[1]
    release_root = source / "release"
    package_name = "INAS-Shipping-Tool"
    target = release_root / package_name
    output = args.output or release_root / f"{package_name}.zip"

    copy_release_tree(source, target)
    create_zip(target, output)
    print(f"Created: {output}")
    print(f"SHA-256: {sha256(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
