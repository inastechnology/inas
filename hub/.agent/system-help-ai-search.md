# Cloudflare AI Search を使ったシステムヘルプ検索

この計画は進行中に更新する。`Progress`、`Discoveries`、`Decision Log`、`Outcomes` は作業に合わせて維持する。

## Purpose

Hub の栽培相談とは分離したシステムヘルプ検索層を評価する。共有Cloud Hubを
廃止したため、検索を製品化する場合はLocal Hubから呼ぶ任意connectorまたは
独立した認証済みserviceとして再設計し、顧客業務DBとは分離する。

## Progress

- [x] (2026-07-22) 既存の栽培チャット、Cloudflare Worker、文書群、レイヤ境界を調査した。
- [x] (2026-07-22) Cloudflare AI Search の現行 API、Workers binding、ハイブリッド検索、Items API を公式仕様で確認した。
- [x] 利用者向けシステムヘルプ文書と登録マニフェストを作成した。
- [x] Worker に認証済み検索 API と単体テストを追加した。
- [x] 文書同期・索引・評価を再現できるスクリプトを追加した。
- [x] ローカルのテスト22件と型検査を完了した。
- [x] Cloudflare を再認証し、AI Search インスタンスとR2バケットを作成して6文書を登録した。
- [x] 代表質問9件を実行し、検索設定を改善して9/9成功を確認した。
- [x] Workerの既存デプロイがないことを確認した。
- [x] (2026-07-23) 管理付きLocal Hub方針への変更に伴い、未deployのWorker API、
  binding、同期scriptをrepoから削除した。既存AI Search/R2 resourceはこの変更で
  操作せず、将来の明示的な再設計まで製品経路から使用しない。

## Discoveries

- 現在の栽培チャットは圃場、作付け、カレンダー、提案、肥料履歴、過去質問を直接 LLM に渡しており、文書検索は持たない。
- 現在の質問ポリシーは栽培・農作業・圃場機器以外を拒否するため、システムヘルプは別 API / UI として扱う必要がある。
- 旧`hub/cloudflare` Hono/Turso試作は未deployであり、管理付きLocal Hub方針では
  不要になった。
- Wrangler の保存済み OAuth セッションは期限切れで、実リソース操作前に再ログインが必要である。
- Cloudflare AI Search の instance binding は `ai_search` で設定し、`search()` は文書チャンク、スコア、source key を返す。

## Decision Log

- AI Search は回答生成ではなく検索層として使う。検索結果を Hub 側の既存 LLM と組み合わせられるよう、Worker API はチャンクと出典を返す。
- 初期文書は既存の開発者向け仕様を丸ごと登録せず、利用者が実際に行う操作とトラブル対応を短い日本語ヘルプとして再構成する。
- AI Search の public endpoint は使わず、Cloudflare Access と Worker 内ロール判定を通した API のみ公開する。
- 検索は日本語の固有 UI 名にも強い hybrid を使い、取得件数と最低スコアを Worker 側で固定する。

## Validation

この実験経路は現在製品に接続していない。再開時は新しい認証境界、Local Hub側の
connector、文書同期、評価set、data保持方針を別ExecPlanで定義してから検証する。

## Outcomes

CloudflareにR2バケット `inas-system-help-docs` とAI Searchインスタンス
`inas-system-help` を作成し、代表質問9/9まで検索品質を確認したが、公開endpointと
Workerは作成していない。共有Cloud Hub廃止後は未使用resourceとして扱い、削除や
再利用は別の明示的な運用判断に委ねる。
