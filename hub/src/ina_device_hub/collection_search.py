"""Shared query normalization and pagination for searchable Hub collections."""

import math
import re
import unicodedata

_SEPARATOR_RE = re.compile(r"[\s\u3000・_\-/]+")


def normalize_search_text(value) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("灌", "潅")
    return _SEPARATOR_RE.sub("", normalized)


def search_terms(query, *, max_length: int = 200) -> tuple[str, ...]:
    raw = unicodedata.normalize("NFKC", str(query or "")).strip()[:max_length]
    return tuple(term for part in re.split(r"[\s\u3000]+", raw) if (term := normalize_search_text(part)))


def matches_search(terms: tuple[str, ...], values) -> bool:
    if not terms:
        return True
    haystack = normalize_search_text(" ".join(_flatten_search_values(values)))
    return all(term in haystack for term in terms)


def paginate(items: list, *, page=1, page_size=50, maximum_page_size: int = 100) -> dict:
    try:
        page = max(1, int(page))
        page_size = min(maximum_page_size, max(1, int(page_size)))
    except (TypeError, ValueError) as exc:
        raise ValueError("page and page_size must be integers") from exc
    total = len(items)
    page_count = max(1, math.ceil(total / page_size))
    page = min(page, page_count)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": page_count,
        "has_previous": page > 1,
        "has_next": page < page_count,
    }


def _flatten_search_values(value):
    if value is None:
        return []
    if isinstance(value, dict):
        flattened = []
        for key, item in value.items():
            flattened.extend(_flatten_search_values(key))
            flattened.extend(_flatten_search_values(item))
        return flattened
    if isinstance(value, list | tuple | set):
        flattened = []
        for item in value:
            flattened.extend(_flatten_search_values(item))
        return flattened
    return [str(value)]
