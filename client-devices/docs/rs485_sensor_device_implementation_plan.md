# RS485 Sensor Device Implementation Plan

## 方針

`SOI` と `ENV` は測定専用デバイスとして実装する。ただし電源要件が異なるため、`SOI` は 18650 バッテリー前提の土壌水分専用、`ENV` は 12V 電源前提の RS485 センサーハブとして分ける。

RS485 Modbus RTU の低レベル処理は共通ライブラリに置き、`ENV` は register map と status payload だけを持つ。`SOI` は現状の接続制約に合わせて ADC 土壌水分センサーのみを読む。

## 実装ステップ

1. 新規デバイス scaffold
   - `client-devices/scripts/create_device_project.py` で `soil-sensor-device` / `SOI` を生成する。
   - 同じく `environment-sensor-device` / `ENV` を生成する。

2. SOI firmware
   - 起床時に `A0` の土壌水分センサーを読む。
   - raw ADC 値を dry/wet キャリブレーションで 0-100% に変換する。
   - `soil_calibration.mode` で `capture_dry` / `capture_wet` / `reset` を受け取り、ユーザ主導の初回キャリブレーションを行う。
   - `dry_raw`、`wet_raw`、`min_delta_raw`、`sample_count`、`sample_interval_ms` は runtime config で調整できるようにする。
   - キャリブレーション値は LittleFS に保存し、deep sleep 後も保持する。
   - 初期 sleep interval は 900 秒。

3. RS485/Modbus 共通 HAL
   - `hal_rs485_modbus_init()` で UART と DE/RE ピンを初期化する。
   - `hal_rs485_modbus_read_registers()` で Modbus function `0x03` / `0x04` を読む。
   - CRC16、slave id、function code、byte count を検証する。
   - timeout や CRC 不一致は `false` で返し、status payload では `par_ok=false` / `soil_rs485_ok=false` にする。

4. ENV firmware
   - 起床時に PAR register を読む。
   - 12V が必要な EC/pH/NPK 土壌センサーは `APP_ENV_SOIL_RS485_ENABLED=1` の時だけ読む。
   - `par_umol_m2_s`、soil RS485 values、raw register を MQTT status に含める。
   - `env_sensors` で PAR/土壌 RS485 の slave id、function、register を変更できるようにする。
   - `env_calibration` で測定項目ごとの `scale`、`offset`、`calibrated` を保持する。
   - `capture_reference` では既知の基準値と現在値の差を offset として LittleFS に保存する。
   - 初期 sleep interval は 300 秒。

5. DB / Hub
   - `sensor_measurement_definitions` に測定項目、表示名、単位、対応 device_kind を定義する。
   - `sensor_measurements` に ENV/SOI/WTR の測定値を縦持ちで保存する。
   - ENV status 受信時に `par_umol_m2_s`、土壌水分、地温、EC、pH、N/P/K を測定値へ正規化する。
   - DB 書き込みに失敗しても MQTT status 記録は継続する。

6. ビルド検証
   - `make build`
   - `make check-firmware`

## 未確定事項

現時点でセンサーの正式な Modbus register table がないため、register map は仮実装である。実機マニュアル入手後、以下を確認する。

- slave id 初期値
- baud rate
- parity / stop bits
- function code (`0x03` or `0x04`)
- register address
- scale
- signed / unsigned
- 16-bit / 32-bit
- NPK の単位
- PAR センサーの単位と scale

## 変更しやすい箇所

SOI `platformio.ini` の build flags は未校正時の初期値:

```ini
-D APP_SOI_MOISTURE_PIN=A0
-D APP_SOI_MOISTURE_DRY_RAW=3200
-D APP_SOI_MOISTURE_WET_RAW=1500
-D APP_SOI_MOISTURE_SAMPLE_COUNT=20
-D APP_SOI_MOISTURE_SAMPLE_INTERVAL_MS=40
```

運用中の SOI キャリブレーション値は Hub の runtime config で更新する:

```json
{
  "soil_calibration": {
    "mode": "capture_dry",
    "request_id": "cal-20260712-001",
    "calibrated": false,
    "dry_raw": 3200,
    "wet_raw": 1500,
    "min_delta_raw": 80,
    "sample_count": 20,
    "sample_interval_ms": 40
  }
}
```

Hub UI では「通常」「乾いた状態を記録」「湿った状態を記録」「未校正に戻す」として表示する。詳細設定では手動の乾燥値・湿潤値・測定回数・測定間隔を編集できる。
`normal` 以外の mode は一回限りのコマンドとして扱い、Hub は保存時に `request_id` を付与する。SOI は同じ `request_id` を二重処理せず、処理後はローカル設定を `normal` に戻す。

ENV build flags は未受信時の初期値:

```ini
-D APP_RS485_UART_NUM=1
-D APP_RS485_TX_PIN=43
-D APP_RS485_RX_PIN=44
-D APP_RS485_DE_PIN=5
-D APP_RS485_BAUD=4800
-D APP_ENV_PAR_ENABLED=1
-D APP_ENV_PAR_MODBUS_SLAVE_ID=1
-D APP_ENV_PAR_MODBUS_FUNCTION=3
-D APP_ENV_PAR_REGISTER=0
-D APP_ENV_PAR_SCALE=1.0f
-D APP_ENV_SOIL_RS485_ENABLED=0
-D APP_ENV_SOIL_MODBUS_SLAVE_ID=2
-D APP_ENV_SOIL_MODBUS_FUNCTION=4
-D APP_ENV_SOIL_MODBUS_START_REGISTER=0
```

運用中の ENV 設定は Hub の runtime config で更新する:

```json
{
  "env_sensors": {
    "par": {"enabled": true, "modbus_slave_id": 1, "modbus_function": 3, "register": 0},
    "soil": {"enabled": true, "modbus_slave_id": 2, "modbus_function": 4, "start_register": 0}
  },
  "env_calibration": {
    "mode": "capture_reference",
    "request_id": "env-cal-20260712-001",
    "target": "soil_ph",
    "reference_value": 6.86,
    "soil_ph": {"calibrated": false, "scale": 1.0, "offset": 0.0}
  }
}
```

## リスク

- RS485 トランシーバが 5V 専用の場合、ESP32-S3 の GPIO を破損する可能性がある。
- センサー電源が別系統の場合、GND 共通化が必要。
- 長距離配線では終端抵抗とバイアス抵抗が必要になる場合がある。
- register map がセンサー販売ページと実機ロットで異なる可能性がある。
- ENV の RS485 bus で複数センサーを使う場合、slave id の重複を避ける必要がある。
- SOI の土壌水分 percent は dry/wet raw キャリブレーションに強く依存する。
