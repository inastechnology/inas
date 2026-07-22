# 環境変数 (.env) の説明

このプロジェクトで利用する環境変数（`.env`）について、各キーの意味、必須か任意か、設定例、トークンの入手先などをまとめます。新規導入では対話式CLIで作成してください。設定レイヤの責務は [HUB_CONFIGURATION_MANAGEMENT.md](HUB_CONFIGURATION_MANAGEMENT.md) を参照してください。

```bash
uv run ina-hub install
```

注意: 機密情報（API キー・シークレット）は決して公開リポジトリにコミットしないでください。可能であれば Vault / Secrets Manager を利用して運用し、デバイス側では起動時に `.env` を生成してください。

---

以下は ` .default.env` にあるキーをグループごとに説明したものです。

## 一般

- `WORK_DIR` (任意) — アプリの作業ディレクトリ。例: `~/.ina-device-hub`。
- `LOCAL_STORAGE_BASE_DIR` (任意) — 画像などを保存するローカルディレクトリ。例: `/mnt/storage/ina`。
- `HUB_HTTP_HOST` (任意) — local hub HTTP serverのbind address。既定は`0.0.0.0`。既存デバイスへのLAN内F/W配信を維持するため、リポジトリ更新時に自動変更しない。origin portをインターネットへ直接公開してはならない。
- `HUB_HTTP_SERVER` (任意) — `waitress`または開発用`flask`。新規設定の既定は`waitress`。旧`.env`にキーがない更新環境では従来の`flask`へフォールバックする。
- `HUB_HTTP_THREADS` (任意) — Waitress worker thread数。既定: `8`。
- `HUB_AUTH_MODE` (任意) — `local`または`cloudflare_access`。旧`.env`にキーがない場合は従来互換の`local`。Cloudflare経由で公開する新規本番は`cloudflare_access`を使う。
- `HUB_MAX_REQUEST_BYTES` / `FIRMWARE_MAX_UPLOAD_BYTES` — HTTP全体とF/W単体の受信上限。
- `HUB_BACKUP_DIR` / `HUB_BACKUP_RETENTION` — 状態バックアップ先と保持世代数。
- `HUB_READINESS_TIMEOUT_SECONDS` — systemd/foreground起動で`/readyz`を待つ秒数。
- `HUB_HTTP_PORT` (任意) — local hub HTTP server の port。既定: `39151`。
- `HUB_LOCAL_USER_EMAIL` (任意) — Cloudflare Accessを経由しないローカル利用時のユーザーemail。既定: `local-user@ina.local`。
- `HUB_ADMIN_EMAILS` (Cloudflare公開時は必須) — `/settings`、AI接続確認、機器状態・runtime config・OTA/F/W管理を許可するemailのカンマ区切り。本番では明示する。未設定時はAccess利用者全員を作業者とし、ローカル直利用だけを管理者として扱う。

## Turso (ローカル/リモート DB)

- `TURSO_DATABASE_URL` (必須) — Turso（libsql）接続 URL。例: `libsql://...`。
  - 入手方法: Turso のダッシュボードでデータベースを作成すると接続 URL が得られます。
- `TURSO_AUTH_TOKEN` (必須) — Turso の認証トークン（API トークン）。
  - 入手方法: Turso の管理画面で API トークンを発行してください。
- `TURSO_SYNC_INTERVAL` (任意) — Turso と同期する間隔（秒）。デフォルト `600`。

※ `setting.py` は `TURSO_DATABASE_URL` と `TURSO_AUTH_TOKEN` が未設定だと起動を停止します。必ず設定してください。

Hubは起動時にTursoのlocal replicaを同期し、計測用schemaと指標定義を準備してからHTTP受付を開始する。起動後は`TURSO_SYNC_INTERVAL`をlibSQL clientへ渡し、HTTP要求とは独立してlocal replicaを周期同期する。Hubからの書き込みはcommit後にも同期する。起動同期に失敗した場合は初回ページ表示で待たせるのではなく、起動失敗として運用監視へ通知する。確認サーバは実環境のTurso URLを継承せず、`HUB_DEMO_WORK_DIR`配下のローカルlibSQLを使用する。

## S3 / オブジェクトストレージ（メイン）

- `S3_ENDPOINT_URL` (必須) — S3 互換 API のエンドポイント。例: `https://s3.amazonaws.com` や `https://s3.example.com`。
- `S3_BUCKET_NAME` (必須) — 保存先バケット名。
- `S3_BUCKET_REGION` (必須) — バケットのリージョン（provider により任意）。例: `ap-northeast-1`。
- `S3_ACCESS_KEY` (必須) — S3 用アクセスキー ID。
- `S3_SECRET_KEY` (必須) — S3 用シークレットキー。

取得方法: 使用するストレージプロバイダ（AWS S3、DigitalOcean Spaces、Cloudflare R2 など）の管理コンソールでアクセスキーを発行してください。

栽培記録画像をCloudflare R2へ保存する場合、メインバケットは非公開とし、`r2.dev` URLやcustom domainを有効にしません。ブラウザはAccessで保護されたHubの画像APIを介して取得します。`S3_TMP_BASE_URL` はInstagram等の外部配信用であり、栽培記録画像には使いません。

## S3_TMP（テンポラリ / 一時保存用ストレージ）

- `S3_TMP_ENDPOINT_URL`, `S3_TMP_BUCKET_NAME`, `S3_TMP_BUCKET_REGION`, `S3_TMP_ACCESS_KEY`, `S3_TMP_SECRET_KEY` — 一時保存先（例: 生成画像や大きなファイルの一時置き場）を別バケットにしたい場合に設定します。
- `S3_TMP_BASE_URL` — 一時ストレージの公開ベース URL（CDN など）。

用途によりメインと分けることで、本番バケットへの不要な負荷を避けられます。

Instagram 自動投稿では、この一時ストレージを公開 URL 配信用に使います。`S3_TMP_BASE_URL` は CDN や公開配信ドメインを設定してください。Meta の Graph API に渡す動画 URL と画像 URL は外部から取得可能である必要があります。

## OTA firmware 配信

### Cloudflare Access Operations API

- `HUB_OPERATIONS_SERVICE_IDS` — `/operations/api/v1/*`を利用できるCloudflare Access Service Tokenの`common_name`をカンマ区切りで指定します。例: `01234567-89ab-cdef-0123-456789abcdef.access`。Operations APIは`HUB_AUTH_MODE=cloudflare_access`の場合だけ有効で、通常の利用者email JWTやlocal authでは利用できません。
- `DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS` — Cloudflareを通過してHubへ届いたOperations APIのJWT不正・Service ID許可リスト不一致をDiscordへ通知します。既定は`true`です。
- `DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS` — 同一の接続元IP・method・path・拒否理由を再通知しない時間です。既定は300秒です。

Cloudflare Access側では`/operations/api/*`を対象とするService Auth policyを作成し、クライアントは`CF-Access-Client-Id`と`CF-Access-Client-Secret`を送ります。secretはHubのenvやリポジトリへ保存せず、呼び出し側のsecret storeで管理してください。Cloudflareがoriginへ渡す`Cf-Access-Jwt-Assertion`をHubでも検証し、JWTの`common_name`が上記allowlistに含まれる場合だけ処理します。

Client ID・Secret不正などCloudflare Accessがorigin到達前に拒否する要求はHubから観測できません。Cloudflare側のAccess authentication logsまたはLogpushで別に監視してください。HubのDiscord通知にはJWT、Client ID、Client Secret、query stringを含めません。

センシティブなOperations API操作をDiscordで人が承認してから実行する仕組みは未実装です。将来方針は[Hub Operations API Discord承認方針](HUB_OPERATIONS_DISCORD_APPROVAL_POLICY.md)を参照してください。

第1段階のdevice API:

- `GET /operations/api/v1/health`
- `GET /operations/api/v1/devices?device_kind=WTR&state=active`
- `POST /operations/api/v1/devices/firmware-artifacts/<device_kind>/<version>`（bodyはfirmware binary）
- `POST /operations/api/v1/devices/firmware-rollouts`（既定`dry_run=true`）

- `FIRMWARE_HOSTNAME` (推奨) — OTA 対象デバイスから HTTP で到達できる hub の hostname または IP address。未設定なら OS 環境変数 `HOSTNAME`、さらに未設定なら OS hostname を使います。
- `FIRMWARE_PORT` (任意) — OTA firmware 配信 port。未設定なら `HUB_HTTP_PORT`、既定は `39151`。
- `FIRMWARE_BASE_URL` (任意) — URL を完全に固定したい場合の明示 override。例: `http://<hubのドメイン名またはIPアドレス>:39151`。

firmware binary は `WORK_DIR/firmware/<device_kind>/<version>/firmware.bin` に保存され、hub は `GET /firmware/<device_kind>/<version>/firmware.bin` で配信します。現状のデバイス実装は `http://` のみを受け付けるため、hub も OTA offer では `http://` URL だけを許可します。HTTPS はデバイス側に証明書検証を入れてから有効化します。

artifact URL は `FIRMWARE_BASE_URL` があればその値を使い、未設定なら `http://<FIRMWARE_HOSTNAME または HOSTNAME>:<FIRMWARE_PORT または HUB_HTTP_PORT>` から生成します。Cloudflare Access/Tunnel の public hostname は HTTPS/認証付きの UI 入口なので、現状の OTA download URL には使いません。

upload/register API:

```bash
curl -X POST \
  "http://<hubのドメイン名またはIPアドレス>:39151/local/api/firmware-artifacts/WTR/1.1.0/upload" \
  --data-binary @firmware.bin
```

この API は firmware binary 内の `INAS_FW_MANIFEST_V1` を読み、URL path の `device_kind` / `version` と埋め込み値が一致する場合だけ登録します。`build_id`、`project`、`target`、`framework` も埋め込み manifest から artifact metadata に保存します。size と sha256 は hub が自動計算し、artifact URL を `${resolved_firmware_base_url}/firmware/WTR/1.1.0/firmware.bin` として登録します。MQTT は retained OTA offer と OTA status の制御だけに使い、firmware 本体は hub の HTTP server から配信します。

## Instagram 関連（任意）

- `INSTAGRAM_USER_ID` — Instagram のユーザー ID（数値）。
- `INSTAGRAM_ACCESS_TOKEN` — Instagram Graph API のアクセストークン。
- `INSTAGRAM_SENSOR_ID` — 投稿文生成時に参照するセンサーデバイス ID（任意）。

投稿処理開始時刻、タイムラプス元のカメラ、植物位置の補足は管理者用 `/settings` のInstagramカテゴリで管理します。現在の実装では、設定時刻に前回投稿以降のフレームからタイムラプス動画を作り、選択したカメラの代表画像とあわせて投稿文を生成し、Instagram Reelとして投稿します。

投稿する自分のユーザー名は `INSTAGRAM_USER_ID` とアクセストークンを使ってGraph APIから取得し、非秘密のアカウント情報として保存します。`INSTAGRAM_ADMIN_USERNAME` の手入力は新規環境では使用しません。

取得方法: Facebook (Meta) の Graph API を使い、Instagram Business/Creator アカウントをアプリに接続してアクセストークンを取得します（permissions: instagram_basic, instagram_content_publish 等が関係します）。Instagram のトークン管理はやや複雑なので、[Meta Instagram Platform](https://developers.facebook.com/docs/instagram-platform/) と [Meta公式Instagram APIコレクション](https://www.postman.com/meta/instagram/overview) を参照してください。

## MQTT ブローカー

- `MQTT_BROKER_URL` (必須) — ブローカーのホスト名または IP（例: `mqtt.example.com` / `localhost`）。
- `MQTT_BROKER_PORT` (必須) — ポート番号（例: `1883`）。
- `MQTT_BROKER_USERNAME` (必須) — 接続ユーザー名（ブローカーにより任意）。
- `MQTT_BROKER_PASSWORD` (必須) — 接続パスワード。

MQTTの接続先、port、認証有無は既存デバイス・brokerとの互換条件である。リポジトリ更新時に自動変更せず、現在の`.env`をそのまま引き継ぐ。

Hubの接続は従来どおりMQTT 3.1.1/TCP、keepalive 60秒、usernameが空なら認証なし、空でなければusername/password認証である。TLSへの自動切替やport変更は行わない。

## SwitchBot

SwitchBot Cloud API で Plug Mini などを制御する場合だけ設定します。

- `SWITCHBOT_OPEN_TOKEN` (任意) — SwitchBot アプリの Developer Options で取得した Open Token。
- `SWITCHBOT_SECRET_KEY` (任意) — SwitchBot アプリの Developer Options で取得した Secret Key。
- `SWITCHBOT_PLUG_MINI_DEVICE_ID` (任意) — 制御対象 Plug Mini の device ID。
- `SWITCHBOT_BASE_URL` (任意) — SwitchBot API の base URL。通常は既定値 `https://api.switch-bot.com` のままでよいです。
- `SWITCHBOT_TIMEOUT_SECONDS` (任意) — API timeout 秒数。既定値は `20`。

## センサー / 保存設定

- `SENSOR_SAVE_IMAGE` (任意) — 受信画像をローカルに保存する場合は `true`（デフォルト `false`）。
- `SENSOR_SAVE_AUDIO` (任意) — 音声を保存する場合は `true`（デフォルト `false`）。

これらは `true/false` の文字列比較で評価されます。小文字にして `true`/`false` を使ってください。

## タイムラプス

- `TIMELAPSE_INTERVAL` (必須) — タイムラプスの作成間隔（秒）。例: `600`（10 分）や `3600`（1 時間）。

設定忘れは起動エラーになりますので、必ず `TIMELAPSE_INTERVAL` を設定してください。

## AI 関連設定

- `AI_IMAGE_ANALYZE_API_KEY` — 画像解析用APIキーの旧環境向け初期値。
- `AI_TEXT_ANALYZE_API_KEY` — テキスト解析用APIキーの旧環境向け初期値。

AI有効/無効、APIキー、テキスト/画像のBase URLとモデルは管理者用 `/settings` で管理します。APIキーは `WORK_DIR/runtime-secrets.json` に `0600` で保存し、保存値をHTMLやJSON APIへ返しません。ユーザーごとのタイムゾーンと日付形式は `/preferences` からTursoへ保存します。Hubの表示とAI回答は日本語固定で、翻訳はブラウザ機能を使用します。旧 `AI_ENABLED`、`AI_AGENT_SCHEDULE_START`、`AI_*_BASE_URL`、`AI_*_MODEL` は既存環境の初期値としてだけ互換読み込みします。

現在の実装では、画像解析モデルに代表画像とタイムラプス動画 URL を渡して観察メモを作成し、その結果とセンサーデータをもとにテキストモデルで Instagram 投稿文を生成します。

注意: どの AI サービスを使うかによりキーやベース URL の取得方法が異なります（OpenAI の API キー、DeepSeek の API キー等）。各サービスの管理画面で発行してください。

## Discord / 通知

- `DISCORD_WEBHOOK_URL` (任意) — Discord に通知を送るための Webhook URL。取得方法: Discord チャンネルで Webhook を作成して URL をコピー。
- `DISCORD_NOTIFY_PLANT_TASKS` (既定 `true`) — AI栽培計画の新規作業と、開始7日前から作業期間中までの作業を、毎朝04:00（Asia/Tokyo）にEmbed形式で日次集約通知します。`false` でこの通知だけを停止できます。

栽培作業通知は `WORK_DIR/.plant_task_notification_state.json` に通知済み日と既知の作業IDを保存します。更新後の初回実行では既存作業を「新規」として一括通知せず、作業期間中のものだけを通知します。Discord送信に失敗した場合、新規作業は通知済みにせず翌日に再試行します。

## Cloudflare hosted option（任意）

Cloudflare hosted option を使う場合だけ設定します。値の source of truth は日本版の `hub/.env` です。

- `CLOUDFLARE_ACCOUNT_ID` — 固定して使う Cloudflare account ID。
- `CLOUDFLARE_ACCESS_API_TOKEN` — Access application / group / policy を作成・更新するための API token。Worker には渡しません。旧名 `CLOUDFLARE_API_TOKEN` も script は fallback として読みます。
- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME` — Access application と Tunnel の公開 hostname。例: `hub.example.com`。
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN` — Access JWT issuer。例: `https://<team-name>.cloudflareaccess.com`。`scripts/cloudflare_access_setup.py` が Zero Trust organization から補完できます。
- `CLOUDFLARE_ACCESS_POLICY_AUD` — Access applicationのAudience tag。WorkerとPython Hub双方のJWT検証で使う。Access application作成後に`scripts/cloudflare_access_setup.py`が出力する。
- `CLOUDFLARE_ACCESS_GROUP_ID` — 許可 email を保持する Access group ID。script が出力します。
- `CLOUDFLARE_ACCESS_APP_ID` — Access self-hosted application ID。script が出力します。
- `CLOUDFLARE_ACCESS_POLICY_ID` — Access allow policy ID。script が出力します。
- `CLOUDFLARE_ACCESS_APP_NAME` — Access application 名。既定: `inas-hub-hosted`。
- `CLOUDFLARE_ACCESS_GROUP_NAME` — 許可 email group 名。既定: `inas-hub-allowed-users`。
- `CLOUDFLARE_ACCESS_POLICY_NAME` — Access allow policy 名。既定: `inas-hub-allow-email-group`。
- `CLOUDFLARE_ACCESS_SESSION_DURATION` — Access session duration。初期値は `4h` 程度を推奨します。
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS` — 初期 provision 時に group へ入れる email のカンマ区切り一覧。以後は `scripts/cloudflare_access_setup.py add/remove/apply` で管理できます。
- `CLOUDFLARE_ACCESS_ALLOWED_EMAIL_DOMAINS` — 会社メールドメインのカンマ区切り一覧。ドメイン全体を許可する場合のみ設定し、組織IdPでメール所有と在籍を確認する。
- `CLOUDFLARE_TUNNEL_NAME` — Cloudflare Tunnel 名。既定: `inas-hub`。
- `CLOUDFLARE_TUNNEL_ID` — 作成された Tunnel ID。`scripts/cloudflare_tunnel_setup.sh --write-env` が出力します。
- `CLOUDFLARE_TUNNEL_HOSTNAME` — Tunnel の DNS route hostname。通常は `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME` と同じです。
- `CLOUDFLARE_TUNNEL_ORIGIN_URL` — Tunnel が転送する local hub URL。既定: `http://127.0.0.1:39151`。
- `CLOUDFLARE_TUNNEL_TOKEN_FILE` — `cloudflared tunnel run` 用 token file。`scripts/cloudflare_tunnel_setup.py --write-env provision` が `hub/.data/cloudflare/tunnel-token` に生成します。
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID` — Tunnel 用 CNAME record ID。script が出力します。
- `CLOUDFLARE_ZONE_ID` — DNS record を作る zone ID。未設定なら hostname から自動探索します。
- `CLOUDFLARE_ZONE_NAME` — DNS record を作る zone name。未設定なら hostname から自動探索します。
- `CLOUDFLARE_CLOUDFLARED_BIN` — `cloudflared` binary path。未設定なら PATH または `hub/.data/bin/cloudflared` を探します。
- `CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS` — `cloudflare_hosted_up.sh` が local hub の初期終了を検知する待ち時間。既定: `3`。

API token はユーザー側で発行して `.env` または shell/CI secret に設定してください。Account API token でも利用できます。初期 provision まで行う場合は、対象 account に対して `Access: Apps and Policies Read/Write`、`Access: Organizations, Identity Providers, and Groups Read/Write`、`Cloudflare Tunnel Edit` を付与し、対象 zone に対して `Zone > DNS > Read` と `Zone > DNS > Edit` を付与してください。Cloudflare DNS record 作成 API の accepted permission は `DNS Write` です。

## 例 — よく設定する必須項目のサマリ

- `TURSO_DATABASE_URL`=libsql://...
- `TURSO_AUTH_TOKEN`=your-turso-token
- `S3_ENDPOINT_URL`=https://s3.example.com
- `S3_BUCKET_NAME`=your-bucket
- `S3_ACCESS_KEY`=AKIA...
- `S3_SECRET_KEY`=...
- `MQTT_BROKER_URL`=mqtt.example.com
- `MQTT_BROKER_PORT`=1883
- `TIMELAPSE_INTERVAL`=600

## 確認方法（簡単）

起動前に最小限のキーが設定されているかを確認するスニペット:

```bash
grep -E "TURSO_DATABASE_URL|TURSO_AUTH_TOKEN|S3_ENDPOINT_URL|S3_BUCKET_NAME|MQTT_BROKER_URL|TIMELAPSE_INTERVAL" .env
```

あるいは Python から `src/ina_device_hub/setting.py` を使って設定値を読み込むことで検証できます。

---

## 必要なアカウントと取得手順（概要）

以下は本プロジェクトを運用する際に準備する可能性が高い外部サービスと、最短で使い始めるための要点です。詳しい手順は各サービスの公式ドキュメントを参照してください。

- Turso (libsql)
  - 目的: アプリのメタデータやセンサーデータを保存する DB（ローカル同期やクラウド利用）
  - 必要な値: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
  - 最短手順: Turso にサインアップ → 新しいデータベースを作成 → ダッシュボードで接続 URL と API トークンを取得

- オブジェクトストレージ（例: AWS S3 / DigitalOcean Spaces / Cloudflare R2）
  - 目的: 画像や音声などのメディア保存
  - 必要な値: `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_BUCKET_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
  - 最短手順: プロバイダにアカウント登録 → バケット作成 → アクセスキー（Access Key / Secret）を発行
  - 補足: Cloudflare R2 を使う場合は、R2 のバケット名と Access Key / Secret を取得します。公開 URL が必要なら CDN 設定を行って `S3_TMP_BASE_URL` 等に設定します。

- MQTT ブローカー（例: Mosquitto / HiveMQ / EMQX）
  - 目的: デバイスからセンサーデータを受信するメッセージング
  - 必要な値: `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD`
  - 最短手順: 自身で Mosquitto を立てるか、マネージドブローカーを契約 → ユーザーとパスワードを作成

- Instagram Business / Facebook (Meta)（任意。Instagram データ連携が必要な場合）
  - 目的: Instagram 投稿の取得や自動投稿など
  - 必要な値: `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`（長期トークンを推奨）
  - 最短手順: Instagram を Business/Creator に切り替え → Facebook Page とリンク → Meta for Developers でアプリを作成 → Instagram Basic/Content permissions を付与してアクセストークンを取得（アクセストークンの有効期限に注意）

- AI プロバイダ（例: OpenAI, DeepSeek 等）
  - 目的: 画像解析やテキスト解析を行う場合に利用
  - `.env` に必要な値: `AI_IMAGE_ANALYZE_API_KEY`, `AI_TEXT_ANALYZE_API_KEY`
  - GUIで設定する値: Text/ImageのBase URL、モデル、AI有効/無効
  - 最短手順: 各ベンダにアカウント登録 → APIキーを発行 → `uv run ina-hub configure` でキーを登録 → `/settings` でモデルとエンドポイントを設定

- Discord（任意、通知）
  - 目的: 通知を Discord に送る（アラートや結果の通知）
  - 必要な値: `DISCORD_WEBHOOK_URL`
  - 最短手順: Discord サーバで対象チャンネルの Webhook を作成 → Webhook URL をコピーして `.env` に設定

- 追加: Monitoring / Backup アカウント
  - 目的: 外部監視（Prometheus / Datadog 等）やバックアップ先（別クラウドストレージ）を使う場合は、それぞれのアクセス情報を準備してください。

ヒント:

- テスト用と本番用で別アカウントや別バケットを用意し、アクセス権を最小化してください。
- トークンは短期的に発行されることがあるため、長期運用時は自動更新手段（refresh token / service principal）を検討してください。
