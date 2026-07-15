# ESP32S3 配線表

このドキュメントは、Seeed XIAO ESP32S3 を使う INAS device の製造向け配線表である。基板画像つきのピン割当は [pin_assignments.md](pin_assignments.md) を参照する。

## 共通ルール

- ESP32S3 の GPIO は 3.3V logic として扱う。RS485 transceiver は MAX3485、SP3485、SN65HVD 系など 3.3V logic 対応品を使う。
- 12V 電源 device では、XIAO の `VBUS` に 5V regulated output を入れる。12V を XIAO に直接入れない。
- battery 駆動 profile では、protected cell を `BAT+` / `BAT-` に接続し、外部 sensor と output wiring は対象 profile の範囲に収める。
- ESP32S3 GND、RS485 transceiver GND、12V センサー GND、ポンプ/バルブ電源 GND、DCDC GND は device 内の GND point で共通化する。
- センサー電源 MOSFET で切るのは RS485 センサーへ向かう 12V 分岐だけ。ESP32S3 本体電源をこの switch の後段に置かない。
- 同じ RS485 bus 上の Modbus slave ID は重複させない。
- 任意センサーの未接続は timeout または `*_ok=false` として扱う。センサー構成ごとに XIAO pin assignment を変えない。
- MOSFET で切り替える出力は、hub runtime config の `mosfet_switches` 出力台帳へ記録する。組立時に貼る端子ラベルと、`terminal`、`channel_mask`、`name`、`controlled_load` を一致させる。

## 線色の目安

| 信号種別 | 推奨色 | 備考 |
|---|---|---|
| 12V input / switched 12V | 赤 | 常時 12V と switched 12V をラベルで区別する |
| 5V regulated output | 橙 | DCDC output から XIAO `VBUS` |
| 3.3V sensor power | 紫 | SOI と低電圧 WTR profile の analog sensor 用 |
| GND / 0V | 黒 | 共通 GND |
| RS485 A / D+ | 黄 | RS485 B とツイストする |
| RS485 B / D- | 緑 | RS485 A とツイストする |
| UART TX / RX / DE | 青 / 白 / 灰 | 筐体内の短い配線 |
| MOSFET gate | 青 | XIAO からの内部 signal |
| Analog signal | 白 | ポンプ/バルブ配線から離す |

## WTR

水やり全部入りデバイス。WTR は灌水制御、analog 土壌水分、任意の RS485 センサーを扱う。

| XIAO pin | GPIO | 接続先 | 外部端子 | 線材 | 検査 |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DCDC output | Power `5V_OUT` | 橙 22-24 AWG | XIAO 接続前に 4.75-5.25V |
| `GND` | - | device GND | Power `GND` | 黒 20-24 AWG | 12V negative、RS485 GND と導通 |
| `D2` | `GPIO3` | valve MOSFET gate | Valve output channel 1 | 青 24-26 AWG | valve command 時に gate が変化 |
| `D3` | `GPIO4` | pump MOSFET gate | Pump output | 青 24-26 AWG | valve active 中に pump output が ON |
| `A5` / `D5` | `GPIO6` | analog soil moisture signal | Soil analog `SIG` | 白 24-26 AWG | 乾湿基準で ADC が変化 |
| `D4` | `GPIO5` | RS485 transceiver DE/RE | internal RS485 driver | 灰 24-26 AWG | Modbus TX 時に direction pin が変化 |
| `D6` | `GPIO43` | RS485 transceiver DI | internal RS485 TX | 青 24-26 AWG | request 時に UART TX が出る |
| `D7` | `GPIO44` | RS485 transceiver RO | internal RS485 RX | 白 24-26 AWG | response 時に UART RX が入る |
| `D8` | `GPIO7` | 12V sensor power MOSFET gate | RS485 sensor power switch | 青 24-26 AWG | sensor read 中だけ switched 12V が出る |
| `BOOT` | `GPIO0` | setup AP button | enclosure service button | 2 線 signal | active-low、3.3V へ短絡なし |
| `USER_LED` | `GPIO21` | board LED | internal only | - | firmware status LED が動作 |

外部端子:

| 端子 | 接続先 | 備考 |
|---|---|---|
| `12V_IN+` | 12V supply positive | 可能なら device 前段に fuse |
| `12V_IN-` | 12V supply negative | common ground |
| `VALVE+` / `VALVE-` | solenoid valve または valve driver | 電圧・電流定格を合わせる |
| `PUMP+` / `PUMP-` | pump または pump relay/MOSFET output | MOSFET 定格を超えない |
| `RS485_A` / `RS485_B` | sensor bus A/B | 全センサー無応答なら A/B を疑う |
| `RS485_GND` | sensor bus ground | 圃場配線の安定化に必須 |
| `SENSOR_12V_SW+` | switched sensor 12V | sensor branch のみ |
| `SOIL_SIG` / `SOIL_3V3` / `SOIL_GND` | analog soil moisture sensor | RS485 土壌センサー利用時は任意 |

### WTR 低電圧 H/W profile

device の責務が WTR のまま、小型低電圧 pump、valve driver input、relay input などを駆動する場合の profile。`APP_DEVICE_KIND="WTR"` と WTR firmware の pin contract を維持する。

| XIAO pin | GPIO | 接続先 | 外部端子 | 線材 | 検査 |
|---|---:|---|---|---|---|
| `BAT+` または `VBUS` | - | 承認済み battery または regulated input | power input | 赤/橙 22-24 AWG | XIAO の入力範囲内 |
| `GND` | - | device ground | `GND` terminal | 黒 22-24 AWG | sensor/output GND と共通 |
| `D2` | `GPIO3` | WTR valve/irrigation enable MOSFET gate | `IRR1` または driver enable | 青 24-26 AWG | WTR irrigation channel active 時に gate が変化 |
| `D3` | `GPIO4` | WTR pump/output MOSFET gate | `IRR2` または pump output | 青 24-26 AWG | WTR watering behavior に追従 |
| `A5` / `D5` | `GPIO6` | analog soil moisture signal | Soil analog `SIG` | 白 24-26 AWG | 乾湿基準で ADC が変化 |

低電圧 profile で RS485 sensor を使わない場合、RS485 と `D8` sensor power は未実装でよい。analog soil sensor を `A0` へ移さない。`A0` は SOI の pin contract であり、WTR ではない。

## WRS

RS485 前提の水やり全部入りデバイス。WRS は汎用の灌水 1 系 / 灌水 2 系と RS485 配線を持つ。device は pump / valve の役割を区別せず、設置側が各灌水出力を現場の負荷へ割り当てる。analog soil pin は明示的に使う build でない限り診断用予約とする。

| XIAO pin | GPIO | 接続先 | 外部端子 | 線材 | 検査 |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DCDC output | Power `5V_OUT` | 橙 22-24 AWG | XIAO 接続前に 4.75-5.25V |
| `GND` | - | device GND | Power `GND` | 黒 20-24 AWG | 12V negative、RS485 GND と導通 |
| `D2` | `GPIO3` | 灌水 1 系 MOSFET gate | `IRR1+` / `IRR1-` | 青 24-26 AWG | channel mask bit 0 指定時に gate が変化 |
| `D3` | `GPIO4` | 灌水 2 系 MOSFET gate | `IRR2+` / `IRR2-` | 青 24-26 AWG | channel mask bit 1 指定時に gate が変化 |
| `A5` / `D5` | `GPIO6` | reserved diagnostic analog input | internal test pad | 白 24-26 AWG | 明示仕様がなければ未接続 |
| `D4` | `GPIO5` | RS485 transceiver DE/RE | internal RS485 driver | 灰 24-26 AWG | Modbus TX 時に direction pin が変化 |
| `D6` | `GPIO43` | RS485 transceiver DI | internal RS485 TX | 青 24-26 AWG | request 時に UART TX が出る |
| `D7` | `GPIO44` | RS485 transceiver RO | internal RS485 RX | 白 24-26 AWG | response 時に UART RX が入る |
| `D8` | `GPIO7` | 12V sensor power MOSFET gate | RS485 sensor power switch | 青 24-26 AWG | sensor read 中だけ switched 12V が出る |
| `BOOT` | `GPIO0` | setup AP button | enclosure service button | 2 線 signal | active-low、3.3V へ短絡なし |
| `USER_LED` | `GPIO21` | board LED | internal only | - | firmware status LED が動作 |

外部端子:

| 端子 | 接続先 | 備考 |
|---|---|---|
| `12V_IN+` / `12V_IN-` | 12V supply | 灌水出力、RS485、5V DCDC と GND 共通 |
| `IRR1+` / `IRR1-` | 灌水 1 系の負荷または driver | `channel_mask` bit 0 |
| `IRR2+` / `IRR2-` | 灌水 2 系の負荷または driver | `channel_mask` bit 1 |
| `RS485_A` / `RS485_B` | soil、PAR、日射センサー | sensor ごとに一意の Modbus slave ID |
| `RS485_GND` | sensor bus ground | 長い配線では必須 |
| `SENSOR_12V_SW+` | RS485 sensor 12V branch | sensor branch のみ。ESP32S3 電源ではない |

### WRS + DFRobot SEN0641 配線

| SEN0641 wire | WRS 接続先 | 確認 |
|---|---|---|
| brown / VCC | `SENSOR_12V_SW+` | sensor power ON 時に 12V、sleep 中は 0V |
| black / GND | `RS485_GND` | WRS GND と導通 |
| yellow / 485-A | `RS485_A` | A/B を twisted pair にする |
| blue / 485-B | `RS485_B` | 全読取 timeout 時は A/B 表記を再確認 |

SEN0641 は既定 `4800bps / slave 1 / function 0x03 / register 0x0000 / scale 1.0` とする。土壌センサーは既定 `slave 2` とし、同じ bus で ID を重複させない。

5V MAX485 module を使う場合は 5V で給電し、MAX485 `RO` と XIAO `D7/GPIO44` の間に 3.3V level shifter を入れる。5V `RO` を XIAO へ直結しない。新規製造では 3.3V logic の MAX3485/SP3485/SN65HVD 系を優先する。

推奨 `mosfet_switches` 出力台帳:

| switch_id | name | terminal | channel_mask | controlled_load |
|---|---|---|---:|---|
| `irr1` | 灌水1系 | `IRR1+` / `IRR1-` | `1` | 灌水 1 系へ接続した現場負荷または driver |
| `irr2` | 灌水2系 | `IRR2+` / `IRR2-` | `2` | 灌水 2 系へ接続した現場負荷または driver |
| `sensor_power` | RS485センサー電源 | `SENSOR_12V_SW+` | `0` | RS485 センサー向け switched 12V 分岐 |

## ENV

12V 電源前提の RS485 環境センサーハブ。

| XIAO pin | GPIO | 接続先 | 外部端子 | 線材 | 検査 |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DCDC output | Power `5V_OUT` | 橙 22-24 AWG | XIAO 接続前に 4.75-5.25V |
| `GND` | - | device GND | Power `GND` | 黒 20-24 AWG | 12V negative、RS485 GND と導通 |
| `D4` | `GPIO5` | RS485 transceiver DE/RE | internal RS485 driver | 灰 24-26 AWG | Modbus TX 時に direction pin が変化 |
| `D6` | `GPIO43` | RS485 transceiver DI | internal RS485 TX | 青 24-26 AWG | request 時に UART TX が出る |
| `D7` | `GPIO44` | RS485 transceiver RO | internal RS485 RX | 白 24-26 AWG | response 時に UART RX が入る |
| `BOOT` | `GPIO0` | setup AP button | enclosure service button | 2 線 signal | active-low、3.3V へ短絡なし |
| `USER_LED` | `GPIO21` | board LED | internal only | - | firmware status LED が動作 |

外部端子:

| 端子 | 接続先 | 備考 |
|---|---|---|
| `12V_IN+` / `12V_IN-` | 12V supply | sensors と 5V DCDC を供給 |
| `RS485_A` / `RS485_B` | PAR、soil、EC/pH/NPK、日射センサー | sensor ごとに一意の Modbus slave ID |
| `RS485_GND` | sensor bus ground | 圃場配線の安定化に必須 |
| `SENSOR_12V+` | sensor 12V supply | future switch がない限り常時 12V |

## SOI

18650 バッテリー前提の土壌水分専用ノード。

| XIAO pin | GPIO | 接続先 | 外部端子 | 線材 | 検査 |
|---|---:|---|---|---|---|
| `BAT+` | - | protected 18650 positive | battery holder `+` | 赤 22-24 AWG | battery 挿入前に極性確認 |
| `BAT-` | - | battery negative | battery holder `-` | 黒 22-24 AWG | sensor GND と共通 |
| `3.3V-OUT` | - | analog soil sensor VCC | soil sensor `VCC` | 紫 24-26 AWG | 3.3V のみ |
| `GND` | - | sensor ground | soil sensor `GND` | 黒 24-26 AWG | battery negative と導通 |
| `A0` / `D0` | `GPIO1` | analog soil sensor signal | soil sensor `SIG` | 白 24-26 AWG | 乾湿基準で ADC が変化 |
| `BOOT` | `GPIO0` | setup AP button | enclosure service button | 2 線 signal | active-low、3.3V へ短絡なし |
| `USER_LED` | `GPIO21` | board LED | internal only | - | firmware status LED が動作 |

SOI に 12V RS485 センサーを接続しない。12V または RS485 Modbus が必要なセンサーは ENV または WRS で扱う。
