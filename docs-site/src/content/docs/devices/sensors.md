---
title: SOI / ENV センサー
description: 土壌水分専用SOIとRS485環境センサー用ENVの選択・配線上の要点です。
---

## SOI

SOIは18650 batteryで動く、アナログ土壌水分専用nodeです。潅水出力と12V RS485を持ちません。

| XIAO pin | 接続先 |
|---|---|
| `BAT+ / BAT-` | protected 18650 battery holder |
| `3V3 / GND` | 3.3V soil sensor power |
| `A0 / D0 / GPIO1` | soil sensor signal |
| `BOOT / GPIO0` | setup操作 |

:::danger
SOIへ12V sensorやRS485 transceiverを接続しません。batteryの極性を挿入前に測定してください。
:::

## ENV

ENVは12Vで動くRS485環境sensor nodeです。PAR、土壌、EC・pH・NPKなどのModbus sensorを集約します。

| XIAO pin | GPIO | 役割 |
|---|---:|---|
| `D4` | `GPIO5` | RS485 DE / RE |
| `D6` | `GPIO43` | RS485 TX / DI |
| `D7` | `GPIO44` | RS485 RX / RO |
| `VBUS` | — | 12Vから変換した安定化5V |
| `GND` | — | sensorを含む共通GND |

ENVのsensor 12V branchは現在のprofileでは常時給電です。電源switchが必要な場合は、Device DefinitionとF/Wが対応していることを確認してから配線します。

## どちらを選ぶか

- 1地点の土壌水分を低消費電力で測る: **SOI**
- 12Vの産業sensorをModbusで読む: **ENV**
- 測定と潅水を同じ筐体で行う: **WTRまたはWRS**

すべての機種で、Hubのdevice kind、書き込んだF/W、H/Wラベルが一致していることを受入試験で確認します。
