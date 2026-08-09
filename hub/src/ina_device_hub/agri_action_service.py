from urllib.parse import quote

from ina_device_hub.device_definition_registry import get_device_definition

METRIC_LABELS = {
    "air_temperature_c": "気温",
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
WATERING_DEVICE_KINDS = {"WTR", "WRS"}

OPERATION_PROFILES = {
    "repotting": {
        "label": "定植・植え替え",
        "decision_checks": ["苗と根鉢の状態、植え付け位置、株間、深さを確認する"],
        "stop_conditions": ["苗の損傷、極端な乾燥・過湿、悪天候などで活着が見込めない"],
        "verification_checks": ["株が安定し、根元まで適切に潅水され、植え付け位置を記録した"],
    },
    "watering": {
        "label": "水やり",
        "decision_checks": ["根域の乾き、直近の潅水、降雨見込みを確認する"],
        "stop_conditions": ["根域が十分湿っている、漏水・流量異常・通信異常がある"],
        "verification_checks": ["対象へ水が届き、過湿や漏水がなく、実施量または時間を記録した"],
    },
    "pruning": {
        "label": "剪定",
        "decision_checks": ["作物・品種の適期、樹勢、花芽・結果枝、残す枝を確認する"],
        "stop_conditions": ["切る枝を特定できない、樹勢が弱い、作業後の回復が見込めない"],
        "verification_checks": ["誤切断、裂け、切り残しがなく、剪定後の樹形を記録した"],
    },
    "harvest": {
        "label": "収穫",
        "decision_checks": ["成熟度、天候、用途、保管・出荷条件を確認する"],
        "stop_conditions": ["未熟、濡れ、病害・傷みなどで品質を確保できない"],
        "verification_checks": ["収穫量と品質を記録し、取り残しと株の損傷を確認した"],
    },
}

HUMAN_GUIDED_ACTION_TYPES = {"repotting", "pruning", "harvest"}


def build_calendar_operation_readiness(bundle: dict, field: dict, layout: dict, device_records: dict):
    """Build additive, deterministic execution-readiness data for calendar actions."""
    if not isinstance(bundle, dict):
        return {}
    plantings = {item.get("id"): item for item in bundle.get("plantings", []) if isinstance(item, dict) and item.get("id")}
    readiness = {}
    for planting_id, calendar in (bundle.get("calendars") or {}).items():
        if not isinstance(calendar, dict):
            continue
        planting = plantings.get(planting_id) or plantings.get(calendar.get("planting_id")) or {}
        for action in calendar.get("actions") or []:
            if isinstance(action, dict) and action.get("id"):
                readiness[action["id"]] = build_operation_readiness(action, planting, field, layout, device_records)
    return readiness


def build_operation_readiness(action: dict, planting: dict, field: dict, layout: dict, device_records: dict):
    """Explain who can perform one action and which checks surround execution."""
    action_type = str(action.get("action_type") or "other")
    profile = OPERATION_PROFILES.get(action_type, {})
    work_plan = action.get("work_plan") if isinstance(action.get("work_plan"), dict) else {}
    policy = field.get("control_policy") if isinstance(field.get("control_policy"), dict) else {}
    allowed_actions = set(policy.get("allowed_actions") or ["watering"])
    autonomy_level = str(policy.get("autonomy_level") or "suggest_only")
    candidates = _watering_executor_candidates(planting, layout, device_records) if action_type == "watering" else []

    if action_type == "watering" and candidates:
        executor_mode = "device_assisted"
        summary = f"{candidates[0]['name']}が、この作物へ水を届ける機器として設置されています。"
        next_href = candidates[0]["manage_url"]
        next_label = "水やり機の設定を確認"
    elif action_type == "watering":
        executor_mode = "human"
        summary = "この作物へ接続された水やり機が見つからないため、今回は人が確認して水やりします。"
        next_href = f"/fields/{quote(str(field.get('id') or ''), safe='')}/layout"
        next_label = "設置ビューで水やりルートを確認"
    elif action_type in HUMAN_GUIDED_ACTION_TYPES:
        executor_mode = "human"
        summary = f"{profile.get('label', action_type)}は不可逆または品質に関わるため、現在は人が確認して実施します。"
        next_href = ""
        next_label = ""
    else:
        executor_mode = "human"
        summary = "現在は作業手順と確認点を案内し、人が実施して結果を記録します。"
        next_href = ""
        next_label = ""

    allowed_by_policy = action_type in allowed_actions if action_type == "watering" else True
    if action_type == "watering" and not allowed_by_policy:
        dispatch_reason = "圃場の自動制御方針で水やりが許可されていません。"
    elif action_type == "watering" and not candidates:
        dispatch_reason = "対象作物までの水やりルートが設置ビューで確認できません。"
    elif action_type == "watering":
        dispatch_reason = "安全な即時実行には、受付応答・重複防止・中止・完了結果を扱う実行プロトコルが必要です。現在は候補表示までです。"
    elif action_type in HUMAN_GUIDED_ACTION_TYPES:
        dispatch_reason = "対象認識、到達、操作、作業後確認を満たす機器がまだ登録されていません。"
    else:
        dispatch_reason = "この作業は現在、機器による実行対象ではありません。"

    return {
        "action_type": action_type,
        "operation_label": profile.get("label") or action.get("title") or action_type,
        "executor_mode": executor_mode,
        "automation_stage": "supervised_device" if candidates else "guidance_only",
        "summary": summary,
        "decision_checks": _unique_strings((work_plan.get("start_conditions") or []) + (profile.get("decision_checks") or [])),
        "stop_conditions": _unique_strings((work_plan.get("skip_conditions") or []) + (profile.get("stop_conditions") or [])),
        "verification_checks": _unique_strings((work_plan.get("completion_criteria") or []) + (profile.get("verification_checks") or [])),
        "executor_candidates": candidates,
        "allowed_by_policy": allowed_by_policy,
        "autonomy_level": autonomy_level,
        "requires_approval": autonomy_level != "auto" or action_type != "watering",
        "can_dispatch": False,
        "dispatch_reason": dispatch_reason,
        "next_href": next_href,
        "next_label": next_label,
    }


def _watering_executor_candidates(planting: dict, layout: dict, device_records: dict):
    target_placement_id = str(planting.get("placement_id") or "")
    if not target_placement_id:
        return []
    candidates = []
    seen = set()
    for space in layout.get("spaces") or []:
        for placement in space.get("placements") or []:
            binding = placement.get("binding") if isinstance(placement.get("binding"), dict) else {}
            device_id = str(binding.get("device_id") or "")
            if not device_id or device_id in seen or target_placement_id not in (binding.get("target_placement_ids") or []):
                continue
            record = device_records.get(device_id) if isinstance(device_records, dict) else None
            if not isinstance(record, dict) or str(record.get("state") or "active") not in {"active", "online"}:
                continue
            device_kind = str(record.get("device_kind") or record.get("kind") or "").upper()
            if device_kind not in WATERING_DEVICE_KINDS:
                continue
            definition = get_device_definition(device_kind)
            if not any(item.get("kind") == "irrigation" for item in definition.get("actions", {}).get("actions", []) if isinstance(item, dict)):
                continue
            resource_id = str(binding.get("resource_id") or "")
            output = next((item for item in definition.get("output_slots") or [] if item.get("id") == resource_id), None)
            candidates.append(
                {
                    "device_id": device_id,
                    "name": record.get("name") or placement.get("name") or device_id,
                    "device_kind": device_kind,
                    "placement_name": placement.get("name") or "",
                    "resource_id": resource_id,
                    "channel_mask": (output or {}).get("channel_mask"),
                    "manage_url": f"/mqtt-devices/{quote(device_id, safe='')}?tab=settings",
                }
            )
            seen.add(device_id)
    return candidates


def _unique_strings(values):
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def build_action_candidates(field_context: dict):
    """Build deterministic action candidates from field assumptions and latest observations."""
    if not isinstance(field_context, dict):
        return []

    field = field_context.get("field") if isinstance(field_context.get("field"), dict) else {}
    policy = field.get("control_policy") if isinstance(field.get("control_policy"), dict) else {}
    targets = field.get("growth_targets") if isinstance(field.get("growth_targets"), dict) else {}
    allowed_actions = set(policy.get("allowed_actions") or ["watering"])
    dashboard = field_context.get("dashboard")
    latest_values = (
        _dashboard_metric_values(dashboard) if isinstance(dashboard, dict) else _latest_metric_values(field_context.get("latest_sensor_values") or [])
    )
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
    # A capable, physically routed device is still only a candidate until the Hub
    # has an acknowledged, idempotent on-demand action protocol.
    can_execute = False
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


def _dashboard_metric_values(dashboard):
    metrics = {}
    for item in dashboard.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric")
        value = _number(item.get("value"))
        if metric and value is not None:
            metrics[metric] = value
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
    has_watering_device = any(
        (device.get("record") or {}).get("device_kind") in WATERING_DEVICE_KINDS and bool((device.get("placement") or {}).get("target_placement_ids"))
        for device in devices
        if isinstance(device, dict)
    )
    if has_watering_device:
        return {"supported": True, "reason": "対象区画へ接続されたWTR/WRSデバイスがあります。即時実行は安全な実行プロトコル実装後に有効化します。"}
    return {"supported": False, "reason": "対象区画への水やりルートを持つWTR/WRSデバイスが設置ビューにありません。"}


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
