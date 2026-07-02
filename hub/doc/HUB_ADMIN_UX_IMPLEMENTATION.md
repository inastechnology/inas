# Hub Admin UI UX 改善 実装方針

作成日: 2026-07-02

## 1. 目的

`/mqtt-devices` は MQTT device の管理機能を一通り持っているが、現状は英語の変数名、raw JSON、API 操作用フォームが前面に出ており、営農者が見たい情報にすぐ到達しづらい。

WTR は水やりを行うデバイスなので、admin panel の最初の画面では次を即座に確認できることを優先する。

- 水やりがいつ、どれくらい実行されたか。
- 土壌水分と灌水しきい値。
- 次にいつ起きるか、最後にいつ通信したか。
- 予約されている水やり時刻。
- OTA 更新が必要か、更新中か。

## 2. UX 方針

- 営農者向けの主表示では、日本語の業務語を使う。例: `watering_started` ではなく「灌水」、`next_sleep_sec` ではなく「次回起床」。
- JSON は初期表示の主役にしない。必要な項目をカード、リスト、履歴に parse して表示する。
- raw JSON と技術操作は `<details>` の「詳細・保守」へ移動し、初心者が最初に見る画面からは下げる。
- API route と既存 JS 操作は壊さない。既存の `id` / form は保持して、表示構成だけ改善する。
- 色は状態を補助する目的に限定する。正常、注意、停止、保守を区別する。

## 3. 情報設計

### 3.1 一覧

登録 device 一覧は、device ID よりも状態把握を優先して表示する。
一覧はカード型のサマリに限定し、詳細情報や保守操作を同じ画面には置かない。カードを選ぶと `/mqtt-devices/<device_id>` の水やり機詳細へ遷移する。

- 表示名: device name があれば優先。なければ device ID。
- 種別: `WTR` は「水やり機」。
- 稼働状態: active / pending / disabled / retired を日本語化。
- 最終通信。
- 水やり状態。
- 土壌水分。
- 次回起床。
- 現在 firmware / 目標 firmware。

### 3.2 選択 device の概要

選択 device の先頭には、次のカードを出す。

- 灌水: 実行中 / 灌水予定 / 待機中 / 不明。
- 土壌水分: `%` 表示。しきい値があれば併記。
- 次回起床: status 受信時刻 + `next_sleep_sec`。
- 最終通信: 経過時間付き。
- firmware: 現在 version と更新目標。

### 3.3 水やりと起動の履歴

status history は raw JSON ではなく、時系列のリストとして表示する。

- 「灌水推移」: Plotly の時系列グラフで `watering_started`, `watering_due`, `watering_duration_sec`, `channel_mask` を使い、いつ、どれくらい灌水したかを表示する。
- 「土壌水分推移」: Plotly の時系列グラフで `last_soil_moisture` と `threshold` を表示する。
- 灌水推移と土壌水分推移には、直近3日、2週間、1か月、全期間、カスタムの表示期間を用意する。
- 「起動・通信履歴」: `received_at`, `seq`, `next_sleep_sec`, `config_received`, `time_synced` を使う。

### 3.4 詳細・保守

次は `<details>` 内へ移動する。

- device 承認 / 停止 / 廃止。
- metadata edit。
- runtime config JSON edit / push。
- OTA target edit。
- status / OTA / MQTT event の raw JSON。
- firmware artifact upload。

## 4. 実装方針

- `web_server.py` の `/mqtt-devices` route は維持する。
- `/mqtt-devices` は一覧専用、`/mqtt-devices/<device_id>` は詳細専用にする。
- 既存の `/mqtt-devices?device_id=...` は詳細 path へ redirect して互換性を保つ。
- Python 側で view model を作り、Jinja template は parse 済みの日本語ラベルを表示する。
- Plotly グラフは server side で HTML fragment を生成し、詳細ページに埋め込む。
- 追加 helper は `web_server.py` 内に閉じ、永続データ構造は変えない。
- テストは Flask test client で HTML を検証する。
- 実データがない環境でも UI/UX を確認できるように、固定 fixture のデモページ `/demo/mqtt-devices` を用意する。
- デモページは表示確認専用とし、保存・送信・firmware upload の fetch は実 API に到達させない。
- ローカル確認用に `scripts/run_admin_demo_server.py` を用意し、Flask web UI のみを `127.0.0.1:39251` で起動できるようにする。

## 5. テスト観点

- WTR device が「水やり機」と表示される。
- 一覧ページではカードのサマリだけを表示し、灌水履歴や保守フォームは表示しない。
- 詳細ページでは灌水履歴、起動履歴、OTA 履歴、保守操作を表示する。
- status payload が raw JSON ではなく、「灌水」「土壌水分」「次回起床」「起動・通信履歴」として表示される。
- 灌水推移と土壌水分推移が Plotly で表示され、直近3日、2週間、1か月、全期間、カスタムのレンジ操作が見える。
- 灌水実行履歴に時刻、実行時間、系統が表示される。
- 既存の保守操作 ID が残り、firmware upload / runtime config / OTA target 操作が利用可能なまま。
- raw JSON は「詳細・保守」内に残る。
- デモページは「デモデータ表示中」と表示し、fixture の WTR、灌水履歴、OTA 履歴、firmware URL を描画する。
