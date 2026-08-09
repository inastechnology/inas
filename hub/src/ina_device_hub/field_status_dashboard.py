"""Build field status metrics independently from HTTP rendering concerns."""

import math
from datetime import UTC, datetime
from statistics import median
from urllib.parse import urlencode

_RS485_VALUE_KEYS = {
    "soil_moisture_percent": ("moisture_percent", "soil_moisture_percent"),
    "soil_temperature_c": ("temperature_c", "soil_temperature_c", "soil_temp_c"),
    "soil_ec_us_cm": ("ec_us_cm", "soil_ec_us_cm"),
    "soil_ph": ("ph", "soil_ph"),
    "par_umol_m2_s": ("par_umol_m2_s",),
}

METRIC_SPECS = (
    {
        "metric": "air_temperature_c",
        "label": "気温",
        "unit": "℃",
        "aliases": ("air_temperature_c",),
        "domain": (-40.0, 80.0),
    },
    {
        "metric": "air_humidity_percent",
        "label": "湿度",
        "unit": "%",
        "aliases": ("air_humidity_percent",),
        "domain": (0.0, 100.0),
    },
    {
        "metric": "soil_moisture_percent",
        "label": "土壌水分",
        "unit": "%",
        "aliases": ("soil_moisture_percent", "last_soil_moisture", "soil_moisture_1_pct", "soil_moisture_2_pct"),
        "domain": (0.0, 100.0),
    },
    {
        "metric": "soil_temperature_c",
        "label": "地温",
        "unit": "℃",
        "aliases": ("soil_temperature_c", "soil_temp_c"),
        "domain": (-20.0, 60.0),
    },
    {
        "metric": "soil_ec_us_cm",
        "label": "土壌EC",
        "unit": "uS/cm",
        "aliases": ("soil_ec_us_cm",),
        "domain": (0.0, 3000.0),
    },
    {
        "metric": "soil_ph",
        "label": "土壌pH",
        "unit": "",
        "aliases": ("soil_ph",),
        "domain": (0.0, 14.0),
    },
    {
        "metric": "par_umol_m2_s",
        "label": "光合成有効光量",
        "unit": "umol/m2/s",
        "aliases": ("par_umol_m2_s",),
        "domain": (0.0, 2000.0),
    },
)


def build_field_status_dashboard(field: dict, latest_sensor_values: list, active_plantings: list | None = None):
    targets = field.get("growth_targets") if isinstance(field.get("growth_targets"), dict) else {}
    metrics = [metric for spec in METRIC_SPECS if (metric := _build_metric(field, spec, targets, latest_sensor_values, active_plantings or [])) is not None]
    counts = _state_counts(metrics)
    overall_state, overall_label, summary = _overall_status(metrics, counts)
    observed_at_values = [metric["observed_at"] for metric in metrics if metric.get("observed_at")]
    latest_observed_at = max(observed_at_values, key=_datetime_sort_key, default="")

    return {
        "metrics": metrics,
        "counts": counts,
        "overall_state": overall_state,
        "overall_label": overall_label,
        "summary": summary,
        "latest_observed_at": latest_observed_at,
        "latest_observed_at_display": _format_datetime(latest_observed_at),
    }


def _build_metric(field: dict, spec: dict, default_targets: dict, latest_sensor_values: list, active_plantings: list):
    observation = _median_observation(latest_sensor_values, spec)
    value = observation.get("value") if observation else None
    if value is None:
        return None

    target, target_planting = _metric_target(default_targets, spec["metric"], observation, active_plantings)
    minimum = _number(target.get("min"))
    maximum = _number(target.get("max"))
    domain_min, default_domain_max = spec["domain"]
    domain_max = max(default_domain_max, value * 1.15, (maximum or 0) * 1.15, (minimum or 0) * 1.15)
    state, state_label = _metric_state(value, minimum, maximum)
    target_start = minimum if minimum is not None else domain_min
    target_end = maximum if maximum is not None else domain_max

    return {
        "metric": spec["metric"],
        "label": spec["label"],
        "unit": spec["unit"],
        "value": value,
        "value_display": _number_label(value),
        "minimum": minimum,
        "minimum_display": _number_label(minimum),
        "maximum": maximum,
        "maximum_display": _number_label(maximum),
        "domain_min": domain_min,
        "domain_min_display": _number_label(domain_min),
        "domain_max": domain_max,
        "domain_max_display": _number_label(domain_max),
        "target_left_pct": _position(target_start, domain_min, domain_max),
        "target_width_pct": max(0, _position(target_end, domain_min, domain_max) - _position(target_start, domain_min, domain_max)),
        "marker_pct": _position(value, domain_min, domain_max),
        "state": state,
        "state_label": state_label,
        "device_id": observation.get("device_id") if observation else "",
        "scope_label": observation.get("scope_label") if observation else "",
        "source_count": observation.get("source_count") if observation else 0,
        "source_summary": observation.get("source_summary") if observation else "",
        "observed_at": observation.get("observed_at") if observation else "",
        "observed_at_display": _format_datetime(observation.get("observed_at")) if observation else "",
        "target_url": _target_settings_url(field, spec["metric"], target_planting, active_plantings),
    }


def _metric_state(value, minimum, maximum):
    if minimum is None and maximum is None:
        return "unconfigured", "目標未設定"
    if minimum is not None and value < minimum:
        return "low", "下限未満"
    if maximum is not None and value > maximum:
        return "high", "上限超過"
    return "good", "目標内"


def _state_counts(metrics):
    return {
        "good": sum(metric["state"] == "good" for metric in metrics),
        "attention": sum(metric["state"] in {"low", "high"} for metric in metrics),
        "unknown": 0,
        "unconfigured": sum(metric["state"] == "unconfigured" for metric in metrics),
    }


def _overall_status(metrics, counts):
    if counts["attention"]:
        return "attention", "確認が必要", f"{counts['attention']}項目が目標範囲を外れています"
    if counts["good"]:
        return "good", "目標範囲内", f"取得できた{counts['good']}項目は目標範囲内です"
    if metrics:
        return "unconfigured", "目標未設定", "現在値を判定する目標レンジがありません"
    return "empty", "現在値なし", "取得済みの環境値はありません"


def _metric_target(default_targets: dict, metric: str, observation: dict | None, active_plantings: list):
    target_ids = set((observation or {}).get("target_placement_ids") or [])
    candidates = [planting for planting in active_plantings if planting.get("placement_id") in target_ids]
    if not candidates and len(active_plantings) == 1:
        candidates = active_plantings
    if len(candidates) == 1:
        target = (candidates[0].get("growth_targets") or {}).get(metric)
        return (target if isinstance(target, dict) else {}), candidates[0]
    target = default_targets.get(metric)
    return (target if isinstance(target, dict) else {}), None


def _target_settings_url(field: dict, metric: str, target_planting: dict | None, active_plantings: list):
    field_id = str(field.get("id") or "").strip()
    if not field_id:
        return ""
    planting = target_planting
    if planting is None and active_plantings:
        planting = active_plantings[0]
    query = {"target_metric": metric}
    if planting:
        if planting.get("space_id"):
            query["space"] = planting["space_id"]
        if planting.get("placement_id"):
            query["placement"] = planting["placement_id"]
        if planting.get("id"):
            query["planting"] = planting["id"]
    return f"/fields/{field_id}/layout?{urlencode(query)}"


def _median_observation(latest_sensor_values: list, spec: dict):
    candidates = []
    for index, item in enumerate(latest_sensor_values or []):
        if not isinstance(item, dict):
            continue
        observed_at = item.get("updated_at") or item.get("received_at") or ""
        for sensor_index, sensor_value in enumerate(_sensor_values(item, spec)):
            candidates.append(
                {
                    "value": sensor_value["value"],
                    "device_id": item.get("device_id") or "",
                    "sensor_label": sensor_value.get("sensor_label") or "",
                    "scope_label": item.get("scope_label") or "",
                    "target_placement_ids": item.get("target_placement_ids") or [],
                    "observed_at": observed_at,
                    "sort_key": (_datetime_sort_key(observed_at), index, sensor_index),
                }
            )
    if not candidates:
        return None

    latest = max(candidates, key=lambda item: item["sort_key"])
    device_ids = _unique_nonempty(candidate["device_id"] for candidate in candidates)
    scope_labels = _unique_nonempty(candidate["scope_label"] for candidate in candidates)
    target_placement_ids = _unique_nonempty(placement_id for candidate in candidates for placement_id in candidate["target_placement_ids"])
    source_count = len(candidates)
    device_id = device_ids[0] if len(device_ids) == 1 else ""
    scope_label = scope_labels[0] if len(scope_labels) == 1 else ("圃場内" if scope_labels else "")
    return {
        "value": float(median(candidate["value"] for candidate in candidates)),
        "device_id": device_id,
        "scope_label": scope_label,
        "target_placement_ids": target_placement_ids,
        "observed_at": latest["observed_at"],
        "source_count": source_count,
        "source_summary": _source_summary(candidates, device_ids, scope_label),
    }


def _sensor_values(item: dict, spec: dict):
    values = item.get("values") if isinstance(item.get("values"), dict) else {}
    if spec["metric"] in _RS485_VALUE_KEYS and isinstance(values.get("rs485_devices"), list):
        return _rs485_sensor_values(values, spec["metric"])

    if spec["metric"] == "soil_moisture_percent":
        probe_values = []
        for position, key in enumerate(("soil_moisture_1_pct", "soil_moisture_2_pct"), start=1):
            value = _number(values.get(key))
            if value is not None:
                probe_values.append({"value": value, "sensor_label": f"土壌水分センサー{position}"})
        if probe_values:
            return probe_values

    value = _first_number(values, spec["aliases"])
    return [{"value": value, "sensor_label": ""}] if value is not None else []


def _rs485_sensor_values(values: dict, metric: str):
    value_keys = _RS485_VALUE_KEYS.get(metric)
    devices = values.get("rs485_devices")
    if value_keys is None or not isinstance(devices, list):
        return []

    result = []
    for position, device in enumerate(devices):
        if not isinstance(device, dict) or device.get("enabled") is False or device.get("bus_ready") is False or device.get("ok") is False:
            continue
        value = _first_number(device, value_keys)
        if value is None:
            continue
        name = str(device.get("name") or "").strip()
        location = str(device.get("location") or "").strip()
        sensor_type = str(device.get("type") or "").strip().lower()
        fallback = "土壌センサー" if sensor_type == "soil" else "光センサー" if sensor_type == "par" else "RS485センサー"
        label = name or f"{fallback}{position + 1}"
        result.append({"value": value, "sensor_label": f"{label}（{location}）" if location else label})
    return result


def _source_summary(candidates: list, device_ids: list, scope_label: str):
    if len(candidates) == 1:
        candidate = candidates[0]
        parts = [candidate.get("device_id"), candidate.get("sensor_label"), scope_label]
    else:
        parts = [device_ids[0] if len(device_ids) == 1 else "", f"{len(candidates)}センサーの中央値", scope_label]
    return " / ".join(str(part) for part in parts if part)


def _unique_nonempty(values):
    return list(dict.fromkeys(value for value in values if value not in (None, "")))


def _datetime_sort_key(value):
    parsed = _parse_datetime(value)
    return parsed.timestamp() if parsed is not None else 0


def _parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_datetime(value):
    parsed = _parse_datetime(value)
    if parsed is None:
        return "未取得"
    local_datetime = parsed.astimezone(datetime.now().astimezone().tzinfo)
    timezone_name = local_datetime.tzname() or "local"
    return local_datetime.strftime(f"%Y-%m-%d %H:%M {timezone_name}")


def _number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _first_number(values: dict, aliases: tuple):
    for alias in aliases:
        value = _number(values.get(alias))
        if value is not None:
            return value
    return None


def _number_label(value):
    if value is None:
        return "-"
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _position(value, domain_min, domain_max):
    if value is None or domain_max <= domain_min:
        return 0
    position = (value - domain_min) / (domain_max - domain_min) * 100
    return round(min(100, max(0, position)), 2)
