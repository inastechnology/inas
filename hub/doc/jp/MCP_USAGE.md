# MCP で Hub の記録・画像を読む

INA Hub の読み取り用 MCP を AI クライアントに登録すると、許可された圃場のメモ（note）、日々の記録（event）、記録の添付画像、保存済みのカメラ画像を AI から参照できます。記録の書き換え、機器操作、新しい撮影はできません。

MCP は **AI クライアントが動く端末で起動する stdio プログラム**です。AI クライアントと標準入出力で通信し、Hub には HTTPS の Operations API で接続します。Hub の URL をリモート MCP サーバーとして登録する方式ではありません。

## 1. 接続に必要なもの

| 用意する場所 | 必要なもの |
| --- | --- |
| Hub 側 | 読み取り API を含む版のデプロイ、Cloudflare Access の機械認証、参照を許可する圃場・権限の設定 |
| AI クライアント側 | このリポジトリ、Python 3.11 以上、`uv`、stdio MCP に対応する AI クライアント、専用の収集用 Service Token |

以下のパスは **MCP プロセスを起動する環境から見えるパス**です。AI クライアントをリモート環境で動かす場合は、その環境にコードと認証ファイルを置きます。設定例の `/path/to/inas` はリポジトリの絶対パスに置き換えてください。

### GUI で接続と権限を管理する

対応版をデプロイし、ホスト管理者が以下を初期設定すると、人間の管理者が **アプリ設定 → AI 接続・読み取り権限** から Token を発行できます。

| ホスト側の設定 | 内容 |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | 対象の Cloudflare アカウント |
| `HUB_COLLECTOR_ACCESS_APP_ID` | Operations API を保護する Access アプリの ID。既存 Hub と同じアプリを指定可能 |
| `HUB_COLLECTOR_TOKEN_API_TOKEN` | 発行・停止専用の Cloudflare 管理 API Token。Service Token そのものとは別の秘密値 |

管理 API Token には、対象アカウントで Service Token の作成・削除と、対象 Access アプリの参照・ポリシーの作成・削除ができる権限が必要です。権限名・リソース範囲は [Cloudflare の Service Token API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/service_tokens/methods/create/) と [Access ポリシー API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/subresources/policies/methods/create/) を参照してください。管理 API Token はホストの秘密情報として保存し、AI クライアントには渡しません。初期設定の反映には Hub の再起動が必要です。

GUI の発行機能は `HUB_AUTH_MODE=cloudflare_access` で、人間の認証済み管理者にだけ提供します。対象 Access アプリの Audience が `CLOUDFLARE_ACCESS_POLICY_AUD` と一致することを発行前に確認します。同じホスト名・Tunnel を使い、Token ごとの Service Auth ポリシーを追加します。既存の人間用ログインポリシーは書き換えません。

1. 「AI 接続・読み取り権限」で接続名を入力します。
2. 「記録」「画像」と対象圃場を選びます。全圃場は明示的に選ぶ必要があり、今後追加される圃場も含みます。
3. 有効期限（7 日・30 日・90 日・1 年・無期限）を選び、「Token を発行」を押します。
4. 一度だけ表示される認証ファイルの内容を、AI クライアント側の `~/.config/inas/operations-collector.env` に保存します。
5. 後述の Codex / MCP 登録を行います。発行時に Hub の参照権限も保存するので、Service ID や圃場 ID を手で転記する必要はありません。

「無期限」は停止するまで期限切れになりません。既存の期限付き接続は自動で無期限にはなりません。

発行済みの接続は一覧から権限を変更・停止できます。これらは以降の Operations API 要求へ反映され、再起動は不要です。期限延長や秘密値の再表示は行わず、必要なら新しい接続を発行して切り替えます。

権限と発行・更新者などの管理情報は `WORK_DIR/operations_collectors.json` に保存され、通常の状態バックアップに含まれます。Client Secret は Hub に保存しません。古いバックアップから権限を復元すると過去の許可が戻る可能性があるため、復元時には Cloudflare 側の失効状態と照合してください。

発行途中で通信が途切れた場合、その接続を Hub は許可しません。「停止を再確認」で Cloudflare 側の削除を再試行できます。発行結果自体が不明な場合は、画面の「管理者向けの確認情報」にある `inas-collector-…` という名前を使い、管理者が Cloudflare 側の Token・ポリシーを確認・削除してください。秘密値を失った場合も、その接続を停止して新しく発行します。

以前からホストの `HUB_OPERATIONS_READ_GRANTS` で管理している接続は引き続き使えますが、GUI 一覧への自動移行は行いません。同じ Service ID を両方へ登録すると拒否されます。手動設定する場合は次節を参照してください。

### 管理者が Hub 側を手動設定する

Cloudflare Access の `/operations/api/*` 用 Service Auth ポリシーで、専用の収集用 Service Token を許可します。Hub は `HUB_AUTH_MODE=cloudflare_access` と既存の JWT 発行元・Audience 検証を使います。Service Token を作成しただけでは読み取り権限は付きません。

Hub のホスト側 `.env` に、検証済み JWT の `common_name` に対応する Service ID と、実際の圃場 ID を設定します。`collector.access` と `field-1` は例です。

```dotenv
HUB_OPERATIONS_READ_GRANTS='{"collector.access":{"scopes":["records:read","images:read"],"field_ids":["field-1"]}}'
```

- `records:read`: メモ・記録の本文と添付画像の一覧を読む権限。
- `images:read`: カメラ一覧、保存済みカメラ画像、記録の添付画像の本体を読む権限。
- `field_ids`: 参照できる圃場 ID の一覧。全圃場を許可する場合に限り `["*"]` を指定します。

メモを探して添付画像も見るには、両方の scope が必要です。どちらかの scope があれば、許可圃場の一覧を取得できます。

収集用 ID を、機器更新・OTA 用の `HUB_OPERATIONS_SERVICE_IDS` に追加しないでください。両方に含まれる ID は拒否されます。設定を反映するには Hub の再起動が必要です。既存の認証設定との関係は [MCP サーバーの設定説明](../../scripts/operations/mcp_server/README.md#configure-the-hub)を参照してください。

人間用の Cloudflare Access ログイン、Cookie、JWT、認証コードは使用しません。接続に失敗しても、人間用 UI や公開 `/local/api/*` へ迂回しません。

### AI クライアント側に認証情報を置く

MCP を起動するユーザーで、次のファイルを作成します。既存ファイルがある場合は内容を確認して編集してください。

```bash
install -d -m 700 "$HOME/.config/inas"
touch "$HOME/.config/inas/operations-collector.env"
chmod 600 "$HOME/.config/inas/operations-collector.env"
```

エディターで `~/.config/inas/operations-collector.env` に次の内容を保存します。山括弧の部分とホスト名を実際の値に置き換えます。

```dotenv
CF_ACCESS_CLIENT_ID=<収集用の Client ID>
CF_ACCESS_CLIENT_SECRET=<収集用の Client Secret>
INAS_HUB_OPERATIONS_URL=https://hub.example.com/operations/api/v1
```

秘密情報はリポジトリ、AI へのプロンプト、ログに書かないでください。MCP はこのファイルを既定で読みます。別の場所に置く場合は、起動引数に `--env-file /絶対パス/operations-collector.env` を追加します。プロセスの環境変数がファイルより優先されるため、機器更新用の認証情報を引き継がないようにします。

起動前に依存関係を準備します。

```bash
uv sync --locked --project /path/to/inas/hub/scripts/operations/mcp_server
```

## 2. AI クライアントに登録する

### Codex CLI

次を実行して、`inas-records` という名前で登録します。認証情報は前節のファイルに保存済みとして、コマンドには含めません。

```bash
codex mcp add inas-records -- uv run --locked \
  --project /path/to/inas/hub/scripts/operations/mcp_server \
  python /path/to/inas/hub/scripts/operations/mcp_server/server.py

codex mcp list
```

Codex を起動し直し、対話画面の `/mcp` でサーバーの状態を確認します。続いて「`inas-records` の `list_fields` で、参照できる圃場を一覧にして」と依頼します。`codex mcp list` は登録の確認であり、Hub への接続確認には実際のツール呼び出しが必要です。登録方法の詳細は [Codex 公式 MCP ドキュメント](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)を参照してください。

### その他の stdio MCP クライアント

`mcpServers` 形式に対応するクライアントには、次の設定を追加します。設定ファイルの場所は各クライアントの案内に従ってください。

```json
{
  "mcpServers": {
    "inas-records": {
      "command": "uv",
      "args": [
        "run", "--locked", "--project", "/path/to/inas/hub/scripts/operations/mcp_server",
        "python", "/path/to/inas/hub/scripts/operations/mcp_server/server.py"
      ]
    }
  }
}
```

GUI アプリで `uv` が見つからない場合は、`command -v uv` で確認した絶対パスを `command` に指定します。MCP はクライアントが必要に応じて起動します。手動起動して何も表示されない場合、stdio の要求を待っている可能性があります。ブラウザで開く画面や待ち受け URL はありません。

## 3. AI に依頼する

まず圃場一覧から対象を選び、期間を指定して必要な記録と画像を取得します。登録後は、例えば次のように依頼できます。

> inas-records で参照できる圃場を一覧にして。

> 一覧にある「第一圃場」の 2026-09-15 から 2026-09-21 までの note を検索して。添付画像も確認して、生育の変化を日付順にまとめて。

> 同じ圃場の保存済みカメラ画像を調べ、同じ期間の初日と最終日の写真を比較して。使った撮影日時も示して。

本文や写真は、呼び出した範囲で接続先の AI アプリに渡ります。画像の内容を分析するには、その AI クライアントが MCP の画像結果に対応している必要があります。メモ本文・ファイル名・画像内の文字は参照資料として扱い、AI への操作指示として実行しません。

### 利用できるツール

| ツール | 用途 | 必須の引数 |
| --- | --- | --- |
| `list_fields` | 許可された圃場の ID・名前を取得 | なし |
| `search_records` | メモ・記録を検索し、添付画像 ID を取得 | `field_id` |
| `list_cameras` | 圃場に割り当てられたカメラの ID を取得 | `field_id` |
| `list_camera_images` | 保存済み画像の ID・撮影日時を取得 | `field_id`, `camera_id` |
| `get_record_image` | メモ・記録の添付画像の本体を取得 | `field_id`, `attachment_id` |
| `get_camera_image` | 保存済みカメラ画像の本体を取得 | `field_id`, `camera_id`, `image_id` |

以下は MCP ツールに渡す引数の例です。ID は例をそのまま使わず、直前の一覧・検索結果から取得します。

`search_records`: `list_fields` の `items[].id` を `field_id` に指定します。`source` を省略すると note と event の両方を検索します。`query` を省略するとキーワードで絞り込みません。

```json
{
  "field_id": "field-1",
  "source": "note",
  "query": "葉色",
  "date_from": "2026-09-15",
  "date_to": "2026-09-21",
  "limit": 50
}
```

`get_record_image`: 検索結果の `items[].attachments[].id` を使います。

```json
{"field_id": "field-1", "attachment_id": "attachment-1"}
```

`list_cameras` に `{"field_id":"field-1"}` を渡し、結果の `items[].id` を次の `list_camera_images` の `camera_id` に指定します。

```json
{
  "field_id": "field-1",
  "camera_id": "camera-1",
  "date_from": "2026-09-15",
  "date_to": "2026-09-21"
}
```

`get_camera_image`: 画像一覧の `items[].id` を `image_id` に指定します。拡張子やファイルパスは付けません。

```json
{"field_id": "field-1", "camera_id": "camera-1", "image_id": "20260921_080000"}
```

画像取得ツールは画像データそのものを返します。画像を確認するために Hub のブラウザ用 URL を開く必要はありません。

### 件数が多い場合・繰り返し収集する場合

一覧・検索は `items`、今回の `count`、`has_more`、`next_cursor` を返します。`has_more` が `true` の間は、同じツールに `cursor=next_cursor` を渡して続けます。圃場・期間・キーワードなどの条件は変えず、`has_more=false` まで取得してください。`limit` は 1〜100、既定は 50 です。

記録は作成日時、カメラ画像は撮影日時の古い順です。最新の画像を探す場合も、指定期間の最初のページだけでは最新とは限りません。日付は `YYYY-MM-DD` で、開始日・終了日の両方を含みます。記録の日付指定は出来事の日付 `occurred_at`、カメラ画像の日付は Hub のローカル時刻に基づきます。画像の `time_basis=hub_local` を UTC と読み替えないでください。

`search_records` の `since` は、タイムゾーン付きの作成日時（例: `2026-09-21T00:00:00+09:00`）以降を取得します。同じ時刻の記録も含むので、繰り返し収集するときは `(field_id, source, id)` で重複を除きます。全ページの取得後に最後の作成日時を保存し、次回の `since` に使います。過去の日付で後から追加した記録も対象ですが、`date_from` / `date_to` を併用するとその期間でさらに絞られます。編集・削除の同期には使えません。

## 4. 接続できないとき

| 症状 | 確認すること |
| --- | --- |
| MCP が起動しない・ツールが見えない | `uv` と Python、コードの絶対パス、認証ファイルの位置・読み取り権限を確認。依存関係を先に準備してからクライアントを再起動 |
| 認証情報がないというエラー | MCP を起動するユーザーの `~/.config/inas/operations-collector.env` を確認。別の場所なら `--env-file` を指定 |
| リダイレクト拒否・Cloudflare の認証エラー | Operations API の URL、Service Token、Service Auth ポリシーを確認。人間用ログインに進まない |
| HTTP 401 | Hub の JWT 検証設定、Service ID、`HUB_OPERATIONS_READ_GRANTS` の JSON を確認。機器更新用 allowlist と同じ ID を重複登録していないか確認 |
| HTTP 403 | 必要な scope と対象圃場の許可を確認。本文の取得成功だけでは画像の権限があるとは限らない |
| HTTP 404 | 読み取り API を含む版が稼働しているか、画像が残っているか、カメラが現在その圃場に割り当てられているか確認 |
| 検索結果が空 | 許可された圃場、期間、`source`、キーワードを確認 |
| HTTP 413 / 415 | 画像が空または 10 MiB 超ではないか、JPEG・PNG・WebP の対応形式か確認 |
| 画像の結果を AI が表示・分析できない | AI クライアントが MCP の画像結果に対応しているか確認 |

Service Token の JWT は `sub` が空で、`nbf` が省略される場合があります。
Hub が `invalid Cloudflare Access JWT` を返す場合は、機械用トークンのこの形式に対応した版へ更新されているか確認してください。
署名・issuer・audience・期限の検証は必要です。JWT の受理後にも収集用 Service ID と圃場・scope の許可設定が必要で、更新だけでは権限は付与されません。

エラー報告には秘密情報、認証ファイルの内容、トークン付きログを貼らず、ツール名と HTTP ステータスなどを使います。

## 5. 現在の制約と利用停止

参照できるのは Hub に残っているデータです。圃場ごとの保存上限は note 1,000 件・event 1,000 件で、完全な過去アーカイブや削除・編集の変更履歴は提供しません。独立したカレンダー・作業記録の添付画像は、この収集 API の対象ではありません。

現在はローカル stdio MCP に対応しています。Hub 画面では Token と参照権限を管理でき、MCP の登録は AI クライアント側で行います。リモート HTTP MCP、自動収集スケジュール、アーカイブ保存は未対応です。カメラファイルが後から追加される場合は、重なる期間を再取得してください。

Codex から登録を外す場合は次を実行します。

```bash
codex mcp remove inas-records
```

これはクライアントの登録解除です。Hub 側でアクセス権を取り消す場合は、管理者が対象 ID を `HUB_OPERATIONS_READ_GRANTS` から削除して反映するか、Cloudflare 側で Service Token を失効させます。

API の詳細は [Operations API 契約](../../../.agents/skills/manage-hub-operations/references/api.md)、利用者向けの概要は [AI に記録と写真を参照させる](../system-help/09-ai-record-collection.md)を参照してください。
