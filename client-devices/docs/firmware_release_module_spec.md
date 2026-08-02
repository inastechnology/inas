# INAS Firmware Release Module

## 目的

Shipping ToolとデバイスF/Wを分離して配布するためのZIP形式です。Shipping Tool
本体に特定デバイスのF/Wを埋め込まず、各F/Wプロジェクトが独立したRelease
moduleを生成します。

対象プロジェクト:

- `rs485-debug-device`
- `environment-sensor-device`
- `soil-sensor-device`
- `watering-device`
- `watering-rs485-device`
- `fertigation-device`

各プロジェクトで次を実行します。

```bash
make package
```

## ZIP構成

```text
<module-name>/
├── release-module.json
├── SHA256SUMS.txt
├── bootloader.bin
├── partitions.bin
├── boot_app0.bin
├── firmware.bin
├── littlefs.bin              # LittleFSを使用するF/Wのみ
└── diagnostic-profile.json   # 診断定義がある場合
```

`release-module.json`は次を保持します。

- schemaとmodule type
- module ID、device kind、表示名
- F/W version、target、chip、flash size
- 各BINの書込みアドレス、最大サイズ、初期選択状態
- 各ファイルのSHA-256
- 診断プロファイルのID

## 標準配置

| ファイル | アドレス | Release module読込み時 |
|---|---:|---|
| `bootloader.bin` | `0x0` | ON |
| `partitions.bin` | `0x8000` | ON |
| `boot_app0.bin` | `0xE000` | ON |
| `firmware.bin` | `0x10000` | ON |
| `littlefs.bin` | `0x670000` | OFF |

LittleFSにはWi-Fi、MQTT、個体設定が存在する可能性があるため、ZIPへ含まれていても
初期選択はOFFです。工場出荷時に初期化する場合だけ、Shipping Tool上で明示的に
ONにします。

## Shipping Toolでの検証

Shipping Toolは書込み前に以下を検証します。

- ZIP内に`release-module.json`が1つだけ存在すること
- module schemaとmodule typeが対応形式であること
- manifestで参照されたファイルが存在すること
- 全ファイルのSHA-256がmanifestと一致すること
- ファイルサイズが書込み領域の最大サイズ以下であること
- 書込み領域が重複していないこと
- ZIP path traversal、シンボリックリンク、過大なファイルを含まないこと

Release moduleの生成処理は
`client-devices/common/tools/create_release_module.py`へ共通化されています。新しい
ESP32-S3 F/Wプロジェクトは
`client-devices/common/make/esp32s3-release-module.mk`をincludeしてください。
