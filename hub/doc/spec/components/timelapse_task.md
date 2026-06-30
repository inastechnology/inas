# timelapse_task (src/ina_device_hub/timelapse_task.py)

## 目的

- 定期的にカメラから静止画を取得してストレージへ保存するバックグラウンドタスク（apscheduler を利用）。

## 主要クラス / メソッド

- class TimelapseTask

  - start() -> None
  - stop() -> None
  - __routin() -> None（定期実行ジョブ）
  - get_img_key(device_id) -> str

- function timelapse_task() -> TimelapseTask（シングルトン）

## 依存

- `apscheduler.schedulers.background.BlockingScheduler`, `camera_connector`, `storage_connector`, `setting`, `general_log`

## 注意点

- `routin_scheduler` は `BlockingScheduler` を使用しており、別スレッドで start() する設計。`scheduler.shutdown` の呼び出しが `()` なしで記述されている箇所があるので修正が必要（現状はメソッド参照になっている）。
- ジョブ実行中のエラー処理や重複実行防止は `max_instances=1` でカバーしている。
