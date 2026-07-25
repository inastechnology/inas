---
title: 機器設定キー
description: WTR Runtime Config、潅水、診断の内部キーと制約を技術担当者向けに説明します。
---

:::caution[技術者向け]
このページは機器F/WとHubの設定配信を調査する担当者向けです。画面に表示される一般向けの設定は[画面の設定ガイド](/configure/settings/)を参照してください。
:::

画面に表示される項目はDevice Definitionと権限によって変わります。ここではWTRを中心に、Hubから機器へ配信する内部キーをまとめます。

## 時刻とwake

| key | 内容 | 制約・注意 |
|---|---|---|
| `ntp_server` | 時刻同期先 | deviceから名前解決または到達できるhost/IP |
| `timezone_offset_sec` | UTCからのoffset秒 | 日本は `32400` |
| `ota_check_interval_sec` | OTA確認の最大間隔 | F/W側で1–24時間へ制限 |

## 潅水

| key | 内容 | 制約・注意 |
|---|---|---|
| `moisture_threshold` | 潅水を抑止する水分threshold | 0–100、校正後に決める |
| `force_watering` | 水分判定を無視 | 通常 `false` |
| `schedules` | 時刻・時間・出力 | 最大8件 |
| `schedules[].duration_sec` | 通常の連続ON時間 | 分割有効時は置換される |
| `schedules[].channel_mask` | 対象出力 | WTRは `1` |
| `watering_pattern.enabled` | 分割潅水 | 有効ならpatternを使用 |
| `watering_pattern.on_sec` | 1回のON時間 | 1–3600秒 |
| `watering_pattern.off_sec` | ON間の停止時間 | 0–3600秒 |
| `watering_pattern.repeat_count` | ON回数 | 1–20回 |

## 敷設試験

| key | 内容 | 制約・注意 |
|---|---|---|
| `startup_watering_test.enabled` | cold boot時の強制出力 | 作業中だけ `true` |
| `startup_watering_test.duration_sec` | 試験ON時間 | 1–30秒 |
| `startup_watering_test.channel_mask` | 対象出力 | WTRはF/Wが `1` に固定 |

起動試験はfresh config受信後かつOTAを試行していないcold boot/resetでだけ実行します。deep-sleep wakeでは実行しません。

## 土壌水分校正

| key | 内容 | 注意 |
|---|---|---|
| `soil_calibration.dry_raw` | 乾燥基準ADC | `dry_raw > wet_raw` が必要 |
| `soil_calibration.wet_raw` | 湿潤基準ADC | 現物sensorで測定 |
| `auto_mode_enabled` | 潅水前後から候補生成 | 候補の妥当性を確認 |
| `apply_auto_calibration` | 候補を自動適用 | 初期検証中は無効を推奨 |
| `drift_check_enabled` | 基準driftを監視 | sensor劣化の確認に使用 |

## 診断

| key | 内容 | 注意 |
|---|---|---|
| `debug_log_on_wake` | wakeごとのcompact debug log送信 | 調査中だけ有効化 |

長期間のdebug logはstorageと通信量を増やします。問題の時刻を再現できたら無効に戻します。

:::note[詳細設定]
`env_sensors` と `env_calibration` はRS485環境sensor向けです。標準WTRの `A2/D2 + D4` profileでは無効のまま使います。RS485構成にはWRSまたはENVを選びます。
:::
