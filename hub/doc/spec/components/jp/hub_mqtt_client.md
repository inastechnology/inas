# hub_mqtt_client (src/ina_device_hub/hub_mqtt_client.py)

## 目的

- paho-mqtt を用いて MQTT ブローカーと接続し、受信メッセージを `SensorDataQueue` に流すクライアントラッパー。

## 公開 API

- class HubMQTTClient(subscribed_data_queue)

  - connect_mqtt() -> None
  - start() -> threading.Thread
  - subscribe(topic: str) -> None
  - publish(client, topic: str, msg: str) -> None

## 挙動の要点

- `connect_mqtt` は `setting().get('mqtt')` から接続先を読み取り `paho.mqtt.client.Client` を生成して接続する。
- `subscribe` は on_message コールバックでトピックをパースし、`{device_id, kind, payload, seqId}` 形式の辞書をキューに入れる。payload は生バイト列。

## 依存

- `paho.mqtt.client`
- `ina_device_hub.setting`

## 注意点

- QoS は 1 で subscribe するが、再接続やエラー時の再サブスクライブ処理が明示的ではないため、接続ロジック強化が望ましい。
- クライアントの認証（username/password）の利用は `setting` に情報があるが、 `connect()` 呼び出しでの認証設定の反映が実装に見られない可能性があるため確認が必要。
