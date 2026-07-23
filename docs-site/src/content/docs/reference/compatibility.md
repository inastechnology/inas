---
title: 互換性と制約
description: 現在のHub・F/W・network構成で知っておくべき互換性と制約です。
---

## 対応環境

- Hub: Linux / Raspberry Piを推奨
- F/W build: LinuxまたはWSL2
- board: 各projectが指定するSeeed XIAO ESP32S3 profile
- browser: 現行のChrome、Edge、Firefox、Safari
- Wi-Fi device: 2.4GHz networkを用意

## 現在の主な制約

| 項目 | 制約 |
|---|---|
| OTA download | device F/Wは現在 `http://` URLのみ対応 |
| Cloudflare Access | Hub UI/APIのHTTPS入口。OTA binary URLには使わない |
| deviceのmDNS | 現行F/Wは明示的なmDNS query未実装。自己調達ではHubのDHCP予約IPをMQTT/OTAに使う |
| WTR output | 1系統、`channel_mask=1` |
| WTR pins | soil `A2/D2`、irrigation `D4` |
| WTR schedules | 最大8件 |
| WTR起動試験 | cold boot/reset、fresh config、OTA未試行、1–30秒 |
| WTR分割潅水 | patternがschedule durationを置換、最大20 repeat |
| config待機 | 現行共通F/Wは15秒 |
| 古いMQTT受信 | 512-byte上限の旧WTR F/Wは大きいconfigを受信不可 |

## versionを含めて報告する

互換性問題を調査するときは「最新です」ではなく、次を明記します。

- Hub Git commit
- device kind
- `firmware_version`
- Device Definition `definition_version`
- board/hardware profile
- Runtime Config schemaまたは代表key

## 破壊的になりうる操作

- `flash_merged.bin` はLittleFSを含み、保存済みWi-Fi/MQTT/configを上書きします。
- `.env`の再生成はHub接続・認証・保存先を変える可能性があります。
- Cloudflare setupの再provisionはAccess/Tunnel/DNSを変更します。
- backup importの `--overwrite` は既存runtime fileを置き換えます。

実行前にtarget、backup、rollback方法を確認してください。

Hubの正式な最低・推奨保証スペックと弊社提供機器は検討中です。自己調達時の暫定的な選定目安は[機器を選んで購入する](/start/hardware/)を参照してください。
