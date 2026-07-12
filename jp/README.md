# INAS

このリポジトリは、INAS の hub services と client device firmware を含みます。

## ドキュメント

全体像は [../docs/jp/SYSTEM_SPECIFICATION.md](../docs/jp/SYSTEM_SPECIFICATION.md) から読んでください。hub、Cloudflare、デバイス種別、圃場データ、OTA の関係をまとめています。

英語版の既定ドキュメントは各階層の通常位置に置き、日本語版は同じ階層の `jp/` 配下に置きます。
記載ルールは [../docs/jp/DOCUMENTATION_GUIDE.md](../docs/jp/DOCUMENTATION_GUIDE.md) にまとめています。

## Client Device Layout

client firmware project は `client-devices/` 配下にあります。

```text
client-devices/
  common/
    lib/
      ina-client-common/      # Shared PlatformIO library
  watering-device/            # Watering device firmware, device kind: WTR
```

各 device project は、sensor、actuator、pin、schedule、top-level flow など device 固有の App layer を持ちます。共通 firmware code は `client-devices/common/lib` に置き、各 device project の `lib/` から symbolic link で参照します。

## Linux / WSL2 Requirement

Client firmware は PlatformIO local library の symbolic link を使います。Linux または WSL2 で build してください。Native Windows build はサポートしません。

```bash
cd client-devices/watering-device
cp default.env.user.ini .env.user.ini
make build
```
