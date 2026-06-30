# general_log (src/ina_device_hub/general_log.py)

## 目的

- ローテーティングファイルハンドラと標準出力（自動フラッシュ）を設定したロガーを提供するユーティリティ。

## 公開 API

- function get_rotate_file_logger(name: str, log_file: str) -> Logger
  - 指定名/ファイル名でロガーを作成して返す。

- variable logger: Logger
  - `get_rotate_file_logger("general", "general.log")` による共有インスタンス。

## 依存

- Python 標準の `logging`, `logging.handlers.RotatingFileHandler`
- `ina_device_hub.setting`

## 注意点

- `RotatingFileHandler` の設定でログ最大サイズとバックアップ数が大きめ（10MB、バックアップ100）。必要に応じて調整推奨。
- stdout ハンドラは常に DEBUG レベルでフラッシュするため本番ではログレベル調整を検討。
