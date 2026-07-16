# Hub 設定管理方針

作成日: 2026-07-15

## 1. 目的

設定値を、導入時の接続・秘密情報、運用中に変えるアプリ設定、圃場やデバイスの業務データに分離する。複数の保存先で同じ秘密値を管理せず、圃場ごとの設定へHub全体の設定を混在させない。

## 2. 設定レイヤ

| レイヤ | 保存先 | 変更手段 | 主な値 |
|---|---|---|---|
| 導入・接続設定 | `hub/.env` | `uv run ina-hub install` / `uv run ina-hub configure` | Turso、R2/S3、MQTT、HTTP bind、保存先、Instagram認証、管理者email |
| システム設定 | `WORK_DIR/config.json` | 管理者用 `/settings` | AI有効/無効、Base URL、モデル、Instagram投稿設定 |
| GUI秘密設定 | `WORK_DIR/runtime-secrets.json` | 管理者用 `/settings` | Text/Image AI APIキー |
| 個人設定 | Turso/libSQL `user_preferences` | 全ユーザー用 `/preferences` | タイムゾーン、日付形式、ユーザー別UI設定 |
| 業務データ | 各repository / libSQL | 各業務画面 | 圃場、配置、定植、栽培計画、デバイス関連付け、記録 |

`config.json` はランタイム変更を許可した非秘密項目だけを保存する。Turso token、S3 secret、MQTT password、AI API keyなどを保存してはならない。`config.json` と `runtime-secrets.json` はともに `0600` で作成する。

## 3. AI設定

AI設定は圃場に属さないHub全体のアプリ設定である。入口は圃場設定ではなく `/settings` の `AI` カテゴリとする。

| 設定 | 管理場所 | 理由 |
|---|---|---|
| `AI_TEXT_ANALYZE_API_KEY` | GUI秘密設定 | 管理者が運用中に更新できる。保存値はブラウザへ返さない |
| `AI_IMAGE_ANALYZE_API_KEY` | GUI秘密設定 | 管理者が運用中に更新できる。保存値はブラウザへ返さない |
| AI有効/無効 | GUI | 運用中に変更する |
| Text/Image Base URL | GUI | 利用する互換APIを切り替える |
| Text/Image model | GUI | コスト・性能に応じて変更する |

GUIはAPIキーの設定済み/未設定だけを表示する。password入力は常に空で、空欄保存は現在値を維持し、明示的な削除操作だけが保存値を空にする。接続確認APIはサーバ側の秘密ストアからキーを読み、ブラウザからAPIキーを受け取らない。APIキーをGUIで初めて保存するまでは、既存環境との互換性のため `.env` の値を初期値として使う。GUIで保存または削除した後は秘密ストアを優先する。

管理者が新しいキーを入力して送信する瞬間は、その管理者自身のブラウザの開発者ツールから送信内容を確認できる。ブラウザからサーバへ値を送る以上、これは技術的に防げない。対策対象は保存後の再取得であり、次を保証する。

- GET `/settings`、接続確認API、HTML、レスポンスヘッダーへ保存済みキーを含めない。
- 設定画面と接続確認結果を `Cache-Control: no-store` にする。
- 別ユーザーは設定済み/未設定だけを確認でき、保存値を取得するAPIを設けない。
- `/settings` と更新APIを `HUB_ADMIN_EMAILS` の管理者だけに許可する。

旧バージョンの `config.json` に秘密情報やインフラ設定が含まれる場合、読み込み時に許可項目だけへ正規化して書き直す。旧 `AI_*_BASE_URL`、`AI_*_MODEL`、`AI_ENABLED` 環境変数は既存環境の初期値として読み取るが、GUI保存後は `config.json` を優先する。新規 `.default.env` にはこれらを定義しない。

## 4. システム設定画面

`/settings` は管理者だけが開けるHub全体の設定であり、次のカテゴリを持つ。

- `AI`: テキスト・画像AIの設定、書き込み専用のAPIキー入力、接続確認。
- `Instagram`: 投稿処理開始時刻、投稿元カメラ、植物位置の補足、投稿アカウント情報。
- `システム`: `.env` 接続項目の設定状態。秘密値そのものは表示しない。

画面上部の検索は、表示名、説明、`language`、`OpenAI`、`Turso` などの別名を含めて設定項目を絞り込む。設定画面は圃場詳細の子画面にせず、TOPと圃場詳細の共通ヘッダーから遷移する。

## 5. Instagram設定

Instagramにだけ必要な定期実行時刻は `Instagram投稿処理開始時刻` として管理する。AI全般の「日次処理」には流用しない。別の日次ジョブが必要になった場合は、ジョブごとに設定名とスケジュールを追加する。

`INSTAGRAM_CAMERA_ID` と `INSTAGRAM_PLANT_POSITION_PROMPT` は `/settings` の `Instagram` カテゴリへ移した。カメラIDはカメラrepositoryおよびデバイス台帳の `CAM` デバイスから選択し、自由入力させない。旧環境変数は移行時の初期値としてだけ読み込む。

投稿アカウントのユーザー名は手入力しない。`INSTAGRAM_USER_ID` と `INSTAGRAM_ACCESS_TOKEN` を使ってInstagram Graph APIへ `fields=id,username` を要求し、取得したID、username、取得日時を `config.json` に非秘密メタデータとして保存する。画面の「接続確認・再取得」で更新でき、初回自動投稿時にも未取得なら補完する。旧 `INSTAGRAM_ADMIN_USERNAME` は既存環境のフォールバックに限る。

## 6. 個人設定画面

`/preferences` はログイン中の全ユーザーが開ける。Cloudflare Accessが検証したemailを主キーとしてTursoへ保存し、端末間で共有する。タイムゾーンと日付形式をシステム設定や `.env` へ保存しない。

Hubの画面とAI回答は日本語を正規言語とし、言語設定および`inas_locale` Cookieを持たない。翻訳が必要な場合はブラウザの翻訳機能を使用する。既存DBの`locale`列は移行互換のため残すが、APIは常に`ja`として扱い、画面から変更できない。`localStorage` は未保存フォームやタブ位置など、失っても業務データを壊さない一時的なUI状態にだけ使用する。

個人設定の更新は `version` を使った楽観ロックとし、別画面で先に更新された場合は409とサーバー上の最新版を返す。画面は入力内容を失わず、最新版を採用するか、入力内容を最新版へ再適用するかを選ばせる。詳細は [HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md](HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md) を参照する。

## 7. 初期設定

`hub` ディレクトリで実行する。

```bash
uv sync
uv run ina-hub install
```

対話入力は既存値を表示し、秘密値はマスクする。Enterだけを入力した場合は既存値または既定値を維持する。入力後は次を確認できる。

- 作業・保存ディレクトリ: 書き込み可否と数値設定。
- Turso: local replicaの接続と同期。
- R2/S3: `HeadBucket`。
- MQTT: ユーザー名・パスワードを含むMQTT接続完了。

接続確認に失敗しても入力を破棄せず、最後に `.env` を原子的に保存する。ネットワークを使えない準備環境では `--skip-checks` を指定できる。

```bash
uv run ina-hub install --skip-checks
```

## 8. 再設定

```bash
uv run ina-hub configure
```

カテゴリと変更項目を番号で選択し、1項目ずつ保存・接続確認する。`.env` の値はプロセス起動時に読み込むため、変更後はHubを再起動する。AIのBase URLとモデルは管理者用GUIを使用する。

対象ファイルを明示する場合:

```bash
uv run ina-hub configure --env-file /path/to/.env
```

## 9. セキュリティ原則

- `.env` と `config.json` をGitへ追加しない。
- APIキー、token、passwordをHTML、JSON API、ログへ出力しない。
- AI APIキーの正本はGUIで初回更新後の `runtime-secrets.json` とし、`.env` は移行前の初期値に限定する。
- `.env` の変更権限はHubホストの管理者に限定する。
- Cloudflare AccessはHTTPアクセス制御であり、ホスト上の設定ファイル権限を代替しない。
- `Cf-Access-Authenticated-User-Email` はAccess/Tunnelを通過したリクエストでだけ信頼する。Hub originを外部や認証されていないLANへ直接公開しない。
- Access経由では `HUB_ADMIN_EMAILS` に指定したemailだけが `/settings` とAI接続確認APIを利用できる。未指定時はAccess利用者全員を作業者とし、ローカル直利用だけを管理者として扱う。本番では管理者emailを明示する。
