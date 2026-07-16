import os
import re
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"
ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
CURRENT_USER_ENV_KEY = "ina.current_user"


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

    if authentication_mode() == "local":
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
    if not token:
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


def _verify_access_token(token: str, team_domain: str, audience: str) -> dict:
    signing_key = _jwk_client(team_domain).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=team_domain,
        options={"require": ["exp", "iat"]},
    )


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
    return email if EMAIL_PATTERN.fullmatch(email) else ""


def _normalized_team_domain(value) -> str:
    domain = str(value or "").strip().rstrip("/")
    if not domain:
        return ""
    return domain if domain.startswith(("https://", "http://")) else f"https://{domain}"
