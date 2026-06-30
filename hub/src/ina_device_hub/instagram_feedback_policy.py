import re

MAX_COMMENT_LENGTH = 220

_SECURITY_PATTERNS = [
    re.compile(r"\b(security|secure|auth|token|password|secret|credential|vulnerability|exploit|attack|hack)\b", re.IGNORECASE),
    re.compile(r"\bapi[\s_-]*key\b", re.IGNORECASE),
    re.compile(r"(セキュリティ|認証|認可|権限|パスワード|秘密鍵|脆弱性|攻撃|ハック|トークン|クレデンシャル)"),
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RUNS = re.compile(r"\s+")


def sanitize_comment_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _CONTROL_CHARS.sub("", text)
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = _SPACE_RUNS.sub(" ", cleaned).strip()
    if len(cleaned) > MAX_COMMENT_LENGTH:
        cleaned = cleaned[:MAX_COMMENT_LENGTH].rstrip() + "..."
    return cleaned


def is_security_related(text: str) -> bool:
    normalized = sanitize_comment_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _SECURITY_PATTERNS)


def is_weekly_recap_day(weekday_index: int) -> bool:
    return weekday_index == 6


def collect_comment_feedback(
    comments: list[dict],
    admin_username: str,
    *,
    max_items: int = 10,
) -> dict:
    normalized_admin = (admin_username or "").strip().lower()
    admin_instructions: list[str] = []
    general_topics: list[str] = []
    for comment in comments:
        text = sanitize_comment_text(comment.get("text") or "")
        if not text:
            continue
        username = (comment.get("username") or "").strip().lower()
        if username == normalized_admin:
            admin_instructions.append(text)
            continue
        if is_security_related(text):
            continue
        general_topics.append(text)

    return {
        "admin_username": normalized_admin,
        "admin_instructions": admin_instructions[:max_items],
        "general_topics": general_topics[:max_items],
        "total_comments": len(comments),
    }
