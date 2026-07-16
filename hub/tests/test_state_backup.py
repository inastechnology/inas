import json
import stat
import tarfile
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from ina_device_hub.state_backup import StateBackupError, create_state_backup, restore_state_backup


class StateBackupTest(unittest.TestCase):
    def test_backup_and_restore_round_trip_with_secure_archive(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            work_dir = root / "work"
            backup_dir = root / "backups"
            work_dir.mkdir()
            state_path = work_dir / ".fields.json"
            state_path.write_text(json.dumps({"field-1": {"name": "圃場A"}}))

            archive = create_state_backup(
                work_dir,
                backup_dir,
                now=datetime(2026, 7, 16, tzinfo=UTC),
            )
            state_path.write_text("{}")
            restored = restore_state_backup(archive, work_dir)

            self.assertIn(state_path, restored)
            self.assertEqual(json.loads(state_path.read_text())["field-1"]["name"], "圃場A")
            self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)

    def test_restore_rejects_archive_without_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "invalid.tar.gz"
            payload = root / "payload"
            payload.write_text("invalid")
            with tarfile.open(archive, "w:gz") as output:
                output.add(payload, arcname="data/payload")

            with self.assertRaises(StateBackupError):
                restore_state_backup(archive, root / "work")


if __name__ == "__main__":
    unittest.main()
