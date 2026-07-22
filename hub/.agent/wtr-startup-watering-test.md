# WTR 電源投入時の敷設試験モード

## Purpose

WTR の敷設時に、電源投入またはリセット後の一度だけ短時間の潅水出力を実行し、ポンプ・バルブ・配線の導通を現場で確認できるようにする。通常の予約潅水や土壌水分判定とは分離し、既定OFF、最大30秒、deep sleep 起床では不実行とする。

## Progress

- [x] 既存 WTR 起動シーケンス、Runtime Config、Hub設定画面、Device Definitionを確認した。
- [x] Hub の設定検証、既定値、Device Definition、設定画面を更新した。
- [x] WTR firmware の設定解析とコールドブート時実行、status を実装した。
- [x] ユーザーマニュアルと MQTT 契約を更新した。
- [x] Hubテスト388件、Device Definition生成/check、Ruff、WTR firmware buildを完了した。
- [x] device-detail smokeを実行し、PC/390px画面を目視確認した。

## Decisions

- `force_watering` は予約時刻の水分判定を無視する既存機能として維持し、新しい `startup_watering_test` と混同しない。
- 試験は `woke_from_deep_sleep == false`、設定有効、Runtime Configがこの起動中にMQTTから受信済み、OTA試行なしの場合だけ実行する。
- 試験は土壌水分を無視する。導通試験が目的であること、通水中の無人運用に使わないことを画面で警告する。
- 継続時間は1〜30秒、channel maskは1〜3に制限する。

## Validation

Hub の全Pythonテスト、Device Definition registry生成/check、WTR firmware build、管理画面のdesktop/mobile smokeとスクリーンショット確認を行う。
