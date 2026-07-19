# AI栽培計画の変更案を即時選択・一括反映する

このExecPlanは進行中の実装記録である。変更理由、互換性、検証結果を追記し、単独で実装の意図と完了条件を理解できる状態を保つ。

## 目的

「AI栽培計画を作り直す」の確認モードでは、変更案ごとの「変更する」「変更しない」を押すたびに保存APIと栽培情報の再取得が走る。通信中は全操作が止まり、提案数が多いほど待ち時間が積み上がる。

各提案の選択はブラウザ内で即時に切り替え、利用者が全件を確認したあと、一度のAPI呼び出しで原子的に計画へ反映する。通信失敗時は選択を残して再試行できるようにする。

## 進捗

- [x] (2026-07-20) 現行のReact、API、Flask route、repository、回帰試験を調査した。
- [x] (2026-07-20) 即時選択と原子的な一括反映を採用する設計を決定した。
- [x] (2026-07-20) repositoryとFlaskに一括確定APIを追加した。
- [x] (2026-07-20) React UIをローカル選択、一括操作、一度の確定通信へ変更した。
- [x] (2026-07-20) 単体試験、型チェック、ビルド、ブラウザsmokeを実行した。

## 分かったこと

- 現行UIは各提案ボタンから `onDecideRegeneration` を直接呼び、親コンポーネントが決定APIの後に `loadPlantBundle` を呼ぶ。このため1件につきPOSTとGETが発生し、`busy` により他の提案も操作できない。
- repositoryの `decide_calendar_generation_proposal` は1件ごとに永続化し、採用時はカレンダーrevisionも1件ずつ増やす。
- 生成タスクは全提案が決定されるまで `awaiting_review` のため、一括処理を追加しても既存データ形式を変更する必要はない。
- 既存の1件確定APIは後方互換のため残せる。

## 設計判断

- 各提案の採用・見送りはReact stateへ保存し、クリック時にネットワーク通信しない。選択は何度でも変更できる。
- 「すべて取り入れる」「すべて変更しない」「選択をクリア」を用意し、件数が多い場合も短時間で確認できるようにする。
- 未選択がなくなった時だけ「選択した内容を一括反映」を有効にする。確定時はpending提案の決定を配列で1回送信する。
- repositoryは入力全件と競合を先に検証し、採用案をまとめて適用して1回だけ保存する。不正な1件が含まれる場合は全件を変更しない。
- 一括APIは更新後のfield bundleを同じレスポンスで返す。画面は追加GETを行わず、そのbundleで置き換える。
- 既存の単件APIとrepository methodは互換性維持のため残し、共通の内部一括処理を利用する。

## 実装手順

`plant_management_repository.py` に複数の `{proposal_id, decision}` を受け取るmethodと共通内部処理を追加する。重複ID、不明ID、決定済み提案、不正なdecision、作成後に変更された作業を保存前に検証する。承認案をまとめて適用し、revision、task、timestampを1回で更新する。

`web_server.py` に一括確定routeを追加し、タスクとplantingの所属を確認する。成功時はtask、decided proposals、calendar、更新後のfield bundleを返す。

`api.ts`、`PlantCalendarPage.tsx`、`App.tsx`、`PlantCalendarDrawer.tsx` を変更する。Drawerは提案単位のローカル選択、集計、全選択、クリア、一括確定、失敗時の再試行を提供する。親は一括APIのbundleを直接stateへ設定する。

`styles.css` で選択状態、集計ツールバー、追従する確定バー、モバイル一列表示を整える。既存の生成中ロックや既決定提案の表示は維持する。

## 検証と完了条件

提案ボタンを連続して押しても通信せず即座に表示が変わる。全件選択後の確定操作だけが一括APIを1回呼び、追加GETなしで画面が更新される。通信失敗時は選択が残る。複数承認を一括適用してもカレンダーrevisionは1だけ増える。不正または競合する決定を混ぜた場合は一部だけ反映されない。

実行する検証は次の通り。

    cd hub && PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    cd hub/admin-ui && npm run typecheck
    cd hub/admin-ui && npm run build
    cd hub/admin-ui && npm run smoke:field-detail

## 検証結果

- Pythonの全344テストが成功した。
- 変更したPythonファイルに対するRuffのlintとformat checkが成功した。
- 管理画面のTypeScript型チェックと本番ビルドが成功した。
- Chromiumによるfield detail smokeが成功した。提案ごとの選択では決定APIが0回、一括反映時は決定2件を含むPOSTが1回だけであり、追加GETなしで確認画面が閉じることを確認した。
- デスクトップとモバイルのスクリーンショットを確認し、選択状態、集計、確定操作が表示され、モバイルで横方向のはみ出しがないことを確認した。
- `git diff --check` が成功した。

## 回復性

一括APIは新規追加であり、既存の単件APIと保存済み生成タスクの形式を変更しない。ブラウザ内の未確定選択は永続化前なので、失敗時にサーバ状態を壊さない。競合時はHTTP 409を返し、画面は選択を維持して再読込または再試行を選べる。

Revision note (2026-07-20): 現行実装の調査と即時選択・一括反映の設計を基に初版を作成した。

Revision note (2026-07-20): 実装を完了し、全テスト、型チェック、ビルド、ブラウザsmokeの結果を追記した。
