"""Shared configuration helpers for Cloudflare setup commands."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


class ScriptError(RuntimeError):
    """Report a setup error that should be shown without a traceback."""


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def merged_env(env_file: Path) -> dict[str, str]:
    values = parse_env_file(env_file)
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def quote_env_value(value: str) -> str:
    if not value:
        return ""
    if re.search(r"\s|#|['\"]", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0]
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        else:
            key = key.strip()

        if key in updates:
            output.append(f"{key}={quote_env_value(updates[key])}")
            seen.add(key)
        else:
            output.append(line)

    if output and output[-1] != "":
        output.append("")
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={quote_env_value(value)}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    path.chmod(0o600)


def require_value(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ScriptError(f"Missing required env value: {key}")
    return value


def require_any_value(env: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    raise ScriptError(f"Missing required env value: one of {', '.join(keys)}")
