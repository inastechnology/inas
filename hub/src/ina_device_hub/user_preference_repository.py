import json
import threading
from copy import deepcopy
from functools import lru_cache

from ina_device_hub.ina_db_connector import InaDBConnector, _sync_if_supported

SUPPORTED_TIMEZONES = {"Asia/Tokyo", "UTC"}
SUPPORTED_DATE_FORMATS = {"yyyy-MM-dd", "yyyy/MM/dd", "MM/dd/yyyy"}
SUPPORTED_CULTIVATION_EXPERIENCE_LEVELS = {"beginner", "standard", "professional"}
DEFAULT_CULTIVATION_EXPERIENCE_LEVEL = "standard"


class UserPreferenceValidationError(ValueError):
    pass


class UserPreferenceConflictError(ValueError):
    def __init__(self, current):
        super().__init__("preferences were updated by another session")
        self.current = current


class UserPreferenceRepository:
    def __init__(self, db_connector: InaDBConnector):
        self.db_connector = db_connector
        self._write_lock = threading.RLock()
        self._ensure_table()

    def _ensure_table(self):
        self.db_connector.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_email TEXT PRIMARY KEY,
                locale TEXT NOT NULL DEFAULT 'ja',
                timezone TEXT NOT NULL DEFAULT 'Asia/Tokyo',
                date_format TEXT NOT NULL DEFAULT 'yyyy-MM-dd',
                preferences_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.db_connector.conn.commit()
        _sync_if_supported(self.db_connector.conn)

    def get(self, user_email: str):
        with self._write_lock:
            row = self.db_connector.conn.execute(
                """
                SELECT user_email, locale, timezone, date_format, preferences_json, version, created_at, updated_at
                FROM user_preferences WHERE lower(user_email) = lower(?)
                """,
                (user_email,),
            ).fetchone()
        return _row_to_preferences(row) if row else _default_preferences(user_email)

    def update(self, user_email: str, value: dict, expected_version: int):
        normalized = _normalize_preferences(user_email, value)
        with self._write_lock:
            connection = self.db_connector.conn
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT user_email, locale, timezone, date_format, preferences_json, version, created_at, updated_at
                    FROM user_preferences WHERE lower(user_email) = lower(?)
                    """,
                    (user_email,),
                ).fetchone()
                current = _row_to_preferences(row) if row else _default_preferences(user_email)
                if current["version"] != expected_version:
                    connection.rollback()
                    raise UserPreferenceConflictError(current)

                next_version = expected_version + 1
                if row:
                    connection.execute(
                        """
                        UPDATE user_preferences
                        SET locale = ?, timezone = ?, date_format = ?, preferences_json = ?,
                            version = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE lower(user_email) = lower(?) AND version = ?
                        """,
                        (
                            normalized["locale"],
                            normalized["timezone"],
                            normalized["date_format"],
                            json.dumps(normalized["preferences"], ensure_ascii=False, separators=(",", ":")),
                            next_version,
                            user_email,
                            expected_version,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO user_preferences (
                            user_email, locale, timezone, date_format, preferences_json, version
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_email,
                            normalized["locale"],
                            normalized["timezone"],
                            normalized["date_format"],
                            json.dumps(normalized["preferences"], ensure_ascii=False, separators=(",", ":")),
                            next_version,
                        ),
                    )
                connection.commit()
            except UserPreferenceConflictError:
                raise
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            _sync_if_supported(connection)
        return self.get(user_email)


def effective_preferences(repository, user_email: str):
    return repository.get(user_email)


def _default_preferences(user_email: str):
    return {
        "user_email": user_email.lower(),
        "locale": "ja",
        "timezone": "Asia/Tokyo",
        "date_format": "yyyy-MM-dd",
        "preferences": {"cultivation_experience": DEFAULT_CULTIVATION_EXPERIENCE_LEVEL},
        "version": 0,
        "created_at": "",
        "updated_at": "",
    }


def _normalize_preferences(user_email: str, value: dict):
    if not isinstance(value, dict):
        raise UserPreferenceValidationError("preferences must be an object")
    timezone = str(value.get("timezone") or "Asia/Tokyo")
    date_format = str(value.get("date_format") or "yyyy-MM-dd")
    preferences = value.get("preferences") if isinstance(value.get("preferences"), dict) else {}
    if timezone not in SUPPORTED_TIMEZONES:
        raise UserPreferenceValidationError("unsupported timezone")
    if date_format not in SUPPORTED_DATE_FORMATS:
        raise UserPreferenceValidationError("unsupported date format")
    cultivation_experience = str(preferences.get("cultivation_experience") or DEFAULT_CULTIVATION_EXPERIENCE_LEVEL)
    if cultivation_experience not in SUPPORTED_CULTIVATION_EXPERIENCE_LEVELS:
        raise UserPreferenceValidationError("unsupported cultivation experience level")
    preferences = {**preferences, "cultivation_experience": cultivation_experience}
    serialized = json.dumps(preferences, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > 16 * 1024:
        raise UserPreferenceValidationError("preferences are too large")
    return {
        "user_email": user_email.lower(),
        "locale": "ja",
        "timezone": timezone,
        "date_format": date_format,
        "preferences": deepcopy(preferences),
    }


def _row_to_preferences(row):
    try:
        preferences = json.loads(row[4] or "{}")
    except json.JSONDecodeError:
        preferences = {}
    if not isinstance(preferences, dict):
        preferences = {}
    cultivation_experience = str(preferences.get("cultivation_experience") or DEFAULT_CULTIVATION_EXPERIENCE_LEVEL)
    if cultivation_experience not in SUPPORTED_CULTIVATION_EXPERIENCE_LEVELS:
        cultivation_experience = DEFAULT_CULTIVATION_EXPERIENCE_LEVEL
    preferences["cultivation_experience"] = cultivation_experience
    return {
        "user_email": row[0],
        # Kept in the schema for compatibility; Hub UI content is authored in Japanese.
        "locale": "ja",
        "timezone": row[2],
        "date_format": row[3],
        "preferences": preferences,
        "version": int(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }


@lru_cache(maxsize=1)
def user_preference_repository(db_connector: InaDBConnector | None = None):
    return UserPreferenceRepository(db_connector or InaDBConnector())
