"""Per-service grants for read-only Operations collectors."""

import json
import os
import re
from dataclasses import dataclass

READ_SCOPES = frozenset({"records:read", "images:read"})
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,179}\Z")


class OperationsPermissionError(ValueError):
    pass


@dataclass(frozen=True)
class ReadGrant:
    scopes: frozenset[str]
    field_ids: frozenset[str]

    def allows_field(self, field_id: str) -> bool:
        return "*" in self.field_ids or field_id in self.field_ids

    def require(self, scope: str, field_id: str | None = None):
        if scope not in self.scopes or (field_id is not None and not self.allows_field(field_id)):
            raise OperationsPermissionError("operation is not permitted for this collector")


def read_grant_for_actor(actor: str) -> ReadGrant | None:
    """Malformed configuration must never turn a reader into a legacy writer."""
    try:
        values = json.loads(os.environ.get("HUB_OPERATIONS_READ_GRANTS", "{}").strip() or "{}")
        if not isinstance(values, dict):
            raise ValueError
        grants = {}
        for service_id, value in values.items():
            if not isinstance(service_id, str) or not service_id or not isinstance(value, dict) or set(value) != {"scopes", "field_ids"}:
                raise ValueError
            scopes, fields = value["scopes"], value["field_ids"]
            if not isinstance(scopes, list) or not scopes or any(not isinstance(scope, str) or scope not in READ_SCOPES for scope in scopes):
                raise ValueError
            if (
                not isinstance(fields, list)
                or not fields
                or any(not isinstance(item, str) or (item != "*" and not IDENTIFIER.fullmatch(item)) for item in fields)
            ):
                raise ValueError
            grants[f"service:{service_id}"] = ReadGrant(frozenset(scopes), frozenset(fields))
        return grants.get(actor)
    except (ValueError, TypeError, RecursionError) as exc:
        raise OperationsPermissionError("Operations read grants are not configured correctly") from exc
