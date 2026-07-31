import math
from collections import defaultdict

WEATHER_METRICS = {
    "precipitation_mm",
    "rain_mm",
    "precipitation_hours",
    "sunshine_hours",
    "solar_radiation_mj_m2",
    "et0_fao_evapotranspiration_mm",
    "temperature_2m_max_c",
    "temperature_2m_min_c",
}


def build_research_dataset(field, weather_records, *, date_from="", date_to=""):
    rows = defaultdict(lambda: {"date": None, "weather": {}, "field_records": {}, "provenance": []})
    for record in weather_records:
        for summary in record.get("daily_summaries") or []:
            day = summary.get("date")
            if not _in_range(day, date_from, date_to):
                continue
            row = rows[day]
            row["date"] = day
            for metric in WEATHER_METRICS:
                if summary.get(metric) is not None:
                    row["weather"][metric] = summary[metric]
            row["provenance"].append(
                {
                    "kind": "forecast_snapshot"
                    if (record.get("source") or {}).get("type") == "forecast"
                    else "external_analysis",
                    "record_id": record.get("record_id"),
                    "provider": (record.get("source") or {}).get("provider"),
                    "quality": summary.get("data_quality"),
                }
            )
    for event in field.get("events") or []:
        day = str(event.get("occurred_at") or "")[:10]
        if not _in_range(day, date_from, date_to):
            continue
        row = rows[day]
        row["date"] = day
        for value in event.get("record_values") or []:
            key = value.get("key")
            number = _number(value.get("value"))
            if key and number is not None:
                row["field_records"][key] = number
        if event.get("record_values"):
            row["provenance"].append(
                {"kind": "human_observation", "record_id": event.get("id"), "target": event.get("target_placement_id")}
            )
    return {
        "schema": "ina.cultivation_research_dataset.v1",
        "field_id": field.get("id"),
        "timezone": (field.get("weather_location") or {}).get("timezone") or "Asia/Tokyo",
        "rows": [rows[key] for key in sorted(rows)],
        "disclaimer": "相関は因果関係を示しません。予報値と観測・解析値は別の由来として扱います。",
    }


def analyze_correlation(dataset, x_metric, y_metric, *, method="pearson", lag_days=0):
    if method not in {"pearson", "spearman"}:
        raise ValueError("method must be pearson or spearman")
    lag_days = int(lag_days)
    if abs(lag_days) > 365:
        raise ValueError("lag_days must be between -365 and 365")
    by_date = {row["date"]: row for row in dataset.get("rows") or []}
    ordered_dates = sorted(by_date)
    x_values = []
    y_values = []
    for index, day in enumerate(ordered_dates):
        target_index = index + lag_days
        if target_index < 0 or target_index >= len(ordered_dates):
            continue
        x = _metric(by_date[day], x_metric)
        y = _metric(by_date[ordered_dates[target_index]], y_metric)
        if x is not None and y is not None:
            x_values.append(x)
            y_values.append(y)
    if len(x_values) < 3:
        coefficient = None
    else:
        if method == "spearman":
            x_values, y_values = _ranks(x_values), _ranks(y_values)
        coefficient = _pearson(x_values, y_values)
    return {
        "method": method,
        "x_metric": x_metric,
        "y_metric": y_metric,
        "lag_days": lag_days,
        "sample_size": len(x_values),
        "coefficient": round(coefficient, 6) if coefficient is not None else None,
        "interpretation": _interpret(coefficient, len(x_values)),
        "causal_claim": False,
    }


def _metric(row, key):
    if key.startswith("weather."):
        return _number((row.get("weather") or {}).get(key[8:]))
    if key.startswith("field_records."):
        return _number((row.get("field_records") or {}).get(key[14:]))
    return None


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _in_range(day, date_from, date_to):
    return bool(day) and (not date_from or day >= date_from) and (not date_to or day <= date_to)


def _pearson(xs, ys):
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def _ranks(values):
    result = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original_index, _ in ordered[index:end]:
            result[original_index] = rank
        index = end
    return result


def _interpret(coefficient, sample_size):
    if coefficient is None:
        return "サンプルが3件未満、または値が一定のため判定できません。"
    strength = "弱い" if abs(coefficient) < 0.3 else "中程度" if abs(coefficient) < 0.7 else "強い"
    direction = "正" if coefficient > 0 else "負" if coefficient < 0 else "なし"
    return f"{strength}{direction}の相関です（n={sample_size}）。因果関係を示すものではありません。"
