# デバイス定義仕様

English version: [../DEVICE_DEFINITION_SPECIFICATION.md](../DEVICE_DEFINITION_SPECIFICATION.md)

## 目的

デバイス定義（Device Definition）は、ファームウェア製品が「何を測れるか・何を動かせるか・何を設定できるか・Hub に何を表示するか」を Hub へ伝える静的な決まり事である。実行中の Hub をファームウェアのソースディレクトリへ依存させず、機器の実装、設定 JSON、UI の整合性を保つ。

用語は次のように固定する。

- **デバイス定義**: ファームウェアプロジェクトが所有する製品の静的な決まり事。
- **Runtime Config**: Hub が機器単位で保存し、MQTT で機器へ送る JSON。
- **設置設定**: 接続した設備の名前、設置場所、オプションセンサーを使用するかなど、Hub DB に保存する利用者の選択。

## 目標

- 対応センサー、出力、操作、状態値、Runtime Config の形は各ファームウェアプロジェクトを正とする。
- Hub 側の固定リストではなく、登録済みデバイス定義から機器画面を構築する。
- 製品が対応する値は未取得でもすべて表示し、`未接続`、`未取得`、取得済みの値を区別する。欠損値を `0` と表示しない。
- 通常利用者には電子回路・通信方式の用語を見せない。安定したスロット ID、端子、mask、bus、pin は通常画面で編集させない。
- 移行時に既存 DB の設定値を失わない。

## 対象外

- デバイス定義だけでファームウェアの制御ロジックを追加・変更しない。
- ファームウェア側の入力検証や安全停止を置き換えない。
- 任意の電子回路を定義する仕組みにはしない。用途固定の出力は固定し、汎用出力でもファームウェアが対応する設備種別だけを選択可能にする。
- Hub の実行時にファームウェアディレクトリを直接読まない。

## 所有場所とファイル

各ファームウェアプロジェクトが `hub-definition/` を所有する。

```text
client-devices/<device>/hub-definition/
  device.json
  runtime-config.schema.json
  status.schema.json
  ui.json
  actions.json
```

`device.json` は機種情報、センサースロット、用途固定または用途選択可能な出力スロット、他ファイルへの参照を持つ。スロット ID は変更しない機械用キーであり、上級者向け診断以外では表示しない。

ビルドスクリプトが各ファイルを検証・結合し、Hub パッケージ内に生成済みレジストリを作る。本番 Hub はこのレジストリを使用し、ファームウェアのソースツリーを必要としない。

## 実行時の流れ

```text
firmware project/hub-definition
              |
              | build and validate
              v
      generated hub registry
              |
       +------+------------------+
       |                         |
       v                         v
 definition-driven UI     Runtime Config projection
       |                         |
       | user choices            | device-kind keys only
       v                         v
 existing hub database       MQTT reply/push
```

Hub は互換性のため、既存の保存済み設定オブジェクトをそのまま保持する。MQTT の reply / push の直前に対象機種のデバイス定義を使って送信用 JSON を作る。旧バージョン由来の未知キーは DB から削除しないが、そのキーを宣言していない機種へは送らない。

利用者が変更する設定ではなく製品として常に固定する値は、`runtime-config.schema.json` の `fixed_values` に dot path で宣言できる。固定値は Runtime Config のプレビュー、reply、push で既存の保存値より優先する。各 path の先頭キーは `send_keys` に含める。

## UI 原則

- 通常画面では「給水ポンプ」「攪拌ポンプ」「土のセンサー」のように、農作業として理解できる名前と絵を使う。スイッチ素子や通信アドレスの名称を主画面に出さない。
- 最初に現在の設置状態を閲覧し、そこから明示的に編集へ進む二段構成にする。
- FGT の用途固定出力は付け替え不可とする。WTR / WRS の汎用系統も、各スロットで許可した設備カードからのみ選ばせる。
- オプションセンサーが OFF なら `未接続`、ON だが値がなければ `未取得` と表示する。どちらも製品の対応能力を理解できるようカード自体は表示する。
- 校正は手順付きモーダルで実行し、調整済みの値を操作ボタンに要約する。
- 上級者設定で診断値を表示しても、変更できるのは定義で許可した値だけとする。
- 予約で出力を動かす製品は `ui.scheduled_operation` に、有効条件、予約、出力プログラム、必須出力の path を宣言できる。Hub は実行できる予約と出力されない予約を区別し、動作しない設定を保存・送信する前に警告する。

## 既存 DB との整合性と異常時

- デバイス定義の導入時に既存 DB 行を書き換えない。
- 未知の機種は小さな読み取り専用フォールバック表示を使い、既存設定経路を保持する。
- 定義ファイルの欠落や不正はレジストリ生成時に失敗させる。実行中の Hub は機器やネットワークから未検証の定義を受け取らない。
- `definition_version` は表示・送信射影の版、`schema_version` は定義ファイル形式の版とする。Runtime Config の互換性と安全性は引き続きファームウェアが最終責任を持つ。

## 実装・完了条件

1. 対応する全ファームウェアプロジェクトへデバイス定義を追加する。
2. Hub 用レジストリを生成し、定義を検証する。
3. 機種名、センサーカード、グラフ、出力カード、編集可能セクションをレジストリから構築する。
4. MQTT reply / push の JSON を `runtime_config.send_keys` に従って機種別に射影する。
5. レジストリ網羅性、未取得表示、用途固定スロット、既存 DB 値の保持、機種別 MQTT payload の回帰試験を追加する。
6. 登録済み全機種を Hub デモで開き、画面キャプチャを取得して目視確認し、Runtime Config プレビューと期待キーを比較する。

## 関連文書

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md)
- [ARCHITECTURE_LAYERING_POLICY.md](ARCHITECTURE_LAYERING_POLICY.md)
- [../../hub/doc/jp/HUB_ADMIN_UX_IMPLEMENTATION.md](../../hub/doc/jp/HUB_ADMIN_UX_IMPLEMENTATION.md)
