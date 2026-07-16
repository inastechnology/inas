# hub_mqtt_client (src/ina_device_hub/hub_mqtt_client.py)

## 目的

- paho-mqtt を用いて MQTT ブローカーと接続し、受信メッセージを `SensorDataQueue` に流すクライアントラッパー。

## 公開 API

- class HubMQTTClient(subscribed_data_queue)

  - connect_mqtt() -> None
  - start() -> paho.mqtt.client.Client
  - stop() -> None
  - subscribe(topic: str) -> None
  - publish(topic: str, msg: str, qos: int = 1, retain: bool = False, notify: bool = True)

## 挙動の要点

- `connect_mqtt` は `setting().get('mqtt')` から既存の接続先・port・username/password・client IDを読み取る。接続条件はMQTT 3.1.1/TCP、keepalive 60秒で固定する。
- usernameが空なら認証情報を送らず、空でなければusername/passwordを設定する。TLSへの自動切替は行わない。
- broker切断時はpaho-mqttのnetwork loopで再接続し、接続成功時に既存topicを再subscribeする。
- `subscribe` は on_message コールバックでトピックをパースし、`{device_id, kind, payload, seqId}` 形式の辞書をキューに入れる。payload は生バイト列。

## 依存

- `paho.mqtt.client`
- `ina_device_hub.setting`

## 注意点

- subscribe QoSは従来どおり`0`。デバイス向けconfig/OTA publishも呼び出し側が`qos=0`を明示する。
- topic、payload、QoS、retain、接続先、認証条件は既存運用との互換契約である。変更時は実機を含む移行計画を別途作成する。
