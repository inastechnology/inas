---
title: F/W・OTA更新
description: F/Wをbuild・検査・Hubへ登録し、次回起動で安全にOTA更新する流れです。
---

OTAでは、MQTTは「どのversionへ更新するか」という通知に使い、`firmware.bin` 本体はHubのHTTP endpointから配信します。

## 更新の流れ

1. device projectでF/Wをbuildします。
2. embedded manifestを検査します。
3. Hubへartifactをupload・登録します。
4. size、SHA-256、device kind、URLを確認します。
5. 少数のdeviceへtarget versionを設定します。
6. deviceの次回起動またはwakeでofferを受信させます。
7. HTTP download、検証、適用、再起動を待ちます。
8. 新versionのstatusと機能を確認してから対象を広げます。

## buildと検査

WTRの例です。

```bash
cd client-devices/watering-device
make build
make check-firmware
```

artifactは `.pio/build/seeed_xiao_esp32s3/firmware.bin` です。`make check-firmware` が失敗したbinaryを登録しません。

## Hubへ登録する

HubのF/W管理画面、またはCloudflare Accessで保護されたOperations APIを使います。登録後に次を照合します。

- device kindが対象実機と一致する。
- versionが既存artifactと意図せず重複していない。
- file sizeとSHA-256が表示される。
- download URLへ対象deviceのLANから到達できる。
- URLが現在のF/Wで対応する `http://` である。

## 次回起動で更新する

target versionを設定すると、Hubは対象deviceへOTA offerを出します。省電力deviceは次回wakeで確認します。再起動すれば必ず成功するわけではなく、Wi-Fi、MQTT、HTTP URL、artifact整合性がすべて必要です。

成功後に確認する項目:

- statusの `firmware_version` がtargetと一致する。
- targetが適用済みとして扱われる。
- Runtime Configを再受信できる。
- sensor値とoutputが正しい。
- boot loopやrollbackがない。

:::caution[起動潅水とOTA]
同じcold bootでOTA updateを試行した場合、WTRの起動時潅水試験は実行しません。F/W versionを確認した後、必要なら次のcold bootで導通試験を行ってください。
:::

## 失敗時の切り分け

| 状態 | 確認するもの |
|---|---|
| offerを受けない | MQTT接続、device ID、target、retained message |
| downloadできない | `FIRMWARE_BASE_URL`、host名、port、LAN firewall |
| 検証で失敗 | size、SHA-256、artifact破損 |
| versionが戻る | boot/partition/rollback log、binary互換性 |
| 更新後configなし | MQTT config request/reply、payload size、F/W schema |

多数へ一括適用せず、1台の現場外deviceで成功条件を確認してから段階的に広げます。
