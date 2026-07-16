import tempfile
import unittest
from pathlib import Path

import libsql

from ina_device_hub.user_preference_repository import (
    UserPreferenceConflictError,
    UserPreferenceRepository,
    UserPreferenceValidationError,
    effective_preferences,
)


class LocalConnector:
    def __init__(self, path: Path):
        self.conn = libsql.connect(str(path))


class UserPreferenceRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "preferences.db"
        self.connector = LocalConnector(self.database_path)
        self.repository = UserPreferenceRepository(self.connector)

    def tearDown(self):
        self.connector.conn.close()
        self.temporary_directory.cleanup()

    def test_effective_preferences_are_fixed_to_japanese(self):
        preferences = effective_preferences(self.repository, "worker@example.com")

        self.assertEqual(preferences["locale"], "ja")
        self.assertEqual(preferences["version"], 0)
        self.assertEqual(preferences["preferences"]["cultivation_experience"], "standard")

    def test_update_is_scoped_by_email_and_increments_version(self):
        saved = self.repository.update(
            "worker@example.com",
            {"locale": "en", "timezone": "UTC", "date_format": "MM/dd/yyyy", "preferences": {}},
            expected_version=0,
        )

        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["locale"], "ja")
        self.assertEqual(self.repository.get("other@example.com")["version"], 0)

    def test_stale_update_returns_current_preferences(self):
        first = self.repository.update(
            "worker@example.com",
            {"locale": "ja", "timezone": "Asia/Tokyo", "date_format": "yyyy-MM-dd"},
            expected_version=0,
        )

        with self.assertRaises(UserPreferenceConflictError) as raised:
            self.repository.update(
                "worker@example.com",
                {"locale": "en", "timezone": "UTC", "date_format": "MM/dd/yyyy"},
                expected_version=0,
            )

        self.assertEqual(raised.exception.current["version"], first["version"])
        self.assertEqual(raised.exception.current["locale"], "ja")

    def test_two_repository_instances_do_not_overwrite_a_stale_save(self):
        second_connector = LocalConnector(self.database_path)
        second_repository = UserPreferenceRepository(second_connector)
        try:
            self.repository.update(
                "worker@example.com",
                {"locale": "ja", "timezone": "Asia/Tokyo", "date_format": "yyyy-MM-dd"},
                expected_version=0,
            )
            with self.assertRaises(UserPreferenceConflictError):
                second_repository.update(
                    "worker@example.com",
                    {"locale": "en", "timezone": "UTC", "date_format": "MM/dd/yyyy"},
                    expected_version=0,
                )
        finally:
            second_connector.conn.close()

    def test_ignores_legacy_locale_input(self):
        saved = self.repository.update(
            "worker@example.com",
            {"locale": "en", "timezone": "Asia/Tokyo", "date_format": "yyyy-MM-dd"},
            expected_version=0,
        )

        self.assertEqual(saved["locale"], "ja")

    def test_cultivation_experience_is_validated_and_saved_per_user(self):
        saved = self.repository.update(
            "beginner@example.com",
            {
                "timezone": "Asia/Tokyo",
                "date_format": "yyyy-MM-dd",
                "preferences": {"cultivation_experience": "beginner"},
            },
            expected_version=0,
        )

        self.assertEqual(saved["preferences"]["cultivation_experience"], "beginner")
        self.assertEqual(self.repository.get("other@example.com")["preferences"]["cultivation_experience"], "standard")
        with self.assertRaises(UserPreferenceValidationError):
            self.repository.update(
                "invalid@example.com",
                {
                    "timezone": "Asia/Tokyo",
                    "date_format": "yyyy-MM-dd",
                    "preferences": {"cultivation_experience": "expert-plus"},
                },
                expected_version=0,
            )


if __name__ == "__main__":
    unittest.main()
