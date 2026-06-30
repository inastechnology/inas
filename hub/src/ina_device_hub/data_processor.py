import time
import queue
import json
import threading
import math
from datetime import datetime, timezone

from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.sensor_data_queue import SensorDataQueue
from ina_device_hub.ina_db_connector import InaDBConnector
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class DataProcessor:
    def __init__(self, db_connector: InaDBConnector = None):
        if db_connector is None:
            db_connector = InaDBConnector()

        self.sensor_data_queue = SensorDataQueue()
        self.sensor_device_repository = sensor_device_repository()
        self.sensor_data_repository = sensor_data_repository(db_connector)
        self.sensor_image_repogitory = sensor_image_repogitory(db_connector)
        self.image_buffer = {}
        self.audio_buffer = {}

    def start(self):
        worker_thread = threading.Thread(target=self.process)
        worker_thread.daemon = True
        worker_thread.start()

    def process(self):
        while True:
            try:
                # queue からメッセージを取得
                message = self.sensor_data_queue.get()
                self.sensor_device_repository.add(
                    message["device_id"],
                    {
                        "name": message["device_id"],
                        "type": message["device_id"].split("-")[0],
                        "detected_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )

                # ここでメッセージの処理を実施
                if message["kind"] == "status":
                    self.process_sensor_data(
                        message["device_id"],
                        message["kind"],
                        message["payload"],
                        message["seqId"],
                    )
                elif message["kind"] == "telemetry":
                    self.process_farm_telemetry(
                        message["device_id"],
                        message["payload"],
                    )

                elif message["kind"] == "image":
                    self.process_sensor_image(
                        message["device_id"],
                        message["kind"],
                        message["payload"],
                        message["seqId"],
                    )
                elif message["kind"] == "audio":
                    # TODO: Implement audio processing
                    pass
                else:
                    # 規定外のメッセージの場合はログ出力
                    print(f"Device {message['device_id']} sensor data: {message['payload']}")
                # キューからメッセージを取り出し完了
                self.sensor_data_queue.task_done()
            except queue.Empty:
                # キューが空の場合は何もしない
                time.sleep(1)
                continue
            except Exception as e:
                print(f"Error: {e}")
                logger.exception(e)

                time.sleep(1)
                continue

    def process_sensor_data(self, device_id, kind, payload, seqId):
        """
        Parse sensor data payload
        Args:
            device_id (str): device id
            kind (str): message kind
            payload (str): message payload
                json string - sensor data
            seqId (int): sequence id
        """
        # バイト列の場合は文字列に変換
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        print(f"Device {device_id} sensor data: {payload}")

        # 文字列から辞書型に変換
        payload_as_dict = json.loads(payload)
        append_device_event(
            "sensor_status",
            "inbound",
            device_id,
            kind=kind,
            seq_id=seqId,
            payload=payload_as_dict,
        )

        self.sensor_data_repository.add(device_id, seqId, payload_as_dict)

    def process_farm_telemetry(self, device_id, payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        print(f"Device {device_id} telemetry: {payload}")
        payload_as_dict = json.loads(payload)
        append_device_event(
            "sensor_telemetry",
            "inbound",
            device_id,
            kind="telemetry",
            payload=payload_as_dict,
        )
        normalized_payload = self._normalize_farm_telemetry(device_id, payload_as_dict)
        self.sensor_data_repository.add(device_id, None, normalized_payload)

    def _normalize_farm_telemetry(self, topic_device_id: str, payload_as_dict: dict):
        payload_device_id = payload_as_dict.get("device_id")
        if payload_device_id and payload_device_id != topic_device_id:
            logger.warning(
                "Telemetry device_id mismatch: topic=%s payload=%s",
                topic_device_id,
                payload_device_id,
            )

        return {
            "temp": self._safe_number(payload_as_dict.get("soil_temp_c")),
            "extra": {
                "schema": "farm.telemetry.v1",
                "device_id": topic_device_id,
                "telemetry": payload_as_dict,
                "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    def _safe_number(self, value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
        return None

    def process_sensor_image(self, device_id, kind, payload, seqId):
        """
        Parse image payload
        Args:
            device_id (str): device id
            kind (str): message kind
            payload (str): message payload
                json string - image info. first received data
                binary data - image fragments
            seqId (int): sequence id
        @note
        1. receive image info(json data)
        2. receive image fragments...
        """

        if setting().get("sensor").get("save_image") is False:
            return  # do nothing

        try:
            # check whether payload is image info or not
            payload = json.loads(payload)
            image_size = payload["size"]
            # add image data to buffer
            if device_id not in self.image_buffer:
                self.image_buffer[device_id] = {}

            self.image_buffer[device_id] = dict()
            self.image_buffer[device_id][seqId] = {
                "size": image_size,
                "image": bytearray(),
            }
            return
        except json.JSONDecodeError:
            pass
        except UnicodeDecodeError:
            pass

        if seqId not in self.image_buffer[device_id]:
            logger.error(f"[{device_id}:{seqId}] image info not found")
            return

        image_fragment = bytearray(payload)

        self.image_buffer[device_id][seqId]["image"].extend(image_fragment)
        # check whether all image data received
        if len(self.image_buffer[device_id][seqId]["image"]) >= self.image_buffer[device_id][seqId]["size"]:
            # all image data received
            print(f"[{device_id}:{seqId}] all image data received")
            # all image data received
            image_data = self.image_buffer[device_id][seqId]["image"].copy()
            del self.image_buffer[device_id][seqId]
            # save image data
            self.sensor_image_repogitory.save(device_id, image_data)

    def process_sensor_audio(self, device_id, kind, payload, seqId):
        """
        Parse audio payload
        1. receive audio info(json data) including audio data counts
        2. receive audio fragments...count times
        """
        try:
            payload = json.loads(payload)
            audio_count = payload["count"]
            # add audio data to buffer
            if device_id not in self.audio_buffer:
                self.audio_buffer[device_id] = {}

            self.audio_buffer[device_id] = dict()
            self.audio_buffer[device_id][seqId] = {
                "count": 0,
                "all_count": audio_count,
                "audio": bytearray(),
            }
            return
        except json.JSONDecodeError:
            pass
        except UnicodeDecodeError:
            pass

        if seqId not in self.audio_buffer[device_id]:
            logger.error(f"[{device_id}:{seqId}] audio info not found")
            return

        audio_fragment = bytearray(payload)

        self.audio_buffer[device_id][seqId]["audio"].extend(audio_fragment)
        self.audio_buffer[device_id][seqId]["count"] += 1
        # check whether all audio data received
        if self.audio_buffer[device_id][seqId]["count"] >= self.audio_buffer[device_id][seqId]["all_count"]:
            # all audio data received
            print(f"[{device_id}:{seqId}] all audio data received")
            # all audio data received
            audio_data = self.audio_buffer[device_id][seqId]["audio"].copy()
            del self.audio_buffer[device_id][seqId]
            # save audio data
            # self.sensor_audio_repogitory.save(device_id, audio_data)
