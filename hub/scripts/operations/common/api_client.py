import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_ENV_PATH = Path("~/.config/inas/operations-api.env").expanduser()


class OperationsApiError(RuntimeError):
    pass


def load_operations_env(path: str | Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    env_path = Path(path).expanduser()
    values = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "INAS_HUB_OPERATIONS_URL"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    missing = [key for key in ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "INAS_HUB_OPERATIONS_URL") if not values.get(key)]
    if missing:
        raise OperationsApiError(f"missing Operations API settings: {', '.join(missing)}")
    values["INAS_HUB_OPERATIONS_URL"] = values["INAS_HUB_OPERATIONS_URL"].rstrip("/")
    return values


class OperationsApiClient:
    def __init__(self, settings: dict[str, str], *, timeout_sec: int = 60):
        self.base_url = settings["INAS_HUB_OPERATIONS_URL"]
        self.client_id = settings["CF_ACCESS_CLIENT_ID"]
        self.client_secret = settings["CF_ACCESS_CLIENT_SECRET"]
        self.timeout_sec = timeout_sec

    def get(self, path: str, *, query: dict | None = None):
        suffix = f"?{urlencode(query, doseq=True)}" if query else ""
        return self._request("GET", f"{path}{suffix}")

    def post_json(self, path: str, payload: dict):
        return self._request("POST", path, body=json.dumps(payload, separators=(",", ":")).encode(), content_type="application/json")

    def post_binary(self, path: str, body: bytes):
        return self._request("POST", path, body=body, content_type="application/octet-stream")

    def _request(self, method: str, path: str, *, body: bytes | None = None, content_type: str | None = None):
        headers = {
            "CF-Access-Client-Id": self.client_id,
            "CF-Access-Client-Secret": self.client_secret,
            "Accept": "application/json",
            "User-Agent": "inas-hub-operations/1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(f"{self.base_url}/{path.lstrip('/')}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:  # noqa: S310
                payload = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OperationsApiError(f"Operations API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OperationsApiError(f"Operations API connection failed: {exc.reason}") from exc
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OperationsApiError("Operations API returned non-JSON content") from exc
