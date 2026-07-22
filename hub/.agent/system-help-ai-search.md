# Cloudflare AI Search を使ったシステムヘルプ検索

この計画は進行中に更新する。`Progress`、`Discoveries`、`Decision Log`、`Outcomes` は作業に合わせて維持する。

## Purpose

Hub の栽培相談とは分離したシステムヘルプ検索層を Cloudflare AI Search で構築する。利用者向けに整理した日本語文書だけを登録し、Cloudflare 上の実インデックスへ代表質問を送り、根拠文書と回答可能性を確認する。最終的に、認証済み Cloudflare Worker から検索結果と出典を安全な JSON として取得できる状態にする。

## Progress

- [x] (2026-07-22) 既存の栽培チャット、Cloudflare Worker、文書群、レイヤ境界を調査した。
- [x] (2026-07-22) Cloudflare AI Search の現行 API、Workers binding、ハイブリッド検索、Items API を公式仕様で確認した。
- [x] 利用者向けシステムヘルプ文書と登録マニフェストを作成した。
- [x] Worker に認証済み検索 API と単体テストを追加した。
- [x] 文書同期・索引・評価を再現できるスクリプトを追加した。
- [x] ローカルのテスト22件と型検査を完了した。
- [x] Cloudflare を再認証し、AI Search インスタンスとR2バケットを作成して6文書を登録した。
- [x] 代表質問9件を実行し、検索設定を改善して9/9成功を確認した。
- [x] Workerの既存デプロイがないことを確認した。Access/Turso/custom domainが未設定のため、無効なWorkerは作らず、認証済み検索APIを次回cloud appデプロイへ含める状態にした。

## Discoveries

- 現在の栽培チャットは圃場、作付け、カレンダー、提案、肥料履歴、過去質問を直接 LLM に渡しており、文書検索は持たない。
- 現在の質問ポリシーは栽培・農作業・圃場機器以外を拒否するため、システムヘルプは別 API / UI として扱う必要がある。
- `hub/cloudflare` は Hono + Cloudflare Access + Turso の構成で、`reader` 以上の認証済み利用者向け API を追加できる。
- Wrangler の保存済み OAuth セッションは期限切れで、実リソース操作前に再ログインが必要である。
- Cloudflare AI Search の instance binding は `ai_search` で設定し、`search()` は文書チャンク、スコア、source key を返す。

## Decision Log

- AI Search は回答生成ではなく検索層として使う。検索結果を Hub 側の既存 LLM と組み合わせられるよう、Worker API はチャンクと出典を返す。
- 初期文書は既存の開発者向け仕様を丸ごと登録せず、利用者が実際に行う操作とトラブル対応を短い日本語ヘルプとして再構成する。
- AI Search の public endpoint は使わず、Cloudflare Access と Worker 内ロール判定を通した API のみ公開する。
- 検索は日本語の固有 UI 名にも強い hybrid を使い、取得件数と最低スコアを Worker 側で固定する。

## Validation

ローカルでは `hub/cloudflare` で `npm test` と `npm run typecheck` を実行する。文書同期スクリプトは dry-run とマニフェスト検証を行う。実環境では索引完了後、少なくともセットアップ、デバイス、圃場、栽培カレンダー、権限、障害対応、対象外質問を含む評価セットを実行し、期待する文書が上位に現れるかを確認する。失敗例は文書見出し・語彙・検索しきい値・取得件数を調整して再評価する。

## Outcomes

CloudflareにR2バケット `inas-system-help-docs` とAI Searchインスタンス `inas-system-help` を作成し、6件の日本語システムヘルプを登録した。初回のベクトル検索は7/9、ハイブリッド検索＋日本語再ランキングは2/9だった。再ランキングが正しい日本語候補を過剰に除外していたため、最終設定をハイブリッド検索、再ランキングなし、しきい値0.2、最大5件とし、代表質問9/9で期待文書と必須語句を確認した。公開endpointは使用していない。`ina-device-hub-cloud` WorkerはCloudflare上に未作成で、Access/Turso/custom domainもこのworker設定では未確定なので、検索APIコードとbindingは次回のcloud app初回デプロイへ安全に含める。
