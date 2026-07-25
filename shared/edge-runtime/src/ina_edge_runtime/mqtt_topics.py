from typing import Any

_FARM_TOPIC_PARTS = 3
_MINIMUM_SENSOR_TOPIC_PARTS = 3
_SENSOR_SEQUENCE_INDEX = 3
_MINIMUM_KINDS_TOPIC_PARTS = 4
_MINIMUM_BROKER_LOG_TOPIC_PARTS = 4


def parse_mqtt_message(topic: str, payload: Any) -> dict[str, Any]:
    parts = [part for part in topic.split("/") if part]

    if len(parts) == _FARM_TOPIC_PARTS and parts[0] == "farm" and parts[2] == "telemetry":
        return {
            "message_type": "sensor_data",
            "topic": topic,
            "device_id": parts[1],
            "kind": "telemetry",
            "payload": payload,
            "seqId": None,
        }

    if len(parts) >= _MINIMUM_SENSOR_TOPIC_PARTS and parts[0] == "sensor":
        return {
            "message_type": "sensor_data",
            "topic": topic,
            "device_id": parts[1],
            "kind": parts[2],
            "payload": payload,
            "seqId": parts[_SENSOR_SEQUENCE_INDEX] if len(parts) > _SENSOR_SEQUENCE_INDEX else None,
        }

    if len(parts) >= _MINIMUM_KINDS_TOPIC_PARTS and parts[1] == "kinds":
        return {
            "message_type": "device_config",
            "topic": topic,
            "device_id": parts[0],
            "category": parts[2],
            "action": parts[3],
            "payload": payload,
        }

    if len(parts) >= _MINIMUM_BROKER_LOG_TOPIC_PARTS and parts[0] == "$SYS" and parts[1] == "broker" and parts[2] == "log":
        return {
            "message_type": "mqtt_broker_log",
            "topic": topic,
            "kind": parts[3],
            "payload": payload,
        }

    return {"message_type": "unknown", "topic": topic, "payload": payload}
