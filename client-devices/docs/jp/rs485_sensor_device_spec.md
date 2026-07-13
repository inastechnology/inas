# RS485 Sensor Device Specification

## 目的

INAS のセンサー系デバイスを、測定専用デバイスとして `WTR` から分離する。土壌水分だけを低消費電力で測るデバイスは `SOI`、12V 電源が必要な RS485 センサー群は `ENV` とし、各 `device_kind` ごとに接続センサー、ピン割当、MQTT payload を固定する。WTR と同じ責務を持つ低電圧水やり build は WTR の H/W profile であり、別の sensor device kind ではない。

`capabilities` による可変構成は採用しない。デバイスの機能が変わる場合は、別プロジェクトと別 `device_kind` を作成する。

XIAO ESP32S3 のピン割当図は [pin_assignments.md](pin_assignments.md) を参照する。

## デバイス種別

| device_kind | プロジェクト                | 役割                                         |
| ----------- | --------------------------- | -------------------------------------------- |
| `SOI`       | `soil-sensor-device`        | 18650 バッテリー前提で土壌水分センサーを読む |
| `ENV`       | `environment-sensor-device` | 12V 電源前提で RS485 Modbus センサーを読む   |
| `WTR`       | `watering-device`           | 小規模向け統合水やり機                       |
| `WRS`       | `watering-rs485-device`     | RS485 前提の統合水やり機                     |

## SOI ハードウェア前提

`SOI` は土壌に複数設置する低消費電力ノードとする。現状は土壌水分センサーのみを接続対象にし、RS485 センサーや 12V センサーは接続しない。

| 信号                 | XIAO ピン | 用途                 |
| -------------------- | --------- | -------------------- |
| Soil moisture analog | `A0`      | 土壌水分センサー ADC |

土壌水分センサーは起床時だけ測定し、測定後は deep sleep に戻る。土壌水分のキャリブレーションは初回設置時に Hub からユーザ主導で行う。firmware build flag は未校正時の初期値としてだけ使う。

初期値:

- dry raw: `3200`
- wet raw: `1500`
- sample count: `20`
- sample interval: `40 ms`

## SOI 土壌水分キャリブレーション

SOI は runtime config の `soil_calibration` で校正状態を受け取る。Hub UI では日本語の操作として表示し、通常運用では変数名を利用者に見せない。

キャリブレーションモード:

| mode          | 用途                                |
| ------------- | ----------------------------------- |
| `normal`      | 通常測定                            |
| `capture_dry` | 現在の raw 値を乾いた状態として記録 |
| `capture_wet` | 現在の raw 値を湿った状態として記録 |
| `reset`       | 未校正状態に戻す                    |

初回設置手順:

1. センサーを乾いた基準状態に置き、Hub から「乾いた状態を記録」を送る。
2. 次回起床時、SOI は ADC 平均値を `dry_raw` として保存する。
3. センサーを湿った基準状態に置き、Hub から「湿った状態を記録」を送る。
4. 次回起床時、SOI は ADC 平均値を `wet_raw` として保存する。
5. `dry_raw - wet_raw >= min_delta_raw` を満たしたら `calibrated=true` になり、以後は校正済みの値で percent を算出する。

手動設定も許可する。Hub から `dry_raw`、`wet_raw`、`calibrated` を直接設定でき、センサーや現地環境に合わせて `sample_count` と `sample_interval_ms` を調整できる。`request_id` は同じ記録要求を重複処理しないために使う。`normal` 以外の校正モードでは `request_id` を必須にする。

SOI status payload:

```json
{
  "device_kind": "SOI",
  "sensor_model": "Analog-Soil-Moisture",
  "soil_moisture_ok": true,
  "soil_moisture_percent": 42,
  "raw_soil_moisture": 2486,
  "soil_calibration_required": false,
  "soil_calibration_calibrated": true,
  "soil_calibration_mode": "normal",
  "soil_calibration_dry_raw": 3200,
  "soil_calibration_wet_raw": 1500,
  "soil_calibration_sample_count": 20,
  "soil_calibration_sample_interval_ms": 40
}
```

## ENV ハードウェア前提

対象ボードは当面 `seeed_xiao_esp32s3` とする。RS485 は ESP32-S3 の UART を RS485 トランシーバに接続して使用する。

| 信号        | XIAO ピン |     GPIO | 用途           |
| ----------- | --------: | -------: | -------------- |
| RS485 TX    |      `D6` | `GPIO43` | UART TX        |
| RS485 RX    |      `D7` | `GPIO44` | UART RX        |
| RS485 DE/RE |      `D4` |  `GPIO5` | 送受信方向制御 |

RS485 トランシーバは 3.3V ロジック対応品を使う。例: MAX3485, SP3485, SN65HVD 系。

`ENV` は 12V 電源を前提にする。PAR センサー、日射センサー、EC/pH/NPK など、センサー本体に 12V が必要なものは `ENV` 側に接続する。

## ENV soil RS485 センサー仕様

想定センサーは TH-EC-PH-NPK 系の 7in1 RS485 Modbus 土壌センサー。

測定対象:

- 土壌水分
- 土壌温度
- EC
- pH
- 窒素 N
- リン P
- カリウム K

初期実装の仮 register map:

| offset | payload field           |                scale |
| -----: | ----------------------- | -------------------: |
|      0 | `soil_moisture_percent` |        register / 10 |
|      1 | `soil_temperature_c`    | signed register / 10 |
|      2 | `soil_ec_us_cm`         |             register |
|      3 | `soil_ph`               |        register / 10 |
|      4 | `soil_n_mg_kg`          |             register |
|      5 | `soil_p_mg_kg`          |             register |
|      6 | `soil_k_mg_kg`          |             register |

この register map は製品マニュアル確認前の仮定である。実機導入時に、センサー付属の Modbus register table に合わせて `platformio.ini` と firmware の変換処理を調整する。

ComWinTop 系の公開サンプルでは、水分・温度・EC は `baud=4800`, slave `0x01`, function code `0x04`, register `0x0000` から `U_WORD` で読んでいる。ただし pH/NPK register は別途マニュアル確認が必要。

ENV soil RS485 status payload:

```json
{
  "device_kind": "ENV",
  "sensor_model": "RS485-12V-ENV",
  "soil_rs485_enabled": true,
  "soil_rs485_ok": true,
  "soil_rs485_modbus_slave_id": 2,
  "soil_moisture_percent": 42.1,
  "soil_temperature_c": 21.5,
  "soil_ec_us_cm": 820,
  "soil_ph": 6.5,
  "soil_n_mg_kg": 34,
  "soil_p_mg_kg": 18,
  "soil_k_mg_kg": 102
}
```

## ENV キャリブレーション

ENV は runtime config の `env_sensors` と `env_calibration` を受け取る。`env_sensors` は RS485 の slave id、function code、register を指定し、`env_calibration` は測定項目ごとの `scale`、`offset`、`calibrated` を保持する。

キャリブレーションモード:

| mode                | 用途                                       |
| ------------------- | ------------------------------------------ |
| `normal`            | 通常測定                                   |
| `capture_reference` | 現在値を基準値に合わせるよう offset を保存 |
| `reset`             | 未校正状態に戻す                           |

初回設置手順:

1. PAR、EC、pH などの校正対象を選ぶ。
2. 既知の基準値を Hub に入力する。例: pH 標準液、EC 標準液、別測定器で確認した光量。
3. `capture_reference` を送る。
4. 次回起床時、ENV は現在測定値と基準値の差を offset として保存する。
5. 必要であれば詳細設定で `scale` と `offset` を手動調整する。

この方式は一点補正である。pH や EC の厳密な二点校正、センサー本体の Modbus 校正コマンドが必要な場合は、製品マニュアル確認後に専用 mode を追加する。

## ENV light センサー仕様

想定センサーは 0-2500 umol/m2/s 範囲の太陽活性放射線センサーで、RS485 Modbus 接続とする。

初期実装の仮 register map:

| register | payload field   |                          scale |
| -------: | --------------- | -----------------------------: |
|        0 | `par_umol_m2_s` | register * `APP_ENV_PAR_SCALE` |

ENV status payload:

```json
{
  "device_kind": "ENV",
  "sensor_model": "RS485-12V-ENV",
  "par_enabled": true,
  "par_ok": true,
  "par_modbus_slave_id": 1,
  "par_umol_m2_s": 1234.0
}
```

## WRS ハードウェア前提

`WRS` は RS485 前提の水やり全部入りデバイスである。WTR と同じく灌水出力をローカルに持つが、土壌水分の主フィードバックをアナログ ADC ではなく RS485 bus 上のセンサーに置く。

初期 pin assignment は WTR と同じ灌水出力・RS485 配線を使い、筐体や配線を流用できるようにする。

| 信号 | XIAO ピン | GPIO | 用途 |
|---|---:|---:|---|
| 灌水1系 MOSFET | `D2` | `GPIO3` | 灌水系統 1 |
| 灌水2系 MOSFET | `D3` | `GPIO4` | 灌水系統 2 |
| RS485 DE/RE | `D4` | `GPIO5` | 送受信方向制御 |
| RS485 TX | `D6` | `GPIO43` | UART TX |
| RS485 RX | `D7` | `GPIO44` | UART RX |
| 12V sensor power MOSFET | `D8` | `GPIO7` | RS485 センサーへ向かう 12V 分岐のみを切り替える |

アナログ土壌水分 ADC pin は未使用、または診断用に予約してよい。センサーを増やすたびに pin assignment を増やさない。センサーは RS485 bus に追加し、Modbus slave id を重複させず、未接続センサーは timeout、CRC error、無応答を `*_ok=false` として報告する。

初期 WRS センサー群:

- RS485 PAR センサー: `par_umol_m2_s`
- RS485 土壌センサー: 土壌水分、地温、EC、pH、N/P/K
- 任意の RS485 日射センサー: `solar_radiation_w_m2`

WRS status は ENV/WTR と同じ metric 名を使い、hub が別 schema を持たずに縦持ち保存できるようにする。

```json
{
  "device_kind": "WRS",
  "sensor_model": "RS485-WATERING-AIO",
  "watering_due": true,
  "watering_started": true,
  "soil_rs485_ok": true,
  "soil_moisture_percent": 42.1,
  "soil_temperature_c": 21.5,
  "soil_ec_us_cm": 820,
  "soil_ph": 6.5,
  "par_ok": true,
  "par_umol_m2_s": 1234.0
}
```

## 測定値 DB 定義

ENV/SOI/WTR/WRS の測定値は、固定カラムだけに押し込まず、測定項目定義と時系列測定値を縦持ちで保存する。

`sensor_measurement_definitions`:

- `metric`: `soil_ec_us_cm` などの測定項目 ID
- `display_name`: UI 表示名
- `unit`: 単位
- `category`: `soil` / `light`
- `device_kinds`: 対応 device_kind の JSON
- `value_type`: `float` など

`sensor_measurements`:

- `device_id`
- `device_kind`
- `measured_at`
- `metric`
- `value`
- `unit`
- `quality`
- `raw_value`
- `source`
- `payload`

初期定義には、土壌水分、地温、EC、pH、N/P/K、PAR、将来の日射量を含める。SOI は analog `soil_moisture_percent` を提供する。WRS は ENV と同じ RS485 土壌・光量系 metric を持ち、さらに灌水 action field を持つ。

## OTA

SOI、ENV、WTR、WRS は firmware binary へ `INAS_FW_MANIFEST_V1` を埋め込む。生成後は必ず `make check-firmware` で Hub upload 用 manifest を検査する。

## 運用ルール

- `device_kind` ごとに接続センサーと payload schema を固定する。
- センサー型番や register map が大きく変わる場合は、新しい device project を作る。
- Hub 側では `device_kind` で UI と status parser を切り替える。
- 灌水出力と RS485 土壌/PAR/日射センサーを一つの強い全部入りデバイスにまとめる場合は `WRS` を使う。
- 土壌フィードバックと小型低電圧 output を 1 台に持たせ、WTR と同じ挙動を保つ場合は WTR の H/W profile として扱う。
- `SOI` は土壌水分のみを扱う。12V が必要な土壌 EC/pH/NPK センサーは `ENV` 側で扱う。
- `par_ok=false` / `soil_rs485_ok=false` の status は、センサー未接続、配線不良、レジスタ不一致、CRC エラー、タイムアウトを示す。
