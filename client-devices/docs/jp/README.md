# Client Devices

Device firmware project は device type ごとに分かれている。

全体仕様は [../../../docs/jp/SYSTEM_SPECIFICATION.md](../../../docs/jp/SYSTEM_SPECIFICATION.md) を参照する。
XIAO ESP32S3 の device 別 pin assignment は [pin_assignments.md](pin_assignments.md) にある。

```text
client-devices/
  common/lib/ina-client-common/
  watering-device/              # WTR
  watering-rs485-device/        # WRS
  soil-sensor-device/           # SOI
  environment-sensor-device/    # ENV
```

## Layering Policy

- `common/lib/ina-client-common`: shared client firmware library。
- `<device>/src/app`: device 固有の `AppDevice` subclass、runtime config、product behavior。
- `<device>/src/hal`: sensor、actuator、pin、audio、camera などの device 固有 HAL。
- `<device>/platformio.ini`: board、build flags、device kind code、local dependencies。

共通 library には boot/wake lifecycle、Wi-Fi/MQTT setup、setup AP、OTA、config persistence、time sync など複数 device で再利用できる処理を置く。

device project には watering logic、sensor sampling、pin mapping、runtime configuration schema など product ごとに変わる処理を置く。

## Adding A Device

1. `client-devices/<device-name>/` を作成する。
2. device 固有の `src/app`、`src/hal`、`platformio.ini`、`Makefile` を追加する。
3. concrete `AppDevice` subclass を実装する。
4. shared library を device の `lib/` へ link する。
5. `platformio.ini` に 3 文字 uppercase の device kind code を割り当てる。
6. device directory で build と検証を行う。

## Development Environment

Linux または WSL2 を使う。Native Windows build は symbolic link の扱いが不安定なためサポートしない。

## 配線・製造ドキュメント

- [ESP32S3 配線表](esp32s3_wiring_tables.md)
- [製造要領書](manufacturing_procedure.md)
- [配線要領書](wiring_procedure.md)
- [設置要領書](installation_procedure.md)
- [運用手引き](operation_guide.md)

## 仕様

- [Client firmware レイヤ分離ポリシー](firmware_layering_policy.md)
- [XIAO ESP32S3 pin assignments](pin_assignments.md)
- [RS485 sensor device specification](rs485_sensor_device_spec.md)
- [RS485 sensor device implementation plan](rs485_sensor_device_implementation_plan.md)

## 生成図

XIAO ESP32S3 の pin assignment SVG は
[generate_xiao_pin_assignment_diagrams.py](../generate_xiao_pin_assignment_diagrams.py)
から生成する。生成済み SVG や draw.io を直接編集しない。
