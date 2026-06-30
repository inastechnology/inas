# location_repository (src/ina_device_hub/location_repository.py)

## 目的

- 位置情報（ロケーション）データをローカル JSON ファイルで管理するリポジトリ。

## 公開 API

- class LocationRepository

  - load() / save()
  - get(key) -> dict | None
  - add(device_id, info: dict) -> None
  - remove(device_id) -> None
  - get_all() -> dict
  - clear() -> None

- function location_repository() -> LocationRepository（シングルトン）

## 依存

- `ina_device_hub.setting`

## 注意点

- `camera_device_repository` と同様にファイルベースで単純実装。並行アクセスとデータ整合性に注意。
