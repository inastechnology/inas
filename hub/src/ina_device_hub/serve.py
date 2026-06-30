from ina_device_hub import web_server
from ina_device_hub.data_processor import DataProcessor
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.hub_mqtt_client import HubMQTTClient
from ina_device_hub.instagram_post_task import instagram_post_task
from ina_device_hub.timelapse_task import timelapse_task
from ina_device_hub.weather_record_task import weather_record_task


def run():
    data_processor = DataProcessor()
    hub_mqtt_client = HubMQTTClient(data_processor.sensor_data_queue)
    hub_mqtt_client.connect_mqtt()
    hub_mqtt_client.add_message_handler(device_config_service().handle_mqtt_message)
    device_config_service().attach_mqtt_client(hub_mqtt_client)
    hub_mqtt_client.subscribe("farm/+/telemetry")
    hub_mqtt_client.subscribe("sensor/+/#")
    hub_mqtt_client.subscribe("/+/kinds/config/request")
    hub_mqtt_client.subscribe("/+/kinds/agri/immediate")
    hub_mqtt_client.subscribe("$SYS/broker/log/#")

    # メッセージ処理用のワーカースレッドを開始
    data_processor.start()

    # MQTTクライアントのワーカースレッドを開始
    hub_mqtt_client.start()

    # timelapse task
    timelapse_task().start()
    weather_record_task().start()
    instagram_post_task().start()

    # Flaskサーバーを起動
    web_server.flask_run()


if __name__ == "__main__":
    run()
