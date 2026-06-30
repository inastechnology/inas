import threading

from paho.mqtt import client as mqtt_client

from ina_device_hub.device_event_log import append_mqtt_hub_event, append_mqtt_message_event
from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

client_id = setting().get("mqtt")["mqtt_client_id"]


class HubMQTTClient:
    def __init__(self, subscribed_data_queue):
        self.subscribed_data_queue = subscribed_data_queue
        self.message_handlers = []
        self.discord_notification_service = discord_notification_service()

    def start(self):
        worker_thread = threading.Thread(target=self.client.loop_forever)
        worker_thread.daemon = True
        worker_thread.start()
        print("MQTT Client started")
        return worker_thread

    def connect_mqtt(self) -> None:
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("Connected to MQTT Broker!")
                append_mqtt_hub_event("mqtt_hub_connected", "outbound", topic="$SYS/ina-device-hub/mqtt", payload={"broker": setting().get("mqtt")["mqtt_broker"]})
                self.discord_notification_service.notify_mqtt_activity("connected", "$SYS/ina-device-hub/mqtt", payload={"broker": setting().get("mqtt")["mqtt_broker"]})
            else:
                print("Failed to connect, return code %d\n", rc)
                append_mqtt_hub_event("mqtt_hub_connect_failed", "outbound", topic="$SYS/ina-device-hub/mqtt", payload={"return_code": rc}, mqtt_rc=rc)
                self.discord_notification_service.notify_mqtt_activity("connect_failed", "$SYS/ina-device-hub/mqtt", payload={"return_code": rc})

        client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1, client_id)
        client.on_connect = on_connect
        mqtt_settings = setting().get("mqtt")
        if mqtt_settings["mqtt_username"]:
            client.username_pw_set(mqtt_settings["mqtt_username"], mqtt_settings["mqtt_password"])
        print(f"Connecting to MQTT Broker {setting().get('mqtt')['mqtt_broker']}:{setting().get('mqtt')['mqtt_port']}")
        client.connect(setting().get("mqtt")["mqtt_broker"], setting().get("mqtt")["mqtt_port"])
        self.client = client

    def add_message_handler(self, handler):
        self.message_handlers.append(handler)

    def publish(self, topic: str, msg: str, qos: int = 1, retain: bool = False):
        result = self.client.publish(topic, msg, qos=qos, retain=retain)
        if result.rc == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")
        self.discord_notification_service.notify_mqtt_activity("publish", topic, payload=msg, mqtt_rc=result.rc)
        return result

    def _parse_message(self, topic: str, payload):
        parts = [part for part in topic.split("/") if part]

        if len(parts) == 3 and parts[0] == "farm" and parts[2] == "telemetry":
            return {
                "message_type": "sensor_data",
                "topic": topic,
                "device_id": parts[1],
                "kind": "telemetry",
                "payload": payload,
                "seqId": None,
            }

        if len(parts) >= 3 and parts[0] == "sensor":
            return {
                "message_type": "sensor_data",
                "topic": topic,
                "device_id": parts[1],
                "kind": parts[2],
                "payload": payload,
                "seqId": parts[3] if len(parts) > 3 else None,
            }

        if len(parts) >= 4 and parts[1] == "kinds":
            return {
                "message_type": "device_config",
                "topic": topic,
                "device_id": parts[0],
                "category": parts[2],
                "action": parts[3],
                "payload": payload,
            }

        if len(parts) >= 4 and parts[0] == "$SYS" and parts[1] == "broker" and parts[2] == "log":
            return {
                "message_type": "mqtt_broker_log",
                "topic": topic,
                "kind": parts[3],
                "payload": payload,
            }

        return {"message_type": "unknown", "topic": topic, "payload": payload}

    def subscribe(self, topic: str):
        def on_message(client, userdata, msg):
            omitted_payload = f"{msg.payload[0:100]}..." if len(msg.payload) > 100 else msg.payload
            print(f"Received `{omitted_payload}` from `{msg.topic}` topic")
            parsed_message = self._parse_message(msg.topic, msg.payload)
            append_mqtt_message_event(parsed_message)
            self.discord_notification_service.notify_mqtt_activity("received", msg.topic, payload=msg.payload, parsed_message=parsed_message)

            for handler in self.message_handlers:
                try:
                    handled = handler(client, parsed_message)
                except Exception:
                    logger.exception("MQTT message handler failed for topic=%s", msg.topic)
                    handled = False
                if handled:
                    return

            if parsed_message["message_type"] == "sensor_data":
                self.subscribed_data_queue.put(parsed_message)
                return

            print("Invalid topic")

        self.client.subscribe(topic, qos=0)
        self.client.on_message = on_message
