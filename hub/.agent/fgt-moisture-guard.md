# FGT の予約運転を土壌水分で見送る

この ExecPlan は `hub/AGENTS.md` とアーキテクチャ方針に従って更新する。
参照先 `.agent/PLANS.md` はリポジトリ内に存在しないため、既存の ExecPlan の構成に合わせる。

## 目的と受入条件

FGT に接続した土壌水分計の予約実行直前の値が設定値以上なら、
給水・液肥調製・潅水を含む予約全体を見送る。時間指定とレシピの両方に適用する。
Hub の動作設定から有効化と 0〜100% の整数閾値を設定し、MQTT と機器内保存に反映する。
既存設定は無効を既定値として従来の動作を保つ。

## 設計判断

- 判断は Arduino に依存しない `fgt-core`、測定と実行抑止は Device App が所有する。
- Runtime Config は `fgt.moisture_guard.enabled` と `threshold_percent`。既定値は false / 40。
- 通常表示の土壌水分と同じ、機器の登録順で最初の有効な土壌センサーを使う。
- 読取失敗・無効・非数・範囲外では見送る。任意の質問に回答がないため、この既定方針をユーザーへ伝えて実装した。
- 見送りは運転ジャーナルに消化済みとして保存し、同じ予約の追いかけ実行を防ぐ。
- 判定時の水分・有効性を測定後のステータスと別に保持する。
- Device Definition の既存フォーム宣言を使用する。Hub Extension は追加しない。
- 実機への配信・設定変更は今回の実装検証に含めない。

## 進捗

- [x] 予約・センサー・ジャーナル・Hub フォームを調査した。
- [x] firmware の判定、設定、保存互換性、ステータスを実装した。
- [x] Hub バリデーション、Device Definition、操作説明を更新した。
- [x] native テスト、firmware ビルド・manifest 検証、Hub テスト・lint を実行した。
- [x] 隔離デモで設定の保存と desktop / 390px mobile 表示を検証した。

## 検証

`client-devices/fertigation-device` で `make test`, `make build`, `make check-firmware`。
Hub で Device Definition registry の再生成と `--check`、Python テスト、lint。
隔離デモに対して Device Definition browser smoke を実行して画面を確認する。

## 結果

- Native: 33件成功。実際の設定parser・LittleFS保存処理をメモリー上のFSで実行し、旧版の構造体からの移行も確認した。
- FGT 0.3.0: `make build` と `make check-firmware` 成功。
- Hub: 全552件成功。Device Definition registry `--check` と全体 `ruff check` 成功。
- 変更したPython 4ファイルの `ruff format --check` 成功。全体formatチェックには、変更外の `cultivation_research_service.py`、`plant_management_repository.py`、`test_cultivation_research_service.py`、`test_guided_work_routes.py` の既存指摘がある。
- Browser: 5種類のDevice Definition smoke成功。FGTのキーボード操作、閾値60%の保存、再読込を確認した。
- 画像 `/tmp/ina-fgt-moisture-desktop.png` と `/tmp/ina-fgt-moisture-mobile.png` を目視確認した。390pxでページ横溢れなし。
- 実機への配信、実際のセンサー・ポンプによる動作確認は未実施。水だけで確認する手順を firmware のverification planへ追加した。
