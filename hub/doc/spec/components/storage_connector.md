# storage_connector (src/ina_device_hub/storage_connector.py)

## 目的

- S3 互換ストレージ（boto3）とローカルストレージのラッパー。ファイルの保存・取得を提供する。

## 主要 API

- class StorageConnector

  - save_to_cloud(file_key, fileBytes, content_type="image/jpeg") -> str | None
  - save_to_local(file_key, fileBytes) -> str
  - fetch_from_cloud_as_bytes(file_full_key) -> bytes | None
  - get_file_dir(file_key) / get_file_path(file_key) -> str

- function storage_connector() -> StorageConnector（シングルトン）

## 依存

- `boto3`, `ina_device_hub.setting`, `ina_device_hub.general_log`

## 注意点

- `save_to_cloud`/`fetch_from_cloud_as_bytes` はバケット名を `setting().get('storage_bucket')` から取得する。マルチテナント対応は TODO コメントあり。
- ローカルへの保存はファイルシステム上のパスを生成して直接書き込む。アクセス権やディスク容量に注意。
