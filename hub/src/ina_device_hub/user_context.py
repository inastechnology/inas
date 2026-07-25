import os
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"
ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
CURRENT_USER_ENV_KEY = "ina.current_user"
OPERATIONS_API_PATH_PREFIX = "/operations/api/"


class AccessAuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class CurrentUser:
    email: str
    role: str
    authenticated: bool


def authentication_mode() -> str:
    return os.environ.get("HUB_AUTH_MODE", "local").strip().lower() or "local"


def authenticate_request(request) -> CurrentUser:
    cached = request.environ.get(CURRENT_USER_ENV_KEY)
    if isinstance(cached, CurrentUser):
        return cached

    if request.path.startswith(OPERATIONS_API_PATH_PREFIX):
        user = _operations_service_user(request)
    elif authentication_mode() == "local":
        user = _local_user(request)
    elif authentication_mode() == "cloudflare_access":
        user = _cloudflare_access_user(request)
    else:
        raise AccessAuthenticationError("unsupported HUB_AUTH_MODE")

    request.environ[CURRENT_USER_ENV_KEY] = user
    return user


def current_user_from_request(request) -> CurrentUser:
    return authenticate_request(request)


def _local_user(request) -> CurrentUser:
    email = _normalized_email(request.headers.get(ACCESS_EMAIL_HEADER))
    authenticated = bool(email)
    if not email:
        email = _normalized_email(os.environ.get("HUB_LOCAL_USER_EMAIL")) or "local-user@ina.local"
    return CurrentUser(email=email, role=_role_for_email(email, local_fallback=not authenticated), authenticated=authenticated)


def _cloudflare_access_user(request) -> CurrentUser:
    token = str(request.headers.get(ACCESS_JWT_HEADER) or "").strip()
    if not token or len(token) > 16_384:
        raise AccessAuthenticationError("missing Cloudflare Access JWT")

    team_domain = _normalized_team_domain(os.environ.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN"))
    audience = os.environ.get("CLOUDFLARE_ACCESS_POLICY_AUD", "").strip()
    if not team_domain or not audience:
        raise AccessAuthenticationError("Cloudflare Access verification is not configured")

    try:
        payload = _verify_access_token(token, team_domain, audience)
    except Exception as exc:
        raise AccessAuthenticationError("invalid Cloudflare Access JWT") from exc

    email = _normalized_email(payload.get("email"))
    if not email:
        raise AccessAuthenticationError("Cloudflare Access JWT does not contain a valid email")

    header_email = _normalized_email(request.headers.get(ACCESS_EMAIL_HEADER))
    if header_email and header_email != email:
        raise AccessAuthenticationError("Cloudflare Access identity headers do not match")
    return CurrentUser(email=email, role=_role_for_email(email), authenticated=True)


def _operations_service_user(request) -> CurrentUser:
    if authentication_mode() != "cloudflare_access":
        raise AccessAuthenticationError("operations API requires cloudflare_access authentication")
    token = str(request.headers.get(ACCESS_JWT_HEADER) or "").strip()
    if not token or len(token) > 16_384:
        raise AccessAuthenticationError("missing Cloudflare Access JWT")
    team_domain = _normalized_team_domain(os.environ.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN"))
    audience = os.environ.get("CLOUDFLARE_ACCESS_POLICY_AUD", "").strip()
    if not team_domain or not audience:
        raise AccessAuthenticationError("Cloudflare Access verification is not configured")
    try:
        payload = _verify_access_token(token, team_domain, audience)
    except Exception as exc:
        raise AccessAuthenticationError("invalid Cloudflare Access JWT") from exc
    service_id = str(payload.get("common_name") or "").strip()
    allowed_ids = {value.strip() for value in os.environ.get("HUB_OPERATIONS_SERVICE_IDS", "").split(",") if value.strip()}
    if not service_id or len(service_id) > 512 or _has_control_character(service_id) or service_id not in allowed_ids:
        raise AccessAuthenticationError("Cloudflare Access service is not allowed")
    return CurrentUser(email=f"service:{service_id}", role="service", authenticated=True)


def _verify_access_token(token: str, team_domain: str, audience: str) -> dict:
    signing_key = _jwk_client(team_domain).get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=team_domain,
        options={"require": ["exp", "iat", "nbf", "sub"]},
        leeway=10,
    )
    _validate_access_application_claims(payload)
    return payload


def _validate_access_application_claims(payload: dict) -> None:
    subject = payload.get("sub")
    issued_at = payload.get("iat")
    not_before = payload.get("nbf")
    expires_at = payload.get("exp")
    if (
        payload.get("type") != "app"
        or not isinstance(subject, str)
        or not subject
        or len(subject) > 512
        or _has_control_character(subject)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in (issued_at, not_before, expires_at))
        or expires_at <= issued_at
        or expires_at < not_before
    ):
        raise AccessAuthenticationError("invalid Cloudflare Access application claims")


@lru_cache(maxsize=8)
def _jwk_client(team_domain: str) -> PyJWKClient:
    return PyJWKClient(
        f"{team_domain}/cdn-cgi/access/certs",
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=300,
        timeout=5,
    )


def _role_for_email(email: str, *, local_fallback: bool = False) -> str:
    admin_emails = {normalized for value in os.environ.get("HUB_ADMIN_EMAILS", "").split(",") if (normalized := _normalized_email(value))}
    return "admin" if local_fallback or email in admin_emails else "operator"


def _normalized_email(value) -> str:
    email = str(value or "").strip().lower()
    return email if len(email) <= 254 and not _has_control_character(email) and EMAIL_PATTERN.fullmatch(email) else ""


def _normalized_team_domain(value) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".cloudflareaccess.com")
        or not _valid_dns_hostname(hostname)
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return f"https://{hostname}"


def _valid_dns_hostname(hostname: str) -> bool:
    return len(hostname) <= 253 and all(1 <= len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in hostname.split("."))


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
