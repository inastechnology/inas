# AI Search文書の更新運用

更新日: 2026-07-22

英語要約: [../AI_SEARCH_OPERATIONS.md](../AI_SEARCH_OPERATIONS.md)

## 目的

HubのAI Searchには、利用者が画面操作、設定、記録、機器管理、現在利用できる機能、明示された将来機能を探すための短い日本語文書を登録する。内部設計書を無条件に全文投入せず、検索結果が実装済み機能と将来構想を混同しないようにする。

## 正本

- 検索文書: `hub/doc/system-help/*.md`
- 登録一覧: `hub/cloudflare/data/system-help-manifest.json`
- 検索評価: `hub/cloudflare/data/system-help-evaluation.json`
- R2 bucket: `inas-system-help-docs`
- AI Search instance: `inas-system-help`

設計の詳細は所有レイヤの仕様書へ置き、AI Searchには利用者が知る必要のある要約だけを書く。将来機能には必ず「将来機能」「未実装」「一部提供」等の状態を明記する。

## 更新が必要な変更

- 画面名、導線、ボタン、設定場所が変わった。
- 利用者向けの登録・記録・保守手順が変わった。
- トラブル時の確認方法が変わった。
- 将来機能一覧またはコミュニティ提案方法が変わった。
- AI Searchの回答評価で、正しい文書を取得できなかった。

内部リファクタ、GPIO、private API、DB実装等、利用者の操作や説明が変わらない変更だけなら検索文書を増やさない。

## ローカル確認

```bash
cd hub/cloudflare
npm run system-help:sync -- --dry-run
```

`--dry-run`は文書の存在、キー重複、見出し、最低文字数を検証し、Cloudflareへ接続しない。

依存関係を用意できるNode 22環境では、Workerの試験も行う。

```bash
npm ci
npm test
npm run typecheck
```

## 低負荷の通常同期

```bash
npm run system-help:sync
```

通常同期は、登録文書ごとにR2上の内容と比較し、変更または追加された文書だけをアップロードする。内容が同じ文書は `unchanged` としてスキップし、AI Search instanceを作り直さない。

Cloudflare AI SearchのR2データソースは、通常6時間ごとのスケジュールで新規・変更・削除ファイルを差分同期する。日常的な文言修正はこの定期同期に任せる。

## 早めに反映する場合

利用者から依頼された修正、誤案内の訂正、公開直後に検索可能である必要がある変更は、関連文書をまとめてアップロードした後、1回だけ差分インデックスを要求する。

```bash
npm run system-help:sync -- --trigger-index
```

`--trigger-index`も、アップロード件数が0件ならjobを作らない。複数文書を一件ずつ同期せず、関連変更を一回にまとめる。状態確認を短い間隔で繰り返したり、同じ内容でjobを再作成したりしない。

全件を意図的に再配置する障害復旧時だけ `--force` を使用する。

```bash
npm run system-help:sync -- --force --trigger-index
```

## 評価

AI Search側の差分同期が完了した後に、代表質問を評価する。

```bash
npm run system-help:evaluate
```

新しい文書には、少なくとも次のケースを追加する。

- 利用者が実際に使う質問表現
- 期待する文書名
- 取得断片に必ず含まれる語
- 実装済みと将来機能を取り違えない質問

評価失敗時にscore thresholdをすぐ下げず、文書の見出し、用語、重複、質問への直接的な回答を先に改善する。

## 障害時

- R2比較に失敗した場合、同期完了と表示しない。
- uploadが一部失敗した場合、インデックスjobを開始せず、原因を解消して再実行する。
- AI Search jobが失敗してもR2文書を削除しない。job logを確認し、同じ内容の連続再実行を避ける。
- 認証情報、account ID、API tokenをログまたは検索文書へ書かない。
- AI Searchが未更新の間も、元のシステムヘルプ文書を正として案内する。

## 関連文書

- [システムヘルプ文書](../system-help/README.md)
- [Cloudflare Cloud App実装方針](CLOUDFLARE_CLOUD_APP_IMPLEMENTATION.md)
- [INAS 将来機能・コミュニティ提案一覧](../../../docs/jp/FUTURE_FEATURES.md)
- [Cloudflare AI Search: Syncing](https://developers.cloudflare.com/ai-search/configuration/indexing/syncing/)
- [Cloudflare AI Search: R2 data source](https://developers.cloudflare.com/ai-search/configuration/data-source/r2/)
