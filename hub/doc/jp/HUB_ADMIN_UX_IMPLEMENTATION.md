# Hub Admin UI UX 改善 実装方針

作成日: 2026-07-02

詳細な画面階層、タブ構成、ワイヤーフレームは
[HUB_ADMIN_UI_SCREEN_SPEC.md](HUB_ADMIN_UI_SCREEN_SPEC.md) を参照する。

設置エディタの画面、操作、API、空間モデルは
[HUB_INSTALLATION_LAYOUT_SPEC.md](HUB_INSTALLATION_LAYOUT_SPEC.md) を参照する。

TOPから圃場、設置物、デバイスへ進む階層と大量件数への対応は
[HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md](HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md) を参照する。

## 1. 目的

`/mqtt-devices` は MQTT device の管理機能を一通り持っているが、現状は英語の変数名、raw JSON、API 操作用フォームが前面に出ており、営農者が見たい情報にすぐ到達しづらい。

WTR/WRS の状態は、利用者が圃場を選択した後、その圃場の運用情報として次を即座に確認できることを優先する。TOPには水やり機を直接表示しない。

- 水やりがいつ、どれくらい実行されたか。
- 土壌水分と灌水しきい値。
- 次にいつ起きるか、最後にいつ通信したか。
- 予約されている水やり時刻。
- OTA 更新が必要か、更新中か。

## 2. UX 方針

- 営農者向けの主表示では、日本語の業務語を使う。例: `watering_started` ではなく「灌水」、`next_sleep_sec` ではなく「次回起床」。
- JSON は初期表示の主役にしない。必要な項目をカード、リスト、履歴に parse して表示する。
- raw JSON と状態操作は `履歴・診断` タブへ移動し、初心者が最初に見る画面からは下げる。
- OTA対象設定、更新履歴、F/Wファイル登録は `F/W更新` タブへ集約し、診断情報と混在させない。
- API route と既存 JS 操作は壊さない。既存の `id` / form は保持して、表示構成だけ改善する。
- 色は状態を補助する目的に限定する。正常、注意、停止、保守を区別する。

## 3. 情報設計

### 3.0 TOP

TOPは圃場の検索・選択に限定する。圃場名・所在地検索、都道府県・設置環境フィルタ、18件単位のページングを提供し、全国のデバイス、カメラ、テレメトリを取得しない。

利用者は `TOP → 圃場詳細 → 設置物 → デバイス機能` の順に進む。保守担当者向けのデバイス検索は将来の専用画面とし、TOPに全デバイス一覧を置くことで代用しない。

### 3.1 一覧

登録 device 一覧は、device ID よりも状態把握を優先して表示する。
一覧はカード型のサマリに限定し、詳細情報や保守操作を同じ画面には置かない。カードを選ぶと `/mqtt-devices/<device_id>` の機器詳細へ遷移する。

- 表示名: device name があれば優先。なければ device ID。
- 種別: `WTR` は「水やり機」。
- 稼働状態: active / pending / disabled / retired を日本語化。
- 最終通信。
- 水やり状態。
- 土壌水分。
- 次回起床。
- 現在 firmware / 目標 firmware。

### 3.2 選択 device の概要とタブ

選択 device の先頭には、その機器種別で取得できる現在値と通信・F/W状態を出す。WTR/WRSは潅水と土壌系、ENVは気温・湿度・PAR、SOIは土壌水分・地温・EC・pH、PARはPAR値を優先する。

- 潅水: 実行中 / 潅水予定 / 待機中 / 不明。
- 土壌水分: `%` 表示。しきい値があれば併記。
- 次回起床: status 受信時刻 + `next_sleep_sec`。
- 最終通信: 経過時間付き。
- firmware: 現在 version と更新目標。

機能は次の5タブに分ける。タブ名だけで目的の場所を判断できる名称にする。

- `概要`: 設置場所、潅水系統、予約、通信・F/W状態。
- `計測・稼働`: 機器別時系列グラフ、潅水記録、起動・通信履歴。
- `動作設定`: 表示情報、runtime config、MOSFET SW、予約、センサー校正。
- `F/W更新`: OTA対象、現在/目標F/W、更新履歴、F/Wファイル管理。
- `履歴・診断`: 機器状態操作、runtime config JSON、status/OTA/MQTT raw履歴。

`?tab=settings` などのqueryでタブを直接開けるようにし、圃場画面とグラフ見出しの歯車アイコンは対象機器の `動作設定` を開く。

### 3.3 計測・稼働

status history は raw JSON ではなく、時系列のリストとして表示する。

- 「潅水推移」: Plotly の時系列グラフで `watering_started`, `watering_due`, `watering_duration_sec`, `channel_mask` を使い、いつ、どれくらい潅水したかを表示する。
- 「土壌水分推移」: Plotly の時系列グラフで `last_soil_moisture` と `threshold` を表示する。
- ENVは気温、湿度、PAR、SOI/WRSは取得可能な土壌水分、地温、EC、pH、PARを同じ操作体系で表示する。
- 各推移には、直近3日、2週間、1か月、全期間、カスタムの表示期間を用意する。
- グラフ見出しは `<機器名> / <計測項目>推移` とし、横の歯車アイコンから対象機器の `動作設定` を開く。
- 「起動・通信履歴」: `received_at`, `seq`, `next_sleep_sec`, `config_received`, `time_synced` を使う。

### 3.4 F/W更新と診断

F/W更新タブに置くもの:

- 現在F/W、更新目標、OTA状態。
- OTA target edit。
- OTA更新履歴。
- firmware artifact uploadと登録済みartifact。

履歴・診断タブに置くもの:

- device 承認 / 停止 / 廃止。
- runtime config JSON edit / push。
- status / OTA / MQTT event の raw JSON。

## 4. 実装方針

- `web_server.py` の `/mqtt-devices` route は維持する。
- `/mqtt-devices` は既存の保守URLとして維持するが、TOPの主導線には置かない。
- `/mqtt-devices` は一覧専用、`/mqtt-devices/<device_id>` は詳細専用にする。
- 既存の `/mqtt-devices?device_id=...` は詳細 path へ redirect して互換性を保つ。
- Python 側で view model を作り、Jinja template は parse 済みの日本語ラベルを表示する。
- Plotly グラフは server side で HTML fragment を生成し、詳細ページに埋め込む。
- route固有の薄いhelperだけを `web_server.py` に置く。TODO、記録カレンダー、状態ダッシュボードなど複数データを組み立てる表示処理は `field_*` 表示モデルへ分離し、Flaskに依存させない。
- 永続データ構造は表示都合で変更せず、repositoryと表示モデルの間で責務を分ける。
- Tursoのlocal replica初期同期、計測テーブル準備、センサー指標定義のupsertはHTTP受付前の起動フェーズで完了させる。初回ページ要求をリポジトリ初期化の起点にしない。
- 圃場詳細はFlask/Jinjaのstreaming SSRを使用し、`ヘッダー・タブ・読込状態`、`現在状態・設置・環境`、`月次記録・栽培履歴`の順に送信する。月次計測やグラフ生成の完了まで先頭HTMLを保留しない。
- streaming responseには`X-Accel-Buffering: no`を付け、中継プロキシによるレスポンスバッファリングを抑止する。最終HTMLはサーバ側で完結させ、JavaScriptが無効でも主要情報を参照できる状態を維持する。
- テストは Flask test client で HTML を検証する。
- streaming SSRは、先頭チャンク生成時に圃場contextを未生成であること、月次記録生成前にprimary sectionを送信済みであることをチャンク単位で検証する。
- 実データがない環境でも UI/UX を確認できるように、固定 fixture のデモページ `/demo/mqtt-devices` を用意する。
- デモページは表示確認専用とし、保存・送信・firmware upload の fetch は実 API に到達させない。
- ローカル確認用に `scripts/run_admin_demo_server.py` を用意し、Flask web UI のみを `127.0.0.1:39251` で起動できるようにする。

## 5. テスト観点

- WTR device が「水やり機」、WRS device が「RS485全部入り水やり機」と表示される。
- 一覧ページではカードのサマリだけを表示し、灌水履歴や保守フォームは表示しない。
- 詳細ページでは潅水履歴、環境計測、起動履歴、OTA履歴、診断操作を目的別タブに表示する。
- status payload が raw JSON ではなく、「潅水」「土壌水分」「気温」「湿度」「PAR」「次回起床」「起動・通信履歴」として表示される。
- 各時系列グラフに直近3日、2週間、1か月、全期間、カスタムのレンジ操作が見える。
- 潅水実行履歴に時刻、実行時間、系統が表示される。
- グラフの設定アイコンから同一機器の `動作設定` タブを開ける。
- F/W関連操作が `F/W更新` タブにまとまり、raw履歴は `履歴・診断` に分離されている。
- 既存の保守操作 ID が残り、firmware upload / runtime config / OTA target 操作が利用可能なまま。
- raw JSON は `履歴・診断` 内に残る。
- デモページは「デモデータ表示中」と表示し、fixture の WTR、灌水履歴、OTA 履歴、firmware URL を描画する。
