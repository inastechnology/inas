---
title: HubをRaspberry Piへインストール
description: 準備済みのRaspberry PiへINAS Hubを導入し、.envを設定してsystemdで常時稼働させます。
---

このページのコマンドは、すべて **Hubとして使うRaspberry Pi上** で実行します。先に[Raspberry Piを準備する](/hub/raspberry-pi/)を完了し、`<hub名>.local`でSSH接続でき、Mosquittoの認証付きpublish/subscribeが成功することを確認してください。

## 1. 外部サービスを用意する

Hubの対話式installerを始める前に、次の接続情報を用意します。

- Turso database URLとauth token
- Cloudflare R2またはS3互換storageのendpoint、bucket、region、access key、secret
- Mosquittoのusername/password
- Hub hostname。例: `farm-a01`
- 作業dataを保存する`WORK_DIR`

Cloudflare Access/TunnelはHubのローカル起動確認後に設定できます。Access用tokenをこの段階で公開資料やshell historyへ貼り付けません。

## 2. リポジトリを取得する

```bash
git clone --recurse-submodules https://github.com/inastechnology/inas.git
cd inas/hub
uv sync --locked
```

既にclone済みでsubmoduleが空の場合は、リポジトリrootで次を実行します。

```bash
git submodule update --init --recursive
```

## 3. `.env`を作成する

```bash
uv run ina-hub install
```

対話式installerで外部接続と保存先を設定します。Mosquittoを同じRaspberry Piで動かす自己調達構成では、次を使います。

| 項目 | 設定値 | 理由 |
|---|---|---|
| `MQTT_BROKER_URL` | `localhost` | Hub processから同じPiのMosquittoへ接続 |
| `MQTT_BROKER_PORT` | `1883` | Mosquitto listener |
| `MQTT_BROKER_USERNAME` | 作成したusername | デバイスと共通のbroker認証 |
| `MQTT_BROKER_PASSWORD` | 作成したpassword | `.env`だけに保存 |
| `HUB_HTTP_HOST` | `0.0.0.0` | LAN内デバイスへF/Wを配信 |
| `HUB_HTTP_PORT` | `39151` | Hub UI/API/F/Wのport |
| `FIRMWARE_HOSTNAME` | Raspberry PiのDHCP予約IP | 現行デバイスがLAN内で確実にF/Wを取得 |
| `HUB_AUTH_MODE` | 初回確認は`local` | Cloudflare設定後にAccess認証へ移行 |

Hub自身が使う`localhost`、管理PCが使う`<hub名>.local`、デバイスへ案内するDHCP予約IPを混同しないでください。必要な変数の詳細は、cloneしたリポジトリ内の`hub/doc/ENVIRONMENT.md`を参照します。

```bash
chmod 600 .env
uv run ina-hub check
```

:::caution[`.env`はこのRaspberry Piだけに置く]
`.env`にはdatabase、storage、MQTT、Cloudflareの秘密情報が入ります。Git、Discord、email、公開スクリーンショットへ含めません。
:::

## 4. foregroundで起動確認する

```bash
uv run python src/ina_device_hub/serve.py
```

同じLANのPCで次を開きます。

```text
http://<hub名>.local:39151
```

Raspberry Pi自身では、healthとreadinessを確認します。

```bash
curl --fail http://127.0.0.1:39151/healthz
curl --fail http://127.0.0.1:39151/readyz
```

`/readyz`はWeb初期化だけでなくMQTT接続も確認します。失敗した場合はsystemdへ登録せず、`.env`とMosquittoの状態を修正します。確認後は`Ctrl+C`でforeground processを停止します。

## 5. systemdで常時稼働させる

リポジトリのinstallerは依存関係と外部接続を確認し、状態をbackupしてからsystemd unitを登録します。現在のclone先をそのまま運用場所にする場合は次を実行します。

```bash
sudo ./scripts/install_service.sh --target-dir "$PWD"
```

状態、自動起動、ログを確認します。

```bash
systemctl is-enabled inas-device-hub@main
systemctl status inas-device-hub@main --no-pager
journalctl -u inas-device-hub@main -f
```

helperも利用できます。

```bash
./scripts/hub_service.sh status
./scripts/hub_service.sh logs
sudo ./scripts/hub_service.sh restart
```

:::caution[`--production`の扱い]
この時点では`--production`を付けません。`--production`はCloudflareの初回構築または明示的な再provision時だけ使います。通常の更新では付けず、既存の`.env`、MQTT、HTTP、Cloudflare設定を保持します。
:::

## 6. 別PCから起動確認する

次をすべて満たすことを確認します。

- `systemctl` が `active (running)` を示す。
- `http://<hub名>.local:39151/readyz` が成功する。
- 管理画面へログインできる。
- ログにMQTTの継続的な認証失敗がない。
- `WORK_DIR`へ書き込める。
- Raspberry Piを再起動してもHubとMosquittoが自動起動する。

```bash
sudo reboot
```

再起動後、別PCからもう一度画面と`readyz`を確認します。

## 主な保存先

HubはRuntime Config、イベント、画像、F/W artifactなどを扱います。保存先は `.env` の `WORK_DIR` とS3互換storage設定で決まります。バックアップ対象は[更新とバックアップ](/hub/update-backup/)で確認してください。

次はHubで最初の圃場を作り、[デバイスを1台作って接続](/devices/)します。LAN内での動作確認が終わったら、利用者自身のCloudflare accountで[Cloudflare Accessを設定](/hub/cloudflare/)します。
