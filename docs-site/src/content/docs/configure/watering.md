---
title: 潅水
description: 潅水schedule、土壌水分threshold、分割潅水、起動時試験を安全に設定します。
---

潅水は、scheduleがdueになり、時刻同期・Runtime Config・安全条件を満たしたcycleで実行されます。設定後すぐ常時接続でcommandが走るとは限らず、省電力deviceは次のwakeで設定を取得します。

## 基本設定

| 設定 | 意味 | 最初の推奨 |
|---|---|---|
| `schedules[].hour/minute` | 実行するlocal時刻 | 管理できる昼間で試験 |
| `schedules[].duration_sec` | 通常潅水の連続ON秒数 | 1–5秒から |
| `moisture_threshold` | この水分以上なら潅水を抑止 | sensor校正後に決定 |
| `force_watering` | due時に水分判定を無視 | 通常は `false` |
| `channel_mask` | 対象output | WTRは `1` 固定 |

## scheduleの例

```json
{
  "ntp_server": "192.168.1.10",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 35,
  "force_watering": false,
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

1台につき最大8 schedulesを受け付けます。`timezone_offset_sec=32400` はUTC+9です。NTP serverへ到達できないcold bootでは、時刻を信頼できないため予定潅水を実行しません。

## 分割潅水と潅水時間

分割潅水を有効にすると、scheduleの `duration_sec` と分割patternを両方は実行しません。**同じdue scheduleに対し、分割patternが通常の連続時間を置き換えます。**

```json
{
  "watering_pattern": {
    "enabled": true,
    "on_sec": 10,
    "off_sec": 20,
    "repeat_count": 3
  }
}
```

この例は「10秒ON → 20秒OFF」を3回行います。ただし最後のON後に不要なOFF待機は行いません。

- 合計ON時間: `on_sec × repeat_count` = **30秒**
- 途中の合計OFF時間: `off_sec × (repeat_count - 1)` = **40秒**
- cycle全体: **70秒**
- scheduleの `duration_sec`: 分割有効中は実際のON時間に使われない

:::caution[画面上の両方を設定しても加算されない]
scheduleの潅水時間は、分割を無効に戻したときの通常運転値として残ります。分割有効中の水量は `on_sec × repeat_count` で見積もってください。
:::

## 土壌水分の判定

`force_watering=false` のとき、dueになっても測定水分がthreshold以上なら潅水を開始しません。sensor値が未校正・断線・飽和している場合、意図しない抑止や潅水につながるため、乾燥・湿潤のraw値を確認してからthresholdを決めます。

`force_watering=true` は、due scheduleで水分判定を無視する設定です。敷設試験には[起動時潅水試験](/devices/wtr/#敷設時の起動潅水試験)を使い、常用しません。

## 設定を反映する

1. Hubで保存します。
2. push対応deviceには更新を送ります。
3. 省電力deviceは次のwake、または安全に再起動して取得させます。
4. `config_received=true` と設定値を確認します。
5. 次回予定時刻とtimezoneを確認します。
6. 短時間の試験後、実際の流量から本番時間へ調整します。

設定を保存しただけで完了とせず、[Runtime Configの確認方法](/reference/runtime-config/)に従って実機受信まで確認してください。
