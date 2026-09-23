"""Provision and revoke read-only collectors without rewriting host settings."""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

from ina_device_hub.cloudflare_token_connector import CloudflareTokenConnector, TokenProvisioningError, cloudflare_id
from ina_device_hub.collector_access_repository import CollectorAccessRepository

SCOPES = {"records:read", "images:read"}


def _now():
    return datetime.now(UTC)


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("invalid collector expiration")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError
    return parsed


def managed_grant(service_id):
    """None means unmanaged; inactive managed identities explicitly deny access."""
    records = CollectorAccessRepository().read()
    matches = [item for item in records.values() if item.get("service_id") == service_id]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("duplicate managed collector identity")
    item = matches[0]
    if item["status"] != "active" or _timestamp(item["expires_at"]) <= _now():
        raise ValueError("collector is inactive or expired")
    return {"scopes": item["scopes"], "field_ids": item["field_ids"]}


class CollectorAccessService:
    def __init__(self, fields, repository=None, connector=None):
        self.fields = fields
        self.repository = repository or CollectorAccessRepository()
        self.connector = connector or CloudflareTokenConnector()

    def list(self):
        items = list(self.repository.read().values())
        for item in items:
            if item["status"] == "active" and _timestamp(item["expires_at"]) <= _now():
                item["status"] = "expired"
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def _permissions(self, payload):
        scopes, fields = payload.get("scopes"), payload.get("field_ids")
        if not isinstance(scopes, list) or not scopes or any(not isinstance(scope, str) or scope not in SCOPES for scope in scopes):
            raise TokenProvisioningError("参照する情報を選んでください。")
        if not isinstance(fields, list) or not fields or any(not isinstance(value, str) for value in fields):
            raise TokenProvisioningError("参照する圃場を選んでください。")
        if fields != ["*"] and not set(fields) <= {field["id"] for field in self.fields.list()}:
            raise TokenProvisioningError("選択した圃場が見つかりません。")
        return sorted(set(scopes)), sorted(set(fields))

    def issue(self, payload, actor):
        name = payload.get("name")
        days = payload.get("days")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise TokenProvisioningError("接続名は 1〜80 文字で入力してください。")
        if type(days) is not int or days not in {7, 30, 90, 365}:
            raise TokenProvisioningError("有効期限を選んでください。")
        scopes, fields = self._permissions(payload)
        self.connector.verify_application()
        now = _now()
        item = {
            "id": uuid.uuid4().hex,
            "name": name.strip(),
            "status": "pending",
            "scopes": scopes,
            "field_ids": fields,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=days)).isoformat(),
            "updated_at": now.isoformat(),
            "updated_by": actor,
            "account_id": self.connector.account_id,
            "app_id": self.connector.app_id,
            "cleanup_pending": False,
        }
        with self.repository.lock():
            records = self.repository.read()
            records[item["id"]] = item
            self.repository.write(records)
            try:
                token = self.connector.create_token(f"inas-collector-{item['id']}", days)
                item["token_id"] = cloudflare_id(token.get("id"))
                service_id = token.get("client_id")
                secret = token.get("client_secret")
                if not isinstance(service_id, str) or not service_id or len(service_id) > 512 or any(ord(c) < 33 or ord(c) == 127 for c in service_id):
                    raise TokenProvisioningError("発行された接続 ID を確認できませんでした。")
                item["service_id"] = service_id
                self.repository.write(records)
                host_grants = json.loads(os.environ.get("HUB_OPERATIONS_READ_GRANTS", "{}") or "{}")
                writers = {value.strip() for value in os.environ.get("HUB_OPERATIONS_SERVICE_IDS", "").split(",")}
                if not isinstance(host_grants, dict) or service_id in host_grants or service_id in writers:
                    raise TokenProvisioningError("既存の接続 ID と重複しています。")
                if not isinstance(secret, str) or not secret or any(ord(c) < 33 or ord(c) == 127 for c in secret):
                    raise TokenProvisioningError("発行された接続情報を確認できませんでした。")
                policy = self.connector.create_policy(f"inas-collector-{item['id']}", item["token_id"])
                item["policy_id"] = cloudflare_id(policy.get("id"))
                item["status"] = "active"
                self.repository.write(records)
            except Exception:
                item["status"] = "revoked"
                item["cleanup_pending"] = True
                self.repository.write(records)
                try:
                    self._cleanup(item)
                    item["cleanup_pending"] = False
                    self.repository.write(records)
                except (TokenProvisioningError, OSError):
                    pass
                raise TokenProvisioningError("発行を完了できませんでした。接続一覧で停止状態を確認してください。") from None
        return {"collector": item, "client_id": service_id, "client_secret": secret}

    def update(self, collector_id, payload, actor):
        scopes, fields = self._permissions(payload)
        with self.repository.lock():
            records = self.repository.read()
            item = records.get(collector_id)
            if item is None or item["status"] != "active" or _timestamp(item["expires_at"]) <= _now():
                raise TokenProvisioningError("有効な接続が見つかりません。")
            item.update(scopes=scopes, field_ids=fields, updated_at=_now().isoformat(), updated_by=actor)
            self.repository.write(records)
            return item

    def _cleanup(self, item):
        if item["account_id"] != self.connector.account_id:
            raise TokenProvisioningError("発行時の Cloudflare アカウントを設定してください。")
        if not item.get("token_id"):
            raise TokenProvisioningError("発行結果が不明です。Cloudflare 側で接続名に対応する Token を確認してください。")
        # Delete the credential first. Local access is already denied even when
        # Cloudflare is unavailable or the policy cleanup needs a retry.
        if item.get("token_id"):
            self.connector.delete_token(item["token_id"])
        if item.get("policy_id"):
            self.connector.delete_policy(item["app_id"], item["policy_id"])

    def revoke(self, collector_id, actor):
        with self.repository.lock():
            records = self.repository.read()
            item = records.get(collector_id)
            if item is None:
                raise TokenProvisioningError("接続が見つかりません。")
            item.update(status="revoked", cleanup_pending=True, updated_at=_now().isoformat(), updated_by=actor)
            self.repository.write(records)
            try:
                self._cleanup(item)
                item["cleanup_pending"] = False
                self.repository.write(records)
            except TokenProvisioningError:
                pass
            return item
