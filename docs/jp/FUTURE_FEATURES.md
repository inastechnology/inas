# INAS 将来機能・コミュニティ提案一覧

更新日: 2026-07-22

英語要約: [../FUTURE_FEATURES.md](../FUTURE_FEATURES.md)

## 1. 目的

この文書は、これまでに検討したが、利用可能な機能として完成していない項目を見える形で残す台帳である。将来は利用者やコミュニティから寄せられた提案も同じ形式で追加し、問題、期待する効果、根拠、検討状況、採否理由を公開できるようにする。

ここはリリース予定日を約束するロードマップでも、開発スプリントのバックログでもない。詳細仕様はHub、client device、Extension等の所有レイヤに置き、この一覧からリンクする。実装された項目も無言で削除せず、完了条件を確認して履歴へ移す。

## 2. 状態

| 状態 | 意味 |
|---|---|
| `concept` / 構想 | 解決したい問題と期待結果はあるが、詳細仕様は未確定 |
| `specified` / 仕様あり | レビュー可能な仕様があるが、目的とする機能は未完成 |
| `partial` / 一部提供 | 基盤または一部機能は利用できるが、一覧に記載した結果には未到達 |
| `gated` / 条件待ち | 安全、セキュリティ、法務、外部許諾、運用実証等の前提が必要 |
| `implementing` / 実装中 | 対応するIssue、PR、作業計画を明示して実装中 |
| `released` / 提供済み | 完了条件を満たし、利用可能であることを検証済み |
| `declined` / 見送り | 採用しない理由と再検討条件を記録済み |

`specified` は実装済みを意味しない。`partial` も、残りを自動的に実装すると約束する状態ではない。

## 3. 将来機能一覧

### 栽培判断・圃場作業

| ID | 将来実現したいこと | 状態 | 出典・詳細 |
|---|---|---|---|
| `FUT-001` | 点滴口を1穴ずつ測る吐出量校正、生育・天候に応じた潅水提案、排液ECを使った培地リセット | 仕様あり | [点滴潅水の吐出量校正・潅水提案・培地リセット仕様](../../hub/doc/jp/HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md) |
| `FUT-002` | 肥料カタログ、土壌・培地検査、残効信頼度、過剰を避ける施肥候補 | 仕様あり | [施肥計画・肥料サジェスト実装方針](../../hub/doc/jp/HUB_FERTILIZATION_RECOMMENDATION_POLICY.md) |
| `FUT-003` | カレンダー作業、センサー・画像・気象判断、設備保守、定期作業、利用者登録作業を一つの圃場TODOへ統合 | 一部提供 | [作物前提データと改善ループ](../../hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md) |
| `FUT-004` | 公的な作物知識、画像観察、気象・積算温度による予定調整を、出典と適用条件付きで利用 | 構想 | [植物管理カレンダー仕様](../../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |
| `FUT-005` | 利用許諾を確認したデータ提供元から、農薬登録、作物適用、希釈倍率、使用回数、収穫前日数を検索 | 条件待ち | [植物管理カレンダー仕様](../../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |
| `FUT-006` | FGTの液肥レシピ編集、手動承認、実行、状態・履歴確認を営農者向け画面から操作 | 仕様あり | [全体仕様](SYSTEM_SPECIFICATION.md)、[FGT設計概要](../../client-devices/fertigation-device/docs/jp/README.md) |
| `FUT-007` | 湿度等から噴霧候補を作り、安全能力を宣言した将来デバイスで実行 | 構想 | [作物前提データと改善ループ](../../hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md) |

### チーム・コミュニティ

| ID | 将来実現したいこと | 状態 | 出典・詳細 |
|---|---|---|---|
| `FUT-101` | 圃場単位のメンバー、招待、役割、作業割当、確認、引継ぎ | 仕様あり | [圃場作業の確認と将来の報酬連携](../../hub/doc/jp/WORK_VERIFICATION_AND_COMPENSATION_DESIGN.md) |
| `FUT-102` | 作業完了と送金を分離した追記型の報酬台帳 | 条件待ち | [圃場作業の確認と将来の報酬連携](../../hub/doc/jp/WORK_VERIFICATION_AND_COMPENSATION_DESIGN.md) |
| `FUT-103` | 利用者提案を受付、重複整理、公開レビューし、この台帳へ追加する仕組み | 仕様あり | [コミュニティ提案の流れ](#community-proposal-process) |
| `FUT-104` | 栽培計画の修正例、肥料カタログ、校正例、圃場知見を適用範囲と信頼度付きで共有 | 条件待ち | [施肥計画方針](../../hub/doc/jp/HUB_FERTILIZATION_RECOMMENDATION_POLICY.md)、[植物管理カレンダー仕様](../../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |

### 運用・管理

| ID | 将来実現したいこと | 状態 | 出典・詳細 |
|---|---|---|---|
| `FUT-201` | Operations APIのセンシティブな操作をDiscordで人が承認してから実行 | 仕様あり | [Hub Operations API Discord承認方針](../../hub/doc/jp/HUB_OPERATIONS_DISCORD_APPROVAL_POLICY.md) |
| `FUT-202` | 営農TOPと分離した、デバイスID、状態、所属圃場、設置先、交換状態の保守検索 | 仕様あり | [圃場リソース階層仕様](../../hub/doc/jp/HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md) |
| `FUT-203` | 複数Hubノードで共有できる状態管理と、DBトランザクションによる同時編集制御 | 条件待ち | [ユーザー設定・同時編集設計](../../hub/doc/jp/HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md) |
| `FUT-204` | Sync v1による親Hub・Cloud Hubとの機器状態・command同期。設定・firmwareを含む遠隔運用全体は未完成 | 一部提供 | [Cloud Hub](../../hub-cloud/README.md)、[Local Hub階層Sync](../../hub/doc/jp/HIERARCHICAL_SYNC.md) |

### Extension・外部貢献

| ID | 将来実現したいこと | 状態 | 出典・詳細 |
|---|---|---|---|
| `FUT-301` | Hub所有フォームを使うExtension設定項目と、名前付き導線から開く独立ページ | 条件待ち | [Extension仕様](EXTENSION_SPECIFICATION.md) |
| `FUT-302` | 署名、権限、隔離実行、失効、ロールバックを備えた実行可能Extension | 条件待ち | [Extensionセキュリティレビューポリシー](EXTENSION_SECURITY_REVIEW_POLICY.md) |

### 自動化・将来機器

| ID | 将来実現したいこと | 状態 | 出典・詳細 |
|---|---|---|---|
| `FUT-401` | センサー、天気、実流量、実施結果から潅水量と時刻を閉ループ調整 | 仕様あり | [エージェンティック農作業の実装方針](../../hub/doc/jp/HUB_AGENTIC_FARM_OPERATIONS_POLICY.md) |
| `FUT-402` | 定植、剪定、収穫等を、必要能力と到達範囲が一致する人・固定設備・ロボットへ割り当て | 構想 | [エージェンティック農耕ビジョン](AGENTIC_AGRICULTURE_VISION.md) |

## 4. 一覧へ載せる単位

一覧には「ボタンを追加する」のような実装手段だけでなく、利用者が解決したい問題と確認可能な結果を書く。一件が大きすぎる場合は、利用者価値が単独で確認できる単位へ分ける。

同じ提案が、次のいずれになるかをレビュー時に分類する。

- Hub coreの再利用可能な作業・判断・保存機能
- client device firmwareまたはDevice Definitionの能力追加
- 宣言型Hub Extension
- 作物・肥料・資材等の出典付き参照データ
- 運用手順またはドキュメント改善
- 現在の製品境界では採用しない提案

作物名、Extension ID、デバイス固有表示、GPIO、外部サービス名を、分類前にHub coreへ直接追加しない。

<a id="community-proposal-process"></a>

## 5. コミュニティ提案の流れ

```text
提案
  → 非公開情報・秘密値の除去
  → 重複確認と既存IDへの関連付け
  → 所有レイヤと影響範囲の分類
  → 安全・根拠・互換性・費用の確認
  → 公開候補として登録
  → 調査・仕様化・採否判断
  → 実装と検証
  → 提供済み履歴へ移動
```

初期段階では、maintainerがドキュメントまたはIssueから手作業でこの台帳へ追加する。将来のHub画面では、利用者が提案を送信し、公開前レビュー、補足質問、重複候補、状態通知を受けられるようにする。

提案時の最小項目は次とする。

```text
title                         提案名
problem                       現在困っていること
expected_outcome              できるようになってほしいこと
field_context                 作物・作型・規模等。公開可能な範囲
current_workaround            現在のやり方。任意
evidence_or_reference_urls    写真、計測、資料。任意
safety_or_failure_concerns    失敗した場合の影響
origin_type                   user | community | maintainer | field_observation | research
public_attribution_consent    名前を公開してよいか
```

登録後は次の管理項目を持つ。

```text
proposal_id                   FUT-nnn
status
scope                         hub | firmware | device_definition | extension | reference_data | docs
submitted_at
last_reviewed_at
related_proposal_ids[]
duplicate_of
governing_document
implementation_issue
maintainer_decision
decision_reason
release_evidence
```

## 6. 公開・プライバシー

- 氏名またはハンドル名の公開は明示同意がある場合だけ行う。既定は匿名の「利用者提案」とする。
- メールアドレス、住所、正確な圃場座標、Access情報、APIキー、service token、device ID、非公開写真を提案本文へ掲載しない。
- 圃場写真やログは、公開範囲を切り分け、必要なら匿名化した要約だけを掲載する。
- 元提案を改変して別の意味にせず、公開要約とmaintainerの判断を分けて保存する。
- 見送り時も提案者を否定する表現を避け、理由と再検討条件を記録する。

## 7. 採否と優先度

コミュニティの支持数は、困っている人の多さを知る材料にはできるが、それだけで自動的に採用・実装順を決めない。次を合わせて判断する。

- 解決する問題の大きさと対象利用者数
- 小規模営農者や初心者が得る効果
- 農作業・電気・機械・薬剤・データに関する安全性
- 公的資料、現地測定、再現可能な検証の有無
- 既存レイヤ、互換性、保守負担、運用費への影響
- core、device、Extension、参照データのどこに置くべきか
- 可逆性と、失敗時に安全側へ停止できるか

潅水、施肥、農薬、OTA、実機出力等の安全に関わる提案は、多数決で安全審査を省略しない。AIによる要約やレビューも補助であり、決定的な検証と人の承認を置き換えない。

## 8. コミュニティから実装を受け入れる場合

提案の採用と、提出されたコードまたはExtensionの採用は別の判断とする。

- core変更は、再利用可能な責務とレイヤ境界を満たし、通常のテスト・レビューを通す。
- firmware変更は、対象device kindの契約、安全状態、ビルド、実機検証を必要とする。
- Device Definition変更は、静的能力とRuntime Configの境界を守る。
- 宣言型Extensionは、許可済みschemaだけを使い、静的検査と管理者による個別インストールを必要とする。
- 実行可能Extensionは、[セキュリティレビューポリシー](EXTENSION_SECURITY_REVIEW_POLICY.md)の前提が完成するまで受け入れない。
- 作物基準・肥料データ・校正例は、出典、適用条件、単位、改訂、検証者を必須にする。

提案を送ったことは、DB、MQTT、GPIO、ネットワーク、filesystem、秘密値への権限を付与するものではない。

## 9. 段階導入

### Phase 1: ドキュメント台帳

- この一覧を正本として、既存構想へ安定IDを付ける。
- 新規提案をmaintainerが確認して追記する。
- 重複、関連、出典文書、採否理由を残す。

### Phase 2: 提案フォームとレビュー

- Hubまたは公開サイトから提案できるフォームを用意する。
- 非公開下書き、公開同意、添付の秘密情報警告、moderator reviewを実装する。
- 提案者へ補足質問、状態変更、重複統合を通知する。

### Phase 3: 関心と現地検証

- 利用者が「同じことで困っている」「試験に協力できる」を表明できるようにする。
- いいね数と、計測条件付きの現地検証結果を別に扱う。
- 地域、作物、作型、設備が異なる検証結果を同一条件として集計しない。

### Phase 4: 貢献物の配布

- 出典付き作物データや宣言型Extensionをレビュー・配布できるようにする。
- artifactのversion、digest、publisher identity、互換性、権限、失効を表示する。
- core、firmware、データ、Extensionごとの別々の受入基準を適用する。

## 10. 一覧の更新ルール

1. 新規項目には変更しない `FUT-nnn` を付ける。
2. タイトルが変わってもIDは再利用しない。
3. 重複提案は削除せず `duplicate_of` で代表項目へ結ぶ。
4. 詳細仕様ができたら所有レイヤの文書へリンクする。
5. 実装開始時はIssueまたは作業計画をリンクし、`implementing`へ変更する。
6. `released`へ移す前に、完了条件、テスト、利用者向け入口を確認する。
7. 見送りは理由と再検討条件を記録し、提案履歴を消さない。
8. 少なくとも大きなリリース時に一覧と出典文書の状態を照合する。

## 11. 提案テンプレート

```markdown
### 提案名

### 困っていること

### できるようになってほしいこと

### 作物・作型・設備などの前提

### 現在のやり方（任意）

### 計測結果・写真・参考資料（任意）

### 失敗した場合に心配なこと

### 公開時の名前表示

- [ ] 匿名を希望する
- [ ] 表示名を公開してよい
```

秘密値、個人情報、正確な圃場位置、公開できないdevice IDや写真は記載しない。

## 12. 提供済み・見送り履歴

現時点では、この台帳で管理を開始した将来項目に `released` または `declined` はない。今後、日付、version、完了確認、採否理由を表形式で追記する。

## 13. 関連文書

- [INAS全体仕様](SYSTEM_SPECIFICATION.md)
- [アーキテクチャレイヤ方針](ARCHITECTURE_LAYERING_POLICY.md)
- [デバイス定義仕様](DEVICE_DEFINITION_SPECIFICATION.md)
- [Extension仕様](EXTENSION_SPECIFICATION.md)
- [Extensionセキュリティレビューポリシー](EXTENSION_SECURITY_REVIEW_POLICY.md)
- [エージェンティック農耕ビジョン](AGENTIC_AGRICULTURE_VISION.md)
