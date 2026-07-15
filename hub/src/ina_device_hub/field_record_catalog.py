import math

FIELD_RECORD_CATEGORIES = (
    ("watering", "潅水"),
    ("soil", "土壌・培地"),
    ("environment", "環境"),
    ("cultivation", "栽培作業"),
    ("harvest", "収穫"),
)

FIELD_RECORD_CATALOG = (
    {
        "key": "watering_duration_min",
        "label": "潅水時間",
        "category": "watering",
        "unit": "分",
        "input_type": "number",
        "step": "1",
        "minimum": 0,
        "maximum": 1440,
        "keywords": ["水やり", "点滴", "時間", "ホース"],
    },
    {
        "key": "watering_volume_l",
        "label": "潅水量",
        "category": "watering",
        "unit": "L",
        "input_type": "number",
        "step": "0.1",
        "minimum": 0,
        "maximum": 1000000,
        "keywords": ["水やり", "水量", "リットル"],
    },
    {
        "key": "soil_moisture_percent",
        "label": "土壌水分",
        "category": "soil",
        "unit": "%",
        "input_type": "number",
        "step": "0.1",
        "minimum": 0,
        "maximum": 100,
        "keywords": ["水分", "含水率", "培地"],
    },
    {
        "key": "soil_ec_us_cm",
        "label": "EC",
        "category": "soil",
        "unit": "uS/cm",
        "input_type": "number",
        "step": "1",
        "minimum": 0,
        "maximum": 100000,
        "keywords": ["電気伝導度", "肥料濃度", "培養液"],
    },
    {
        "key": "soil_ph",
        "label": "pH",
        "category": "soil",
        "unit": "pH",
        "input_type": "number",
        "step": "0.1",
        "minimum": 0,
        "maximum": 14,
        "keywords": ["酸度", "アルカリ", "培養液"],
    },
    {
        "key": "soil_temperature_c",
        "label": "地温・培地温",
        "category": "soil",
        "unit": "℃",
        "input_type": "number",
        "step": "0.1",
        "minimum": -50,
        "maximum": 100,
        "keywords": ["温度", "根域", "土"],
    },
    {
        "key": "air_temperature_c",
        "label": "気温",
        "category": "environment",
        "unit": "℃",
        "input_type": "number",
        "step": "0.1",
        "minimum": -50,
        "maximum": 80,
        "keywords": ["温度", "室温", "ハウス"],
    },
    {
        "key": "air_humidity_percent",
        "label": "湿度",
        "category": "environment",
        "unit": "%",
        "input_type": "number",
        "step": "0.1",
        "minimum": 0,
        "maximum": 100,
        "keywords": ["空気", "相対湿度", "ハウス"],
    },
    {
        "key": "par_umol_m2_s",
        "label": "PAR",
        "category": "environment",
        "unit": "umol/m2/s",
        "input_type": "number",
        "step": "1",
        "minimum": 0,
        "maximum": 10000,
        "keywords": ["光", "日射", "光合成", "SEN0641"],
    },
    {
        "key": "fertilizer_amount_g",
        "label": "施肥量",
        "category": "cultivation",
        "unit": "g",
        "input_type": "number",
        "step": "0.1",
        "minimum": 0,
        "maximum": 1000000,
        "keywords": ["追肥", "肥料", "施肥"],
    },
    {
        "key": "pest_observation",
        "label": "病害虫・防除",
        "category": "cultivation",
        "unit": "",
        "input_type": "text",
        "keywords": ["病気", "虫", "薬剤", "農薬", "防除"],
    },
    {
        "key": "plant_condition",
        "label": "作物の状態",
        "category": "cultivation",
        "unit": "",
        "input_type": "text",
        "keywords": ["観察", "葉色", "樹勢", "生育"],
    },
    {
        "key": "harvest_weight_g",
        "label": "収穫量",
        "category": "harvest",
        "unit": "g",
        "input_type": "number",
        "step": "1",
        "minimum": 0,
        "maximum": 10000000,
        "keywords": ["収量", "重量", "収穫"],
    },
)

FIELD_RECORD_CATALOG_BY_KEY = {item["key"]: item for item in FIELD_RECORD_CATALOG}
FIELD_RECORD_CATEGORY_LABELS = dict(FIELD_RECORD_CATEGORIES)


def normalize_field_record_values(values):
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        raise ValueError("record_values must be an array")
    normalized = []
    seen = set()
    for value in values[:30]:
        if not isinstance(value, dict):
            raise ValueError("record_values entries must be objects")
        key = str(value.get("key") or "").strip()
        definition = FIELD_RECORD_CATALOG_BY_KEY.get(key)
        if definition is None:
            raise ValueError(f"unsupported record item: {key}")
        if key in seen:
            continue
        cleaned_value = _normalize_record_value(value.get("value"), definition)
        if cleaned_value is None:
            continue
        normalized.append(
            {
                "key": key,
                "label": definition["label"],
                "category": definition["category"],
                "value": cleaned_value,
                "unit": definition["unit"],
                "input_type": definition["input_type"],
            }
        )
        seen.add(key)
    return normalized


def selected_record_catalog(events, limit=8):
    selected = {}
    for event_index, event in enumerate(events or []):
        occurred_at = str(event.get("occurred_at") or event.get("created_at") or "")
        for value_index, value in enumerate(event.get("record_values") or []):
            key = value.get("key") if isinstance(value, dict) else ""
            definition = FIELD_RECORD_CATALOG_BY_KEY.get(key)
            if definition is None:
                continue
            selected[key] = (occurred_at, event_index, value_index, definition)
    ordered = sorted(selected.values(), key=lambda item: item[:3], reverse=True)
    return [dict(item[3]) for item in ordered[:limit]]


def _normalize_record_value(value, definition):
    if value in (None, ""):
        return None
    if definition["input_type"] == "text":
        text = str(value).strip()
        return text[:1000] if text else None
    if isinstance(value, bool):
        raise ValueError(f"{definition['label']} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{definition['label']} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{definition['label']} must be finite")
    minimum = definition.get("minimum")
    maximum = definition.get("maximum")
    if minimum is not None and number < minimum:
        raise ValueError(f"{definition['label']} must be {minimum} or greater")
    if maximum is not None and number > maximum:
        raise ValueError(f"{definition['label']} must be {maximum} or less")
    return int(number) if number.is_integer() else number
