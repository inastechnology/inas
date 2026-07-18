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

水やり全部入りデバイス。潅水制御、土壌水分 ADC、RS485 センサー、RS485 センサー用電源 MOSFET を持つ。H/W profile によって電源電圧や負荷定格が変わっても、WTR の pin contract は維持する。

![WTR pin assignment](xiao_esp32s3_pin_assignment_wtr.svg)

| 用途 | XIAO pin | GPIO | 備考 |
|---|---|---:|---|
| バルブ MOSFET | `D2` | `GPIO3` | 潅水系統 1 |
| ポンプ MOSFET | `D3` | `GPIO4` | バルブ系統が ON の時に自動 ON |
| 土壌水分 ADC | `A5` / `D5` | `GPIO6` | 既存の `A2/D2` 重複を避ける |
| RS485 DE/RE | `D4` | `GPIO5` | 送受信方向制御 |
| RS485 TX | `D6` | `GPIO43` | UART1 TX |
| RS485 RX | `D7` | `GPIO44` | UART1 RX |
| 12V センサー電源 MOSFET | `D8` | `GPIO7` | RS485 センサーへ向かう 12V 分岐だけを切る |
| 5V input | `VBUS` | - | 12V -> 5V DCDC 後に入力 |
| GND | `GND` | - | 12V 系、RS485、ESP32S3 の GND を共通化 |
| 設定 AP | `BOOT` | `GPIO0` | active-low |

`D8` の後段に ESP32S3 本体電源を置かない。`D8` で切る対象は RS485 センサーの 12V 分岐だけ。

低電圧 WTR H/W profile でも、analog soil moisture は `A5/D5`、灌水出力は `D2`/`D3` の WTR pin contract を使う。電圧や MOSFET 定格の違いだけで sensor を `A0` へ移したり、別 device kind を作ったりしない。

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

RS485 前提の水やり全部入りデバイス。WRS は WTR の灌水出力と RS485 pin assignment を流用し、RS485 土壌/PAR/日射センサーを主フィードバック経路として扱う。WTR の図を WRS にも適用できるが、アナログ土壌水分 ADC は未使用または診断用予約としてよい。

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
