import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ENV_PATH = Path("~/.config/inas/operations-api.env").expanduser()


class OperationsApiError(RuntimeError):
    pass


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0917 -- urllib override signature
        # Access credentials must never follow a redirect to login or another host.
        return None


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
        self.base_url = settings["INAS_HUB_OPERATIONS_URL"].rstrip("/")
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/operations/api/v1"
            or any(ord(value) < 33 for value in self.base_url)
        ):
            raise OperationsApiError("INAS_HUB_OPERATIONS_URL must be an HTTPS URL ending in /operations/api/v1 without credentials, query, or fragment")
        self.client_id = settings["CF_ACCESS_CLIENT_ID"]
        self.client_secret = settings["CF_ACCESS_CLIENT_SECRET"]
        self.timeout_sec = timeout_sec
        self.opener = build_opener(_RejectRedirects())

    def get(self, path: str, *, query: dict | None = None):
        suffix = f"?{urlencode(query, doseq=True)}" if query else ""
        return self._request("GET", f"{path}{suffix}")

    def post_json(self, path: str, payload: dict):
        return self._request("POST", path, body=json.dumps(payload, separators=(",", ":")).encode(), content_type="application/json")

    def post_binary(self, path: str, body: bytes):
        return self._request("POST", path, body=body, content_type="application/octet-stream")

    def get_image(self, path: str) -> tuple[bytes, str]:
        return self._request("GET", path, image=True)

    def _request(self, method: str, path: str, *, body: bytes | None = None, content_type: str | None = None, image: bool = False):
        parsed = urlsplit(path)
        decoded = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or parsed.fragment or "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/")):
            raise OperationsApiError("request must use a relative Operations API path")
        headers = {
            "CF-Access-Client-Id": self.client_id,
            "CF-Access-Client-Secret": self.client_secret,
            "Accept": "image/jpeg, image/png, image/webp" if image else "application/json",
            "User-Agent": "inas-hub-operations/1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(f"{self.base_url}/{path.lstrip('/')}", data=body, headers=headers, method=method)
        maximum_bytes = 10 * 1024 * 1024 if image else 2 * 1024 * 1024
        try:
            with self.opener.open(request, timeout=self.timeout_sec) as response:
                response_type = response.headers.get_content_type()
                payload = response.read(maximum_bytes + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise OperationsApiError(f"Operations API returned HTTP {status}; check machine authentication, permissions, and resource IDs") from None
        except (URLError, OSError):
            raise OperationsApiError("Operations API connection failed") from None
        if len(payload) > maximum_bytes:
            raise OperationsApiError("Operations API response exceeds the size limit")
        if image:
            if response_type not in {"image/jpeg", "image/png", "image/webp"} or not payload:
                raise OperationsApiError("Operations API did not return a supported image")
            return payload, response_type
        if response_type != "application/json":
            raise OperationsApiError("Operations API returned non-JSON content")
        try:
            return json.loads(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            raise OperationsApiError("Operations API returned non-JSON content") from exc
