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

- `save_to_cloud`/`fetch_from_cloud_as_bytes` は、このLocal Hub専用に設定したバケット名を `setting().get('storage_bucket')` から取得する。顧客間のruntime routingは行わない。
- object key先頭の旧`tenant_id`値は既存object pathとの互換namespaceとして固定維持するもので、共有bucket内のテナント選択入力には使わない。
- ローカルへの保存はファイルシステム上のパスを生成して直接書き込む。アクセス権やディスク容量に注意。
