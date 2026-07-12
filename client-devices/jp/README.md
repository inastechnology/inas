# Client Devices

Device firmware project は device type ごとに分かれています。

全体仕様は [../../docs/jp/SYSTEM_SPECIFICATION.md](../../docs/jp/SYSTEM_SPECIFICATION.md) を参照してください。XIAO ESP32S3 の device 別 pin assignment は [../docs/jp/pin_assignments.md](../docs/jp/pin_assignments.md) にあります。

```text
client-devices/
  common/lib/ina-client-common/
  watering-device/
```

## Layering Policy

- `common/lib/ina-client-common`: shared client firmware library。
- `<device>/src/app`: device 固有の `AppDevice` subclass、runtime config、product behavior。
- `<device>/src/hal`: sensor、actuator、pin、audio、camera などの device 固有 HAL。
- `<device>/platformio.ini`: board、build flags、device kind code、local dependencies。

共通 library には boot/wake lifecycle、Wi-Fi/MQTT setup、setup AP、OTA、config persistence、time sync など複数 device で再利用できる処理を置きます。

device project には watering logic、sensor sampling、pin mapping、runtime configuration schema など product ごとに変わる処理を置きます。

## Adding A Device

1. `client-devices/<device-name>/` を作成します。
2. device 固有の `src/app`、`src/hal`、`platformio.ini`、`Makefile` を追加します。
3. concrete `AppDevice` subclass を実装します。
4. shared library を device の `lib/` へ link します。
5. `platformio.ini` に 3 文字 uppercase の device kind code を割り当てます。
6. device directory で build と検証を行います。

## Development Environment

Linux または WSL2 を使ってください。Native Windows build は symbolic link の扱いが不安定なためサポートしません。
