from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DiagnosticProfileError(ValueError):
    pass


@dataclass(frozen=True)
class StatusField:
    field_id: str
    label: str
    json_key: str
    true_label: str
    false_label: str
    false_severity: str
    unit: str


@dataclass(frozen=True)
class LineStatusRule:
    field_id: str
    label: str
    pattern: re.Pattern[str]
    value_group: str
    value_map: dict[str, str]
    severity_map: dict[str, str]


@dataclass(frozen=True)
class DeviceRule:
    pattern: re.Pattern[str]
    identity_template: str
    display_template: str


@dataclass(frozen=True)
class ErrorRule:
    pattern: re.Pattern[str]
    severity: str


@dataclass(frozen=True)
class DiagnosticProfile:
    profile_id: str
    display_name: str
    console_baud: int
    json_prefix: str
    status_fields: tuple[StatusField, ...]
    line_status_rules: tuple[LineStatusRule, ...]
    device_rules: tuple[DeviceRule, ...]
    error_rules: tuple[ErrorRule, ...]
    source_path: Path

    @classmethod
    def load(cls, path: Path) -> "DiagnosticProfile":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiagnosticProfileError(f"診断プロファイルを読めません: {exc}") from exc
        if value.get("schema_version") != 1:
            raise DiagnosticProfileError("未対応の診断プロファイルschemaです")

        def compile_pattern(item: dict[str, Any], field: str) -> re.Pattern[str]:
            try:
                return re.compile(str(item[field]))
            except (KeyError, re.error) as exc:
                raise DiagnosticProfileError(f"不正な正規表現: {item}") from exc

        status_fields = tuple(
            StatusField(
                field_id=str(item["id"]),
                label=str(item["label"]),
                json_key=str(item["json_key"]),
                true_label=str(item.get("true_label", "正常")),
                false_label=str(item.get("false_label", "異常")),
                false_severity=str(item.get("false_severity", "error")),
                unit=str(item.get("unit", "")),
            )
            for item in value.get("status_fields", [])
        )
        line_status_rules = tuple(
            LineStatusRule(
                field_id=str(item["id"]),
                label=str(item["label"]),
                pattern=compile_pattern(item, "pattern"),
                value_group=str(item.get("value_group", "value")),
                value_map={str(k): str(v) for k, v in item.get("value_map", {}).items()},
                severity_map={
                    str(k): str(v) for k, v in item.get("severity_map", {}).items()
                },
            )
            for item in value.get("line_status_rules", [])
        )
        device_rules = tuple(
            DeviceRule(
                pattern=compile_pattern(item, "pattern"),
                identity_template=str(item["identity_template"]),
                display_template=str(item["display_template"]),
            )
            for item in value.get("device_rules", [])
        )
        error_rules = tuple(
            ErrorRule(
                pattern=compile_pattern(item, "pattern"),
                severity=str(item.get("severity", "error")),
            )
            for item in value.get("error_rules", [])
        )
        return cls(
            profile_id=str(value["id"]),
            display_name=str(value["display_name"]),
            console_baud=int(value.get("console_baud", 115200)),
            json_prefix=str(value.get("json_status_prefix", "Sending status: ")),
            status_fields=status_fields,
            line_status_rules=line_status_rules,
            device_rules=device_rules,
            error_rules=error_rules,
            source_path=path.resolve(),
        )


@dataclass
class DiagnosticValue:
    label: str
    value: str
    severity: str = "unknown"


class DiagnosticEngine:
    def __init__(self, profile: DiagnosticProfile) -> None:
        self.profile = profile
        self.statuses: dict[str, DiagnosticValue] = {}
        self.devices: dict[str, str] = {}
        self.errors: list[tuple[str, str]] = []
        self._buffer = ""

    def reset(self) -> None:
        self.statuses.clear()
        self.devices.clear()
        self.errors.clear()
        self._buffer = ""

    def feed(self, text: str) -> bool:
        self._buffer += text.replace("\r\n", "\n").replace("\r", "\n")
        lines = self._buffer.split("\n")
        self._buffer = lines.pop()
        changed = False
        for line in lines:
            changed |= self.feed_line(line)
        return changed

    def feed_line(self, line: str) -> bool:
        changed = False
        prefix_index = line.find(self.profile.json_prefix)
        if prefix_index >= 0:
            payload = line[prefix_index + len(self.profile.json_prefix) :].strip()
            try:
                status = json.loads(payload)
            except json.JSONDecodeError:
                status = None
            if isinstance(status, dict):
                for field in self.profile.status_fields:
                    if field.json_key not in status:
                        continue
                    raw = status[field.json_key]
                    if isinstance(raw, bool):
                        value = field.true_label if raw else field.false_label
                        severity = "ok" if raw else field.false_severity
                    else:
                        value = f"{raw}{field.unit}"
                        severity = "ok"
                    self.statuses[field.field_id] = DiagnosticValue(
                        field.label, value, severity
                    )
                    changed = True

        for rule in self.profile.line_status_rules:
            match = rule.pattern.search(line)
            if match is None:
                continue
            raw = match.groupdict().get(rule.value_group, match.group(0))
            value = rule.value_map.get(raw, raw)
            severity = rule.severity_map.get(raw, "ok")
            self.statuses[rule.field_id] = DiagnosticValue(rule.label, value, severity)
            changed = True

        for rule in self.profile.device_rules:
            match = rule.pattern.search(line)
            if match is None:
                continue
            groups = match.groupdict()
            identity = rule.identity_template.format(**groups)
            self.devices[identity] = rule.display_template.format(**groups)
            changed = True

        for rule in self.profile.error_rules:
            if rule.pattern.search(line):
                entry = (rule.severity, line.strip())
                if not self.errors or self.errors[-1] != entry:
                    self.errors.append(entry)
                    self.errors = self.errors[-100:]
                    changed = True
        return changed


def discover_profiles(paths: list[Path]) -> list[DiagnosticProfile]:
    profiles: dict[str, DiagnosticProfile] = {}
    for directory in paths:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            profile = DiagnosticProfile.load(path)
            profiles[profile.profile_id] = profile
    return sorted(profiles.values(), key=lambda item: item.display_name)
