import json
import threading
from datetime import UTC, datetime, timedelta, timezone
from urllib import error, request

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

DISCORD_CONTENT_LIMIT = 2000
PAYLOAD_PREVIEW_LIMIT = 900


class DiscordNotificationService:
    def __init__(self, webhook_url: str | None = None):
        discord_settings = setting().get("discord") or {}
        self.webhook_url = (webhook_url if webhook_url is not None else discord_settings.get("webhook_url", "")).strip()

    def enabled(self):
        return bool(self.webhook_url)

    def notify_mqtt_activity(self, direction: str, topic: str, payload=None, parsed_message: dict | None = None, mqtt_rc: int | None = None):
        if not self.enabled():
            return

        content = format_mqtt_activity(direction, topic, payload=payload, parsed_message=parsed_message, mqtt_rc=mqtt_rc)
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


def _event_title(direction: str, topic: str, parsed_message: dict):
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


def _payload_summary(direction: str, parsed_message: dict, payload_data):
    category = parsed_message.get("category")
    action = parsed_message.get("action")

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
    return not isinstance(payload_data, dict)


def _decode_payload(payload):
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


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
