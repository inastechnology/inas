# sensor_image_repogitory (src/ina_device_hub/sensor_image_repogitory.py)

## 目的

- センサーカメラから保存された画像をクラウド（S3 互換）へアップロードし、DB にメタ情報を登録／取得する。

## 主要 API

- class SensorImageRepogitory(db_connector: InaDBConnector)

  - save(device_id, imageBytes) -> None
    - ストレージへアップロードし、DB に `insert_sensor_image_data` を呼ぶ。

  - fetch_latest(device_id, limit: int = 1) -> list[dict]
  - fetch_from_cloud_as_bytes(image_path) -> bytes | None
  - get_image_dir(device_id) / get_image_path(device_id) -> str

- function sensor_image_repogitory(db_connector: InaDBConnector = None) -> SensorImageRepogitory（シングルトン）

## 依存

- `boto3`, `storage_connector`, `InaDBConnector`, `setting`, `general_log`

## 注意点

- `save` はクラウド保存後に DB 登録を行う。ネットワーク障害時の再試行やローカル保存フォールバックが必要な場合は拡張を検討。
