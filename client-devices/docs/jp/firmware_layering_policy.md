# Client Firmware レイヤ分離ポリシー

英語版: [../firmware_layering_policy.md](../firmware_layering_policy.md)

## 目的

この文書は、INAS client firmware のレイヤ境界を定義する。device、sensor、actuator、bus、protocol driver を追加するときは、この原則に従う。

目的は、H/W 抽象を再利用可能で理解しやすい形に保つことである。既存 HAL 呼び出しを `device_kind` や製品名で束ねるだけの HAL module は作らない。

## レイヤ責務

| レイヤ | 持つもの | 持たないもの |
|---|---|---|
| Common App | boot/wake lifecycle、setup AP、Wi-Fi/MQTT transport、OTA、time sync、debug log、共通 task/config utility | device 固有 runtime config schema、pin map、sensor/actuator behavior |
| Device App | `device_kind`、製品挙動、runtime config parsing、schedule/control policy、sensor sampling order、payload shape | 共通 HAL が存在する GPIO/UART の生制御 |
| HAL | switched MOSFET/power rail、ADC、camera、audio、RS485 UART/DE、I2C/SPI device などの物理 H/W primitive | 製品 policy、device kind semantics、MQTT payload、runtime config parsing |
| Protocol Driver | Modbus register map など、bus 上の wire/register protocol | power sequencing、灌水判断、MQTT、sleep scheduling |
| Hub | device orchestration、UI、config distribution、persistence、cloud integration | firmware GPIO/pin behavior |

## HAL ルール

- HAL module 名は H/W primitive または具体的な peripheral を表す。製品名や `device_kind` を表さない。
- 同じ H/W primitive が複数 device に出る可能性がある場合は、共通 HAL を優先する。
- device 固有 HAL を作ってよいのは、特定 camera wiring、基板固有 ADC 回路、sensor の電気的挙動など、その device 固有の実 H/W primitive がある場合だけである。
- 既存 HAL に委譲するだけ、または pin 名を言い換えるだけの `hal_<device_kind>` wrapper は作らない。
- HAL に MQTT topic、status JSON field、runtime config parsing、schedule decision、作物・製品 policy を入れない。
- pin selection は `platformio.ini`、device App の小さな constant block、または focused pin map helper に置く。pin selection だけでは新しい HAL layer を作る理由にならない。
- H/W だけの variant は pin map、build flag、BOM、配線 profile に置く。同じ挙動と status/config payload を持つなら、新しい firmware project や `device_kind` は作らない。

## App ルール

- device App は orchestration を持つ。いつ sensor 電源を入れるか、いつ読むか、いつ灌水するか、いつ止めるか、どの status を publish するかを判断する。
- 複数の共通 HAL を組み合わせる処理が製品挙動を表す場合、device App から共通 HAL を直接使ってよい。
- timed irrigation behavior は App behavior である。再利用可能な timed output primitive として一般化する場合だけ、共通 HAL に切り出す。
- device App は HAL/protocol header に依存してよい。ただし HAL/protocol module は device App header を include してはいけない。

## RS485 ルール

RS485 は 3 層に分ける。

1. `hal_rs485_modbus`: UART、DE/RE 制御、Modbus frame send/receive、CRC、response timeout。
2. `hal_rs485_bus`: register read/write 形式で見せる H/W bus boundary。
3. `hal_rs485_sensor_protocol`: sensor-specific register map と unit conversion。

device App は、どの sensor を有効化するか、sensor rail に電源を入れるか、どの protocol driver を呼ぶか、未接続 sensor を `*_ok=false` として扱うかを判断する。

新しい RS485 sensor を追加する場合、通常は protocol driver を追加または拡張する。新しい device HAL wrapper は作らない。

## MOSFET / 電源ルール

- MOSFET で切り替える power rail または simple on/off output は `hal_power_switch` を使う。
- 灌水1系、灌水2系、12V sensor power のように独立出力が複数ある場合は、複数の `hal_power_switch_t` instance を使う。
- 出力が pump、valve、solenoid、relay のどれに接続されるかは device App config とドキュメントの責務である。HAL は電気的な出力を ON/OFF するだけでよい。
- 「点滴ライン A」「RS485センサー電源」のような営農者向け表示名や制御対象メモは、`mosfet_switches` などの hub / device App runtime config metadata に置く。`hal_power_switch` に name や role を持たせない。
- 再利用可能な timed multi-channel output primitive が必要になった場合は、device-kind 固有 HAL ではなく generic common HAL として実装する。

## WRS への適用

`WRS` は次を使う。

- 灌水1系、灌水2系、12V sensor power は `hal_power_switch` instance。
- RS485 H/W boundary は `hal_rs485_bus`。
- soil/PAR sensor register map は `hal_rs485_sensor_protocol`。
- 灌水 policy、schedule handling、sensor power sequencing、MQTT status field は `app_wrs_runtime_config` と `app.cpp`。

WRS が既存 HAL で表現できない具体的な H/W primitive を持つまでは、`hal_wrs` wrapper を定義しない。

## WTR H/W profile

`WTR` は複数の H/W profile を持ってよい。12V pump/valve build と、小型低電圧または battery 補助の水やり build は、local irrigation output、local soil moisture feedback、WTR status/config semantics を保つ限り同じ WTR である。

H/W profile の差は pin assignment、端子 label、BOM、製造要領で表現する。installer が pump、valve、relay、低電圧 driver input のどれを接続しても、switched output は `hal_power_switch` で表現する。

## レビュー時チェックリスト

新しい firmware module を追加する前に、次を確認する。

1. module 名は hardware、protocol、product behavior のどれを表しているか。
2. HAL なら、現在の `device_kind` を知らなくても他 device が再利用できるか。
3. 既存 HAL 呼び出しを包んでいる場合、実 H/W 抽象を追加しているか。製品挙動を束ねているだけではないか。
4. HAL が App header を include したり、runtime config JSON を parse したりしていないか。
5. protocol driver が power rail 制御や製品判断を持っていないか。
6. App orchestration と既存 common HAL の組み合わせで十分ではないか。
