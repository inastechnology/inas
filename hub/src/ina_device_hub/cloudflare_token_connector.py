"""Cloudflare management transport; never expose provider bodies or secrets."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class TokenProvisioningError(ValueError):
    pass


def cloudflare_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", value):
        raise TokenProvisioningError("Cloudflare の識別情報を確認してください。")
    return value


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0917
        return None


class CloudflareTokenConnector:
    def __init__(self):
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        self.app_id = os.environ.get("HUB_COLLECTOR_ACCESS_APP_ID", "").strip()
        self._token = os.environ.get("HUB_COLLECTOR_TOKEN_API_TOKEN", "").strip()
        self.opener = build_opener(_NoRedirects())

    @property
    def configured(self):
        return bool(self.account_id and self.app_id and self._token and os.environ.get("HUB_AUTH_MODE") == "cloudflare_access")

    def request(self, method, path, body=None):
        if not self.configured:
            raise TokenProvisioningError("管理者による AI 接続の初期設定が必要です。")
        account = cloudflare_id(self.account_id)
        request = Request(
            f"https://api.cloudflare.com/client/v4/accounts/{account}/access/{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json", "Accept": "application/json"},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if method == "DELETE" and status == 404:
                return {}
            raise TokenProvisioningError(f"Cloudflare との通信に失敗しました（HTTP {status}）。") from None
        except (URLError, OSError):
            raise TokenProvisioningError("Cloudflare に接続できませんでした。") from None
        try:
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get("result"), dict):
                raise ValueError
            return payload["result"]
        except (ValueError, UnicodeError):
            raise TokenProvisioningError("Cloudflare からの応答を確認できませんでした。") from None

    def verify_application(self):
        app = self.request("GET", f"apps/{cloudflare_id(self.app_id)}")
        audience = os.environ.get("CLOUDFLARE_ACCESS_POLICY_AUD", "").strip()
        if not audience or app.get("aud") != audience or app.get("type") != "self_hosted":
            raise TokenProvisioningError("AI 接続先の Access アプリが Hub の認証設定と一致しません。")

    def create_token(self, name, days):
        return self.request("POST", "service_tokens", {"name": name, "duration": f"{days * 24}h"})

    def create_policy(self, name, token_id):
        return self.request(
            "POST",
            f"apps/{cloudflare_id(self.app_id)}/policies",
            {"name": name, "decision": "non_identity", "include": [{"service_token": {"token_id": cloudflare_id(token_id)}}]},
        )

    def delete_policy(self, app_id, policy_id):
        return self.request("DELETE", f"apps/{cloudflare_id(app_id)}/policies/{cloudflare_id(policy_id)}")

    def delete_token(self, token_id):
        return self.request("DELETE", f"service_tokens/{cloudflare_id(token_id)}")
