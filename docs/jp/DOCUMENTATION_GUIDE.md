# ドキュメント記載ルール

英語版: [../DOCUMENTATION_GUIDE.md](../DOCUMENTATION_GUIDE.md)

この文書は、このリポジトリでドキュメントを書くときの言語、配置、リンク、図の管理ルールをまとめる。

## 言語ルール

- 既定のドキュメントは英語で書く。
- 日本語版は、`docs/`、`doc/`、`<device>/docs/` など、対象のドキュメントツリー内にある `jp/` ディレクトリ配下に置く。
- 可能な限り、英語版と日本語版で同じファイル名を使う。
- 詳細な既存文書が日本語だけの場合は、日本語原文を対象ドキュメントツリーの `jp/` に置き、既定位置には英語の要約または入口文書を置く。
- `docs-site/` の公開手順サイトは明示的な例外とし、初期利用者向けに日本語を root locale とする。将来の翻訳は内部仕様ツリーの `jp/` ではなく、Starlight の locale として追加する。

例:

```text
docs/SYSTEM_SPECIFICATION.md
docs/jp/SYSTEM_SPECIFICATION.md

hub/README.md
hub/doc/jp/README.md

hub/doc/OPERATIONS.md
hub/doc/jp/OPERATIONS.md

client-devices/README.md
client-devices/docs/jp/README.md

client-devices/docs/pin_assignments.md
client-devices/docs/jp/pin_assignments.md
```

## ディレクトリルール

各ドキュメント階層は、自分の階層に日本語版ディレクトリを持つ。専用の `doc` / `docs` ディレクトリを持たない入口文書は、最も近いドキュメントツリーに日本語版を置く。

| 既定位置 | 日本語版 | 対象 |
|---|---|---|
| `README.md` | `docs/jp/README.md` | repository 入口文書 |
| `docs/` | `docs/jp/` | 横断仕様、全体図 |
| `hub/README.md` | `hub/doc/jp/README.md` | hub の入口文書 |
| `hub/doc/` | `hub/doc/jp/` | hub 運用、Cloudflare、UX、設計メモ |
| `hub/doc/spec/` | `hub/doc/spec/jp/` | hub 実装仕様 |
| `client-devices/README.md` | `client-devices/docs/jp/README.md` | client device の入口文書 |
| `client-devices/docs/` | `client-devices/docs/jp/` | device 共通仕様、図 |
| `client-devices/<device>/docs/` | `client-devices/<device>/docs/jp/` | device 固有の手順書、仕様書 |

下位コンポーネントに属する日本語文書を、グローバルな `jp/` だけに集約しない。また、repository root、`hub/`、`client-devices/` の直下に top-level `jp/` を作らず、`doc` / `docs` 配下に置く。

## リンクルール

- Markdown の相対リンクを使う。
- 英語文書には、対応する日本語版がある場合はリンクを置く。
- 日本語文書からは、可能な限り日本語版の関連文書へリンクする。
- 日本語版がない場合は英語文書へリンクしてよい。
- 文書を `jp/` に移した後は、相対リンクを必ず確認する。`../` が 1 階層足りなくなることが多い。

## 画像・図のルール

- 言語依存の図やスクリーンショットも同じ `jp/` ルールで管理する。
- 言語に依存しない画像は既定側の assets を共有してよい。
- 生成 SVG は直接編集せず、生成スクリプトから再生成する。
- draw.io の編集元は、出力 SVG/PNG の近くに置く。

現在の生成コマンド:

```sh
python3 docs/assets/generate_system_diagrams.py
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

## 書き方

- 簡潔で、実装判断に使える文章を優先する。
- 現在の仕様と将来予定を分けて書く。
- コマンド例はコピーして実行できる形にする。
- device kind は `WTR`、`WRS`、`FGT`、`SOI`、`ENV` のような安定した名前を使う。
- 環境変数、topic、ファイルパス、API path は monospace で書く。
- 営農者向けの説明では、変数名より先に「何が分かるか」「何を判断できるか」を書く。
- 概要文書に実装詳細を詰め込みすぎない。詳細仕様へリンクする。

## 推奨構成

仕様書の推奨構成:

1. 目的
2. 対象範囲
3. 現在の仕様
4. データモデルまたは topic/API 契約
5. 運用ルール
6. 障害時の扱い
7. 関連文書

実装検討書の推奨構成:

1. ゴール
2. やらないこと
3. 制約
4. 設計案
5. 移行手順
6. テスト
7. 未決事項

## 日付とバージョン

- 日付が必要な場合は `2026-07-12` のような ISO 形式を使う。
- 長く残る文書では「今日」「来月」のような相対日付を避ける。
- 互換性は firmware version、device kind、schema version、migration state などで表す。

## 生成物・外部依存

- `node_modules`、`.pio` などの依存物ディレクトリ内の README は、このリポジトリの管理対象ドキュメントとして扱わない。
- vendored README を、このリポジトリの説明のために編集しない。
- 生成ファイルを追加する場合は、生成コマンドも記載する。

## 変更時チェックリスト

ドキュメント変更後は、少なくとも次を確認する。

```sh
rg -n "[ぁ-んァ-ン一-龥]" --glob '*.md' --glob '*.svg' --glob '!**/jp/**' README.md docs client-devices hub
python3 docs/assets/generate_system_diagrams.py
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

Markdown link check を行う場合は、`node_modules` や `.pio` などの依存物ディレクトリを除外する。
