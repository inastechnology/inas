---
title: WRS 潅水・RS485
description: 2系統の潅水出力とRS485センサーを扱うWRSの構成を説明します。
---

WRSは、2つのgeneric irrigation出力とRS485 sensor busを持つ構成です。WTRの1出力profileとはpin contractが異なります。

## pin contract

| XIAO pin | GPIO | 役割 |
|---|---:|---|
| `D2` | `GPIO3` | irrigation output 1 |
| `D3` | `GPIO4` | irrigation output 2 |
| `D4` | `GPIO5` | RS485 DE / RE |
| `D6` | `GPIO43` | RS485 TX / DI |
| `D7` | `GPIO44` | RS485 RX / RO |
| `D8` | `GPIO7` | 12V sensor power switch |
| `VBUS` | — | 安定化5V入力 |
| `GND` | — | 共通GND |

出力1・2はpump/valveという固定役割ではありません。現場の接続先をHub Runtime Configの `mosfet_switches` inventoryと端子ラベルに一致させます。

## RS485

- 3.3V logicのMAX3485、SP3485、SN65HVD系を推奨します。
- `RS485_A` と `RS485_B` はtwisted pairにします。
- `RS485_GND` をsensor busと一緒に通します。
- 同じbusのModbus slave IDを重複させません。
- 全sensorがtimeoutする場合はA/B、baud rate、GND、slave IDの順で確認します。
- 5V MAX485の `RO` をXIAO RXへ直結しません。3.3Vへlevel shiftします。

## SEN0641の例

| SEN0641 wire | WRS terminal |
|---|---|
| brown / VCC | `SENSOR_12V_SW+` |
| black / GND | `RS485_GND` |
| yellow / 485-A | `RS485_A` |
| blue / 485-B | `RS485_B` |

既定profileは `4800bps / slave 1 / function 0x03 / register 0x0000` です。同じbusで土壌sensorを使う場合は別のslave IDを割り当てます。

:::caution
WRS F/WとHubのDevice Definitionを使ってください。WTR F/WのままWRS配線へ変更しないでください。
:::

製造向けの詳細な端子・線色・検査表は、repositoryの `client-devices/docs/jp/esp32s3_wiring_tables.md` を参照してください。
