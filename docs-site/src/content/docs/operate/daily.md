---
title: 日々の確認
description: INAS Hubと圃場デバイスを安全に運用するための日次・週次チェックです。
---

すべてのraw logを見る必要はありません。まず異常、最終受信、次の作業、次の潅水を確認し、必要なdeviceだけ詳細を開きます。

## 毎日

- Hub dashboardに重大な警告がない。
- 対象圃場の最終測定時刻が想定wake周期内にある。
- 土壌水分がsensorの正常範囲にあり、急な張り付きがない。
- 今日・明日の潅水予定と流量が作物の状態に合う。
- 潅水eventに `watering_started` と完了結果が残っている。
- 作業kanbanに期限超過・確認待ちがないか確認する。

## 毎週

- deviceごとのRSSI、batteryまたは電源状態を確認する。
- sensor cable、筐体、配管、filter、valve周辺を目視する。
- 漏水、詰まり、異音、発熱がないか確認する。
- Cloudflare Tunnelを使う場合はconnector状態を確認する。
- Hub backupが取得できているか確認する。
- 未適用のF/W targetと失敗中のOTAを確認する。

## 設定変更時

1. 変更前の値を記録します。
2. 対象device IDを再確認します。
3. 一度に1種類の変更を行います。
4. deviceが新しいRuntime Configを受信したことを確認します。
5. 実行eventと現場の動作を比較します。
6. 異常時に戻せる値を用意します。

:::tip[水量で管理する]
秒数だけではなく、実際の流量を測り「ON秒数 × 流量 = 水量」で記録すると、pumpや圧力を変えたときも設定を見直しやすくなります。
:::

## 異常を見つけたら

- 最終受信が古い: [デバイスがオフライン](/troubleshoot/device-offline/)
- scheduleがdueなのに水が出ない: [潅水されない](/troubleshoot/watering/)
- 保存値とdevice値が違う: [設定が反映されない](/troubleshoot/config/)
- F/W versionが変わらない: [F/W・OTA更新](/operate/firmware/)
