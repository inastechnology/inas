# Hub Operations API Discord承認方針

## 1. 状態

この文書は将来実装の方針を定める。Discord承認フローは未実装であり、現行のHub Operations APIの挙動を変更しない。

現行機能は次のとおり。

- Cloudflare Access Service TokenとHub側service ID allowlistによる機械認証
- 読み取り、firmware artifact登録、OTA rolloutのdry-runと適用
- Hubまで到達したOperations API認証拒否のDiscord通知

本方針は認証失敗通知とは別に、認証済み主体によるセンシティブな操作へ人の承認を追加するものである。

## 2. 目的

Operations APIの申請権限、Discord上の承認権限、Hubの実行権限を分離する。Service Tokenが漏えい、誤設定、または誤操作された場合でも、実機や運用状態を直ちに変更できない境界を設ける。

目標とする分離は次のとおり。

```text
Codex / CI / 運用スクリプト: 操作を申請できるが承認できない
Discord承認者: 内容を確認し許可・不許可を決められるが内容を変更できない
Hub: 承認済みの保存内容だけを一度実行する
```

## 3. 承認レベル

すべてのOperations APIを承認待ちにしない。副作用と回復可能性に応じて分類する。

| レベル | 操作例 | 方針 |
|---|---|---|
| 低 | health、デバイス・圃場・作業の読み取り、dry-run | 承認不要 |
| 中 | OTA更新予約、runtime config保存・push、運用設定変更 | Discordで1名承認 |
| 高 | 即時潅水、全台一括更新、デバイス無効化・廃止、不可逆な削除 | Discordで2名承認または管理者限定 |

firmware artifactの登録は実機へ影響しないため原則承認不要とし、artifactを対象デバイスへ割り当てるrolloutを承認対象とする。artifactの上書きを許す場合は別途中リスクとして扱い、基本は変更ごとに新しいversionを使用する。

## 4. 処理モデル

センシティブな要求はその場で実行せず、immutableな承認申請を作成して`202 Accepted`を返す。

```text
Operations API request
  -> 入力検証と対象解決
  -> canonical payloadとSHA-256を保存
  -> approval_idを発行
  -> Discordへ承認カードを送信
  -> 人が許可または不許可
  -> Discord Interaction署名と承認者権限を検証
  -> 保存済みpayloadだけを一度実行
  -> API、Discord、監査ログへ結果を反映
```

申請作成応答の例:

```json
{
  "approval_id": "apr_01JEXAMPLE",
  "state": "pending",
  "operation": "firmware_rollout",
  "target_count": 1,
  "expires_at": "2026-07-22T14:00:00+09:00"
}
```

申請状態は次の状態機械で管理する。

```text
pending -> approved -> executing -> completed
       \-> rejected
       \-> expired
       \-> notification_failed
approved/executing -> failed
```

終端状態から`executing`へ戻さない。同じ`approval_id`の再送、二重クリック、再試行による二重実行を防ぐ。

## 5. 承認内容の固定

申請時に対象を具体的なresource IDへ解決し、canonical JSONとhashを保存する。承認後にdevice kind検索などを再実行して対象を拡大しない。

```json
{
  "operation": "firmware_rollout",
  "device_kind": "WTR",
  "version": "0.0.4",
  "device_ids": ["INADS-..."],
  "artifact_sha256": "d910c27b..."
}
```

Discord表示、承認レコード、実行時payloadのhashが一致しない場合は実行を拒否する。申請後に対象resourceの状態やartifactが変化した場合も、実行直前のprecondition検証で失敗させ、新しい申請を要求する。

## 6. Discord境界

送信専用Webhookではボタン操作を受信できないため、将来実装ではDiscord ApplicationのInteractions endpointを使用する。

- Discord署名を公開鍵で検証する。
- timestampの許容範囲を検証し、replayを拒否する。
- `custom_id`だけを承認根拠にしない。
- Discord user IDとrole allowlistを照合する。
- Service Token主体とDiscord承認者を別の監査主体として保存する。
- Discord表示でJWT、Client ID、Client Secret、request bodyの秘密値を公開しない。
- `allowed_mentions`を無効にし、攻撃者入力による意図しないmentionを防ぐ。

Discordカードには、操作種別、申請主体、対象名とID、変更前後、対象数、artifact hash、有効期限を表示する。承認者が確認できない情報を省略したまま許可させない。

## 7. 有効期限とfail-closed

推奨する初期TTLは次のとおり。

| 操作 | TTL |
|---|---:|
| 即時潅水・出力 | 3分 |
| OTA更新予約 | 15分 |
| runtime config push | 10分 |
| デバイス廃止 | 10分 |

Discord送信失敗、Interaction署名不正、承認者不明、期限切れ、payload hash不一致、precondition不一致の場合は実行しない。Discord障害時にOperations Service Tokenだけで承認を迂回できるfallbackを設けない。

緊急操作が必要な場合は、対象ホスト上のローカル管理者など、Operations APIとは異なる認証・監査境界で別途定義する。

## 8. 監査要件

最低限、次を追記型で保存する。

- approval ID、operation type、risk level
- 申請主体のService Token `common_name`
- canonical payload hashと対象resource ID
- 申請・通知・承認・拒否・期限切れ・実行開始・実行結果の時刻
- Discord承認者user IDと承認時role
- 実行結果、失敗理由、関連するdevice eventまたはcommand ID
- Cloudflare Ray IDなどの通信相関ID

秘密値は保存しない。既存レコードを上書きして履歴を消さず、状態遷移イベントを追記する。

## 9. 想定コンポーネント

将来実装では次を分離する。

- `OperationApprovalService`: policy判定、申請、承認、実行orchestration
- approval repository: immutable payload、状態、TTL、監査イベント
- operation executor: operation typeごとに既存Hub serviceを呼ぶ
- Discord adapter: カード送信・更新
- Discord Interaction route: 署名検証と承認入力
- Operations API: 申請作成と状態取得
- cleanup task: 未処理申請の期限切れ処理

Flask routeへ業務判断や直接的なdevice操作を置かない。圃場系・作業系・デバイス系のexecutorは分け、共通の承認policyと監査契約を使う。

## 10. 段階導入

1. approval repository、状態取得API、監査ログを実装する。
2. OTA rolloutの`dry_run=false`だけを1名承認へ移行する。
3. Discord Application署名、approver allowlist、カード更新を本番検証する。
4. runtime config pushを承認対象へ追加する。
5. 即時潅水などの高リスク操作を2名承認で追加する。
6. 圃場系・作業系は操作ごとにrisk levelをレビューして追加する。

各段階で、Discord障害、期限切れ、二重クリック、再送、承認直前の対象変更、executor失敗をテストする。

## 11. 非目標

- DiscordをHubの主認証基盤にしない。
- Discordメッセージを永続的な監査台帳の代わりにしない。
- 読み取りやdry-runまで一律承認制にしない。
- 承認者が申請payloadを書き換えられるようにしない。
- Cloudflare AccessまたはHub側Service Token allowlistをDiscord承認で代替しない。

## 12. 関連文書

- [Hub Agentic Farm Operations Policy](HUB_AGENTIC_FARM_OPERATIONS_POLICY.md)
- [Hub環境設定](ENVIRONMENT.md)
- Operations API skill: `.agents/skills/manage-hub-operations/SKILL.md`
