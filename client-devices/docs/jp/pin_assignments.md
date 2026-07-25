# XIAO ESP32S3 Pin Assignments

このドキュメントは、`seeed_xiao_esp32s3` を使う INAS device のピン割当をまとめる。

製造向け配線表:

- [esp32s3_wiring_tables.md](esp32s3_wiring_tables.md)

関連手順書:

- [manufacturing_procedure.md](manufacturing_procedure.md)
- [wiring_procedure.md](wiring_procedure.md)
- [installation_procedure.md](installation_procedure.md)
- [operation_guide.md](operation_guide.md)

draw.io source:

- [xiao_esp32s3_pin_assignments.drawio](xiao_esp32s3_pin_assignments.drawio)

Update command:

```sh
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

ピン枠は基板画像内のピン名ラベルに重ねている。座標を変更する場合は SVG や draw.io を直接編集せず、
[generate_xiao_pin_assignment_diagrams.py](../generate_xiao_pin_assignment_diagrams.py) の `TOP_RECTS` / `BACK_RECTS` を更新して再生成する。

SVG previews:

- [WTR](xiao_esp32s3_pin_assignment_wtr.svg)
- [ENV](xiao_esp32s3_pin_assignment_env.svg)
- [SOI](xiao_esp32s3_pin_assignment_soi.svg)

## WTR

アナログ土壌水分と 1 系統の潅水出力を持つデバイス。H/W profile によって電源電圧や負荷定格が変わっても、WTR の pin contract は維持する。RS485 と 2 系統出力が必要な場合は WRS を使う。

![WTR pin assignment](xiao_esp32s3_pin_assignment_wtr.svg)

| 用途 | XIAO pin | GPIO | 備考 |
|---|---|---:|---|
| 土壌水分 ADC | `A2` / `D2` | `GPIO3` | アナログ土壌水分 signal |
| 潅水 output | `D4` | `GPIO5` | 外部 MOSFET、relay、driver input を制御 |
| 5V input | `VBUS` | - | 12V -> 5V DCDC 後に入力 |
| 3.3V sensor power | `3V3` | - | 3.3V 対応 soil sensor だけを接続 |
| GND | `GND` | - | sensor、driver、ESP32S3 の GND を共通化 |
| 設定 AP | `BOOT` | `GPIO0` | active-low |

低電圧 WTR H/W profile でも、analog soil moisture は `A2/D2`、潅水出力は `D4` の WTR pin contract を使う。pump や valve を GPIO へ直結せず、負荷定格に合う外部 driver と flyback protection を使う。WTR の `D4` を RS485 direction として配線しない。

## ENV

12V 電源前提の RS485 Modbus センサーハブ。PAR、EC/pH/NPK などの RS485 センサーを同じ bus にぶら下げる。

![ENV pin assignment](xiao_esp32s3_pin_assignment_env.svg)

| 用途 | XIAO pin | GPIO | 備考 |
|---|---|---:|---|
| RS485 DE/RE | `D4` | `GPIO5` | 送受信方向制御 |
| RS485 TX | `D6` | `GPIO43` | UART1 TX |
| RS485 RX | `D7` | `GPIO44` | UART1 RX |
| 5V input | `VBUS` | - | 12V -> 5V DCDC 後に入力 |
| GND | `GND` | - | RS485 GND と共通 |
| 設定 AP | `BOOT` | `GPIO0` | active-low |

## WRS

RS485 前提の水やり全部入りデバイス。WRS は `D2/D3` の 2 系統潅水出力と `D4/D6/D7` の RS485 pin assignment を持ち、RS485 土壌/PAR/日射センサーを主フィードバック経路として扱う。WTR とは異なる pin contract であり、アナログ土壌水分 ADC は未使用または診断用予約としてよい。

追加センサーは同じ RS485 bus に接続する。未接続センサーは Modbus timeout、CRC error、無応答によって検出し、`*_ok=false` として報告する。センサー追加のたびに XIAO の pin assignment を増やさない。

## FGT

FGT は MCP23017 用の I2C に `D0/D1`、外部 pull-down 付きの全 actuator
許可信号に `D3`、原水流量 pulse に `D5`、RS485 に `D4/D6/D7`、RS485
sensor 電源に `D8` を使う。`D2/GPIO3` は strapping pin のため予約する。
5つの actuator 選択と4つの安全入力は MCP23017 へ接続する。詳細な割当と
reset 時 OFF の配線規則は
[fertigation-device/docs/hardware_and_power.md](../../fertigation-device/docs/hardware_and_power.md)
を参照する。

## SOI

18650 バッテリー前提の土壌水分専用ノード。現状は RS485 を持たない。

![SOI pin assignment](xiao_esp32s3_pin_assignment_soi.svg)

| 用途 | XIAO pin | GPIO | 備考 |
|---|---|---:|---|
| 土壌水分 ADC | `A0` / `D0` | `GPIO1` | `APP_SOI_MOISTURE_PIN=A0` |
| センサー VCC | `3.3V-OUT` | - | 土壌水分センサーの電源 |
| センサー GND | `GND` | - | 電源 GND |
| Battery + | `BAT+` | - | 18650 battery + |
| Battery - | `BAT-` | - | 18650 battery - |
| 設定 AP | `BOOT` | `GPIO0` | active-low |

## Common

| 用途 | XIAO pin | GPIO | 備考 |
|---|---|---:|---|
| Setup portal / reset entry | `BOOT` | `GPIO0` | common firmware default |
| Status LED | `USER_LED` | `GPIO21` | board LED |
