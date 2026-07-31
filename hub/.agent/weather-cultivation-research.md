# 気象と圃場データを生育研究・作業判断へ接続する

このExecPlanは実装中に更新する。`hub/AGENTS.md`、`docs/jp/ARCHITECTURE_LAYERING_POLICY.md`、`hub/doc/jp/HUB_WEATHER_CULTIVATION_RESEARCH_SPEC.md`に従う。

## 目的

現行のHub全体向け気象JSONLを、圃場ごとの気象実績・予報履歴として保存し、センサー、潅水、施肥、管理作業、生育観察、収穫へ安全に結合する。最初の提供価値は研究ビュー、探索的相関、仮説保存とし、気象による作業・機器の無承認自動変更は行わない。

## 進捗

- [x] 現行のOpen-Meteo日別取得、JMA予報、気象JSONL、圃場・配置・定植・記録・センサー保存を調査した。
- [x] 気象実績、予報、圃場実測、派生値を分離する仕様を策定した。
- [x] Phase 1Aの初期実装: 圃場気象地点、圃場スコープ付き気象保存・期間取得、確認済み地点のOpen-Meteo取得を実装した。connector分離、JMA並行取得、移行CLIは継続課題。
- [x] Phase 1Bの初期実装: 外部気象と手入力圃場記録を日次整列し、由来を保持する研究データセットを実装した。センサー・植物管理記録の結合と生育結果カタログは継続課題。
- [x] Phase 1Cの初期実装: Pearson、Spearman、日差、少数標本・定数系列対応、分析スナップショット、仮説CRUDを実装した。移動平均・作業前後比較は継続課題。
- [x] Phase 1Dの初期実装: 圃場詳細の研究タブ、地点確認、蓄積状況、相関UI、CSV出力を実装した。散布図・欠測率・元記録遷移とブラウザ回帰は継続課題。
- [ ] Phase 2以降はPhase 1の実地検証後に別ExecPlanで開始する。

## 設計判断

- 気象取得地点はHub設定ではなく圃場に属する。Hub既定地点は移行用フォールバックに限定する。
- Open-Meteo等の外部実績、JMA等の予報、ENV等の圃場実測、派生指標を同じ値として上書きしない。
- 予報は発表時刻ごとのスナップショットとして追記し、後日確定した実績と比較できるようにする。
- 外部プロバイダー形式はconnectorで正規化し、植物管理・分析サービスはprovider固有フィールドを参照しない。
- UI向け分析はrepositoryから直接組み立てず、日次データセットserviceを境界にする。
- Pearson、Spearman、遅延比較、欠測率はサーバーの決定的処理とし、LLMへ計算させない。
- 同じ指標を持つ複数センサーは暗黙に平均せず、設置範囲と利用者選択を要求する。
- 既存JSONLは未割当データとして保持し、座標が近いという理由だけで圃場へ自動帰属させない。
- 初期UIは研究・振り返り用とし、通常の圃場概要へ統計指標を大量に追加しない。
- Phase 1は作業とRuntime Configを変更しない。注意喚起、承認付き変更、自動制御は段階ごとに別の安全条件を定める。

## 実装方針

### Phase 1A: 保存と取得

1. 圃場モデルへ`weather_location`を追加し、位置精度、確認状態、タイムゾーンを検証する。
2. `WeatherConnector`境界を定義し、現行Open-Meteo/JMA serviceをadapterとして配置する。
3. 圃場ID、期間、粒度、観測種別、品質を持つWeather repositoryを追加する。
4. `WeatherRecordTask`を圃場単位の取得へ変更し、同地点・同期間の要求をキャッシュする。
5. 実績と予報を並行取得し、予報スナップショットを上書きしない。
6. 既存JSONL移行コマンドを追加し、dry-run、manifest、件数、checksum、再実行安全性を持たせる。

### Phase 1B: 研究用データ

1. 圃場記録カタログへ生育段階、草丈、葉数、花数、着果数、収穫個数、糖度等の共通項目を追加する。
2. 潅水、施肥、承認済み管理作業、圃場イベント、センサー集計を期間検索できるrepository methodへ整理する。
3. `CultivationResearchDatasetService`で圃場タイムゾーンの日次行を生成する。
4. すべての列へ元データ参照と品質フラグを保持する。
5. センサー交換、移設、校正、設備変更を分析境界として返す。

### Phase 1C: 分析と仮説

1. `CultivationResearchAnalysisService`へPearson、Spearman、移動平均、作業前後、指定遅延比較を実装する。
2. 有限値、定数系列、欠測、少数サンプル、外れ値候補を検証する。
3. 分析入力、結果、品質、計算バージョンをスナップショットとして保存する。
4. 圃場・定植に属する研究仮説repositoryとCRUD APIを追加する。
5. CSV/JSONエクスポートに権限、期間、最大行数、位置情報除外を適用する。

### Phase 1D: UI

1. 圃場詳細へ研究ワークスペースを追加する。
2. 圃場、配置、定植、期間を選び、気象、環境、根域、作業、生育をレーン表示する。
3. 観測、外部解析、予報、推定、欠測を色以外でも識別する。
4. 二系列比較では係数より先に期間、サンプル数、欠測、散布図を表示する。
5. 結果から仮説、別の説明、次の観察を保存できるようにする。
6. デスクトップとモバイルのスクリーンショットを確認する。

## 予定モジュール

- `weather_connector.py`: provider非依存取得contract
- `open_meteo_weather_connector.py`: Open-Meteo adapter
- `jma_weather_connector.py`: JMA adapter
- `weather_repository.py`: 実績・予報・地点・期間検索
- `weather_migration.py`: 既存JSONL移行
- `cultivation_research_dataset_service.py`: 時間・場所の整列
- `cultivation_research_analysis_service.py`: 決定的分析
- `cultivation_research_repository.py`: 仮説と分析スナップショット
- `admin-ui/src/field-research/`: 研究ビュー

既存moduleの責務で十分な場合は新しいwrapperを作らず、上記名を調整する。

初期実装では既存の`weather_record_repository.py`を互換拡張し、データセットと分析は
`cultivation_research_service.py`へまとめた。外部providerの追加前にconnector境界を分離する。

## API

- `GET/PATCH /local/api/fields/<field_id>/weather-location`
- `GET /local/api/fields/<field_id>/weather/observations`
- `GET /local/api/fields/<field_id>/weather/forecasts`
- `GET /local/api/fields/<field_id>/research/dataset`
- `POST /local/api/fields/<field_id>/research/analyses`
- `GET/POST/PATCH /local/api/fields/<field_id>/research/hypotheses`
- `GET /local/api/fields/<field_id>/research/export.csv`

Flask routeは入力、権限、responseへ限定し、集計と判断を持たない。

## 受入条件

- 複数圃場で別々の気象地点を利用できる。
- 外部実績と予報スナップショットを同時に保存できる。
- 予報を実績へ、外部グリッドを圃場実測へ誤分類しない。
- 気象、センサー、潅水、施肥、作業、生育、収穫の日次行を生成できる。
- 異なる配置または定植のデータを誤結合しない。
- サンプル数、欠測率、Pearson、Spearman、遅延相関を再現可能に計算できる。
- 研究ビューから元記録と画像を確認できる。
- 分析条件、結果、仮説、次の観察を保存できる。
- 既存気象JSONL、Instagram投稿、植物管理、機器制御を壊さない。
- Phase 1では作業日、潅水予約、Runtime Configを自動変更しない。

## 検証

    cd hub
    PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check <変更したPythonファイル>
    cd admin-ui
    npm run typecheck
    npm run build

追加する重点試験:

- 気象地点、タイムゾーン、単位、欠測、実績・予報分離
- 複数圃場、複数配置、複数定植の分離
- JSONL dry-run・移行・再実行
- 日次集計、派生指標、相関、遅延、定数系列
- API期間・件数・権限制限
- UIの欠測・品質・少数サンプル表示

## 回復性

新repositoryと既存JSONLを移行期間中は分離する。移行はdry-runを既定とし、既存ファイルを変更しない。新しい圃場気象取得を無効化しても、現行気象記録とInstagram投稿を継続できる。日次集計と分析結果は元データから再生成可能にし、派生値を正本にしない。
