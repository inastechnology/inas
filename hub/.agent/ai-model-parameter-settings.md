# AIモデル特性設定と接続診断ダイアログ

このExecPlanは進行中の実装記録である。変更理由、互換性、検証結果を追記し、単独で実装の意図と完了条件を理解できる状態を保つ。

## 目的

OpenAI互換モデルは、同じChat Completions APIでも受け付ける生成パラメーターが異なる。現状のHubは用途別のtemperatureを必ず送るため、temperatureの既定値しか受け付けない `gpt-5.6-luna` へ切り替えると、接続確認とすべてのAI処理が失敗する。

通常利用者には互換性を自動調整する安全な既定値を提供し、上級者には温度と推論の深さを明示的に設定できるUIを提供する。接続確認の結果は小さな行内文字列ではなくダイアログで示し、失敗時に「原因」「どう直すか」「技術情報」を読み分けられるようにする。

## 進捗

- [x] (2026-07-20) `gpt-5.6-luna` がtemperature 0を拒否し、省略時は同一APIキーで成功することを実APIで確認した。
- [x] (2026-07-20) 設定保存、接続確認API、Chat Completions共通処理、現在の設定画面と試験を調査した。
- [x] (2026-07-20) 既存設定と後方互換なモデルパラメーター設定を永続化した。
- [x] (2026-07-20) Chat Completionsに自動互換調整と構造化エラーを実装した。
- [x] (2026-07-20) 上級者設定と接続結果ダイアログを実装した。
- [x] (2026-07-20) 単体・回帰・ブラウザ試験と画面キャプチャを完了した。

## 分かったこと

- `AIContentService._chat_completion` は接続確認だけでなく栽培計画、質問、画像評価等の全処理でtemperatureを送る。
- OpenAIのHTTP 400は文字列のRuntimeErrorとなり、接続確認APIが一律HTTP 502に変換する。Cloudflareはこの502をブランド付きHTMLへ置換するため、ブラウザから本来の修正方法を読めない。
- ランタイム設定は許可フィールドだけを `config.json` へ保存し、欠けた値は `DEFAULT_SETTINGS` とマージする。新フィールドの追加は既存DB・既存設定ファイルの移行を不要にできる。
- OpenAI公式モデル情報では、GPT-5.6系列は推論の深さを持ち、Lunaはコスト重視のモデルとして案内されている。一方、実APIではLunaのtemperatureは既定値だけを受け付ける。

## 設計判断

- 温度設定は `auto`、`default`、`custom` の三種類とする。`auto` は用途別の既存温度を試し、OpenAI互換APIがtemperature非対応を明示した場合だけtemperatureを省略して一度再試行する。`default` は最初から省略し、`custom` は利用者の指定を尊重して自動再試行しない。
- 推論の深さは未指定を推奨値とし、none、minimal、low、medium、high、xhigh、maxを上級者が選べるようにする。未対応モデルでのエラーは勝手に別値へ変更せず、診断ダイアログで戻し方を示す。
- 接続確認の外部APIエラーはHTTP 422のJSONとして返す。外部接続確認というアプリケーション操作の診断結果であり、Cloudflareにインフラ障害の502として扱わせない。
- エラー応答はAPIキーを含めず、category、code、parameter、message、title、suggestions、technical_detailを返す。画面はすべてtextContentで描画し、外部HTMLを埋め込まない。
- 正常接続でも自動調整が発生した場合はダイアログへ表示し、実運用で同じ調整が適用されることを利用者へ説明する。

## 実装手順

`setting.py` のAI既定値とランタイム許可フィールドへ、チャンネル別のtemperature mode、temperature、reasoning effortを追加する。既存configに値がなくてもautoと未指定へ正規化されるようにする。

`ai_content_service.py` に構造化されたAIRequestError、パラメーター組み立て、temperature非対応時の一回限りの自動再試行を追加する。既存の用途別temperatureはauto時の希望値として維持する。接続確認は適用パラメーターと自動調整内容を返す。

`web_server.py` でフォーム値と接続確認JSONを検証し、構造化診断をHTTP 422で返す。秘密値のマスキングは維持する。

`hub_settings.html` の各AIチャンネルへ上級者設定を追加する。温度はモード選択とスライダー、推論は選択肢で設定する。モデル入力の下には既知モデルの用途説明を動的に表示する。接続確認は成功・失敗共通のダイアログを開く。

## 検証と完了条件

既存configを読み込むと新設定がautoとして扱われ、保存済みモデル、Base URL、APIキーを失わない。gpt-5.4のautoは従来どおりtemperatureを送れる。gpt-5.6-lunaのautoは最初のunsupported temperatureを検出し、temperatureなしで再試行して成功する。custom temperatureは利用者指定を隠さず、失敗ダイアログでモデル既定またはautoへ戻す方法を示す。

接続確認ダイアログは成功、互換調整付き成功、認証失敗、モデル不明、パラメーター非対応、非JSONのゲートウェイ障害を人向けの文章で区別する。モバイルで横溢れせず、Esc、閉じるボタン、背景クリックで閉じられる。

実行する検証は次の通り。

    cd hub && PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    cd hub/admin-ui && npm run smoke:settings

設定画面のデスクトップとモバイル、成功ダイアログ、エラーダイアログを撮影して目視する。

## 検証結果

- `PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests`: 343件成功。
- `HUB_URL=http://127.0.0.1:40123 npm run smoke:settings`: 成功。温度モード切替、0.2の表示、互換調整付き成功ダイアログ、temperature非対応の対処案、モバイル横幅を自動確認した。
- `/tmp/ina-ai-model-advanced.png`、`/tmp/ina-ai-model-success.png`、`/tmp/ina-ai-model-error.png`、`/tmp/ina-app-settings-mobile.png` を目視し、情報の優先順位、背景遮蔽、対処手順、モバイルの一列表示に問題がないことを確認した。
- 既存設定に新項目がない場合は `setting.py` の既定値とマージされ、`auto / 1.0 / 推論未指定` になる。既存モデル、Base URL、秘密ファイルは変更しない。

## 回復性

新設定は追加フィールドだけで、既存configと秘密ファイルの形式を壊さない。autoが新しい既定なので、旧設定はモデル変更後も互換調整を受けられる。明示的なcustom設定は自動で書き換えない。API呼び出しの再試行はtemperature非対応が明示された場合の一回だけで、タイムアウトや認証エラーを無制限に再試行しない。

Revision note (2026-07-20): 実APIのtemperature互換性調査と現行実装の調査を基に初版を作成した。

Revision note (2026-07-20): 実装、343件の回帰試験、ブラウザ操作、デスクトップ・モバイルの目視結果を追記して完了した。
