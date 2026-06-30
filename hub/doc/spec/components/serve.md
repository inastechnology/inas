# serve (src/ina_device_hub/serve.py)

## 目的

- アプリケーションのエントリポイント。DataProcessor、HubMQTTClient、TimelapseTask、Flask サーバを起動するランナー。

## 公開関数

- run() -> None
  - 各コンポーネントを初期化しサービスを起動する。

## 注意点

- `run()` はブロッキングで Flask サーバを `flask_run()` で起動するため、起動順や例外ハンドリングの責務を明確にする必要がある。
- サービス起動時のログ出力やプロセス監視（systemd ユニット化は `systemd/inas-device-hub@.service` がある）を考慮すること。
