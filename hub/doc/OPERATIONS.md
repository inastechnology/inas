# 運用ガイド — ina-device-hub

短い説明

この文書は `ina-device-hub` を本番または現場デバイスで運用するための手順と運用上の注意をまとめたものです。インストール手順や systemd 管理、ログ/監視、バックアップ、トラブルシュート、更新手順を含みます。

対象読者
r
- デバイス運用者、SRE、現場エンジニア

前提

- Linux（systemd）環境
- sudo 権限
- リポジトリがデバイス上にクローン済みであること（またはインストールスクリプトをリポジトリから実行できること）

目次

- クイックデプロイ
- systemd 管理
- 環境変数とシークレット管理
- DB とストレージのバックアップ
- ログと監視
- トラブルシュート（よくある原因と対処）
- 更新とロールバック
- 定期メンテナンス

クイックデプロイ

1. 依存を同期

```bash
rye sync
```

2. 環境ファイルを配置（リポジトリに ` .default.env` があればコピー）

```bash
cp .default.env .env
# 必要に応じて編集
```

3. systemd のインストールスクリプトでデプロイ（sudo）

```bash
sudo ./scripts/install_service.sh
```

オプションで `--user` / `--target-dir` を指定できます。スクリプトは `systemd/inas-device-hub@.service` をインストールし、`frontend` と `backend` インスタンスを有効化・起動します。

systemd 管理

主要コマンド

```bash
# ステータス確認
systemctl status inas-device-hub@frontend
systemctl status inas-device-hub@backend

# ログ確認（フォロー）
journalctl -u inas-device-hub@frontend -f
journalctl -u inas-device-hub@backend -f

# 再起動 / 再読み込み
sudo systemctl restart inas-device-hub@frontend
sudo systemctl restart inas-device-hub@backend
sudo systemctl daemon-reload
```

テンプレート変更時

1. `/etc/systemd/system/inas-device-hub@.service` を編集
2. `sudo systemctl daemon-reload`
3. `sudo systemctl restart inas-device-hub@frontend`（必要に応じて backend も）

環境変数とシークレット管理

- 機密情報は `./.env` に保存します。ファイルパーミッションは最低でも `600` にしてください。

```bash
chmod 600 /path/to/ina-device-hub/.env
```

- 必須キー（抜粋、詳細は `src/ina_device_hub/setting.py` を参照）:
  - `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
  - `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_BUCKET_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
  - `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD`
  - `TIMELAPSE_INTERVAL`

- 本番では Vault（HashiCorp / cloud provider KMS）や AWS Secrets Manager 等により配布し、デバイス側で `.env` を生成する運用が推奨されます。

DB とストレージのバックアップ

ローカル DB

- アプリは `WORK_DIR`（デフォルト `~/.ina-device-hub`）下に `ina.db` を置いている可能性があります（`setting.py` を確認）。簡易バックアップ:

```bash
# stop service
sudo systemctl stop inas-device-hub@frontend inas-device-hub@backend

# copy database
cp ~/.ina-device-hub/ina.db /var/backups/ina-device-hub/ina.db.$(date +%F-%T)

# restart
sudo systemctl start inas-device-hub@frontend inas-device-hub@backend
```

※ Turso（リモート）を利用している場合は Turso の CLI/エクスポート機能を使用してください。

オブジェクトストレージ（S3 互換）

- バケットのバージョニングを有効にし、重要データは定期的に別のロケーションへコピーしてください。例: `aws s3 sync` 互換ツールで定期バックアップ。

ログと監視

- systemd ジャーナルを基本とし、外部監視を追加することを推奨します（Prometheus node_exporter + alertmanager など）。
- ログローテーション: 大量の画像やメディアを扱う場合、ローカル保存領域が肥大化します。`logrotate` ではなく、メディア保存ディレクトリを定期に古いファイルから削除するジョブを用意してください。

例: 30 日より古い画像を削除する cron スクリプト

```bash
# /usr/local/bin/inas-cleanup.sh
find /path/to/storage -type f -mtime +30 -delete

# crontab (root またはサービス実行ユーザー)
0 3 * * * /usr/local/bin/inas-cleanup.sh
```

トラブルシュート（よくある原因と対処）

- サービスが起動しない
  - `journalctl -u inas-device-hub@frontend -b` を確認。多くは `.env` の未設定やパーミッション、`serve.sh` の実行権限不足。
  - `sudo chmod +x /path/to/ina-device-hub/serve.sh` を確認。

- MQTT 接続できない
  - ブローカー情報（URL/PORT/ユーザー/パスワード）を `.env` で確認。
  - ネットワーク（ファイアウォール、DNS）が ブローカーへ到達できるか `nc` / `telnet` で確認。

- ストレージへアップロード失敗
  - S3 エンドポイント・認証情報を確認。バケット名やリージョンが正しいかも確認。

- DB エラー
  - ローカル DB ファイルのロックや破損。バックアップから復元して起動確認。

更新とロールバック

更新手順（簡易）

1. リポジトリを pull するか、管理サーバから最新ファイルを rsync する

```bash
cd /path/to/ina-device-hub
git pull origin master
# or from central server: rsync -a ...
```

2. 必要なら依存を再同期

```bash
rye sync
```

3. systemd インストールを再実行（ユニット差分を反映）

```bash
sudo ./scripts/install_service.sh --target-dir /path/to/ina-device-hub
```

4. サービス再起動

```bash
sudo systemctl restart inas-device-hub@frontend inas-device-hub@backend
```

ロールバック

- 新バージョン適用前に必ず DB と重要ファイルのバックアップを取得してください（上記参照）。問題があればバックアップを戻し、以前のリリースタグに戻してサービスを再起動します。

定期メンテナンス項目

- ディスク使用量チェック（`df -h`）
- ローカルストレージの古いファイル削除
- セキュリティアップデート適用（OS レベル）
- 依存ライブラリの定期更新（テストを経て適用）

セキュリティの注意

- `.env` を公開リポジトリへ入れない。Secrets をコミットしないこと。
- サービス実行ユーザーは最小権限にする。
- S3 認証キーは必要最小限の権限にする（書き込み対象バケットに限定）。

最後に

このガイドは基本的な運用をカバーします。運用環境（ネットワーク、クラウドプロバイダ、監視基盤）に合わせて手順を調整してください。追加したい手順や自動化（Ansible/Cloud-init / Mender など）を伝えていただければ、具体的なプレイブックやスクリプトを作成します。
