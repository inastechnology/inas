# アカウントとセットアップ（Turso / Instagram / ストレージ / MQTT）

目的

本ドキュメントは、ina-device-hub を本番運用または現場で稼働させる前に準備すべき外部アカウントと、その最小限のセットアップ手順をまとめたものです。特に Turso（データベース）、Instagram（画像公開等で利用する場合）、S3 互換ストレージ、MQTT ブローカーについて扱います。

対象読者

- システム管理者、導入担当者、開発者

前提

- 本リポジトリの `src/ina_device_hub/setting.py` は環境変数から多数の設定を読み込みます。未設定時にプロセスが終了する項目があるため、本ドキュメントにある最小必須項目をセットしてください。

必須アカウントと目的（最小セット）

- Turso（または互換の SQLite/クラウド DB） — 端末の計測データやメタ情報の永続化。
- S3 互換ストレージ（AWS S3 / DigitalOcean Spaces / MinIO 等） — 画像や timelapse の保存。
- MQTT ブローカー（自前 Mosquitto / HiveMQ Cloud 等） — デバイスとハブのメッセージ交換。

オプション（利用する場合）

- Instagram（Meta Graph API） — 画像を Instagram に投稿する場合。事前に App の登録とアクセストークン取得が必要。


---

## 1) Turso（libsql）アカウントの準備

 公式: [Turso](https://turso.tech/)

1. Turso にサインアップしてプロジェクトを作成する（または既存 DB を用意）。
2. データベースの接続情報（sync URL / database URL）と認証トークン（auth token）を取得する。
   - 取得方法は Turso のコンソールで「Database」→「Connection」から確認できます。
3. ローカルで接続を試す（任意）: turso CLI や libsql の接続サンプルを実行して認証が通るか確認。

環境変数（`setting.py` に対応）

- TURSO_DATABASE_URL — Turso の sync URL（例: [https://db.turso.example](https://db.turso.example)）
- TURSO_AUTH_TOKEN — Turso の認証トークン
- LOCAL_STORAGE_BASE_DIR / LOCAL_DB_PATH は `setting.py` で既定値が使われますが、変更する場合は環境変数で上書きまたは設定ファイルに記載します。

検証

- ina-device-hub を起動する前に小さな Python スクリプトで libsql.connect(db_path, sync_url=..., auth_token=...) が成功するか検証してください。

---

## 2) S3 互換ストレージ（画像保存用）の準備

一般的な選択肢

- AWS S3: [https://aws.amazon.com/s3/](https://aws.amazon.com/s3/)
- DigitalOcean Spaces: [https://www.digitalocean.com/products/spaces/](https://www.digitalocean.com/products/spaces/)
- MinIO（オンプレ）: [https://min.io/](https://min.io/)

1. バケット（またはバケット相当）を作成する。
2. API キー（アクセスキー / シークレットキー）を作成する。
3. バケットのエンドポイント URL を確認（リージョン・エンドポイント）。

環境変数（`setting.py` に対応）

- S3_ENDPOINT_URL — 例: [https://nyc3.digitaloceanspaces.com](https://nyc3.digitaloceanspaces.com) またはカスタムエンドポイント
- S3_BUCKET_NAME — バケット名
- S3_BUCKET_REGION — リージョン名（必要な場合）
- S3_ACCESS_KEY — アクセスキー
- S3_SECRET_KEY — シークレットキー

検証

- `boto3` を使った簡単な put_object/get_object テストを行い、アップロード・ダウンロードができることを確認してください。

---

## 3) MQTT ブローカーの準備

選択肢

- 自前 Mosquitto（サーバ/コンテナ）: [https://mosquitto.org/](https://mosquitto.org/)
- HiveMQ Cloud / CloudMQTT などのマネージドサービス

1. ブローカーを用意して接続するためのホスト名、ポート、ユーザー名、パスワードを確保する。

2. QoS やトピック設計（例: `sensor/<device_id>/<kind>/<seqId>`）を決める。

環境変数（`setting.py` に対応）

- MQTT_BROKER_URL — ホスト名または IP
- MQTT_BROKER_PORT — ポート番号（通常 1883 / 8883）
- MQTT_BROKER_USERNAME — 認証が必要な場合
- MQTT_BROKER_PASSWORD — 認証のパスワード
- mqtt_client_id は `setting.py` 内でデバイス名から取得されるが、必要なら明示的に設定してください。

検証

- `mosquitto_pub` / `mosquitto_sub`（CLI）や簡易 Python スクリプトで publish/subscribe の疎通を確認してください。

---

## 4) Instagram (Meta Graph API) アプリの準備（任意）

- 公式ドキュメント: [Instagram Graph API ドキュメント](https://developers.facebook.com/docs/instagram-api)

> 注意: Instagram Graph API を通じて自動投稿を行う場合、Meta の審査やビジネスアカウント要件がある点に注意してください。

基本手順（概要）

1. Facebook for Developers へ登録: [https://developers.facebook.com/](https://developers.facebook.com/)
2. 新しい App を作成する（Business アプリ推奨）。
3. Instagram Basic Display / Instagram Graph API をアプリに追加し、必要な権限（media_publish 等）を確認する。
4. Instagram ビジネスアカウントまたはクリエイターアカウントを用意し、Facebook ページとリンクさせる。
5. アクセストークン（長期トークンが必要な場合あり）を取得する。開発中は短期トークン → 長期トークンに交換する手順を踏んでください。
6. Webhook（リアルタイム更新）が必要なら設定する。

環境変数 / 設定（アプリ設計による）

- INSTAGRAM_APP_ID
- INSTAGRAM_APP_SECRET
- INSTAGRAM_ACCESS_TOKEN (長期推奨)
- INSTAGRAM_ACCOUNT_ID

検証

- Graph API Explorer（developers.facebook.com/tools/explorer）で簡単な GET/POST が動くか確認します。
- 画像投稿フローは審査やアプリ権限により制限されるため、事前に小さな検証を行ってください。

---

## 5) 環境変数リスト（まとめ）

最低限セットすることを推奨する環境変数（`setting.py` の読み取りに基づく）：

- TURSO_DATABASE_URL
- TURSO_AUTH_TOKEN
- S3_ENDPOINT_URL
- S3_BUCKET_NAME
- S3_BUCKET_REGION
- S3_ACCESS_KEY
- S3_SECRET_KEY
- MQTT_BROKER_URL
- MQTT_BROKER_PORT
- MQTT_BROKER_USERNAME
- MQTT_BROKER_PASSWORD
- TIMELAPSE_INTERVAL
- SENSOR_SAVE_IMAGE (true|false)
- SENSOR_SAVE_AUDIO (true|false)

オプション（Instagram）:

- INSTAGRAM_APP_ID
- INSTAGRAM_APP_SECRET
- INSTAGRAM_ACCESS_TOKEN
- INSTAGRAM_ACCOUNT_ID

---

## 6) 動作確認手順（簡易）

1. 環境変数を `.env` に記載（プロジェクトルートに置く）
2. 仮想環境を作り依存をインストール（`requirements.lock` を参照）
3. 小さな接続テストスクリプトで Turso / S3 / MQTT の接続を確認
4. ina-device-hub を立ち上げ（`serve.run()` など）し、ログにエラーが出ないか確認
5. MQTT にダミーメッセージを publish して、DataProcessor の処理と S3 へのアップロードが行われるか確認

---

## 7) 参考リンク

- Turso: [https://turso.tech/](https://turso.tech/)
- Instagram Graph API: [https://developers.facebook.com/docs/instagram-api](https://developers.facebook.com/docs/instagram-api)
- AWS S3: [https://aws.amazon.com/s3/](https://aws.amazon.com/s3/)
- DigitalOcean Spaces: [https://www.digitalocean.com/products/spaces/](https://www.digitalocean.com/products/spaces/)
- MinIO: [https://min.io/](https://min.io/)
- Mosquitto: [https://mosquitto.org/](https://mosquitto.org/)
- HiveMQ Cloud: [https://www.hivemq.com/mqtt-cloud-broker/](https://www.hivemq.com/mqtt-cloud-broker/)

---

## 8) トラブルシュート（よくある問題）

- 認証エラー
  - トークン有効期限、権限範囲、環境変数のタイポを確認する。
- 接続タイムアウト
  - ファイアウォール／VPC 設定、エンドポイント URL の誤りを確認する。
- アップロード失敗（S3）
  - バケットポリシー、キー名のエンコーディング、ContentType を確認する。




