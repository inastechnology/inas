# data_processor (src/ina_device_hub/data_processor.py)

## 目的

- MQTT 等から受信したセンサデータ（status, image, audio）を処理し、永続化や画像組立て等を行うバックグラウンドワーカ。

## 主要クラス / メソッド

- class DataProcessor

  - __init__(db_connector: InaDBConnector = None)
    - SensorDataQueue、SensorDeviceRepository、SensorDataRepository、SensorImageRepogitory を初期化する。

  - start() -> None
    - スレッドで `process()` を開始する。

  - process() -> None
    - キューからメッセージを取り出し、種類に応じて処理メソッドを呼ぶ無限ループ。

  - process_sensor_data(device_id, kind, payload, seqId) -> None
    - payload を JSON として解析し、最新データを DB に保存する。

  - process_sensor_image(device_id, kind, payload, seqId) -> None
    - まず画像メタ（JSON）を受け取り、続くバイナリ断片を組み立てて完全な画像を保存する。

  - process_sensor_audio(...)
    - TODO: 未実装（プレースホルダあり）。

## 依存

- SensorDataQueue、sensor_* リポジトリ、InaDBConnector、general_log、setting

## 注意点

- payload が bytes の場合のデコードは UTF-8 を前提としているため、エンコーディング不一致に注意。
- 画像/音声の組立てはメモリ上で行われるため、大きなファイルで OOM の恐れがある。必要なら一時ファイル化を検討。
- エラー時の可観測性（ログ・メトリクス・アラート）を整備すると運用が楽になる。
