---
title: 更新とバックアップ
description: Hubを安全に更新し、設定・データ・F/Wをバックアップする手順です。
---

通常更新では、既存の `.env`、MQTT、HTTP、Cloudflare設定、Runtime Configを保持します。更新前に状態を保存し、更新後にhealth checkを行います。

## 更新前

```bash
cd hub
bash scripts/migrate_local_files.sh list
bash scripts/migrate_local_files.sh export-zip /tmp/ina-hub-backup.zip --include-work-dir
```

次を記録します。

- 現在のGit commit
- Hub serviceの状態
- `/readyz` の応答
- 接続中デバイス数
- 直近のMQTT error
- F/W targetが設定されたデバイス

## 更新する

リポジトリを更新した後、production flagを付けずにinstallerを再実行します。

```bash
git pull --ff-only
git submodule update --init --recursive
cd hub
sudo ./scripts/install_service.sh
```

installerは既存設定を検査し、backup、unit更新、Hub再起動、`/readyz`確認を行います。

## 更新後

```bash
systemctl status inas-device-hub@main
curl --fail http://127.0.0.1:39151/readyz
./scripts/hub_service.sh logs
```

画面から圃場、登録デバイス、Runtime Configが保持されていることも確認します。

## バックアップから戻す

復元先と内容を確認してから実行します。`--overwrite` は既存ファイルを置き換えるため、先に別のbackupを取ってください。

```bash
bash scripts/migrate_local_files.sh import-zip \
  /tmp/ina-hub-backup.zip \
  --include-work-dir \
  --overwrite
```

復元後はHubを再起動し、`/readyz` とデバイス接続を確認します。

:::tip[バックアップの保管]
backup archiveはHub本体とは別のstorageへ保存し、権限を制限します。`.env`やtokenが含まれる可能性があるため、公開bucketへ置きません。
:::
