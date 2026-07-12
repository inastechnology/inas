# camera_device_repository (src/ina_device_hub/camera_device_repository.py)

## 目的

- カメラデバイス情報をローカル JSON ファイルに保存・読み書きする軽量リポジトリ。

## 公開 API

- class CameraDeviceRepository

  - load() / save()
  - get(key) -> dict | None
  - add(device_id: str = None, info: dict = {}) -> None
  - remove(device_id) -> None
  - get_all() -> dict
  - clear() -> None

- function camera_device_repository() -> CameraDeviceRepository（シングルトン）

## 引数/戻り値の要点

- `add` は device_id が None の場合に UUID ベースの ID を生成して登録する。
- 永続化先は `setting().get_work_dir() + '/.camera_device_list.json'`。

## 依存

- `ina_device_hub.setting`

## 注意点

- JSON ファイルを直接上書きするため、並行アクセスや破損時のリカバリロジックはほとんどない（運用環境ではロックやトランザクションを検討）。
- `info` のデフォルト引数にミュータブルな `{}` が使われているため呼び出し側で意図せぬ共有が発生する可能性がある（推奨修正: None をデフォルトにする）。
