---
title: Runtime Config
description: Hubからdeviceへ送るRuntime Configの保存・配信・確認方法です。
---

Runtime Configは、登録deviceごとの運用設定です。Device Definitionが送信可能なkeyを宣言し、Hubが保存・配信し、F/Wが検証して適用します。

## 通信

| 方向 | topic | 用途 |
|---|---|---|
| device → Hub | `/<device_id>/kinds/config/request` | 最新設定を要求 |
| Hub → device | `/<device_id>/kinds/config/reply` | requestへの返信 |
| Hub → device | `/<device_id>/kinds/config/push` | 即時更新 |

Hubのlocal APIでは、次のendpointで保存とpushを行えます。

```text
PUT /local/api/device-configs/<device_id>?push=true
```

管理APIを直接使う場合は認証・権限・Origin制約に従ってください。通常の利用者はHub画面から変更します。

## WTR example

```json
{
  "ntp_server": "192.168.1.10",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 35,
  "force_watering": false,
  "startup_watering_test": {
    "enabled": false,
    "duration_sec": 5,
    "channel_mask": 1
  },
  "debug_log_on_wake": false,
  "ota_check_interval_sec": 21600,
  "watering_pattern": {
    "enabled": false,
    "on_sec": 10,
    "off_sec": 20,
    "repeat_count": 3
  },
  "schedules": [
    {
      "hour": 6,
      "minute": 30,
      "duration_sec": 20,
      "channel_mask": 1
    }
  ]
}
```

## 保存と適用は別

1. Hubが設定を保存する。
2. deviceがrequestする、またはHubがpushする。
3. deviceがpayloadを受信する。
4. F/Wがschemaと値を検証する。
5. valid configをLittleFSへ保存する。
6. statusで `config_received` とactive設定を報告する。

Hub画面の保存成功は1だけを示します。作業完了は5–6まで確認した時点です。

## offline時

保存済みvalid configがあり、deep-sleepから起きてRTC時刻が維持されている場合は、一時的なWi-Fi/MQTT failureでも既存scheduleを使えることがあります。power loss後のcold bootではRTC時刻を信頼せず、networkなしの予定潅水を行いません。

:::caution[安全な変更]
schedule、force watering、起動試験を変更したら、対象device ID、受信status、次回動作を必ず確認してください。
:::
