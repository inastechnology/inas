OPERATIONAL_ERROR_LABELS = {
    "journal_error": "運転履歴を読み取れません",
    "recovery_required": "安全確認後の復旧待ちです",
    "output_error": "ポンプ・出力を開始できません",
    "sensor_12v_power_error": "センサー電源を開始できません",
    "runtime_config_invalid": "機器の動作設定が不正です",
    "watering_stop_reason:output_start_failed": "潅水出力を開始できません",
}


def device_operational_error_details(status: dict | None):
    if not isinstance(status, dict):
        return None

    reasons = []
    for key in (
        "journal_error",
        "recovery_required",
        "output_error",
        "sensor_12v_power_error",
    ):
        if status.get(key) is True:
            reasons.append(key)

    if status.get("runtime_config_valid") is False:
        reasons.append("runtime_config_invalid")

    fgt_fault = str(status.get("fgt_fault") or "").strip().lower()
    if fgt_fault and fgt_fault != "none":
        reasons.append(f"fgt_fault:{fgt_fault}")

    watering_stop_reason = str(status.get("watering_stop_reason") or "").strip().lower()
    if watering_stop_reason in {"output_start_failed"}:
        reasons.append(f"watering_stop_reason:{watering_stop_reason}")

    if not reasons:
        return None
    return {
        "reasons": reasons,
        "reason_labels": [
            OPERATIONAL_ERROR_LABELS.get(
                reason,
                f"機器異常: {reason.removeprefix('fgt_fault:')}",
            )
            for reason in reasons
        ],
        "batch_skip_reason": status.get("batch_skip_reason"),
        "schedule_epoch_utc": status.get("schedule_epoch_utc"),
        "batch_delay_sec": status.get("batch_delay_sec"),
    }


def device_operational_error_signature(status: dict | None):
    details = device_operational_error_details(status)
    if details is None:
        return None
    return tuple(details["reasons"])
