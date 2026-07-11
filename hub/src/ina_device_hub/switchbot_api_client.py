import base64
import hashlib
import hmac
import json
import time
import uuid
from urllib import error, request
from urllib.parse import quote

from ina_device_hub.setting import setting


class SwitchBotAPIError(RuntimeError):
    def __init__(self, message: str, http_status: int | None = None, api_status: int | None = None, body: dict | str | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.api_status = api_status
        self.body = body


class SwitchBotAPIClient:
    DEFAULT_BASE_URL = "https://api.switch-bot.com"

    def __init__(
        self,
        token: str | None = None,
        secret: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        nonce_factory=None,
        clock=None,
    ):
        switchbot_settings = setting().get("switchbot") or {}
        self.token = (token if token is not None else switchbot_settings.get("open_token", "")).strip()
        self.secret = (secret if secret is not None else switchbot_settings.get("secret_key", "")).strip()
        self.base_url = (base_url if base_url is not None else switchbot_settings.get("base_url", self.DEFAULT_BASE_URL)).strip().rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else int(switchbot_settings.get("timeout_seconds", 20))
        self.nonce_factory = nonce_factory or uuid.uuid4
        self.clock = clock or time.time

    def get_devices(self):
        return self._request("GET", "/v1.1/devices").get("body", {})

    def get_device_status(self, device_id: str):
        return self._request("GET", f"/v1.1/devices/{quote(device_id, safe='')}/status").get("body", {})

    def send_device_command(self, device_id: str, command: str, parameter="default", command_type: str = "command"):
        payload = {
            "commandType": command_type,
            "command": command,
            "parameter": parameter,
        }
        return self._request("POST", f"/v1.1/devices/{quote(device_id, safe='')}/commands", payload).get("body", {})

    def _request(self, method: str, path: str, payload: dict | None = None):
        self._validate_credentials()
        data = None
        headers = self._build_headers()
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf8"

        req = request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise SwitchBotAPIError(f"SwitchBot API HTTP error: {exc.code}: {detail}", http_status=exc.code, body=detail) from exc
        except (error.URLError, json.JSONDecodeError) as exc:
            raise SwitchBotAPIError(f"SwitchBot API request failed: {exc}") from exc

        api_status = response_body.get("statusCode")
        if api_status != 100:
            raise SwitchBotAPIError(
                f"SwitchBot API error: statusCode={api_status}, message={response_body.get('message')}",
                api_status=api_status,
                body=response_body,
            )
        return response_body

    def _build_headers(self):
        timestamp = str(int(round(self.clock() * 1000)))
        nonce = str(self.nonce_factory())
        string_to_sign = f"{self.token}{timestamp}{nonce}".encode()
        secret = self.secret.encode()
        sign = base64.b64encode(hmac.new(secret, msg=string_to_sign, digestmod=hashlib.sha256).digest()).decode("utf-8")
        return {
            "Authorization": self.token,
            "sign": sign,
            "t": timestamp,
            "nonce": nonce,
        }

    def _validate_credentials(self):
        if not self.token or not self.secret:
            raise ValueError("SwitchBot open token and secret key must be configured")
