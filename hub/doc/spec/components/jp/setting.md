# setting (src/ina_device_hub/setting.py)

## 目的

- 環境変数や `.env` を読み込み、アプリケーションの設定とワークディレクトリを提供するユーティリティ。デフォルト設定と永続化メソッドを持つ。

## 主要クラス / 関数

- class Setting

  - __init__(path: str | None = None)
  - load() / save()
  - get(key) -> Any
  - set(key, value) -> None
  - get_work_dir() -> str

- function setting() -> Setting
  - モジュールレベルのシングルトンを返す。

## 依存

- python-dotenv（`.env` 読み込みに使用）

## 注意点

- `.env`の必須環境変数（`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`等）が未設定だとprocessを停止する。Local Hubごとのenv管理が必須。
- `SETTING_FILE_PATH` のデフォルトは `~/.ina-device-hub/config.json`。複数インスタンス運用時は競合やパスの上書きに注意すること。
