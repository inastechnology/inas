METRIC_LABELS = {
    "last_soil_moisture": "土壌水分",
    "soil_moisture_1_pct": "土壌水分1",
    "soil_moisture_2_pct": "土壌水分2",
    "soil_moisture_percent": "土壌水分",
    "soil_temp_c": "地温",
    "soil_temperature_c": "地温",
    "soil_ec_us_cm": "土壌EC",
    "soil_ph": "土壌pH",
    "air_humidity_percent": "湿度",
    "par_umol_m2_s": "光合成に使える光",
    "solar_radiation_w_m2": "日射量",
    "battery_v": "電池電圧",
    "rssi": "通信強度",
    "threshold": "灌水しきい値",
}

ACTION_LABELS = {
    "watering": "灌水",
    "fertigation": "液肥",
    "misting": "噴霧",
    "observation": "観察",
}

SUPPORTED_ACTIONS = {"watering"}
FUTURE_ACTIONS = {"fertigation", "misting"}


def build_action_candidates(field_context: dict):
    """Build deterministic action candidates from field assumptions and latest observations."""
    if not isinstance(field_context, dict):
        return []

    field = field_context.get("field") if isinstance(field_context.get("field"), dict) else {}
    policy = field.get("control_policy") if isinstance(field.get("control_policy"), dict) else {}
    targets = field.get("growth_targets") if isinstance(field.get("growth_targets"), dict) else {}
    allowed_actions = set(policy.get("allowed_actions") or ["watering"])
    latest_values = _latest_metric_values(field_context.get("latest_sensor_values") or [])
    candidates = []

    moisture_candidate = _build_range_candidate(
        action_type="watering",
        metric="soil_moisture_percent",
        latest_values=latest_values,
        target=targets.get("soil_moisture_percent"),
        field=field,
        policy=policy,
        allowed_actions=allowed_actions,
        devices=field_context.get("devices") or [],
        low_title="土壌水分が目標より低いため灌水を検討",
        low_reason="現在の土壌水分が設定した下限を下回っています。作物名、栽培ステージ、栽培方式を前提条件として、まず水分不足を解消する候補です。",
        high_title="土壌水分が高いため灌水を見送り",
        high_reason="現在の土壌水分が設定した上限を上回っています。過湿による根傷みや病害リスクを避けるため、灌水しない判断候補です。",
    )
    if moisture_candidate:
        candidates.append(moisture_candidate)

    fertigation_candidate = _build_low_metric_candidate(
        action_type="fertigation",
        metric="soil_ec_us_cm",
        latest_values=latest_values,
        target=targets.get("soil_ec_us_cm"),
        field=field,
        policy=policy,
        allowed_actions=allowed_actions,
        devices=field_context.get("devices") or [],
        title="土壌ECが目標より低いため液肥を検討",
        reason="土壌ECが設定した下限を下回っています。作物と栽培ステージの前提を確認し、液肥で養分濃度を補う候補です。",
    )
    if fertigation_candidate:
        candidates.append(fertigation_candidate)

    misting_candidate = _build_low_metric_candidate(
        action_type="misting",
        metric="air_humidity_percent",
        latest_values=latest_values,
        target=targets.get("air_humidity_percent"),
        field=field,
        policy=policy,
        allowed_actions=allowed_actions,
        devices=field_context.get("devices") or [],
        title="湿度が目標より低いため噴霧を検討",
        reason="湿度が設定した下限を下回っています。蒸散負荷を抑えるため、噴霧による湿度調整を検討する候補です。",
    )
    if misting_candidate:
        candidates.append(misting_candidate)

    if not candidates:
        candidates.append(_observation_candidate(field, policy, latest_values))

    return candidates


def _build_range_candidate(
    action_type,
    metric,
    latest_values,
    target,
    field,
    policy,
    allowed_actions,
    devices,
    low_title,
    low_reason,
    high_title,
    high_reason,
):
    value = _metric_value(latest_values, metric)
    minimum = _target_number(target, "min")
    maximum = _target_number(target, "max")
    if value is None:
        return None
    if minimum is not None and value < minimum:
        return _candidate(
            action_type=action_type,
            metric=metric,
            status="proposed",
            title=low_title,
            scientific_reason=low_reason,
            current_value=value,
            target=target,
            field=field,
            policy=policy,
            allowed_actions=allowed_actions,
            devices=devices,
            direction="increase",
        )
    if maximum is not None and value > maximum:
        return _candidate(
            action_type="observation",
            metric=metric,
            status="proposed",
            title=high_title,
            scientific_reason=high_reason,
            current_value=value,
            target=target,
            field=field,
            policy=policy,
            allowed_actions=allowed_actions,
            devices=devices,
            direction="hold",
        )
    return None


def _build_low_metric_candidate(
    action_type,
    metric,
    latest_values,
    target,
    field,
    policy,
    allowed_actions,
    devices,
    title,
    reason,
):
    value = _metric_value(latest_values, metric)
    minimum = _target_number(target, "min")
    if value is None or minimum is None or value >= minimum:
        return None
    return _candidate(
        action_type=action_type,
        metric=metric,
        status="proposed",
        title=title,
        scientific_reason=reason,
        current_value=value,
        target=target,
        field=field,
        policy=policy,
        allowed_actions=allowed_actions,
        devices=devices,
        direction="increase",
    )


def _candidate(
    action_type,
    metric,
    status,
    title,
    scientific_reason,
    current_value,
    target,
    field,
    policy,
    allowed_actions,
    devices,
    direction,
):
    support = _action_support(action_type, devices)
    allowed = action_type in allowed_actions or action_type == "observation"
    autonomy_level = policy.get("autonomy_level") or "suggest_only"
    can_execute = allowed and support["supported"] and autonomy_level in {"manual_approval", "auto"}
    return {
        "status": status,
        "action_type": action_type,
        "action_label": ACTION_LABELS.get(action_type, action_type),
        "metric": metric,
        "metric_label": METRIC_LABELS.get(metric, metric),
        "title": title,
        "scientific_reason": scientific_reason,
        "preconditions": {
            "crop_name": (field.get("crop_profile") or {}).get("crop_name") or field.get("crop"),
            "cultivar": (field.get("crop_profile") or {}).get("cultivar"),
            "growth_stage": (field.get("crop_profile") or {}).get("growth_stage") or field.get("stage"),
            "cultivation_method": (field.get("cultivation_context") or {}).get("cultivation_method"),
            "soil_type": (field.get("cultivation_context") or {}).get("soil_type"),
            "objective": policy.get("objective"),
            "monitoring_units": field.get("areas") or [],
            "device_placements": field.get("device_placements") or [],
        },
        "evidence": {
            "current_value": current_value,
            "target": target or {},
            "direction": direction,
        },
        "expected_effect": _expected_effect(action_type, metric, direction),
        "risk": _risk(action_type),
        "support": support,
        "allowed_by_policy": allowed,
        "autonomy_level": autonomy_level,
        "can_execute_now": can_execute,
        "control_payload": {
            "intent": f"{direction}_{metric}",
            "action_type": action_type,
            "metric": metric,
            "current_value": current_value,
            "target": target or {},
        },
        "source": "rule_based_field_context",
    }


def _observation_candidate(field, policy, latest_values):
    return {
        "status": "proposed",
        "action_type": "observation",
        "action_label": ACTION_LABELS["observation"],
        "metric": "",
        "metric_label": "",
        "title": "追加制御は保留して観察を継続",
        "scientific_reason": "現在の最新値と目標レンジから、すぐに制御すべき明確な差分は見つかっていません。",
        "preconditions": {
            "crop_name": (field.get("crop_profile") or {}).get("crop_name") or field.get("crop"),
            "growth_stage": (field.get("crop_profile") or {}).get("growth_stage") or field.get("stage"),
            "objective": policy.get("objective"),
            "monitoring_units": field.get("areas") or [],
            "device_placements": field.get("device_placements") or [],
        },
        "evidence": {"latest_values": latest_values},
        "expected_effect": "データを継続収集し、次回の判断精度を上げる。",
        "risk": "変化が速い環境では判断が遅れる可能性があります。",
        "support": {"supported": True, "reason": "観察記録のみ"},
        "allowed_by_policy": True,
        "autonomy_level": policy.get("autonomy_level") or "suggest_only",
        "can_execute_now": False,
        "control_payload": {},
        "source": "rule_based_field_context",
    }


def _latest_metric_values(latest_sensor_values):
    metrics = {}
    for item in latest_sensor_values:
        if not isinstance(item, dict):
            continue
        values = item.get("values") if isinstance(item.get("values"), dict) else {}
        for key, value in values.items():
            number = _number(value)
            if number is not None:
                metrics[_canonical_metric(key)] = number
    return metrics


def _canonical_metric(metric):
    aliases = {
        "last_soil_moisture": "soil_moisture_percent",
        "soil_moisture_1_pct": "soil_moisture_percent",
        "soil_moisture_2_pct": "soil_moisture_percent",
        "soil_temp_c": "soil_temperature_c",
    }
    return aliases.get(metric, metric)


def _metric_value(metrics, metric):
    return _number(metrics.get(metric))


def _target_number(target, key):
    if not isinstance(target, dict):
        return None
    return _number(target.get(key))


def _number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _action_support(action_type, devices):
    if action_type in FUTURE_ACTIONS:
        return {
            "supported": False,
            "reason": "hubの判断モデルには入れていますが、対応デバイス制御は今後実装です。",
        }
    if action_type not in SUPPORTED_ACTIONS:
        return {"supported": True, "reason": "制御を伴わない記録です。"}
    has_watering_device = any(((device.get("record") or {}).get("device_kind") == "WTR") for device in devices if isinstance(device, dict))
    if has_watering_device:
        return {"supported": True, "reason": "WTRデバイスで制御可能です。"}
    return {"supported": False, "reason": "灌水可能なWTRデバイスが圃場に紐づいていません。"}


def _expected_effect(action_type, metric, direction):
    if action_type == "watering":
        return "土壌水分を目標範囲へ近づける。"
    if action_type == "fertigation":
        return "養液濃度を補い、土壌ECを目標範囲へ近づける。"
    if action_type == "misting":
        return "湿度を上げ、蒸散負荷を抑える。"
    if direction == "hold":
        return f"{METRIC_LABELS.get(metric, metric)}の過剰側リスクを避ける。"
    return "観察を継続する。"


def _risk(action_type):
    if action_type == "watering":
        return "過灌水になると根傷みや病害リスクがあります。日内上限と間隔を守ってください。"
    if action_type == "fertigation":
        return "過剰な液肥は肥料焼けや塩類集積につながります。EC/pHと作物ステージを確認してください。"
    if action_type == "misting":
        return "過湿は病害リスクを上げます。葉面濡れ時間と換気を確認してください。"
    return "観察だけでは状態悪化を止められない場合があります。"
