# INAS Documentation

このディレクトリは、INAS の hub services と client device firmware を横断する日本語ドキュメントを置く。

英語版の入口は [../../README.md](../../README.md)。
日本語 Markdown は root 直下の `jp/` ではなく、`docs/jp/`、`hub/doc/jp/`、`client-devices/docs/jp/` のように doc/docs 配下へ置く。
記載ルールは [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md) にまとめている。

## 最初に読む文書

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md): INAS 全体仕様。hub、Cloudflare、デバイス種別、圃場データ、OTA の関係をまとめる。
- [ARCHITECTURE_LAYERING_POLICY.md](ARCHITECTURE_LAYERING_POLICY.md): hub、firmware、contract、storage、UI、adapter の全体レイヤ境界。
- [DEVICE_DEFINITION_SPECIFICATION.md](DEVICE_DEFINITION_SPECIFICATION.md): 各ファームウェアが Hub へ伝えるデバイスの決まり事、定義駆動 UI、Runtime Config、既存 DB との互換方針。
- [CULTIVATION_SYSTEM_ORCHESTRATION.md](CULTIVATION_SYSTEM_ORCHESTRATION.md): イチゴ点滴栽培のような作物別システムを、複数デバイスと hub のオーケストレーションとして扱う設計方針。
- [../../hub/doc/jp/README.md](../../hub/doc/jp/README.md): hub の日本語ドキュメント入口。
- [../../client-devices/docs/jp/README.md](../../client-devices/docs/jp/README.md): client device firmware と配線・製造ドキュメントの日本語入口。

## Client Device Layout

client firmware project は `client-devices/` 配下にある。

```text
client-devices/
  common/
    lib/
      ina-client-common/      # Shared PlatformIO library
  watering-device/            # Watering device firmware, device kind: WTR
  watering-rs485-device/      # RS485 watering device firmware, device kind: WRS
  fertigation-device/         # 液肥作成・潅水 device firmware, device kind: FGT
  soil-sensor-device/         # Soil sensor device firmware, device kind: SOI
  environment-sensor-device/  # Environment sensor device firmware, device kind: ENV
```

各 device project は、sensor、actuator、pin、schedule、top-level flow など device 固有の App layer を持つ。
共通 firmware code は `client-devices/common/lib` に置き、各 device project の `lib/` から symbolic link で参照する。

## Linux / WSL2 Requirement

Client firmware は PlatformIO local library の symbolic link を使う。Linux または WSL2 で build する。
Native Windows build はサポートしない。

```bash
cd client-devices/watering-device
cp default.env.user.ini .env.user.ini
make build
```

## 図

- [../assets/inas_system_diagrams.drawio](../assets/inas_system_diagrams.drawio): 全体構成、データ/制御フロー、デバイス配置、OTA の draw.io 編集元。

図を更新する場合は、SVG や draw.io を直接編集せず、次のコマンドで再生成する。

```sh
python3 docs/assets/generate_system_diagrams.py
```
