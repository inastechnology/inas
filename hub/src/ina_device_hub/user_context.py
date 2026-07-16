import os
import re
from dataclasses import dataclass

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"


@dataclass(frozen=True)
class CurrentUser:
    email: str
    role: str
    authenticated: bool


def current_user_from_request(request) -> CurrentUser:
    email = str(request.headers.get(ACCESS_EMAIL_HEADER) or "").strip().lower()

    authenticated = bool(email and EMAIL_PATTERN.fullmatch(email))
    if not authenticated:
        email = os.environ.get("HUB_LOCAL_USER_EMAIL", "local-user@ina.local").strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            email = "local-user@ina.local"

    admin_emails = {
        value.strip().lower()
        for value in os.environ.get("HUB_ADMIN_EMAILS", "").split(",")
        if EMAIL_PATTERN.fullmatch(value.strip().lower())
    }
    role = "admin" if email in admin_emails or not authenticated else "operator"
    return CurrentUser(email=email, role=role, authenticated=authenticated)
