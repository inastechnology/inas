import json
import struct
import threading
from datetime import UTC, datetime, timedelta, timezone
from urllib import error, request

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

DISCORD_CONTENT_LIMIT = 2000
PAYLOAD_PREVIEW_LIMIT = 900
DEBUG_LOG_HEADER_SIZE = 16
DEBUG_LOG_RECORD_SIZE = 13
DEBUG_LOG_MAX_DISPLAY_RECORDS = 20

DEBUG_LOG_LEVELS = {
    1: "INFO",
    2: "WARNING",
    3: "ERROR",
}

DEBUG_LOG_FILES = {
    1: ("APP", "src/app/src/app.cpp"),
    2: ("NETWORK", "common/lib/ina-client-common/src/app/src/app_network.cpp"),
    3: ("RUNTIME_CONFIG", "src/app/src/app_runtime_config.cpp"),
    4: ("WATERING", "src/app/src/app_watering.cpp"),
}

DEBUG_LOG_EVENTS = {
    1: ("BOOT", "起動"),
    2: ("LITTLEFS_MOUNTED", "LittleFS マウント完了"),
    3: ("CONFIG_LOADED", "保存設定読み込み"),
    4: ("RUNTIME_CONFIG_INIT", "runtime config 初期化"),
    5: ("NETWORK_START", "ネットワーク開始"),
    6: ("NETWORK_UNAVAILABLE", "ネットワーク利用不可"),
    7: ("RUNTIME_CONFIG_REQUEST", "runtime config 要求"),
    8: ("RUNTIME_CONFIG_ACTIVE", "runtime config 適用中"),
    9: ("TIME_SYNC_NTP_FAILED_RTC", "NTP 同期失敗、RTC を使用"),
    10: ("TIME_SYNC_OFFLINE_RTC", "オフラインのため RTC を使用"),
    11: ("TIME_SYNC_UNAVAILABLE", "時刻同期不可"),
    12: ("TIME_SYNC_OK", "時刻同期成功"),
    13: ("SCHEDULE_CHECK", "スケジュール判定"),
    14: ("WATERING_DUE_RESULT", "灌水予定判定結果"),
    15: ("SLEEP_PLANNED", "次回 sleep 計画"),
    16: ("STATUS_SENT", "status 送信成功"),
    17: ("STATUS_FAILED", "status 送信失敗"),
    18: ("STATUS_SKIPPED", "status 送信スキップ"),
    19: ("DEBUG_LOG_PUBLISH_ENABLED", "debug log 送信有効"),
    30: ("MQTT_DNS_FAILED", "MQTT DNS 解決失敗"),
    31: ("MQTT_CONNECTED", "MQTT 接続成功"),
    32: ("MQTT_FAILED", "MQTT 接続失敗"),
    33: ("WIFI_FAILED", "Wi-Fi 接続失敗"),
    34: ("WIFI_CONNECTED", "Wi-Fi 接続成功"),
    35: ("WIFI_RECONNECT_FAILED", "Wi-Fi 再接続失敗"),
    36: ("WIFI_RECONNECTED", "Wi-Fi 再接続成功"),
    50: ("RUNTIME_CONFIG_UPDATED", "runtime config 更新"),
    70: ("WATERING_OUTPUT_MAP", "灌水出力マップ"),
    71: ("WATERING_DECISION", "灌水判定"),
    72: ("WATERING_OUTPUT_START_FAILED", "灌水出力開始失敗"),
    73: ("WATERING_STARTED", "灌水開始"),
    74: ("WATERING_SKIPPED_MOISTURE", "土壌水分により灌水スキップ"),
    75: ("WATERING_COMPLETED", "灌水完了"),
    82: ("OTA_OFFER_TIMEOUT", "OTA offer 待機タイムアウト"),
    83: ("OTA_OFFER_RECEIVED", "OTA offer 受信"),
    84: ("OTA_HANDLE_RESULT", "OTA 処理結果"),
}


class DiscordNotificationService:
    def __init__(self, webhook_url: str | None = None):
        discord_settings = setting().get("discord") or {}
        self.discord_settings = discord_settings
        self.webhook_url = (webhook_url if webhook_url is not None else discord_settings.get("webhook_url", "")).strip()

    def enabled(self):
        return bool(self.webhook_url)

    def notification_enabled(self, notification_type: str):
        key = f"notify_{notification_type}"
        return bool(self.discord_settings.get(key, True))

    def notify_mqtt_activity(self, direction: str, topic: str, payload=None, parsed_message: dict | None = None, mqtt_rc: int | None = None):
        if not self.enabled() or not self.notification_enabled("mqtt_activity"):
            return

        content = format_mqtt_activity(direction, topic, payload=payload, parsed_message=parsed_message, mqtt_rc=mqtt_rc)
        worker_thread = threading.Thread(target=self._post, args=(content,), daemon=True)
        worker_thread.start()

    def notify_new_device(self, device_id: str, record: dict, source: str, payload: dict | None = None):
        if not self.enabled() or not self.notification_enabled("new_device"):
            return

        content = format_new_device(device_id, record, source, payload=payload)
        worker_thread = threading.Thread(target=self._post, args=(content,), daemon=True)
        worker_thread.start()

    def notify_health_alert(self, alert_type: str, device_id: str, record: dict, details: dict):
        if not self.enabled() or not self.notification_enabled(alert_type):
            return

        content = format_health_alert(alert_type, device_id, record, details)
        worker_thread = threading.Thread(target=self._post, args=(content,), daemon=True)
        worker_thread.start()

    def _post(self, content: str):
        body = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "ina-device-hub"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                if response.status >= 300:
                    logger.warning("Discord webhook returned status=%s", response.status)
        except error.HTTPError as exc:
            logger.warning("Discord webhook failed with status=%s", exc.code)
        except Exception:
            logger.exception("Discord webhook notification failed")


def format_mqtt_activity(direction: str, topic: str, payload=None, parsed_message: dict | None = None, mqtt_rc: int | None = None):
    parsed_message = {**_parse_topic(topic), **(parsed_message or {})}
    payload_data = _decode_payload(payload)
    lines = [f"[INA Device Hub] {_event_title(direction, topic, parsed_message)}", f"時刻: {_local_time()}"]

    device_id = parsed_message.get("device_id")
    if device_id is not None:
        lines.append(f"デバイス: {device_id}")

    if mqtt_rc is not None:
        lines.append(f"MQTT結果: {'成功' if mqtt_rc == 0 else f'失敗 rc={mqtt_rc}'}")

    summary = _payload_summary(direction, parsed_message, payload_data)
    if summary:
        lines.extend(summary)

    lines.append(f"topic: {topic}")

    if _should_show_raw_payload(parsed_message, payload_data):
        payload_preview = _payload_preview(payload_data if payload_data is not None else payload)
        if payload_preview:
            lines.append("詳細:")
            lines.append(f"```json\n{payload_preview}\n```")

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[: DISCORD_CONTENT_LIMIT - 20] + "\n...[省略]"
    return content


def format_new_device(device_id: str, record: dict, source: str, payload: dict | None = None):
    lines = [
        "[INA Device Hub] 【新規デバイス検出】未登録デバイスが接続しました",
        f"時刻: {_local_time()}",
        f"デバイス: {device_id}",
        f"状態: {record.get('state') or 'pending'}",
        f"検出元: {source}",
    ]

    if record.get("first_seen_at"):
        lines.append(f"初回検出: {record['first_seen_at']}")

    device_kind = record.get("device_kind") or (payload or {}).get("device_kind")
    if device_kind:
        lines.append(f"種別: {device_kind}")

    firmware_version = record.get("firmware_version") or (payload or {}).get("firmware_version")
    if firmware_version:
        lines.append(f"FW: {firmware_version}")

    firmware_build_id = record.get("firmware_build_id") or (payload or {}).get("firmware_build_id")
    if firmware_build_id:
        lines.append(f"Build: {firmware_build_id}")

    if isinstance(payload, dict):
        status_lines = _payload_summary("received", {"category": "agri", "action": "immediate"}, payload)
        if status_lines:
            lines.append("状態概要:")
            lines.extend(status_lines[:8])

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[: DISCORD_CONTENT_LIMIT - 20] + "\n...[省略]"
    return content


def format_health_alert(alert_type: str, device_id: str, record: dict, details: dict):
    if alert_type == "device_offline":
        title = "【死活監視】デバイスの接続が途絶えています"
    elif alert_type == "watering_missing":
        title = "【死活監視】水やりが一定期間確認できません"
    elif alert_type == "soil_calibration_suggested":
        title = "【水分計】校正値の見直し候補があります"
    else:
        title = "【死活監視】確認が必要です"

    lines = [
        f"[INA Device Hub] {title}",
        f"時刻: {_local_time()}",
        f"デバイス: {device_id}",
        f"状態: {record.get('state') or 'unknown'}",
    ]
    if record.get("name"):
        lines.append(f"名前: {record['name']}")
    if record.get("location"):
        lines.append(f"場所: {record['location']}")
    if record.get("device_kind"):
        lines.append(f"種別: {record['device_kind']}")

    if details.get("last_seen_at"):
        lines.append(f"最終接続: {details['last_seen_at']}")
    if details.get("offline_hours") is not None:
        lines.append(f"未接続時間: {details['offline_hours']:.1f} 時間")
    if details.get("offline_threshold_hours") is not None:
        lines.append(f"しきい値: {details['offline_threshold_hours']} 時間")
    if details.get("last_watering_at"):
        lines.append(f"最終水やり: {details['last_watering_at']}")
    if details.get("days_since_watering") is not None:
        lines.append(f"未水やり日数: {details['days_since_watering']:.1f} 日")
    if details.get("watering_threshold_days") is not None:
        lines.append(f"しきい値: {details['watering_threshold_days']} 日")
    if details.get("soil_raw_before_watering") is not None:
        lines.append(f"灌水前 raw: {details['soil_raw_before_watering']}")
    if details.get("soil_raw_after_watering") is not None:
        lines.append(f"灌水後 raw: {details['soil_raw_after_watering']}")
    if details.get("soil_calibration_dry_raw") is not None and details.get("soil_calibration_wet_raw") is not None:
        lines.append(f"現在の校正値: dry={details['soil_calibration_dry_raw']} wet={details['soil_calibration_wet_raw']}")
    if details.get("soil_calibration_suggested_dry_raw") is not None and details.get("soil_calibration_suggested_wet_raw") is not None:
        lines.append(
            f"候補の校正値: dry={details['soil_calibration_suggested_dry_raw']} wet={details['soil_calibration_suggested_wet_raw']}"
        )
    if details.get("soil_calibration_applied") is not None:
        lines.append(f"device反映: {_format_value(details['soil_calibration_applied'], 'soil_calibration_applied')}")

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[: DISCORD_CONTENT_LIMIT - 20] + "\n...[省略]"
    return content


def _event_title(direction: str, topic: str, parsed_message: dict):  # noqa: PLR0911
    category = parsed_message.get("category")
    action = parsed_message.get("action")
    message_type = parsed_message.get("message_type")
    kind = parsed_message.get("kind")

    if direction == "connected":
        return "【MQTT接続】Hub が broker に接続しました"
    if direction == "connect_failed":
        return "【MQTT接続失敗】Hub が broker に接続できません"
    if direction == "publish" and category == "config" and action == "reply":
        return "【設定返信】Hub が runtime config を送信しました"
    if direction == "publish" and category == "config" and action == "push":
        return "【設定Push】Hub が runtime config を即時配信しました"
    if direction == "received" and category == "config" and action == "request":
        return "【設定要求】デバイスが runtime config を要求しました"
    if direction == "received" and category == "agri" and action == "immediate":
        return "【状態通知】デバイスの稼働状態を受信しました"
    if direction == "received" and category == "debug" and action == "log":
        return "【Debug Log】デバイスの起床ログを受信しました"
    if direction == "received" and message_type == "sensor_data":
        return f"【センサーデータ】{kind or 'telemetry'} を受信しました"
    if direction == "publish":
        return "【MQTT送信】Hub が message を publish しました"
    if direction == "received":
        return "【MQTT受信】Hub が message を受信しました"
    return f"【MQTT】{direction}"


def _parse_topic(topic: str):
    parts = [part for part in topic.split("/") if part]
    if len(parts) == 3 and parts[0] == "farm" and parts[2] == "telemetry":
        return {"message_type": "sensor_data", "device_id": parts[1], "kind": "telemetry"}
    if len(parts) >= 3 and parts[0] == "sensor":
        return {"message_type": "sensor_data", "device_id": parts[1], "kind": parts[2]}
    if len(parts) >= 4 and parts[1] == "kinds":
        return {"message_type": "device_config", "device_id": parts[0], "category": parts[2], "action": parts[3]}
    return {}


def _payload_summary(direction: str, parsed_message: dict, payload_data):  # noqa: PLR0911
    category = parsed_message.get("category")
    action = parsed_message.get("action")

    if category == "debug" and action == "log" and isinstance(payload_data, dict) and payload_data.get("_payload_type") == "debug_log":
        return _format_debug_log_summary(payload_data)

    if direction == "connected" and isinstance(payload_data, dict):
        broker = payload_data.get("broker")
        return [f"接続先: {broker}"] if broker else []

    if category == "config" and action == "request":
        request_name = payload_data.get("request") if isinstance(payload_data, dict) else None
        return [f"要求: {request_name or 'runtime_config'}"]

    if category == "config" and action in {"reply", "push"} and isinstance(payload_data, dict):
        lines = []
        if payload_data.get("ntp_server"):
            lines.append(f"NTP: {payload_data['ntp_server']}")
        if payload_data.get("timezone_offset_sec") is not None:
            lines.append(f"Timezone offset: {payload_data['timezone_offset_sec']} 秒")
        if payload_data.get("moisture_threshold") is not None:
            lines.append(f"灌水しきい値: {payload_data['moisture_threshold']}%")
        if payload_data.get("force_watering") is not None:
            lines.append(f"強制灌水: {_format_value(payload_data['force_watering'], 'force_watering')}")
        schedules = payload_data.get("schedules")
        if isinstance(schedules, list):
            lines.append("スケジュール: " + _format_schedules(schedules))
        return lines

    if category == "agri" and action == "immediate" and isinstance(payload_data, dict):
        label_map = {
            "seq": "seq",
            "config_received": "設定受信",
            "time_synced": "時刻同期",
            "watering_due": "灌水予定時刻",
            "watering_started": "灌水開始",
            "last_soil_moisture": "土壌水分",
            "next_sleep_sec": "次回起床",
            "threshold": "しきい値",
            "battery_v": "電池電圧",
            "rssi": "RSSI",
        }
        lines = []
        for key, label in label_map.items():
            if key in payload_data:
                lines.append(f"{label}: {_format_value(payload_data[key], key)}")
        return lines

    if isinstance(payload_data, dict):
        important_keys = ("device_id", "timestamp", "soil_moisture_1_pct", "soil_moisture_2_pct", "soil_temp_c", "battery_v", "rssi")
        lines = [f"{key}: {_format_value(payload_data[key], key)}" for key in important_keys if key in payload_data]
        return lines[:8]

    return []


def _format_schedules(schedules: list):
    if not schedules:
        return "なし"
    formatted = []
    for schedule in schedules[:4]:
        if not isinstance(schedule, dict):
            continue
        hour = schedule.get("hour")
        minute = schedule.get("minute")
        duration_sec = schedule.get("duration_sec")
        channel_mask = schedule.get("channel_mask")
        if isinstance(hour, int) and isinstance(minute, int):
            formatted.append(f"{hour:02d}:{minute:02d} / {duration_sec}秒 / ch={channel_mask}")
    if len(schedules) > 4:
        formatted.append(f"ほか {len(schedules) - 4} 件")
    return ", ".join(formatted) if formatted else "不明"


def _format_value(value, key: str):
    if isinstance(value, bool):
        return "はい" if value else "いいえ"
    if key == "next_sleep_sec":
        return _format_next_wake_time(value)
    if key == "battery_v":
        return f"{value} V"
    if key in {"soil_moisture_1_pct", "soil_moisture_2_pct", "last_soil_moisture", "threshold"}:
        return f"{value}%"
    return value


def _should_show_raw_payload(parsed_message: dict, payload_data):
    if payload_data is None:
        return False
    if not parsed_message.get("message_type"):
        return True
    category = parsed_message.get("category")
    action = parsed_message.get("action")
    if category == "config" and action in {"request", "reply", "push"}:
        return False
    if category == "agri" and action == "immediate":
        return False
    if category == "debug" and action == "log" and isinstance(payload_data, dict) and payload_data.get("_payload_type") == "debug_log":
        return False
    return not isinstance(payload_data, dict)


def _decode_payload(payload):
    if payload is None:
        return None
    if isinstance(payload, bytes):
        debug_log = _decode_debug_log_payload(payload)
        if debug_log is not None:
            return debug_log
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


def _decode_debug_log_payload(payload: bytes):
    if len(payload) < DEBUG_LOG_HEADER_SIZE or payload[:3] != b"DLG":
        return None

    version = payload[3]
    if version != 1:
        return {
            "_payload_type": "debug_log",
            "decode_error": f"unsupported debug log version: {version}",
            "version": version,
            "raw_bytes": len(payload),
        }

    seq, total_records, sent_records, dropped = struct.unpack_from("<IHHH", payload, 4)
    record_size = payload[14]
    flags = payload[15]
    if record_size != DEBUG_LOG_RECORD_SIZE:
        return {
            "_payload_type": "debug_log",
            "decode_error": f"unsupported debug log record size: {record_size}",
            "version": version,
            "seq": seq,
            "total_records": total_records,
            "sent_records": sent_records,
            "dropped": dropped,
            "flags": flags,
            "raw_bytes": len(payload),
        }

    records = []
    offset = DEBUG_LOG_HEADER_SIZE
    for index in range(sent_records):
        if offset + record_size > len(payload):
            return {
                "_payload_type": "debug_log",
                "decode_error": f"truncated debug log record at index {index}",
                "version": version,
                "seq": seq,
                "total_records": total_records,
                "sent_records": sent_records,
                "dropped": dropped,
                "flags": flags,
                "raw_bytes": len(payload),
                "records": records,
            }
        file_id, line, level, event_code, arg0, arg1 = struct.unpack_from("<BHBBii", payload, offset)
        records.append(
            {
                "file_id": file_id,
                "line": line,
                "level": level,
                "event": event_code,
                "arg0": arg0,
                "arg1": arg1,
            }
        )
        offset += record_size

    return {
        "_payload_type": "debug_log",
        "version": version,
        "seq": seq,
        "total_records": total_records,
        "sent_records": sent_records,
        "dropped": dropped,
        "record_size": record_size,
        "flags": flags,
        "raw_bytes": len(payload),
        "records": records,
    }


def _format_debug_log_summary(debug_log: dict):
    if debug_log.get("decode_error"):
        return [
            "Debug log decode error: " + str(debug_log["decode_error"]),
            f"payload bytes: {debug_log.get('raw_bytes')}",
        ]

    records = debug_log.get("records") or []
    lines = [
        f"Debug seq: {debug_log.get('seq')}",
        f"Records: {debug_log.get('sent_records')}/{debug_log.get('total_records')} sent, dropped={debug_log.get('dropped')}, bytes={debug_log.get('raw_bytes')}",
    ]
    if debug_log.get("flags"):
        lines.append(f"Flags: {debug_log.get('flags')}")

    for index, record in enumerate(records[:DEBUG_LOG_MAX_DISPLAY_RECORDS], start=1):
        lines.append(f"{index}. {_format_debug_log_record(record)}")

    if len(records) > DEBUG_LOG_MAX_DISPLAY_RECORDS:
        lines.append(f"...ほか {len(records) - DEBUG_LOG_MAX_DISPLAY_RECORDS} 件")
    return lines


def _format_debug_log_record(record: dict):
    level = DEBUG_LOG_LEVELS.get(record.get("level"), f"LEVEL-{record.get('level')}")
    file_name, source_path = DEBUG_LOG_FILES.get(record.get("file_id"), (f"FILE-{record.get('file_id')}", "unknown"))
    event_symbol, event_label = DEBUG_LOG_EVENTS.get(record.get("event"), (f"EVENT-{record.get('event')}", "未定義イベント"))
    args = _format_debug_log_args(record.get("event"), record.get("arg0"), record.get("arg1"))
    return f"[{level}] {event_label} ({event_symbol}) @ {file_name}:{record.get('line')} [{source_path}] {args}"


def _format_debug_log_args(event_code, arg0, arg1):  # noqa: PLR0911
    if event_code in {8, 50}:
        flags = _decode_runtime_flags(arg0)
        parts = [
            f"しきい値={flags['moisture_threshold']}%",
            f"強制灌水={_yes_no(flags['force_watering'])}",
            f"debug_log={_yes_no(flags['debug_log_on_wake'])}",
            f"schedule_count={flags['schedule_count']}",
        ]
        if event_code == 50:
            parts.append(f"timezone_offset_sec={arg1}")
        return ", ".join(parts)
    if event_code == 1:
        return f"reset_reason={arg0}"
    if event_code == 3:
        return f"network_configured={_yes_no(arg0)}, config_crc32=0x{arg1 & 0xFFFFFFFF:08x}"
    if event_code == 4:
        return f"runtime_config_valid={_yes_no(arg0)}, debug_log_on_wake={_yes_no(arg1)}"
    if event_code == 5:
        return f"network_start={_success_fail(arg0)}, mqtt_connected={_yes_no(arg1)}"
    if event_code == 7:
        return f"request_published={_yes_no(arg0)}, config_received={_yes_no(arg1)}"
    if event_code in {9, 10}:
        return f"using_rtc={_yes_no(arg0)}"
    if event_code == 11:
        return f"woke_from_deep_sleep={_yes_no(arg0)}"
    if event_code == 12:
        return f"epoch={arg0}"
    if event_code == 13:
        return f"watering_due={_yes_no(arg0 & 1)}, runtime_config_valid={_yes_no(arg0 & 2)}, last_executed_schedule_utc={arg1}"
    if event_code == 14:
        return f"duration_sec={arg0 & 0xFFFF}, watering_started={_yes_no(arg0 & 0x10000)}, channel_mask={arg1}"
    if event_code == 15:
        return f"sleep_sec={arg0}"
    if event_code == 19:
        return f"status_sent={_yes_no(arg0)}, sleep_sec={arg1}"
    if event_code in {30, 31, 32}:
        context = {1: "startup", 2: "reconnect"}.get(arg0, arg0)
        if event_code == 31:
            return f"context={context}, mqtt_port={arg1}"
        if event_code == 32:
            return f"context={context}, mqtt_state={arg1}"
        return f"context={context}"
    if event_code in {33, 35}:
        return f"wifi_status={arg0}"
    if event_code in {34, 36}:
        return f"rssi={arg0} dBm"
    if event_code == 70:
        return f"valve_mask={arg0}, pump_mask={arg1}"
    if event_code == 71:
        flags = _decode_watering_decision_flags(arg0)
        return f"soil={flags['soil_moisture']}%, threshold={flags['threshold']}%, force_watering={_yes_no(flags['force_watering'])}, output_mask={arg1}"
    if event_code in {72, 73}:
        return f"duration_sec={arg0}, output_mask={arg1}"
    if event_code == 74:
        return f"soil={arg0}%, threshold={arg1}%"
    if event_code == 82:
        return f"offer_wait_ms={arg0}"
    if event_code == 83:
        return f"offer_received={_yes_no(arg0)}, offer_wait_timeout_ms={arg1}"
    if event_code == 84:
        return f"update_attempted={_yes_no(arg0)}"
    return f"arg0={arg0}, arg1={arg1}"


def _decode_runtime_flags(value):
    return {
        "moisture_threshold": value & 0xFF,
        "force_watering": bool(value & 0x100),
        "debug_log_on_wake": bool(value & 0x200),
        "schedule_count": (value >> 16) & 0xFF,
    }


def _decode_watering_decision_flags(value):
    return {
        "soil_moisture": value & 0xFF,
        "threshold": (value >> 8) & 0xFF,
        "force_watering": bool(value & 0x10000),
    }


def _yes_no(value):
    return "はい" if bool(value) else "いいえ"


def _success_fail(value):
    return "成功" if bool(value) else "失敗"


def _local_time():
    return datetime.now(UTC).astimezone(_jst()).strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_next_wake_time(next_sleep_sec):
    if not isinstance(next_sleep_sec, int | float):
        return next_sleep_sec
    wake_time = datetime.now(UTC).astimezone(_jst()) + timedelta(seconds=next_sleep_sec)
    return f"{wake_time.strftime('%Y-%m-%d %H:%M:%S JST')} ({int(next_sleep_sec)} 秒後)"


def _jst():
    return timezone(timedelta(hours=9), "JST")


def _payload_preview(payload):
    if payload is None:
        return ""

    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            text = str(payload)

    text = text.strip()
    if len(text) > PAYLOAD_PREVIEW_LIMIT:
        text = text[:PAYLOAD_PREVIEW_LIMIT] + "...[省略]"
    return text


def discord_notification_service():
    return DiscordNotificationService()
