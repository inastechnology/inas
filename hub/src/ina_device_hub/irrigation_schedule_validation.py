from datetime import date, timedelta

IRRIGATION_DEVICE_KINDS = {"WTR", "WRS", "FGT"}
SCHEDULE_SAFETY_BUFFER_SEC = 5 * 60
# Any pair of supported 1-31 day intervals repeats within 930 days.
_SCHEDULE_CYCLE_DAYS = 1000
_SCHEDULE_LOOKAHEAD_DAYS = 32
_DEFAULT_CYCLE_START = date(2024, 1, 7)  # Sunday
_FGT_OUTPUT_IDS = ("water_inlet", "nutrient_a", "nutrient_b", "mixer", "irrigation")


def find_irrigation_schedule_spacing_conflicts(config: dict, device_kind: str | None) -> list[dict]:
    """Return recurring irrigation starts that are too close to the preceding run."""
    if str(device_kind or "").upper() not in IRRIGATION_DEVICE_KINDS:
        return []

    schedules = config.get("schedules")
    if not isinstance(schedules, list):
        return []
    enabled_schedules = [(index, schedule) for index, schedule in enumerate(schedules) if isinstance(schedule, dict) and schedule.get("enabled", True)]
    if not enabled_schedules:
        return []

    interval_start_dates = [
        _parse_date((schedule.get("frequency") or {}).get("start_date"))
        for _, schedule in enabled_schedules
        if (schedule.get("frequency") or {}).get("mode") == "interval"
    ]
    cycle_start = max((value for value in interval_start_dates if value is not None), default=_DEFAULT_CYCLE_START)
    occurrences = []
    for day_offset in range(_SCHEDULE_CYCLE_DAYS + _SCHEDULE_LOOKAHEAD_DAYS + 1):
        current_date = cycle_start + timedelta(days=day_offset)
        for schedule_index, schedule in enabled_schedules:
            if not _schedule_occurs_on(schedule, current_date):
                continue
            occurrences.append(
                {
                    "schedule_index": schedule_index,
                    "timestamp_sec": day_offset * 86400 + int(schedule.get("hour", 0)) * 3600 + int(schedule.get("minute", 0)) * 60,
                    "date": current_date,
                }
            )
    occurrences.sort(key=lambda item: (item["timestamp_sec"], item["schedule_index"]))

    conflicts_by_pair = {}
    for current, following in zip(occurrences, occurrences[1:], strict=False):
        if current["timestamp_sec"] >= _SCHEDULE_CYCLE_DAYS * 86400:
            break
        schedule = schedules[current["schedule_index"]]
        operation_duration_sec, duration_source = irrigation_operation_duration_sec(config, schedule, device_kind)
        required_gap_sec = operation_duration_sec + SCHEDULE_SAFETY_BUFFER_SEC
        gap_sec = following["timestamp_sec"] - current["timestamp_sec"]
        if gap_sec >= required_gap_sec:
            continue

        suggested_timestamp_sec = _ceil_to_minute(current["timestamp_sec"] + required_gap_sec)
        suggested_day_offset, suggested_clock_sec = divmod(suggested_timestamp_sec, 86400)
        source_day_offset, _ = divmod(current["timestamp_sec"], 86400)
        pair = (current["schedule_index"], following["schedule_index"])
        conflict = {
            "source_index": current["schedule_index"],
            "next_index": following["schedule_index"],
            "source_time": _schedule_time(schedule),
            "next_time": _schedule_time(schedules[following["schedule_index"]]),
            "next_day_offset": (following["date"] - current["date"]).days,
            "gap_sec": gap_sec,
            "operation_duration_sec": operation_duration_sec,
            "duration_source": duration_source,
            "required_gap_sec": required_gap_sec,
            "shortage_sec": required_gap_sec - gap_sec,
            "suggested_time": f"{suggested_clock_sec // 3600:02d}:{suggested_clock_sec % 3600 // 60:02d}",
            "suggested_day_offset": suggested_day_offset - source_day_offset,
            "maximum_operation_duration_sec": max(0, gap_sec - SCHEDULE_SAFETY_BUFFER_SEC),
        }
        previous = conflicts_by_pair.get(pair)
        if previous is None or conflict["gap_sec"] < previous["gap_sec"]:
            conflicts_by_pair[pair] = conflict

    return sorted(conflicts_by_pair.values(), key=lambda item: (item["source_index"], item["next_index"]))


def irrigation_operation_duration_sec(config: dict, schedule: dict, device_kind: str | None) -> tuple[int, str]:
    kind = str(device_kind or "").upper()
    if kind == "FGT":
        fgt = config.get("fgt") if isinstance(config.get("fgt"), dict) else {}
        timed_outputs = fgt.get("timed_outputs") if isinstance(fgt.get("timed_outputs"), dict) else {}
        if timed_outputs.get("enabled") is True:
            duration_sec = 0
            for output_id in _FGT_OUTPUT_IDS:
                output = timed_outputs.get(output_id) if isinstance(timed_outputs.get(output_id), dict) else {}
                on_sec = max(0, int(output.get("on_sec", 0)))
                off_sec = max(0, int(output.get("off_sec", 0)))
                repeat_count = max(0, int(output.get("repeat_count", 0)))
                duration_sec += on_sec * repeat_count + off_sec * max(0, repeat_count - 1)
            return duration_sec, "fgt_timed_outputs"

        limits = fgt.get("limits") if isinstance(fgt.get("limits"), dict) else {}
        return max(0, int(limits.get("max_batch_sec", 1800))), "fgt_max_batch"

    watering_pattern = config.get("watering_pattern") if isinstance(config.get("watering_pattern"), dict) else {}
    if watering_pattern.get("enabled") is True:
        on_sec = max(0, int(watering_pattern.get("on_sec", 0)))
        off_sec = max(0, int(watering_pattern.get("off_sec", 0)))
        repeat_count = max(0, int(watering_pattern.get("repeat_count", 0)))
        return on_sec * repeat_count + off_sec * max(0, repeat_count - 1), "watering_pattern"
    return max(0, int(schedule.get("duration_sec", 0))), "schedule"


def schedule_spacing_error_message(conflict: dict) -> str:
    next_label = _time_with_day_offset(conflict["next_time"], conflict["next_day_offset"])
    suggested_label = _time_with_day_offset(conflict["suggested_time"], conflict["suggested_day_offset"])
    return (
        f"{conflict['source_time']} の予約から次の {next_label} までの間隔が不足しています。"
        f"運転時間 {_format_duration(conflict['operation_duration_sec'])} に安全余裕 5分を加え、"
        f"最低 {_format_duration(conflict['required_gap_sec'])} 空けてください。"
        f"次の予約を {suggested_label} 以降にするか、直前の運転時間を短くしてください。"
    )


def _schedule_occurs_on(schedule: dict, current_date: date) -> bool:
    frequency = schedule.get("frequency") if isinstance(schedule.get("frequency"), dict) else {}
    mode = frequency.get("mode", "daily")
    if mode == "daily":
        return True
    if mode == "weekdays":
        # Runtime Config uses Sunday=0, while date.weekday() uses Monday=0.
        runtime_weekday = (current_date.weekday() + 1) % 7
        return runtime_weekday in frequency.get("weekdays", [])
    if mode == "interval":
        start_date = _parse_date(frequency.get("start_date"))
        interval_days = int(frequency.get("interval_days", 1))
        if start_date is None or interval_days <= 0 or current_date < start_date:
            return False
        return (current_date - start_date).days % interval_days == 0
    return False


def _parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _schedule_time(schedule: dict) -> str:
    return f"{int(schedule.get('hour', 0)):02d}:{int(schedule.get('minute', 0)):02d}"


def _ceil_to_minute(seconds: int) -> int:
    return ((seconds + 59) // 60) * 60


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}時間")
    if minutes:
        parts.append(f"{minutes}分")
    if remaining_seconds:
        parts.append(f"{remaining_seconds}秒")
    return "".join(parts) or "0秒"


def _time_with_day_offset(clock: str, day_offset: int) -> str:
    if day_offset == 0:
        return clock
    if day_offset == 1:
        return f"翌日 {clock}"
    return f"{day_offset}日後 {clock}"
