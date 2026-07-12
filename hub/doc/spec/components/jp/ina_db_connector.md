# ina_db_connector (src/ina_device_hub/ina_db_connector.py)

## 目的

- libsql（Turso）への接続ラッパー。DB への upsert/insert/fetch 操作を提供する。

## 主要 API（抜粋）

- class InaDBConnector

  - upsert_device_info(device_id: str, info: dict, device_type: str = None, ...) -> None
  - upsert_device_status(device_id: str, status: str) -> None
  - upsert_latest_sensor_data(device_id: str, data: dict) -> None
  - insert_aggregated_sensor_data(device_id: str, yyyymmdd_hh: str, data: dict) -> None
  - fetch_latest_sensor_data(device_id: str) -> Row | None
  - fetch_latest_aggregated_sensor_data(device_id: str, limit: int = 50) -> list
  - fetch_aggregated_sensor_data_by_range(device_id: str, start: str, end: str) -> list
  - insert_sensor_image_data(device_id: str, yyyymmddhhmmss: str, image_path: str) -> None
  - fetch_sensor_latest_image(device_id: str, num: int = 1) -> list
  - その他: insert_user_note, upsert_sensor_info, insert_system_alert, insert_maintenance_log, 等

## 実装のポイント

- デコレータ `commit_and_sync` により、メソッド実行の最後に `conn.commit()` と `conn.sync()` が常に実行される。
- `libsql.connect(db_path, sync_url=url, auth_token=auth_token)` で接続し `conn.sync()` を呼んでいる。

## 依存

- `libsql`
- `ina_device_hub.setting`

## 注意点 / 改善案

- SQL 文の一部で f-string による値組み込みが行われており（特に `insert_aggregated_sensor_data` 等）、SQL インジェクションや値エスケープの問題が潜在する。プレースホルダを使用することを推奨。
- 日時の扱いやタイムゾーンの正規化が重要（現状で UTC を利用する箇所あり）。
- 例外ハンドリングは `commit_and_sync` 内で表層的に行われるが、障害時のリトライ戦略やアラートを検討すること。
