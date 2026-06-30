# sensor_device_repository (src/ina_device_hub/sensor_device_repository.py)

## 目的

- センサー（デバイス）一覧をローカル JSON ファイルで管理するリポジトリ。

## 公開 API

- class SensorDeviceRepository

  - load() / save()
  - get(key) -> dict | None
  - add(device_id, info: dict) -> None
  - remove(device_id) -> None
  - get_all() -> dict
  - clear() -> None

- function sensor_device_repository() -> SensorDeviceRepository（シングルトン）

## 注意点

- `camera_device_repository` と同様の実装上の注意（ミュータブル引数、並行アクセス、データ破損）。
