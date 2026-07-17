from ina_device_hub import web_server
from ina_device_hub.data_processor import DataProcessor
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.health_monitor_task import health_monitor_task
from ina_device_hub.hub_mqtt_client import DEFAULT_SUBSCRIPTION_TOPICS, HubMQTTClient
from ina_device_hub.instagram_post_task import instagram_post_task
from ina_device_hub.ota_update_service import ota_update_service
from ina_device_hub.plant_calendar_generation_task import plant_calendar_generation_task
from ina_device_hub.plant_task_notification_task import plant_task_notification_task
from ina_device_hub.timelapse_task import timelapse_task
from ina_device_hub.weather_record_task import weather_record_task


def run():
    data_processor = DataProcessor()
    web_server.initialize_web_server()
    hub_mqtt_client = HubMQTTClient(data_processor.sensor_data_queue)
    hub_mqtt_client.connect_mqtt()
    hub_mqtt_client.add_message_handler(device_config_service().handle_mqtt_message)
    hub_mqtt_client.add_message_handler(ota_update_service().handle_mqtt_message)
    device_config_service().attach_mqtt_client(hub_mqtt_client)
    ota_update_service().attach_mqtt_client(hub_mqtt_client)
    for topic in DEFAULT_SUBSCRIPTION_TOPICS:
        hub_mqtt_client.subscribe(topic)
    web_server.register_readiness_check("mqtt", hub_mqtt_client.is_connected)

    # メッセージ処理用のワーカースレッドを開始
    data_processor.start()

    # MQTTクライアントのワーカースレッドを開始
    hub_mqtt_client.start()

    # timelapse task
    timelapse_task().start()
    weather_record_task().start()
    instagram_post_task().start()
    health_monitor_task().start()
    plant_calendar_generation_task().start()
    plant_task_notification_task().start()

    # Flaskサーバーを起動
    web_server.serve_http()


if __name__ == "__main__":
    run()
