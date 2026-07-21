# Hub Extension 仕様

英語版: [../EXTENSION_SPECIFICATION.md](../EXTENSION_SPECIFICATION.md)

## 目的

Hub Extensionは、デバイス情報、栽培知識、外部連携、補助UIを機能ごとの
フォルダへ分離し、Hub本体の変更範囲を抑えて改善できるようにする仕組みである。
Hubは安定した拡張位置と安全規則を持ち、各Extensionは定義、画像、試験、
表示内容を所有する。

最初のExtension APIは宣言型に限定する。任意のPython、JavaScript、HTMLを
Hubプロセスへ読み込んで実行しない。

## フォルダ構成

```text
extensions/<extension-name>/
  extension.json
  assets/                 # 任意
  tests/                  # 任意
```

`hub/scripts/build_extension_registry.py`が全定義を検証し、実行中のHubが読む
レジストリを生成する。

```text
hub/src/ina_device_hub/extensions/generated/registry.json
```

将来、同じ定義形式のまま各フォルダを別リポジトリへ移動できる。開発時は
`extensions/`へ配置し、本番ではバージョンを固定した成果物を配備前に取り込む。

## UI拡張位置

Version 1では機器詳細画面に次の2種類を用意する。

- `overview_cards`: 日常的に一目で確認する短い補足。設定画面の代用にはしない。
- `tabs`: 独立した作業目的や考え方を持つ、まとまった補助画面。

設定項目の差し込みと大規模な独立ページは、将来の拡張位置として予約する。
表示はHubの共通部品で構築し、スマートフォン対応、キーボード操作、文字サイズ、
コントラスト、HTMLエスケープをHub側で保証する。

Version 1で利用できる表示部品は次のとおり。

- `callout`: 見出しと短い説明。
- `metric_grid`: `device`、`status`、`config`の許可されたパスから取得する値。
- `process_flow`: 見出しと説明を持つ順序付き工程。

## 安全性と互換性

- Extension IDと表示要素IDを検証し、安定した識別子として扱う。
- `compatibility.hub_extension_api`で対応APIを宣言する。
- 未知の表示部品やデータ取得元があれば、レジストリ生成を失敗させる。
- 値はHubが解決し、テンプレート描画時にエスケープする。
- Extension UIは実行可能なHTML、スクリプト、イベント属性、外部画像を追加できない。
- MQTT操作、秘密情報、DB接続をUIレジストリへ公開しない。

実行コードを持つExtensionは、別プロセスのRunnerと権限制御されたHost APIを
設計してから追加する。ExtensionフォルダのPythonを自動importする方式にはしない。

## ビルドと試験

```bash
cd hub
uv run python scripts/build_extension_registry.py
uv run python scripts/build_extension_registry.py --check
uv run python -m unittest tests.test_extension_registry
```

生成済みレジストリはコミット対象とし、インストール済みHubが実行時に
リポジトリ全体を必要としないようにする。

## 管理画面からの追加

管理者は「アプリ設定 → 追加機能」から、単一の`extension.json`または
`.inas-extension`を選択できる。アップロード時に行うのはHub内の静的検査だけで、
インストールもAIへの送信も行わない。静的検査を通過すると、AI監査前の独立した
確認ダイアログを開ける。ここで送信する情報、利用モデル、送信先、費用発生の可能性を
示し、明示同意後だけAI監査を開始する。インストールはその後の別操作である。

追加済みmanifestはHubの作業ディレクトリへ保存し、同梱レジストリと結合する。
同梱機能と同じ厳格なschema検証とHub所有の描画を使い、実行コードは許可しない。
詳細は[Extensionセキュリティ監査方針](EXTENSION_SECURITY_REVIEW_POLICY.md)を参照する。

AI開発者は[`../../extensions/AGENTS.md`](../../extensions/AGENTS.md)にも従う。
新規Extensionは
[`../../extensions/_template/extension.example.json`](../../extensions/_template/extension.example.json)
を雛形として使用する。
