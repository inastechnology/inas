# Hub全体の処理中表示をINASらしいモーションへ統一する

このExecPlanは進行中の実装記録である。React管理画面とサーバー生成画面を横断するため、判断、対象範囲、検証結果を継続して更新する。

## 目的

「年間カレンダーを読み込んでいます...」などの文字だけの待機表示では、画面が動作しているのか止まっているのか判断しにくい。全面ローディング、部分ローディング、非同期ボタンを、INASの栽培・計測を連想できる共通モーションへ統一する。

中心の芽と広がる計測リングをCSSだけで描画し、画面では大きく、検索結果では小さく、ボタンでは最小のリングとして使う。処理内容の文言を必ず併記し、装飾だけに状態を依存しない。動きを抑えるOS設定ではアニメーションを停止する。

## 進捗

- [x] (2026-07-20) React、サーバー生成HTML、既存JavaScriptのローディング表示と非同期ボタンを調査した。
- [x] (2026-07-20) 芽＋計測リングの3サイズ共通モーションと `aria-busy` を使う設計を決定した。
- [x] (2026-07-20) Reactの全面・部分ローディングを共通コンポーネントへ変更した。
- [x] (2026-07-20) Reactの主要な非同期ボタンに処理中アイコン、操作別の文言、`aria-busy`を追加した。
- [x] (2026-07-20) サーバー生成画面の初期表示、ストリーム表示、非同期フォーム・ボタンへ共通モーションを適用した。
- [x] (2026-07-20) 型チェック、ビルド、全テスト、ブラウザsmoke、目視確認を実行した。
- [ ] 稼働Hubへ反映し、ヘルスチェックを確認する。

## 分かったこと

- Reactの全面待機は `App.tsx` と `PlantCalendarPage.tsx` の `layout-state` に文字だけを表示している。JavaScript起動前の `field_layout.html` と `field_calendar.html` にも同じ文字だけのfallbackがある。
- `LoaderCircle.spin` はAI計画作成と一括反映の一部だけにあり、保存、作業記録、施肥、定植などのボタンは無効化されても処理中の見た目がない。
- サーバー生成画面の `data-stateful-form` は `stateful-actions.js` が一括管理しているため、ここでsubmitボタンの `aria-busy` を制御すれば設定・圃場・記録フォームへ横断適用できる。
- AI接続確認、Instagram情報取得、カメラ接続確認、生育AI評価、記録の追加読込は個別JavaScriptでボタンを無効化しており、明示的に `aria-busy` を切り替える必要がある。
- `hub-ui.css` はサーバー生成画面とReactを載せる画面の双方から読み込まれる。共通CSS primitiveをここへ置き、React bundleにも同じprimitiveを含めれば初期fallbackからReact描画後まで見た目を維持できる。

## 設計判断

- 全面表示は `LoadingState`、部分表示は `InlineLoading`、ボタン内は `ButtonActivity` としてReactで共通化する。
- CSS primitiveは `.inas-activity`、`.inas-loading-state`、`.inas-inline-loading`、`.inas-button-activity` とする。芽は疑似要素、計測リングは回転と穏やかなpulseで表現し、外部画像を追加しない。
- `button[aria-busy="true"]` には控えめな光の走査を加え、処理中であることをボタン全体でも示す。無効理由による通常のdisabledボタンには適用しない。
- `stateful-actions.js` はbusy中だけsubmitへ `aria-busy="true"` を付け、標準のform submitでも送信直前にbusyへ移行する。
- 個別JavaScriptの非同期ボタンは開始・終了時に `aria-busy` を切り替える。ページ遷移まで処理が続く場合は成功時に解除しない。
- `prefers-reduced-motion: reduce` では回転、pulse、走査を停止し、静止した芽とリングを残す。

## 検証と完了条件

年間カレンダーと設置ビューの初期表示に共通アニメーションと処理文言が表示される。検索、AI計画生成、保存、設定確認、カメラ処理などで、処理中の対象にだけ同じ系統の小型アニメーションと `aria-busy` が表示される。通常の入力不備や未変更によるdisabledボタンはアニメーションしない。モバイルで横方向にはみ出さず、動きを抑える設定ではアニメーションが停止する。

実行する検証は次の通り。

    cd hub/admin-ui && npm run typecheck
    cd hub/admin-ui && npm run build
    cd hub/admin-ui && npm run smoke:field-detail
    cd hub && .venv/bin/python -m unittest discover -s tests
    cd .. && git diff --check

## 検証結果

- `npm run typecheck`: 成功。
- `npm run build`: 成功。配布用の管理画面CSS/JavaScriptとアイコンchunkを更新した。
- `.venv/bin/python -m unittest discover -s tests`: 344件成功。
- `npm run smoke:field-detail`: 隔離したデモHubとChromiumで成功。年間カレンダーの全面ローディング、通常モーション、`prefers-reduced-motion: reduce`時の停止、API待機中ボタン、無関係なボタンがbusy表示にならないことを検証した。
- `/tmp/ina-calendar-loading-motion.png` と `/tmp/ina-calendar-busy-button.png` を目視し、デスクトップでの配置、背景、文言、処理対象の識別を確認した。
- `git diff --check`: 成功。
- 本番配備は安全配備スクリプトが「origin/mainに未反映のローカルコミットが2件ある」ため停止した。作業差分は保持されており、コミット・pushの許可後に再実行する。

## 回復性

ローディング表示は表示層とアクセシビリティ属性だけを変更し、APIや保存データ形式は変更しない。共通CSSが読み込めない場合も処理文言は残る。アニメーションを停止しても操作状態と文言は維持される。

Revision note (2026-07-20): 全画面・部分・ボタンのローディングを横断調査し、共通モーションと適用範囲を定義した。

Revision note (2026-07-20): 共通モーションをReactとサーバー生成画面へ実装し、処理対象のボタンだけがbusy表示になるよう操作単位の状態を追加した。隔離デモでブラウザ検証まで完了し、本番配備のGit境界を記録した。
