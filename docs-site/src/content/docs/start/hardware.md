---
title: 機器を選んで購入する
description: Raspberry Pi Hub、ストレージ、電源、ネットワーク機器、最初のデバイスを選定します。
---

ソフトウェアのセットアップを始める前に、このページで機器を確定します。現在公開している手順は、利用者がRaspberry Piとデバイス部品を自己調達する構成です。**弊社提供の完成品は準備中**です。

設置場所、2.4GHz Wi‑Fi、電源、valve・pumpの定格をまだ確認していない場合は、注文前に[購入前チェックリスト](/start/prerequisites/)を完了してください。

:::caution[Hubの正式な保証スペックは検討中です]
以下は現行ソフトウェアを小規模に導入するための暫定的な選定目安です。正式な対応機種、デバイス台数、保存量ごとの性能保証ではありません。カメラ、動画生成、長期のローカル保存を使う場合は推奨構成を選んでください。
:::

## Raspberry Pi Hubの選定目安

| 項目 | 最低目安 — 評価・小規模 | 推奨 — 常時稼働 | 選定理由 |
|---|---|---|---|
| 本体 | Raspberry Pi 4 Model B / RAM 2GB | Raspberry Pi 5 / RAM 4GB以上 | Hub、MQTT broker、Tunnelを同じ機器で動かす |
| OS | Raspberry Pi OS Lite 64-bit | Raspberry Pi OS Lite 64-bit | GUIを常時動かさず、systemdで運用する |
| ストレージ | 32GB以上の高耐久microSD | 64GB以上のSSDまたはNVMe | 更新、ログ、F/W、画像による容量増加と書き込み耐久に備える |
| 電源 | Pi 4用の良質な5V/3A USB-C電源 | Pi 5公式27W USB-C電源 | 電圧降下による再起動・ストレージ破損を避ける |
| 冷却 | 通気のあるケース | Pi 5 Active Coolerまたはファン付きケース | 常時稼働時のthermal throttlingを抑える |
| LAN | 安定したWi‑Fiまたは有線LAN | 有線Ethernet | HubのIPとMQTT/OTA経路を安定させる |
| 停電対策 | 正常shutdownできる運用 | 小型UPS + shutdown手順 | 書き込み中の突然の電源断を避ける |

Raspberry Pi公式は、Pi 4に3A USB-C電源、Pi 5に27W USB-C電源を推奨しています。Pi 5でSSDなどのUSB機器も給電する場合は、特に電源容量を省略しないでください。

- [Raspberry Pi OS 64-bit / Liteの配布ページ](https://www.raspberrypi.com/software/operating-systems/)
- [Raspberry Piの電源・冷却に関する公式資料](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply)

## Hub用の購入チェックリスト

- [ ] 選定したRaspberry Pi本体
- [ ] モデルに合うUSB-C電源
- [ ] microSDまたはSSD/NVMeと必要なadapter・HAT
- [ ] 放熱できるケースと、Pi 5なら冷却部品
- [ ] 有線LANケーブル
- [ ] OSを書き込むためのmicroSD readerまたはSSD接続手段
- [ ] 必要に応じてUPS
- [ ] 屋内の乾燥した設置場所と、ケーブルを固定する用品

Raspberry Piを防水筐体へ密閉すると温度が上がります。圃場に置く場合も、水・結露・薬剤・直射日光の影響を受けない屋内盤や管理棟を優先してください。

## ネットワーク機器の条件

次を満たすルーターまたはアクセスポイントが必要です。

- デバイス設置場所まで届く **2.4GHz Wi‑Fi**
- Raspberry Piを接続できるEthernet port、または安定したWi‑Fi
- Raspberry PiへDHCP予約を設定できること
- Wi‑Fi端末同士を遮断する「AP isolation」「client isolation」が無効であること
- HubからCloudflare、Turso、R2へ接続できるInternet回線
- Internet側からport 1883や39151を転送しないこと

建物・ハウス・圃場が離れている場合は、購入前に実際の設置位置で2.4GHzの電波強度を確認してください。中継器を使う場合も、端末間通信とmDNS multicastを通せる機種を選びます。

## 最初のデバイスを選ぶ

土壌水分と1系統の潅水から始める場合はWTRが最小構成です。

- Seeed Studio XIAO ESP32S3
- data通信対応USB-C cable
- 3.3V対応土壌水分sensor
- 負荷定格に合うMOSFET、relay、またはdriver
- pumpまたはsolenoid valve
- flyback protection、fuse、端子台、共通GND配線
- 安定化電源、防滴筐体、cable gland
- multimeter、電流制限付き電源、圧着工具

出力数やsensor方式で必要部品が変わります。購入前に[デバイス一覧](/devices/)でkindを確定し、各デバイスページのpin contractと部品表を確認してください。

### 機種別購入部品の概要

| kind | 主な基板・電源 | 接続部品 | 向いている用途 |
|---|---|---|---|
| WTR | XIAO ESP32S3、5V安定化電源 | 3.3V analog soil sensor、潅水driver 1系統 | 土壌水分 + 1系統潅水 |
| WRS | XIAO ESP32S3、12V電源、5V変換 | 潅水driver 2系統、3.3V logic RS485 transceiver、Modbus sensor | 2系統潅水 + RS485 |
| SOI | XIAO ESP32S3、protected 18650とholder | 3.3V analog soil sensor | battery駆動の土壌水分測定 |
| ENV | XIAO ESP32S3、12V電源、5V変換 | 3.3V logic RS485 transceiver、対応Modbus sensor | PAR、EC、pH、NPKなどの測定 |

これは発注数量を確定するための概要です。端子、fuse、protection、線材、筐体を含む最終構成は各デバイスページと[安全上の注意](/start/safety/)で確認します。

:::danger[電圧・電流を先に確認する]
valve、pump、電源、driverの定格が決まるまで部品を注文しないでください。XIAO ESP32S3のGPIOへ12V負荷を直接接続することはできません。
:::

## 弊社提供機器を購入する場合

弊社でセットアップ済みHub・デバイスを提供する構成は、現在仕様を検討中です。購入方法、型式、同梱品、保証スペックはまだ公開していません。[弊社提供機器のセットアップ（準備中）](/start/provided-hardware/)には、予定している利用開始までの流れだけを掲載しています。

購入品が揃ったら、次は[ネットワーク構成を決めます](/start/network/)。
