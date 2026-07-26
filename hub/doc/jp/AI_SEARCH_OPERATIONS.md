# AI Search文書検索の現状

更新日: 2026-07-26

英語要約: [../AI_SEARCH_OPERATIONS.md](../AI_SEARCH_OPERATIONS.md)

## 現在の状態

以前評価したHubのシステムヘルプAI Searchは、現在の製品経路には接続していない。
管理付きLocal Hubを中心とする構成へ変更した際に、未デプロイだったWorker、
AI Search binding、登録manifest、評価データ、同期scriptを
`hub/cloudflare`から削除した。

Cloudflare上に作成したR2 bucketとAI Search instanceは未使用resourceとして扱う。
このリポジトリから同期、再作成、削除、indexing jobの実行は行わない。

## 維持する文書

利用者向けシステムヘルプの正本は `hub/doc/system-help/*.md` とする。
画面、設定、記録、機器管理、トラブル対応、将来機能の説明が変わる場合は、
該当する文書を更新する。

文書では次を守る。

- 現在利用できる機能と将来機能を明確に分ける。
- 内部設計書をそのまま利用者向け文書へ複製しない。
- 操作方法、確認理由、次に行うことを一般利用者向けに説明する。
- 認証情報、正確な圃場位置、非公開device ID、秘密値を含めない。

## 再開に必要な設計

文書検索を製品化する場合は、旧`hub/cloudflare`実装を復元せず、新しい計画で
次を定義してから実装する。

- 認証済みの独立service、またはLocal Hubから明示的に有効化するconnector
- 顧客の業務DBと分離した認可、tenant境界、data保持方針
- 文書の公開、更新、削除、rollback手順
- 差分同期、負荷制御、監視、障害時の扱い
- 実装済み機能と将来構想を取り違えない検索評価
- 検索結果を利用するUIと、栽培相談との責務分離

## 関連文書

- [システムヘルプ文書](../system-help/README.md)
- [INAS 将来機能・コミュニティ提案一覧](../../../docs/jp/FUTURE_FEATURES.md)
- [過去のAI Search評価記録](../../.agent/system-help-ai-search.md)
