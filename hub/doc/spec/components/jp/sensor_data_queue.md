# sensor_data_queue (src/ina_device_hub/sensor_data_queue.py)

## 目的

- MQTT 受信データをプロセス間/スレッド間で安全にやり取りするためのスレッドセーフなキューラッパー。

## 公開 API

- class SensorDataQueue

  - put(data) -> None
  - get(timeout=None) -> Any
  - empty() -> bool
  - task_done() -> None

- インスタンス `sensor_data_queue` がモジュールで生成されている。

## 実装のポイント

- 内部は `queue.Queue` と `threading.Lock` を用いており、`put` はロックで保護される。

## 注意点

- `get` のタイムアウトはデフォルト None（ブロッキング）。ワーカ側は例外処理（queue.Empty）を行っているため問題は少ないが、スケーラビリティの観点からバックプレッシャ制御を検討。
