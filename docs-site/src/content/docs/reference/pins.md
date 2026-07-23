---
title: ピンアサイン
description: XIAO ESP32S3を使うWTR・WRS・SOI・ENVのpin contract一覧です。
---

同じXIAO pinでもdevice kindごとに役割が異なります。F/W、Device Definition、実配線、筐体ラベルをこの表へ合わせます。

## 一覧

| kind | 測定 | 潅水出力 | RS485 | 電源 |
|---|---|---|---|---|
| WTR | soil `A2/D2/GPIO3` | `D4/GPIO5` 1系統 | なし | profileに合う5V/3.3V |
| WRS | diagnostic `A5/D5` | `D2/GPIO3`, `D3/GPIO4` | `D4`, `D6`, `D7`, sensor power `D8` | 12V → 5V VBUS |
| SOI | soil `A0/D0/GPIO1` | なし | なし | protected 18650 + 3.3V sensor |
| ENV | RS485 sensors | なし | `D4`, `D6`, `D7` | 12V → 5V VBUS |

## WTR

| pin | GPIO | 役割 |
|---|---:|---|
| `A2 / D2` | 3 | 土壌水分signal |
| `D4` | 5 | 潅水driver制御 |
| `3V3 / GND` | — | 3.3V soil sensor |
| `VBUS / GND` | — | 安定化5V入力 |

## WRS / ENVのRS485

| pin | GPIO | 役割 |
|---|---:|---|
| `D4` | 5 | DE / RE direction |
| `D6` | 43 | TX / DI |
| `D7` | 44 | RX / RO |
| `D8` | 7 | WRS sensor 12V power switch |

:::danger
WTRの `D4` は潅水です。WRS/ENVの `D4` はRS485 directionです。device kindを決めずに配線表だけを流用しないでください。
:::

製造用の線色・外部端子・検査表とboard画像は、repositoryの `client-devices/docs/jp/esp32s3_wiring_tables.md` と `client-devices/docs/xiao_esp32s3_pin_assignment_*.svg` を参照してください。
