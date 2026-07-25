---
title: Runtime Config
description: Hubからdeviceへ送るRuntime Configの保存・配信・確認方法です。
---

Runtime Configは、登録deviceごとの運用設定です。Device Definitionが送信可能なkeyを宣言し、Hubが保存・配信し、F/Wが検証して適用します。

<figure class="process-map" aria-labelledby="runtime-config-lifecycle-title">
  <div class="process-map__heading">
    <strong id="runtime-config-lifecycle-title">Runtime Configのライフサイクル</strong>
    <span>Stored → Active</span>
  </div>
  <ol class="process-map__steps">
    <li><strong>Hubに保存</strong><small>deviceごとの運用設定を保持する</small></li>
    <li><strong>配信を開始</strong><small>requestへのreply、またはpushを送る</small></li>
    <li><strong>deviceが受信</strong><small>MQTT topicとpayloadを受け取る</small></li>
    <li><strong>検証・永続化</strong><small>schema確認後にLittleFSへ保存する</small></li>
    <li><strong>active値を報告</strong><small>statusで受信結果と適用値を返す</small></li>
  </ol>
  <figcaption>「保存済み」と「実機で有効」は別の状態です。右端まで確認して作業完了とします。</figcaption>
</figure>

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

<figure class="product-screenshot">
  <a href="/images/screenshots/watering-settings.webp" aria-label="Runtime Configを編集する動作設定画面を原寸で開く">
    <img src="/images/screenshots/watering-settings.webp" alt="潅水機の接続先、閾値、予約を編集するRuntime Configの動作設定画面" loading="lazy" decoding="async" />
  </a>
  <figcaption>通常はJSONを直接編集せず、機器詳細の「動作設定」から保存します。保存後に、同じ機器の状態で受信済みの値まで確認してください。</figcaption>
</figure>

## offline時

保存済みvalid configがあり、deep-sleepから起きてRTC時刻が維持されている場合は、一時的なWi-Fi/MQTT failureでも既存scheduleを使えることがあります。power loss後のcold bootではRTC時刻を信頼せず、networkなしの予定潅水を行いません。

:::caution[安全な変更]
schedule、force watering、起動試験を変更したら、対象device ID、受信status、次回動作を必ず確認してください。
:::
