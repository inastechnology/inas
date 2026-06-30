# API仕様（spec）

このフォルダは `src/ina_device_hub` の各モジュールに対する軽量仕様書を集めた場所です。
開発者向けのクイックリファレンスとして使用してください。

## 目次

- `00-overview.md` — プロジェクト全体の概要と作成方針
- `camera_connector.md` — カメラ(FFmpeg) 統合：静止画取得 / MJPEG ストリーミング
- `camera_device_repository.md` — カメラデバイスのローカル JSON リポジトリ
- `data_processor.md` — センサーデータ処理ワーカ（MQTT -> 永続化 / 画像組立）
- `general_log.md` — ロガー設定（ローテーション、stdout）
- `hub_mqtt_client.md` — MQTT クライアントラッパー（paho）
- `ina_db_connector.md` — Turso/libsql への DB ラッパー
- `location_repository.md` — ロケーション情報のローカルリポジトリ
- `sensor_data_queue.md` — スレッドセーフなデータキュー
- `sensor_data_repository.md` — センサーデータの一時保存と集計ロジック
- `sensor_device_repository.md` — センサーデバイス情報のローカルリポジトリ
- `sensor_image_repogitory.md` — センサー画像のクラウド保存と DB 登録
- `serve.md` — アプリケーション起動エントリポイント
- `setting.md` — 環境変数/.env からの設定管理
- `storage_connector.md` — S3 互換ストレージ（boto3）ラッパー
- `timelapse_task.md` — 定期撮影タスク（apscheduler）
- `utils.md` — ユーティリティ（Plotly でのグラフ作成など）
- `web_server.md` — Flask ベースのローカル管理 UI / API

## 使い方

- 各ファイルを参照してモジュールの目的、公開 API、依存、注意点を確認してください。
- ドキュメントは簡易仕様です。実装の詳細やコード例を追加したい場合は該当ファイルを編集してください。

## 次の推奨アクション

1. CI に Markdown lint（例: `markdownlint`）を導入して目次とフォーマットを自動検査する。
2. 重要モジュール（DB、ストレージ、ストリーミング）に使用例コードスニペットを追記する。
3. ドキュメントの自動化: 将来的にコードコメントから API 抽出するツールを検討する。

