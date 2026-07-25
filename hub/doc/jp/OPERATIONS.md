# 運用ガイド — ina-device-hub

短い説明

この文書は `ina-device-hub` を本番または現場デバイスで運用するための手順と運用上の注意をまとめたものです。インストール手順や systemd 管理、ログ/監視、バックアップ、トラブルシュート、更新手順を含みます。

対象読者

- デバイス運用者、SRE、現場エンジニア

前提

- Linux（systemd）環境
- sudo 権限
- `git`、`uv`、`curl`が本番サーバにインストール済みであること
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

初回デプロイ

1. 依存を同期

```bash
uv sync --locked
```

2. 対話式に環境ファイルを作成し、接続を確認

```bash
uv run ina-hub install
```

3. Local HubのAccess/Tunnelを使う場合は構築し、本番条件を確認

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
uv run ina-hub check --production
```

`check --production` は`.env`権限、HTTP公開条件、Access JWT設定、Turso、
R2、既存MQTT設定を確認する。1項目でも失敗した状態でデプロイしない。

開発PCや確認用PCの`.env`を本番値へ変更して、このチェックを通す運用にはしない。本番値はデプロイ先ホストの`.env`へ構成する。

4. systemdへデプロイ

```bash
sudo ./scripts/install_service.sh --production --enable-cloudflare-tunnel --target-dir "$PWD"
```

`--production`は初回構築またはAccess/Tunnelを明示的に再構成するときだけ使う。
通常の`git pull`更新では付けず、既存`.env`と外部接続設定を維持する。

スクリプトは`uv.lock`どおりの依存同期、Turso/R2/MQTT接続確認、状態バックアップ、unit更新、Hub再起動、`/readyz`確認を順に行う。接続確認までは稼働中プロセスを停止しない。

systemd 管理

主要コマンド

```bash
# ステータス確認
systemctl status inas-device-hub@main
systemctl status inas-cloudflare-tunnel
systemctl status inas-device-hub-backup@main.timer

# ログ確認（フォロー）
journalctl -u inas-device-hub@main -f
journalctl -u inas-cloudflare-tunnel -f
journalctl -u inas-device-hub-backup@main.service

# 再起動 / 再読み込み
sudo systemctl restart inas-device-hub@main
sudo systemctl restart inas-cloudflare-tunnel
sudo systemctl daemon-reload

# liveness / readiness
curl --fail http://127.0.0.1:39151/healthz
curl --fail http://127.0.0.1:39151/readyz
```

`/healthz`はHTTPプロセスの生存、`/readyz`はWeb初期化とMQTT接続を示す。外部監視は両方を監視し、`readyz=503`を運用アラートにする。

テンプレート変更時

1. `/etc/systemd/system/inas-device-hub@.service` を編集
2. `sudo systemctl daemon-reload`
3. `sudo systemctl restart inas-device-hub@main`

環境変数とシークレット管理

- 機密情報は`./.env`に保存する。group/otherへ読み取りを許可せず、`0600`にする。設定CLI、Cloudflare setup、installerはいずれも`0600`を強制する。

```bash
chmod 600 /path/to/ina-device-hub/.env
```

- 必須キー（詳細は `src/ina_device_hub/setting.py` を参照）:
  - `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
  - `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_BUCKET_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
  - `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD`
  - `TIMELAPSE_INTERVAL`

- 本番では Vault（HashiCorp / cloud provider KMS）や AWS Secrets Manager 等により配布し、デバイス側で `.env` を生成する運用が推奨されます。
- MQTT brokerはHubの外部依存である。通常更新時のインストーラーは既存のURL、port、ユーザー名、パスワードを変更せず、その設定で接続確認だけを行う。

MQTT互換性

- 接続はMQTT 3.1.1/TCP、keepalive 60秒、従来のHub client IDを維持する。
- usernameが空なら認証情報を送らず、空でない場合だけ既存username/passwordを使う。
- subscribe topicとQoS 0、device config/OTAのtopic・payload・QoS・retainを変更しない。
- 通常更新ではTLS追加、port変更、credential生成、broker設定変更を行わない。
- 詳細契約は[MQTT Server Integration Specification](../spec/jp/mqtt-server-spec.md)を参照する。

DB とストレージのバックアップ

Hub状態

圃場、設置ビュー、定植、栽培カレンダー、機器設定、F/WメタデータとF/Wバイナリは、チェックサム付きtar.gzへ保存する。systemd timerが日次実行し、`HUB_BACKUP_RETENTION`世代を保持する。手動実行は次のとおり。

バックアップには`runtime-secrets.json`などのHub秘密情報も含まれる。保存ディレクトリは`0700`、archiveは`0600`を維持し、平文のまま公開バケットや共有ストレージへ置かない。ホスト障害に備える場合は、暗号化した上で別ホストまたは非公開バックアップストレージへ複製する。

```bash
uv run ina-hub backup
systemctl list-timers inas-device-hub-backup@main.timer
```

復元時はプロセス内キャッシュによる再上書きを防ぐため、必ずHubを停止する。復元処理はmanifest、パス、SHA-256を検証してからatomicに配置する。

```bash
sudo systemctl stop inas-cloudflare-tunnel inas-device-hub@main
uv run ina-hub restore ~/.ina-device-hub/backups/ina-hub-state-YYYYMMDDTHHMMSSZ.tar.gz --force
sudo systemctl start inas-device-hub@main inas-cloudflare-tunnel
curl --fail http://127.0.0.1:39151/readyz
```

Turso

`ina.db`はLocal HubのTurso local replicaである。Tursoのbackup/exportと復元手順を
定期実行し、少なくとも四半期ごとに復元試験を行う。このLocal Hub DBはCloud Hub
のdirectory DBや顧客専用DBと共有しない。

オブジェクトストレージ（R2/S3互換）

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
  - `journalctl -u inas-device-hub@main -b` を確認。多くは `.env` の未設定やパーミッション、`serve.sh` の実行権限不足。
  - `sudo chmod +x /path/to/ina-device-hub/serve.sh` を確認。

- MQTT 接続できない
  - ブローカー情報（URL/PORT/ユーザー/パスワード）を `.env` で確認。
  - ネットワーク（ファイアウォール、DNS）が ブローカーへ到達できるか `nc` / `telnet` で確認。

- ストレージへアップロード失敗
  - S3 エンドポイント・認証情報を確認。バケット名やリージョンが正しいかも確認。

- DB エラー
  - ローカル DB ファイルのロックや破損。バックアップから復元して起動確認。

更新とロールバック

サーバ上での更新手順

本番サーバにclone済みのリポジトリを直接更新する。`.env`と`WORK_DIR`はGit管理外のまま維持する。

1. 作業ツリーと現在revisionを確認する

```bash
cd /path/to/ina-device-hub
command -v git uv curl
git status --short
PREVIOUS_REVISION="$(git rev-parse HEAD)"
printf 'rollback revision: %s\n' "$PREVIOUS_REVISION"
```

`git status --short`に意図しない変更がある場合は更新を中止し、先に差分の所有者と扱いを確認する。

2. fast-forwardだけを許可してpullする

```bash
git fetch origin main
git pull --ff-only origin main
```

3. 通常更新モードで反映する

```bash
sudo ./scripts/install_service.sh --target-dir "$PWD"
```

通常更新では`--production`を付けない。これにより既存`.env`、MQTT接続、HTTP bind、Cloudflare resourceを変更せず、依存同期と外部接続確認に成功してからバックアップ、unit更新、Hub再起動、readiness確認を行う。Cloudflare TunnelのIDが既に`.env`へある場合は、その既存serviceを維持する。

4. 稼働確認

```bash
systemctl status inas-device-hub@main --no-pager
curl --fail http://127.0.0.1:39151/healthz
curl --fail http://127.0.0.1:39151/readyz
journalctl -u inas-device-hub@main --since '-10 minutes' --no-pager
```

確認項目は、MQTT接続成功、既存deviceのtelemetry受信、runtime config応答、F/W URL到達、圃場一覧・主要画面、端末内DB/R2書き込みである。任意のremote replicaがある場合だけ同期も確認する。

ロールバック

- installerが作成した事前バックアップと、更新前に記録した`PREVIOUS_REVISION`を確認する。
- 作業ツリーがcleanであることを確認し、`git switch --detach "$PREVIOUS_REVISION"`で更新前コードへ切り替える。
- `sudo ./scripts/install_service.sh --target-dir "$PWD"`を再実行する。通常更新モードなのでMQTTやCloudflare設定は変更しない。
- データschemaの互換性がない場合だけ`ina-hub restore`で対応するバックアップを戻す。復元後に`/readyz`、主要画面、MQTT受信を確認する。
- 原因解消後は`git switch main`で管理branchへ戻し、再度fast-forward更新する。

定期メンテナンス項目

- ディスク使用量チェック（`df -h`）
- ローカルストレージの古いファイル削除
- セキュリティアップデート適用（OS レベル）
- 依存ライブラリの定期更新（テストを経て適用）

セキュリティの注意

- `.env` を公開リポジトリへ入れない。Secrets をコミットしないこと。
- サービス実行ユーザーは最小権限にする。
- S3 認証キーは必要最小限の権限にする（書き込み対象バケットに限定）。
- Cloudflare経由で公開する本番は`HUB_AUTH_MODE=cloudflare_access`とし、Access JWTの署名、issuer、audience、emailをHubでも検証する。
- 既存deviceへのLAN内F/W配信のため`HUB_HTTP_HOST=0.0.0.0`を使用できる。origin portはdevice LANからだけ到達可能にし、インターネットへ直接公開しない。
- `/firmware/<device_kind>/<version>/firmware.bin`は既存deviceがAccess JWTを送れないためdevice向け公開endpointとする。管理APIと画面は同じ扱いにせず、Cloudflare Accessで保護する。

最後に

このガイドは基本的な運用をカバーします。運用環境（ネットワーク、クラウドプロバイダ、監視基盤）に合わせて手順を調整してください。追加したい手順や自動化（Ansible/Cloud-init / Mender など）を伝えていただければ、具体的なプレイブックやスクリプトを作成します。
