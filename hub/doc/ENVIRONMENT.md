# 環境変数 (.env) の説明

このプロジェクトで利用する環境変数（`.env`）について、各キーの意味、必須か任意か、設定例、トークンの入手先などをまとめます。リポジトリにある ` .default.env` をコピーして ` .env` を作成し、値を実運用向けに編集してください。

```bash
cp .default.env .env
chmod 600 .env
```

注意: 機密情報（API キー・シークレット）は決して公開リポジトリにコミットしないでください。可能であれば Vault / Secrets Manager を利用して運用し、デバイス側では起動時に `.env` を生成してください。

---

以下は ` .default.env` にあるキーをグループごとに説明したものです。

## 一般

- `LANGUAGE` (任意) — ロケール/言語指定。例: `en`。
- `WORK_DIR` (任意) — アプリの作業ディレクトリ。例: `~/.ina-device-hub`。
- `LOCAL_STORAGE_BASE_DIR` (任意) — 画像などを保存するローカルディレクトリ。例: `/mnt/storage/ina`。

## Turso (ローカル/リモート DB)

- `TURSO_DATABASE_URL` (必須) — Turso（libsql）接続 URL。例: `libsql://...`。
  - 入手方法: Turso のダッシュボードでデータベースを作成すると接続 URL が得られます。
- `TURSO_AUTH_TOKEN` (必須) — Turso の認証トークン（API トークン）。
  - 入手方法: Turso の管理画面で API トークンを発行してください。
- `TURSO_SYNC_INTERVAL` (任意) — Turso と同期する間隔（秒）。デフォルト `600`。

※ `setting.py` は `TURSO_DATABASE_URL` と `TURSO_AUTH_TOKEN` が未設定だと起動を停止します。必ず設定してください。

## S3 / オブジェクトストレージ（メイン）

- `S3_ENDPOINT_URL` (必須) — S3 互換 API のエンドポイント。例: `https://s3.amazonaws.com` や `https://s3.example.com`。
- `S3_BUCKET_NAME` (必須) — 保存先バケット名。
- `S3_BUCKET_REGION` (必須) — バケットのリージョン（provider により任意）。例: `ap-northeast-1`。
- `S3_ACCESS_KEY` (必須) — S3 用アクセスキー ID。
- `S3_SECRET_KEY` (必須) — S3 用シークレットキー。

取得方法: 使用するストレージプロバイダ（AWS S3、DigitalOcean Spaces、Cloudflare R2 など）の管理コンソールでアクセスキーを発行してください。

## S3_TMP（テンポラリ / 一時保存用ストレージ）

- `S3_TMP_ENDPOINT_URL`, `S3_TMP_BUCKET_NAME`, `S3_TMP_BUCKET_REGION`, `S3_TMP_ACCESS_KEY`, `S3_TMP_SECRET_KEY` — 一時保存先（例: 生成画像や大きなファイルの一時置き場）を別バケットにしたい場合に設定します。
- `S3_TMP_BASE_URL` — 一時ストレージの公開ベース URL（CDN など）。

用途によりメインと分けることで、本番バケットへの不要な負荷を避けられます。

Instagram 自動投稿では、この一時ストレージを公開 URL 配信用に使います。`S3_TMP_BASE_URL` は CDN や公開配信ドメインを設定してください。Meta の Graph API に渡す動画 URL と画像 URL は外部から取得可能である必要があります。

## Instagram 関連（任意）

- `INSTAGRAM_USER_ID` — Instagram のユーザー ID（数値）。
- `INSTAGRAM_ACCESS_TOKEN` — Instagram Graph API のアクセストークン。
- `INSTAGRAM_SENSOR_ID` — 投稿文生成時に参照するセンサーデバイス ID（任意）。
- `INSTAGRAM_CAMERA_ID` — タイムラプス元のカメラデバイス ID。自動投稿を使う場合は必須です。
- `INSTAGRAM_PLANT_POSITION_PROMPT` — Instagram 投稿の位置情報や解析プロンプト（任意）。

現在の実装では、`AI_AGENT_SCHEDULE_START` の時刻に前回投稿以降のフレームからタイムラプス動画を作り、`INSTAGRAM_CAMERA_ID` の代表画像とあわせて投稿文を生成し、Instagram Reel として投稿します。

取得方法: Facebook (Meta) の Graph API を使い、Instagram Business/Creator アカウントをアプリに接続してアクセストークンを取得します（permissions: instagram_basic, instagram_content_publish 等が関係します）。Instagram のトークン管理はやや複雑なので公式ドキュメントを参照してください。

## MQTT ブローカー

- `MQTT_BROKER_URL` (必須) — ブローカーのホスト名または IP（例: `mqtt.example.com` / `localhost`）。
- `MQTT_BROKER_PORT` (必須) — ポート番号（例: `1883`）。
- `MQTT_BROKER_USERNAME` (必須) — 接続ユーザー名（ブローカーにより任意）。
- `MQTT_BROKER_PASSWORD` (必須) — 接続パスワード。

注意: ブローカーが TLS を要求する場合、証明書の配置やポート（8883 など）を設定してください。

## センサー / 保存設定

- `SENSOR_SAVE_IMAGE` (任意) — 受信画像をローカルに保存する場合は `true`（デフォルト `false`）。
- `SENSOR_SAVE_AUDIO` (任意) — 音声を保存する場合は `true`（デフォルト `false`）。

これらは `true/false` の文字列比較で評価されます。小文字にして `true`/`false` を使ってください。

## タイムラプス

- `TIMELAPSE_INTERVAL` (必須) — タイムラプスの作成間隔（秒）。例: `600`（10 分）や `3600`（1 時間）。

設定忘れは起動エラーになりますので、必ず `TIMELAPSE_INTERVAL` を設定してください。

## AI 関連設定

- `AI_ENABLED` (任意) — AI 機能を有効にする場合は `true`。
- `AI_AGENT_SCHEDULE_START` (任意) — AI エージェントが動作を開始する時刻（例: `09:01`）。日次の Instagram 投稿ジョブ時刻として使われます。
- `AI_IMAGE_ANALYZE_API_KEY` — 画像解析用 API キー（例: OpenAI, DeepSeek などのキー）。
- `AI_IMAGE_ANALYZE_BASE_URL` — 画像解析 API のベース URL。未設定時は OpenAI 互換の既定 URL を使います。
- `AI_IMAGE_ANALYZE_MODEL` — 画像解析で使うモデル名（例: `gpt-4o` 等）。
- `AI_TEXT_ANALYZE_API_KEY`, `AI_TEXT_ANALYZE_BASE_URL`, `AI_TEXT_ANALYZE_MODEL` — テキスト解析用の API キー・エンドポイント・モデル。

現在の実装では、画像解析モデルに代表画像とタイムラプス動画 URL を渡して観察メモを作成し、その結果とセンサーデータをもとにテキストモデルで Instagram 投稿文を生成します。

注意: どの AI サービスを使うかによりキーやベース URL の取得方法が異なります（OpenAI の API キー、DeepSeek の API キー等）。各サービスの管理画面で発行してください。

## Discord / 通知

- `DISCORD_WEBHOOK_URL` (任意) — Discord に通知を送るための Webhook URL。取得方法: Discord チャンネルで Webhook を作成して URL をコピー。

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
  - 必要な値: `AI_IMAGE_ANALYZE_API_KEY`, `AI_IMAGE_ANALYZE_MODEL`, `AI_TEXT_ANALYZE_API_KEY`, `AI_TEXT_ANALYZE_BASE_URL`, `AI_TEXT_ANALYZE_MODEL`
  - 最短手順: 各ベンダにアカウント登録 → API キーを発行 → 必要ならモデル名やエンドポイントを確認して設定

- Discord（任意、通知）
  - 目的: 通知を Discord に送る（アラートや結果の通知）
  - 必要な値: `DISCORD_WEBHOOK_URL`
  - 最短手順: Discord サーバで対象チャンネルの Webhook を作成 → Webhook URL をコピーして `.env` に設定

- 追加: Monitoring / Backup アカウント
  - 目的: 外部監視（Prometheus / Datadog 等）やバックアップ先（別クラウドストレージ）を使う場合は、それぞれのアクセス情報を準備してください。

ヒント:

- テスト用と本番用で別アカウントや別バケットを用意し、アクセス権を最小化してください。
- トークンは短期的に発行されることがあるため、長期運用時は自動更新手段（refresh token / service principal）を検討してください。
