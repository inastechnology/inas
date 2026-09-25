"""Host-local collector metadata and grants. Client secrets are never stored."""

import json
import os
from datetime import datetime
from pathlib import Path

from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock


class CollectorStorageError(ValueError):
    pass


class CollectorAccessRepository:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("WORK_DIR", "~/.ina-device-hub")).expanduser() / "operations_collectors.json"

    def lock(self):
        return repository_file_lock(str(self.path))

    def read(self):
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("collectors"), dict):
                raise ValueError
            for key, item in data["collectors"].items():
                if not isinstance(item, dict) or item.get("id") != key or item.get("status") not in {"pending", "active", "revoked"}:
                    raise ValueError
                if not all(
                    isinstance(item.get(name), str) and item[name]
                    for name in ("name", "created_at", "expires_at", "updated_at", "updated_by", "account_id", "app_id")
                ):
                    raise ValueError
                for name in ("created_at", "expires_at", "updated_at"):
                    if name == "expires_at" and item[name] == "forever":
                        continue
                    if datetime.fromisoformat(item[name].replace("Z", "+00:00")).tzinfo is None:
                        raise ValueError
                if (
                    not isinstance(item.get("scopes"), list)
                    or not item["scopes"]
                    or any(scope not in {"records:read", "images:read"} for scope in item["scopes"])
                ):
                    raise ValueError
                if (
                    not isinstance(item.get("field_ids"), list)
                    or not item["field_ids"]
                    or any(not isinstance(value, str) or not value for value in item["field_ids"])
                ):
                    raise ValueError
                if item["status"] == "active" and not all(isinstance(item.get(name), str) and item[name] for name in ("service_id", "token_id", "policy_id")):
                    raise ValueError
            return data["collectors"]
        except (OSError, ValueError, TypeError):
            raise CollectorStorageError("AI 接続の保存情報を読み取れません。管理者に確認してください。") from None

    def write(self, records):
        # Explicit allowlist prevents accidentally persisting an API response.
        keys = {
            "id",
            "name",
            "status",
            "service_id",
            "token_id",
            "policy_id",
            "account_id",
            "app_id",
            "scopes",
            "field_ids",
            "created_at",
            "expires_at",
            "updated_at",
            "updated_by",
            "cleanup_pending",
        }
        if any(set(item) - keys for item in records.values()):
            raise CollectorStorageError("AI 接続の保存形式が不正です。")
        atomic_write_json(str(self.path), {"version": 1, "collectors": records})
