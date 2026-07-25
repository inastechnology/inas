# ユーザー設定・同時編集設計

作成日: 2026-07-15

## 1. 目的

複数の利用者が同じHubへログインする前提で、ユーザー個人の日時表示設定と会社・Hub全体のシステム設定を混在させない。また、同じ配置や設定を複数画面から編集しても、後から保存した人が先の変更を無言で消さない。

## 2. 認証主体

- 本番のユーザーIDはCloudflare Accessが検証したemailとする。
- 本番では `HUB_AUTH_MODE=cloudflare_access` とし、Hub自身が `Cf-Access-Jwt-Assertion` をCloudflare JWKS、issuer、audienceで検証する。
- JWT内emailを小文字へ正規化し、`Cf-Access-Authenticated-User-Email` がある場合は両者の一致も確認する。JWT欠落、検証失敗、不一致は`401`とする。
- ローカル開発だけは `HUB_AUTH_MODE=local` とし、`HUB_LOCAL_USER_EMAIL` を使用する。
- `HUB_ADMIN_EMAILS` のemailを `admin`、それ以外を `operator` とする。
- 本番ではHubを `127.0.0.1` にbindし、Cloudflare Tunnel以外からoriginへ到達させない。外部から任意の認証ヘッダーを送れる構成は不可とする。
- 本番の更新要求は公開originとの一致を必須とし、cross-originまたはOrigin欠落の要求を`403`とする。機器状態、runtime config、OTA/F/W管理は`admin`だけが更新できる。

現行ロール境界は、`admin` がアプリ設定とAI接続確認を利用でき、`operator` は個人設定と圃場業務画面を利用できる範囲である。`HUB_ADMIN_EMAILS` が空の場合、Access経由の利用者は全員`operator`となり、ローカル直利用だけを`admin`として扱う。圃場別権限や承認フローは将来拡張とする。

## 3. 保存先と責務

| データ | 正本 | スコープ | ブラウザ保存 |
|---|---|---|---|
| AI APIキー | `WORK_DIR/runtime-secrets.json` | Hub | 保存しない |
| Turso/R2/MQTT接続 | `.env` | Hub | 保存しない |
| AIモデル、AI有効化、Instagram設定 | `WORK_DIR/config.json` | Hub | 保存しない |
| タイムゾーン、日付形式、栽培アドバイス習熟度 | Turso `user_preferences` | email | 保存しない |
| 配置、定植、記録 | repository。順次Tursoへ移行 | 会社・圃場 | 未保存入力だけ一時保持可能 |

Cookieや`localStorage`だけで個人設定を管理すると、端末ごとに値が分かれ、共有PCの利用者切替にも弱い。そのため個人設定の正本はTursoに置く。`localStorage`はタブ位置や未送信フォームなど再生成可能な状態に限定する。Hubの言語は日本語固定であり、翻訳はブラウザ機能に委ねる。

## 4. 個人設定API

### 取得

```http
GET /local/api/me/preferences
```

認証email本人の設定だけを返す。リクエストから任意emailを指定するAPIにはしない。

### 更新

```http
PATCH /local/api/me/preferences
Content-Type: application/json

{
  "version": 3,
  "timezone": "Asia/Tokyo",
  "date_format": "yyyy-MM-dd",
  "preferences": {
    "cultivation_experience": "beginner"
  }
}
```

`cultivation_experience` は `beginner`、`standard`、`professional` のいずれかとし、未設定は `standard` とする。これは初回栽培カレンダー、カレンダー再生成、作業完了後の差分タスクで共通利用する。Hub全体のAIモデルやAPIキーとは分離し、利用者ごとに説明量と専門性だけを調整する。初心者設定でも安全条件、数値、製品ラベル確認を省略しない。

サーバーはトランザクション内で現在の`version`を比較し、一致した場合だけ更新して`version + 1`を保存する。競合時は次を返す。

```json
{
  "code": "revision_conflict",
  "current": {
    "version": 4,
    "timezone": "Asia/Tokyo",
    "date_format": "yyyy-MM-dd"
  }
}
```

画面は409を一般エラーとして消費せず、サーバー上の最新版とこの画面の入力を比較表示する。利用者は「最新版を使う」または「入力内容で再保存」を選べる。

## 5. 業務データの同時編集原則

編集対象は`revision`または`version`を持つ。更新要求は読込時の値を必ず送り、サーバーは次の処理を同一の排他区間またはDBトランザクションで行う。

1. 正本から最新版を読む。
2. 要求されたrevisionと比較する。
3. 一致すれば更新し、revisionを増やす。
4. 一致しなければ書き込まず、409と最新版を返す。

確認してから保存するまでが原子的である必要がある。Pythonのインメモリ辞書だけで比較したり、JSONファイルを直接truncateしてから書き込んだりしてはならない。

## 6. 設置ビューの競合UX

設置ビューは次の3世代をクライアントで保持する。

- `base`: この画面が最後に読み込んだ版。
- `local`: 利用者が編集した未保存版。
- `server`: 409で返された最新版。

競合時は三者比較を行う。片側だけが変更した空間・配置・項目は自動統合する。同じ項目を両側が変更した場合だけ競合として列挙し、次を選択できる。

- 自分の変更を破棄して最新版を表示する。
- 競合箇所だけ最新版を採用し、重ならない変更は統合する。
- 競合箇所だけ自分の入力を採用し、重ならない変更は統合する。

統合結果は即時確定せず「未保存」としてCanvasへ戻し、利用者が内容を確認してから再保存する。409には`updated_by`、`updated_at`、`revision`を含め、誰のどの版と競合したかを表示する。

### 6.1 設置ビューのライブpresence

保存競合が起きる前に相手の存在を伝えるため、Hubは`field_id`単位の一時roomを持つ。roomは次だけを保持し、layout本文や未保存入力は保持しない。

- タブごとのランダムな`client_id`。
- Hubが認証情報から確定したemail。
- 開いている空間、選択中の配置物。
- `viewing`、`editing`、`saving`、`conflict`の状態。
- 最終heartbeatと、最新版layoutのrevision・更新者・更新日時。

ブラウザは表示中に約2秒、非表示時に約8秒間隔で短いHTTP同期を行う。30秒heartbeatがない参加者は期限切れとする。通信失敗時は「再接続中」と表示するだけで入力や保存を無効化しない。

最新版revisionを検出したクライアントは既存GETでlayoutを取得する。未編集なら置換し、未保存変更があれば`base / local / server`の三者比較を行う。非重複変更は自動統合し、同一項目だけを競合ダイアログへ送る。保存直前に競合した場合も同じ処理を使い、非重複なら1回だけ自動再保存する。

presenceは現在の単一Hubプロセス内だけで共有する補助UXであり、永続化・排他・正本ではない。Hub再起動、通信断、複数プロセスでは消失または分断してよい。正しさは従来どおりrepositoryのファイルロック、revision、409で保証する。将来WebSocketや外部room coordinatorへ移す場合も、このpresence snapshot契約と保存APIは維持する。

## 7. 現行JSON repositoryの排他

設置ビュー、圃場・記録、栽培計画、デバイス設定は同一Hubホスト上の複数スレッド・複数プロセスを考慮し、共通JSON repository I/O層で次を実施する。設置ビューはこれにrevision競合検出を加える。

- OSファイルロック取得後に正本を再読込する。
- revision比較、更新、保存を同じロック内で行う。
- 同一ディレクトリの一時ファイルへ書き、`fsync`後に`os.replace`で原子的に置換する。
- JSON破損とlost updateを回帰試験する。

この方式は単一Hubホストには有効だが、複数Hubノードや共有不能なファイルシステムをまたぐ排他には使えない。会社ごとに1台のHubを置く現行構成では実用上の境界を満たす。将来Hubを水平分割する場合は、配置、圃場、定植、記録もTursoへ移し、条件付きUPDATEまたはトランザクションでrevisionを管理する。

## 8. 起動と同期

Tursoのlocal replica初期同期とschema準備はHTTP受付前の `initialize_web_server()` で行う。個人設定テーブルもここで準備する。ページ表示のたびに初期同期やschema作成を行わない。

起動後の書き込みはローカルDBへcommitした後に同期する。競合判定は同一Hub内のローカルトランザクションで即時に行い、ページレンダリングをリモート同期完了待ちにしない。

## 9. 回帰試験

- 同じemailのversion 0を2画面から保存すると、1件だけ成功し1件が409になる。
- emailが異なる個人設定は互いに変更されない。
- legacyな`locale`入力を送っても日本語固定の契約が変わらない。
- 栽培アドバイス習熟度はemailごとに分離され、未知の値を保存できない。
- 初回計画、再生成、作業完了後の差分生成へ同じ利用者の習熟度が渡る。
- 同じ設置ビューのrevision 0を2リポジトリから同時保存すると、1件だけ成功し1件が409になる。
- 409応答に最新版、更新者、revisionが含まれる。
- 重ならない配置変更は自動統合できる。
- 同じ項目の変更は採用する版を利用者が選べる。
- 共同編集bodyに別emailを指定しても、presenceには認証済みemailだけが記録される。
- 同じ圃場の複数タブは別clientとして保持され、別圃場とは混ざらず、期限切れと退出で除去される。
- 2画面で参加者と遠隔選択が表示され、非重複の未保存変更を保ったまま相手の保存を自動統合できる。
- 管理者以外は`/settings`、AI接続確認、legacyを含む機器状態・runtime config・OTA/F/W更新APIへアクセスできない。
