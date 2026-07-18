import copy
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from ina_device_hub.collection_search import matches_search, paginate, search_terms
from ina_device_hub.device_config_repository import (
    DeviceStateConflictError,
    device_config_repository,
    validate_device_config,
)
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.general_log import logger
from ina_device_hub.sensor_measurement_repository import safe_record_status_measurements
from ina_device_hub.setting import setting


class DeviceConfigService:
    def __init__(self, repository=None, notification_service=None):
        self.repository = repository or device_config_repository()
        self.notification_service = notification_service or discord_notification_service()
        self.mqtt_client = None

    def attach_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def default_config(self):
        device_config_defaults = setting().get("device_config_defaults")
        return {
            "ntp_server": device_config_defaults["ntp_server"],
            "timezone_offset_sec": device_config_defaults["timezone_offset_sec"],
            "moisture_threshold": device_config_defaults["moisture_threshold"],
            "force_watering": True,
            "debug_log_on_wake": False,
            "ota_check_interval_sec": 21600,
            "watering_pattern": {
                "enabled": False,
                "on_sec": 0,
                "off_sec": 0,
                "repeat_count": 0,
            },
            "soil_calibration": {
                "mode": "normal",
                "request_id": "",
                "calibrated": False,
                "auto_mode_enabled": False,
                "apply_auto_calibration": False,
                "drift_check_enabled": False,
                "dry_raw": 1895,
                "wet_raw": 1285,
                "min_delta_raw": 80,
                "drift_tolerance_raw": 120,
                "sample_count": 20,
                "sample_interval_ms": 40,
            },
            "env_sensors": {
                "par": {
                    "enabled": True,
                    "modbus_slave_id": 1,
                    "modbus_function": 3,
                    "register": 0,
                },
                "soil": {
                    "enabled": False,
                    "modbus_slave_id": 2,
                    "modbus_function": 4,
                    "start_register": 0,
                },
                "power_settle_ms": 800,
            },
            "env_calibration": {
                "mode": "normal",
                "request_id": "",
                "target": "par_umol_m2_s",
                "reference_value": 0.0,
                "par_umol_m2_s": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_moisture_percent": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_temperature_c": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_ec_us_cm": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_ph": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_n_mg_kg": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_p_mg_kg": {"calibrated": False, "scale": 1.0, "offset": 0.0},
                "soil_k_mg_kg": {"calibrated": False, "scale": 1.0, "offset": 0.0},
            },
            "wrs": {
                "watering": {
                    "enabled": True,
                    "auto_on_low_moisture": False,
                    "require_soil_feedback": True,
                    "force_watering": False,
                    "moisture_threshold": device_config_defaults["moisture_threshold"],
                    "stop_moisture_percent": 55,
                    "max_duration_sec": 60,
                    "check_interval_sec": 10,
                    "channel_mask": 1,
                },
                "sensors": {
                    "soil": {
                        "enabled": True,
                        "modbus_slave_id": 2,
                        "modbus_function": 4,
                        "start_register": 0,
                    },
                    "par": {
                        "enabled": False,
                        "modbus_slave_id": 1,
                        "modbus_function": 3,
                        "register": 0,
                        "scale": 1.0,
                    },
                    "power_settle_ms": 800,
                },
            },
            "mosfet_switches": [
                {
                    "switch_id": "irr1",
                    "name": "灌水1系",
                    "enabled": True,
                    "role": "irrigation",
                    "terminal": "IRR1",
                    "channel_mask": 1,
                    "controlled_load": "",
                    "notes": "",
                },
                {
                    "switch_id": "irr2",
                    "name": "灌水2系",
                    "enabled": True,
                    "role": "irrigation",
                    "terminal": "IRR2",
                    "channel_mask": 2,
                    "controlled_load": "",
                    "notes": "",
                },
            ],
            "schedules": [
                {
                    "hour": 6,
                    "minute": 30,
                    "duration_sec": 1,
                    "channel_mask": 1,
                    "frequency": {"mode": "daily"},
                }
            ],
        }

    def get_record(self, device_id: str):
        return self.repository.get_or_create(device_id, self.default_config())

    def find_record(self, device_id: str):
        return self.repository.get(device_id)

    def get_config(self, device_id: str):
        return self.get_record(device_id)["config"]

    def get_all_records(self):
        return self.repository.get_all()

    def search_records(self, *, query="", states=None, device_kinds=None, page=1, page_size=50):
        terms = search_terms(query)
        state_filter = {str(item or "").strip() for item in (states or []) if str(item or "").strip()}
        kind_filter = {str(item or "").strip().upper() for item in (device_kinds or []) if str(item or "").strip()}
        matches = []
        for device_id, record in self.repository.get_all().items():
            state = str(record.get("state") or "unknown")
            last_status = record.get("last_status") if isinstance(record.get("last_status"), dict) else {}
            device_kind = str(record.get("device_kind") or last_status.get("device_kind") or "").upper()
            if state_filter and state not in state_filter:
                continue
            if kind_filter and device_kind not in kind_filter:
                continue
            config = record.get("config") if isinstance(record.get("config"), dict) else {}
            switches = config.get("mosfet_switches") if isinstance(config.get("mosfet_switches"), list) else []
            if not matches_search(
                terms,
                [
                    device_id,
                    record.get("name"),
                    record.get("location"),
                    record.get("memo"),
                    state,
                    device_kind,
                    [[switch.get("name"), switch.get("switch_id"), switch.get("controlled_load")] for switch in switches if isinstance(switch, dict)],
                ],
            ):
                continue
            summary = copy.deepcopy(record)
            summary.pop("status_history", None)
            summary.pop("ota_status_history", None)
            summary.pop("runtime_config", None)
            matches.append((device_id, summary))
        matches.sort(key=lambda item: ((item[1].get("name") or item[0]).casefold(), item[0]))
        result = paginate(matches, page=page, page_size=page_size)
        result["items"] = {device_id: record for device_id, record in result["items"]}
        return result

    def update_config(self, device_id: str, config: dict):
        return self.repository.upsert(device_id, config)

    def record_config_request(self, device_id: str):
        is_new_device = self.repository.get(device_id) is None
        record = self.repository.record_config_request(device_id, self.default_config())
        if is_new_device:
            self._notify_new_device(device_id, record, "config_request")
        return record

    def record_status(self, device_id: str, status: dict):
        is_new_device = self.repository.get(device_id) is None
        record = self.repository.record_status(device_id, status)
        if is_new_device:
            self._notify_new_device(device_id, record, "status", payload=status)
        _log_device_status(device_id, record["last_status_at"], status)
        safe_record_status_measurements(device_id, status, record["last_status_at"])
        append_device_event(
            "device_status",
            "inbound",
            device_id,
            category="agri",
            action="immediate",
            payload=status,
            occurred_at=record["last_status_at"],
        )
        return record

    def update_metadata(self, device_id: str, metadata: dict):
        return self.repository.update_metadata(device_id, metadata)

    def set_state(self, device_id: str, state: str, approved_by: str | None = None):
        return self.repository.set_state(device_id, state, approved_by=approved_by)

    def list_statuses(self, device_id: str, limit: int = 100):
        return self.repository.list_statuses(device_id, limit=limit)

    def _config_for_reply(self, device_id: str):
        record = self.repository.record_config_request(device_id, self.default_config())
        if record["state"] == "active" and record.get("config"):
            return validate_device_config(record["config"])
        return self.default_config()

    def publish_config(self, device_id: str, action: str, config: dict | None = None, retain: bool = False):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        config = validate_device_config(config or self.get_config(device_id))
        topic = f"/{device_id}/kinds/config/{action}"
        payload = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
        result = self.mqtt_client.publish(topic, payload, qos=0, retain=retain)
        append_device_event(
            "device_config_publish",
            "outbound",
            device_id,
            topic=topic,
            category="config",
            action=action,
            payload=config,
            mqtt_rc=result.rc,
            retain=retain,
        )
        if result.rc != 0:
            logger.error(
                "Failed to publish config for device_id=%s topic=%s rc=%s",
                device_id,
                topic,
                result.rc,
            )
        return {"topic": topic, "payload": config, "mqtt_rc": result.rc}

    def publish_reply(self, device_id: str):
        published = self.publish_config(device_id, "reply", config=self._config_for_reply(device_id), retain=False)
        self.repository.record_config_reply(device_id)
        return published

    def publish_push(self, device_id: str):
        record = self.repository.get(device_id)
        state = record.get("state") if record else "pending"
        if state != "active":
            raise DeviceStateConflictError(f"runtime config can only be sent to active devices (current: {state})")
        return self.publish_config(device_id, "push", retain=True)

    def handle_mqtt_message(self, mqtt_client, message: dict):
        del mqtt_client
        if message.get("message_type") != "device_config":
            return False

        device_id = message["device_id"]
        category = message.get("category")
        action = message.get("action")
        if category == "config" and action == "request":
            try:
                request_payload = _decode_optional_json_payload(message.get("payload"))
                append_device_event(
                    "device_config_request",
                    "inbound",
                    device_id,
                    topic=message.get("topic"),
                    category=category,
                    action=action,
                    payload=request_payload,
                )
                if request_payload is not None and request_payload.get("request") != "runtime_config":
                    logger.warning("Unexpected config request payload for device_id=%s payload=%s", device_id, request_payload)
                is_new_device = self.repository.get(device_id) is None
                self.publish_reply(device_id)
                if is_new_device:
                    record = self.repository.get(device_id)
                    self._notify_new_device(device_id, record, "config_request", payload=request_payload)
            except Exception:
                logger.exception("Config reply failed for device_id=%s", device_id)
                raise
            return True

        if category == "agri" and action == "immediate":
            try:
                self.record_status(device_id, _decode_json_payload(message.get("payload")))
            except ValueError:
                logger.exception("Status payload parse failure for device_id=%s", device_id)
                return True
            return True

        return False

    def update_and_optionally_push(self, device_id: str, config: dict, push: bool = False):
        record = self.update_config(device_id, config)
        published: dict | None = None
        if push:
            published = self.publish_push(device_id)
        return {"record": record, "published": published}

    def _notify_new_device(self, device_id: str, record: dict | None, source: str, payload: dict | None = None):
        if record is None:
            return
        try:
            self.notification_service.notify_new_device(device_id, record, source, payload=payload)
        except Exception:
            logger.exception("New device Discord notification failed for device_id=%s", device_id)


def _decode_json_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("payload must be valid JSON") from exc
    else:
        decoded = payload

    if not isinstance(decoded, dict):
        raise ValueError("payload must be a JSON object")
    return decoded


def _decode_optional_json_payload(payload):
    if payload in (None, b"", ""):
        return None

    try:
        return _decode_json_payload(payload)
    except ValueError:
        logger.warning("Ignoring invalid config request payload: %r", payload)
        return None


def _log_device_status(device_id: str, received_at: str, status: dict):
    next_sleep_sec = status.get("next_sleep_sec")
    next_wake_at = None
    if isinstance(next_sleep_sec, int | float):
        received_at_dt = datetime.fromisoformat(received_at)
        if received_at_dt.tzinfo is None:
            received_at_dt = received_at_dt.replace(tzinfo=UTC)
        next_wake_at = (received_at_dt + timedelta(seconds=next_sleep_sec)).isoformat()

    logger.info(
        "Device sleep status: device_id=%s received_at=%s next_sleep_sec=%s next_wake_at=%s seq=%s config_received=%s time_synced=%s watering_due=%s watering_started=%s "
        "watering_duration_sec=%s channel_mask=%s last_soil_moisture=%s threshold=%s force_watering=%s payload=%s",
        device_id,
        received_at,
        next_sleep_sec,
        next_wake_at,
        status.get("seq"),
        status.get("config_received"),
        status.get("time_synced"),
        status.get("watering_due"),
        status.get("watering_started"),
        status.get("watering_duration_sec"),
        status.get("channel_mask"),
        status.get("last_soil_moisture"),
        status.get("threshold"),
        status.get("force_watering"),
        json.dumps(status, ensure_ascii=True, separators=(",", ":")),
    )


@lru_cache(maxsize=1)
def device_config_service():
    return DeviceConfigService()
