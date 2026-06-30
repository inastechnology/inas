# プロジェクト概要

このディレクトリは `src/ina_device_hub` の各モジュールについての軽量仕様書を格納します。目的は保守性向上と外部参照用の簡易 API ドキュメントを提供することです。

## 含まれるファイル（要約）

- camera_connector.md
- camera_device_repository.md
- data_processor.md
- general_log.md
- hub_mqtt_client.md
- ina_db_connector.md
- location_repository.md
- sensor_data_queue.md
- sensor_data_repository.md
- sensor_device_repository.md
- sensor_image_repogitory.md
- serve.md
- setting.md
- storage_connector.md
- timelapse_task.md
- utils.md
- web_server.md

## 作成方針

- 各ファイルは目的・公開 API（関数/クラス）・主要引数/戻り値・依存・注意点を含みます。
- 実装の詳細ではなく、取り扱いに必要な情報を短くまとめます。
