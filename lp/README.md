# INAS App 広告・需要検証LP

`lp/` は、Web広告から流入した方へINAS Appの価値を短時間で伝え、需要を計測するための独立したサイトです。公開URLは `https://inas-technologies.com/app/` です。LPの静的ファイル、フォーム受付Worker、D1スキーマをまとめて管理し、Hubの実行環境には依存しません。

## ローカル確認

見た目だけを素早く確認する場合は、リポジトリのルートで次を実行します。

```bash
python -m http.server 4173 --directory lp
```

ブラウザで `http://127.0.0.1:4173/` を開きます。キャンペーン表示は、例えば次のURLで確認できます。

```text
http://127.0.0.1:4173/?utm_source=instagram&utm_medium=paid_social&utm_campaign=early_interest&audience=home
```

フォームAPIとD1を含む公開構成は次の手順で確認します。

```bash
cd lp
npm install
cp .env.example .env
# .env の DISCORD_WEB_HOOK_URL を障害通知用Webhookへ変更
npm run build
npm run db:local
npm run dev:worker
```

ブラウザで `http://127.0.0.1:8787/app/` を開きます。ローカルD1は `.wrangler/` 以下に作成され、Gitには含まれません。

## 公開構成

Cloudflare Worker `inas-app-lp` が `inas-technologies.com/app/*` を担当します。静的ファイルは `dist/app/` へ生成し、`/app/api/leads` だけをフォームAPIとして処理します。回答はD1 `inas-lp-leads` に保存し、送信から365日を超えたものを自動削除します。IPアドレスは回答テーブルに保存しません。

回答の保存後、登録メールアドレスを小文字へ正規化してSHA-256ハッシュを生成し、`subjectId`としてService Binding `DISCORD_INVITES`から非公開Worker `inas-discord-invite`へ渡します。招待Workerは、この識別子に対して24時間・1回限定のDiscord招待を発行します。メールアドレスそのものは招待Workerへ渡しません。招待URLはCloudflare Email Serviceから登録者本人へ送信し、APIレスポンス、D1、通常のWorkerログには出力しません。通常時の運営者通知は行わず、招待発行または登録者へのメール送信が失敗した場合だけDiscord Webhookへ障害通知を送ります。

APIは、サーバー側の許可値・文字数・同意確認、Origin確認、レート制限、ハニーポット、任意のTurnstile検証を実施します。Turnstileを有効にする場合は、公開サイトキーを `config.js` の `turnstileSiteKey` に設定し、秘密キーを次のようにWorker Secretへ登録します。

```bash
npx wrangler secret put TURNSTILE_SECRET_KEY
```

秘密キーを `config.js`、JavaScript、Wranglerの通常変数へ書いてはいけません。

初回デプロイではCloudflare上にD1を作成し、返された `database_id` を `wrangler.jsonc` に反映してからマイグレーションとデプロイを実行します。

```bash
npx wrangler d1 create inas-lp-leads
npm run db:remote
npm run deploy
```

最近の回答は、Cloudflare Dashboardの `Storage & databases` → `D1` → `inas-lp-leads` → `Console`、または権限のある運用端末から確認できます。自由記述やメールアドレスを通常のWorkerログへ出力しないでください。

```bash
npm run leads:summary
npm run leads:list
```

登録者への送信にはCloudflare Email ServiceのEmail Sendingを使います。`inas-technologies.com` を送信ドメインとしてオンボードし、Workers Paidプランで任意の登録先へ送信できる状態にしてください。送信元は `wrangler.jsonc` の `LEAD_EMAIL_FROM` で管理します。

障害通知先はGit管理外の `lp/.env` にある `DISCORD_WEB_HOOK_URL` で管理します。初回は `.env.example` をコピーし、通知先チャンネルで発行したDiscord Webhook URLへ変更してください。

```bash
cp .env.example .env
```

`npm run dev:worker` と `npm run deploy` は専用ラッパーを通します。ローカル実行ではWebhook URLだけを一時envファイルとしてWranglerへ渡し、デプロイ時は一時secretsファイルを介してCloudflare Secret `DISCORD_WEB_HOOK_URL` として登録します。一時ファイルはWrangler終了時に削除され、`.env` のほかの値はアップロードしません。Webhook URLが未設定またはDiscord以外のURLの場合は、Workerの起動・デプロイ前に失敗します。CIでは同名の環境変数で上書きでき、別のenvファイルを使う場合は `LP_ENV_FILE` にパスを指定できます。

メールやDiscordの進行状態はD1へ保存しません。既に追加済みの `notification_status`、`notification_sent_at`、`notification_error_code` はマイグレーション `0003_remove_lead_notification_status.sql` で削除します。Discord障害通知には登録ID、処理段階、機械可読なエラーコードだけを含め、登録メールアドレス、招待URL、自由記述は含めません。Webhook通知にも失敗した場合に備え、個人情報を含まないエラーコードをWorkerログへ記録します。

## フォーム契約

`config.js` の `leadEndpoint` は本番の同一オリジンAPI `/app/api/leads` を指します。設定を空にしたプレビューでは個人情報を送信せず、「受付先が未設定」と明示します。受付完了を偽って表示することはありません。

エンドポイントはJSONのPOSTを受け取り、2xxを返す必要があります。送信項目は次のとおりです。

- `role`: 利用者区分
- `scale`: 栽培規模
- `pain`: 主な困りごと
- `email`: 案内先
- `message`: 任意の要望
- `website`: bot判定用の非表示項目。通常は空文字
- `consent`: 同意の有無
- `turnstile_token`: Turnstile有効時の検証トークン
- `audience`: LP上で選択した利用者区分
- `attribution`: UTM、広告クリックID、流入元ホスト、最初のLPパス
- `submitted_at`: ISO 8601形式の送信日時
- `source`: `inas-demand-validation-lp`

クライアントが送る `submitted_at` は参考値であり、保存時刻にはWorkerが生成した時刻を使用します。

## 計測

ページはCTA、対象選択、動画、FAQ、フォーム結果で`inas:conversion`という`CustomEvent`を発行します。同じイベントを`window.dataLayer`と、設定されている場合の`gtag`・`fbq`にも送ります。イベントにはメールアドレスや自由記述を含めません。

`config.js`で以下を任意設定できます。

- `analyticsMeasurementId`: `G-`から始まるGA4 Measurement ID
- `metaPixelId`: 現時点では外部ローダーを自動挿入しません。CMPまたはタグマネージャーで`fbq`を読み込む場合の管理用項目です

GA4や広告ピクセルを有効にする場合は、公開地域と利用するサービスに応じて、同意管理、プライバシーポリシー、オプトアウト導線を公開前に整備してください。IDが空の初期状態では外部計測スクリプトを読み込みません。

計測イベント例：

- `cta_click`
- `video_open`, `video_play`, `video_complete`
- `audience_select`
- `faq_open`
- `lead_validation_error`, `lead_endpoint_missing`
- `lead_submit_success`, `lead_submit_error`

## 広告運用時の推奨指標

広告セットごとに`utm_campaign`と`utm_content`を変え、次の順に確認します。

1. LP到達数
2. ファーストビューCTA率
3. 動画再生率
4. フォーム到達率
5. フォーム完了率
6. 利用者区分・規模・困りごとの構成

クリック率だけで需要を判断せず、フォームの具体的な困りごとと、実際にデモや先行利用へ進む割合を重視してください。

## ファイル構成

- `index.html`: LP本文
- `styles.css`: レスポンシブ・アクセシブルな見た目
- `config.js`: 公開環境ごとのURL・計測設定
- `app.js`: 計測、対象切替、動画モーダル、フォーム送信
- `worker.js`: 静的配信、セキュリティヘッダー、フォーム受付API
- `wrangler.jsonc`: `/app/*` ルート、D1、レート制限、静的アセット設定
- `migrations/`: D1の回答保存スキーマ
- `assets/`: 既存チラシで使用した写真、実画面、デモ動画。画面表示には約181KBのWebPを使い、PNGはフォールバック、JPEGはOGP用です
- `scripts/build.mjs`: 公開ファイルを `dist/app/` に生成
- `scripts/worker-test.mjs`: APIの入力検証・保存・bot判定テスト
- `scripts/smoke.mjs`: PC・スマホのブラウザ回帰と画面キャプチャ
- `artifacts/`: smokeで生成する確認用キャプチャ
