import hashlib
import io
import json
import os
import tarfile
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ina_device_hub.json_repository_io import repository_file_lock

BACKUP_FORMAT_VERSION = 1
STATE_FILE_PATTERNS = ("*.json", ".*.json", "*.jsonl", ".*.jsonl")
STATE_DIRECTORIES = ("firmware",)


class StateBackupError(ValueError):
    pass


def create_state_backup(work_dir, backup_dir, *, retention: int = 14, now=None) -> Path:
    work_path = Path(work_dir).expanduser().resolve()
    backup_path = Path(backup_dir).expanduser().resolve()
    backup_path.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_path, 0o700)

    created_at = now or datetime.now(UTC)
    archive_path = backup_path / f"ina-hub-state-{created_at.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    files = _state_files(work_path, backup_path)
    lock_paths = sorted(path for path in files if path.suffix in {".json", ".jsonl"})

    with ExitStack() as stack:
        for path in lock_paths:
            stack.enter_context(repository_file_lock(str(path)))
        manifest = _manifest(work_path, files, created_at)
        with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            manifest_bytes = json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8")
            manifest_info = tarfile.TarInfo("manifest.json")
            manifest_info.size = len(manifest_bytes)
            manifest_info.mode = 0o600
            manifest_info.mtime = int(created_at.timestamp())
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            for path in files:
                archive.add(path, arcname=f"data/{path.relative_to(work_path).as_posix()}", recursive=False)

    os.chmod(archive_path, 0o600)
    _apply_retention(backup_path, max(1, int(retention)))
    return archive_path


def restore_state_backup(archive_path, work_dir) -> list[Path]:
    archive_path = Path(archive_path).expanduser().resolve()
    work_path = Path(work_dir).expanduser().resolve()
    if not archive_path.is_file():
        raise StateBackupError(f"backup archive not found: {archive_path}")
    work_path.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        manifest_member = next((member for member in members if member.name == "manifest.json"), None)
        if manifest_member is None or not manifest_member.isfile():
            raise StateBackupError("backup manifest is missing")
        manifest_file = archive.extractfile(manifest_member)
        manifest = json.load(manifest_file) if manifest_file is not None else {}
        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise StateBackupError("unsupported backup format")

        data_members = [member for member in members if member.name.startswith("data/")]
        _validate_members(data_members)
        expected = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}

        with tempfile.TemporaryDirectory(prefix=".ina-restore-", dir=work_path) as temporary_directory:
            staging = Path(temporary_directory)
            restored = []
            for member in data_members:
                if not member.isfile():
                    continue
                relative_path = PurePosixPath(member.name).relative_to("data")
                source = archive.extractfile(member)
                if source is None:
                    raise StateBackupError(f"could not read backup member: {member.name}")
                payload = source.read()
                expected_hash = expected.get(relative_path.as_posix(), {}).get("sha256")
                if expected_hash != hashlib.sha256(payload).hexdigest():
                    raise StateBackupError(f"backup checksum mismatch: {relative_path}")
                staged_path = staging.joinpath(*relative_path.parts)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(payload)
                os.chmod(staged_path, 0o600)
                restored.append((relative_path, staged_path))

            lock_paths = sorted(work_path.joinpath(*relative.parts) for relative, _staged in restored if relative.suffix in {".json", ".jsonl"})
            with ExitStack() as stack:
                for path in lock_paths:
                    stack.enter_context(repository_file_lock(str(path)))
                targets = []
                for relative_path, staged_path in restored:
                    target = work_path.joinpath(*relative_path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged_path, target)
                    targets.append(target)
    return targets


def _state_files(work_path: Path, backup_path: Path) -> list[Path]:
    selected = set()
    if not work_path.exists():
        return []
    for pattern in STATE_FILE_PATTERNS:
        selected.update(path for path in work_path.glob(pattern) if path.is_file() and not path.is_symlink())
    for directory_name in STATE_DIRECTORIES:
        directory = work_path / directory_name
        if not directory.is_dir() or directory.is_symlink():
            continue
        selected.update(path for path in directory.rglob("*") if path.is_file() and not path.is_symlink())
    return sorted(path for path in selected if backup_path not in path.parents)


def _manifest(work_path: Path, files: list[Path], created_at: datetime) -> dict:
    return {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": created_at.isoformat(),
        "files": {
            path.relative_to(work_path).as_posix(): {
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_members(members: list[tarfile.TarInfo]) -> None:
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not member.isfile():
            raise StateBackupError(f"unsafe backup member: {member.name}")


def _apply_retention(backup_path: Path, retention: int) -> None:
    archives = sorted(backup_path.glob("ina-hub-state-*.tar.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    for archive in archives[retention:]:
        archive.unlink()
