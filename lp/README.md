# INAS App 広告・需要検証LP

`lp/` は、Web広告から流入した方へINAS Appの価値を短時間で伝え、需要を計測するための独立した静的サイトです。Hubの実行環境やデータベースには依存しません。

## ローカル確認

リポジトリのルートで次を実行します。

```bash
python -m http.server 4173 --directory lp
```

ブラウザで `http://127.0.0.1:4173/` を開きます。キャンペーン表示は、例えば次のURLで確認できます。

```text
http://127.0.0.1:4173/?utm_source=instagram&utm_medium=paid_social&utm_campaign=early_interest&audience=home
```

## 公開前に必ず設定する項目

`config.js` の `leadEndpoint` に、先行案内フォームを受け取るHTTPSエンドポイントを設定してください。設定しない場合、フォームは個人情報を送信せず、「受付先が未設定」と明示します。受付完了を偽って表示することはありません。

エンドポイントはJSONのPOSTを受け取り、2xxを返す必要があります。送信項目は次のとおりです。

- `role`: 利用者区分
- `scale`: 栽培規模
- `pain`: 主な困りごと
- `email`: 案内先
- `message`: 任意の要望
- `consent`: 同意の有無
- `audience`: LP上で選択した利用者区分
- `attribution`: UTM、広告クリックID、流入元ホスト、最初のLPパス
- `submitted_at`: ISO 8601形式の送信日時
- `source`: `inas-demand-validation-lp`

静的ファイルに秘密情報を置くことはできません。APIキーを`config.js`やJavaScriptへ入れず、公開フォーム専用のエンドポイント側でレート制限、bot対策、入力検証、保存、通知を行ってください。

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
- `assets/`: 既存チラシで使用した写真、実画面、デモ動画。画面表示には約181KBのWebPを使い、PNGはフォールバック、JPEGはOGP用です
- `scripts/smoke.mjs`: PC・スマホのブラウザ回帰と画面キャプチャ
- `artifacts/`: smokeで生成する確認用キャプチャ
