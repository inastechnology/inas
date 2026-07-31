# 圃場気象・生育相関研究と作業判断への活用仕様

更新日: 2026-07-30

状態: 仕様あり。現行の気象記録を維持しながら段階的に実装する。初期段階では研究・説明・注意喚起を対象とし、気象だけを根拠に機器を自動制御しない。

## 1. 目的

Hubが取得している気象データを単なる追記ログで終わらせず、圃場センサー、潅水、施肥、管理作業、生育観察、画像、収穫品質と同じ時間軸・場所・定植へ結び付ける。

利用者が次の問いを自分の圃場データから研究できる状態をつくる。

- 雨、日射、気温、ET0に対して、土壌・培地水分はどのように変化したか。
- 同じ潅水時間または水量でも、季節や生育段階により反応が違うか。
- 施肥後の降雨・潅水とEC、生育、収量、品質にどのような関係があるか。
- 外気象とハウス内環境にはどの程度の差があるか。
- 開花、着果、収穫等の生育イベントは、積算温度や日射の変化からどの程度遅れて現れたか。
- 過去の作業判断と、当時利用できた予報、実際に起きた天気、作業結果は整合していたか。

本機能は相関から普遍的な栽培正解を自動生成するものではない。圃場固有の仮説を立て、次の観察または比較試験へつなぐ研究支援機能である。

## 2. 最上位原則

### 2.1 気象実績、予報、圃場実測、計算値を分ける

同じ「雨」「温度」でも意味と品質が異なるため、次を別の観測種別として保存する。

| 種別 | 例 | 主な用途 |
|---|---|---|
| `field_observation` | 圃場雨量計、ENV、SOI、手持ち計測 | 圃場で実際に観測した値 |
| `external_analysis` | Open-Meteo解析・再解析値 | 圃場実測がない期間の気象履歴 |
| `forecast_snapshot` | 気象庁・外部予報の取得時点スナップショット | 当時の作業判断と予報精度の振り返り |
| `derived_metric` | 積算温度、VPD、移動平均、日水収支 | 決定的な計算で作った派生値 |
| `model_estimate` | 有効降雨、根域流入量、乾燥予測 | 前提と不確実性を持つ推定値 |
| `human_observation` | 萎れ、葉色、樹勢、生育段階 | センサーで代替しない利用者観察 |

予報を過去の実績として扱わない。解析・再解析データを圃場雨量計の実測として表示しない。派生値で元の観測値を上書きしない。

### 2.2 場所の粒度を失わない

気象外部データは圃場全体、ENVは圃場またはハウス、SOIは畝・鉢・測点、作業と生育結果は配置または定植に属する。分析時に日付だけで無条件に結合せず、各データの代表範囲を保持する。

```text
field
  weather_location
  external weather
  layout space
    placement
      planting
      sensor measurements
      irrigation/fertilization/work events
      growth observations
```

圃場気象をハウス内の実測値として扱わない。雨が当たる露地と、屋根のある培地を区別する。

### 2.3 相関を因果と表示しない

相関係数が高くても原因とは断定しない。季節、生育段階、作業、設備変更、センサー交換等の交絡要因を併記する。

画面とAI説明は、次の表現を使う。

- 「この期間では一緒に変化する傾向が見られます」
- 「原因とはまだ断定できません」
- 「対象期間と生育段階を揃えた追加観測が必要です」
- 「データ数が少ないため参考値です」
- 「設備変更前後を分けて比較してください」

### 2.4 判断支援と自動制御を分ける

初期段階では、研究ビュー、気象コンテキスト、確認提案、作業の注意喚起までとする。予報だけで既存カレンダー、潅水予約、Runtime Configを自動変更しない。

自動制御へ進める場合は、作業ごとに安全上限、実測フィードバック、欠測時動作、承認レベル、停止条件を別仕様で定める。

### 2.5 LLMへ集計と統計判定を任せない

日次集計、積算、相関、遅延比較、欠測率、信頼度は決定的なサービスで計算する。LLMは計算済み結果を説明し、仮説候補と追加観測を提案できるが、未計算の相関値、因果関係、圃場固有の推奨量を生成しない。

## 3. 現状と課題

現行Hubは、Open-Meteoから前日までの日別解析・再解析データを取得し、気象記録JSONLへ保存する。日降水量、降雨時間、日照時間、短波放射量、ET0、最高・最低気温を保持できる。設定により気象庁XMLから地域天気と降水確率を保存でき、Instagram投稿では別の予報スナップショットを利用する。

現状の制約:

- Hub全体で一つの設定緯度経度を使い、圃場IDへ帰属しない。
- Open-Meteoの過去日別データとJMA予報のどちらか一方を記録する設定である。
- 気象記録がセンサー、潅水、施肥、管理作業、生育記録へ結合されていない。
- 植物管理AI、栽培相談、作業サジェストは気象記録を参照していない。
- 圃場画面に気象とセンサーを重ねる研究ビューがない。
- 予報取得時点の履歴と、後日確定した実績を比較できない。
- 生育段階、開花、着果、収穫品質等の目的変数が十分に構造化されていない。

## 4. 対象範囲

### 4.1 初期対象

- 圃場ごとの気象取得地点
- 外部気象の実績と予報スナップショット
- 時間・日単位の正規化と品質情報
- 圃場センサー、手入力記録、潅水、施肥、作業、定植との結合
- 日単位研究データセット
- 複数系列を重ねる研究ビュー
- Pearson、Spearman、遅延相関の探索的表示
- 積算温度、VPD、ET0、簡易水収支等の派生値
- 気象を根拠の一つとする非自動の作業注意喚起
- CSV/JSONエクスポート

### 4.2 初期対象外

- 気象だけによる潅水の自動実行
- カレンダー日付の無承認自動変更
- 農薬散布の自動判断・実行
- 収量や病害発生の確定的な予測
- 複数圃場データを匿名化せず横断学習すること
- LLMによる統計量の生成
- 気象プロバイダーの値を農業用観測所と同等に保証すること
- 研究結果を一般的な作物基準として自動共有すること

## 5. 圃場気象地点

圃場へ `weather_location` を追加する。

```text
weather_location:
  mode                     coordinates | municipality | hub_default | disabled
  latitude
  longitude
  timezone
  elevation_m
  source                   user | geocoded | imported | hub_default
  accuracy                 exact | approximate | municipality | unknown
  confirmed_at
  confirmed_by
```

- 既定は圃場所在地から候補を作り、利用者が確認する。
- 正確な座標を登録したくない場合は、市区町村代表点または概略位置を選べる。
- `hub_default` は移行用フォールバックであり、複数圃場の正式運用では確認を促す。
- 座標は認証済みの圃場設定として扱い、SNS、公開研究、通常ログへ出さない。
- 気象取得停止を選べる。

気象地点の変更時に過去データを新地点へ付け替えない。各記録は取得時の地点と解像度を保持する。

## 6. 気象データモデル

### 6.1 正規化気象レコード

```text
weather_observation:
  id
  field_id
  observed_at
  period_start
  period_end
  granularity              hourly | daily
  observation_type         field_observation | external_analysis
  provider
  provider_dataset
  provider_revision
  location:
    latitude
    longitude
    elevation_m
    spatial_resolution
    accuracy
  metrics:
    precipitation_mm
    rain_mm
    precipitation_hours
    air_temperature_mean_c
    air_temperature_max_c
    air_temperature_min_c
    relative_humidity_mean_percent
    wind_speed_mean_m_s
    wind_speed_max_m_s
    solar_radiation_mj_m2
    sunshine_hours
    et0_fao_mm
  quality:
    status                  valid | partial | suspect | missing
    missing_metrics[]
    provider_flags[]
  source_record_id
  fetched_at
```

未提供の値は `null` とし、0へ変換しない。単位は正規形へ変換し、元の単位とプロバイダー応答を監査可能に保持する。

### 6.2 予報スナップショット

```text
weather_forecast_snapshot:
  id
  field_id
  issued_at
  fetched_at
  valid_from
  valid_to
  provider
  area_or_grid
  granularity              hourly | daily
  horizons[]:
    forecast_at
    weather_code
    weather_text
    precipitation_probability_percent
    precipitation_mm
    temperature_c
    temperature_min_c
    temperature_max_c
    relative_humidity_percent
    wind_speed_m_s
    wind_gust_m_s
    solar_radiation
  quality
  source_record_id
```

同じ対象時刻でも、発表時刻が異なる予報を上書きしない。作業判断時に実際に利用できた最新スナップショットを再現できるようにする。

### 6.3 派生指標

```text
derived_metric:
  id
  field_id
  target_placement_id
  planting_id
  metric_key
  value
  unit
  period_start
  period_end
  calculation_version
  input_refs[]
  assumptions[]
  quality
  calculated_at
```

初期指標:

- 日平均、最小、最大、標準偏差
- 日積算降水量、潅水量
- ET0と降水・潅水の差
- 有効降雨量。ただし雨曝露係数を明示する
- VPD
- 基準温度を持つ積算温度
- 日射・PAR積算
- 土壌水分の低下速度
- 潅水前後の水分変化量
- ECの作業前後変化量

計算式、入力、バージョンを保存し、式の更新で過去結果の意味が変わらないようにする。

## 7. 雨曝露と施設内外

配置または空間へ次を持たせる。

```text
rain_exposure:
  mode                     exposed | partial | sheltered | indoor
  coefficient              0.0..1.0
  source                   default | user | measured
  notes
```

- 露地は開始値 `exposed`、屋内は `indoor` としてよいが、利用者が確認する。
- ハウス、軒下、鉢では外部降水量を根域流入量として直接使わない。
- 有効降雨量は `model_estimate` であり、圃場雨量計や排液計測より優先しない。
- 雨曝露係数は分析フィルタとして使い、元の降水量を変更しない。

## 8. 生育・品質・作業結果

相関研究には結果となる目的変数が必要である。既存の圃場記録カタログを拡張し、デバイスがなくても入力できる。

共通候補:

- 生育段階
- 草丈
- 葉数
- 花数
- 着果数
- 果実数
- 葉色・樹勢の段階評価
- 萎れ、病斑、害虫程度
- 収穫個数
- 収穫重量
- 糖度
- 規格内率
- 作業者の5段階評価
- 定点画像

作物別項目はカタログまたは将来の宣言型参照データで提供し、作物名ごとの条件分岐をHub coreへ追加しない。

測定法、単位、対象、測定位置を保存する。同じ「草丈」でも測り方が変わった場合は一続きの系列として断定しない。

## 9. 分析用日次データセット

`CultivationResearchDatasetService` は、保存層を直接UIへ露出せず、指定した圃場、配置、定植、期間、タイムゾーンに対して日次行を生成する。

入力:

```text
field_id
target_placement_id
planting_id
start_date
end_date
timezone
metric_keys[]
aggregation_policy_version
```

出力例:

```text
date
weather_precipitation_mm
weather_et0_mm
weather_solar_radiation_mj_m2
weather_temperature_max_c
weather_temperature_min_c
field_air_temperature_mean_c
soil_moisture_mean_percent
soil_moisture_min_percent
soil_ec_max_us_cm
irrigation_volume_l
irrigation_duration_min
fertilizer_n_kg
work_event_keys[]
growth_stage
plant_condition_rating
harvest_weight_g
source_refs[]
quality_flags[]
```

集約規則:

- 日付境界は圃場タイムゾーンを使う。
- 平均だけでなく、用途に応じて最小、最大、積算、件数を保持する。
- 欠測日は行を削除せず `null` と品質フラグを返す。
- 同じ指標の複数センサーは自動平均せず、代表範囲と分析選択を求める。
- センサー交換、校正変更、設備変更をイベントとして境界表示する。
- 元データ参照を残し、グラフから根拠レコードへ移動できるようにする。

## 10. 探索的分析

### 10.1 対応する初期分析

- 時系列重ね合わせ
- 散布図
- Pearson相関
- Spearman順位相関
- 1、3、7、14、30日の遅延相関
- 移動平均
- 作業前後比較
- 生育段階別の期間分割
- 設備変更前後の期間分割
- 欠測率、サンプル数、外れ値候補の表示

### 10.2 表示する最低情報

```text
analysis_type
x_metric
y_metric
lag_days
sample_count
missing_count
coefficient
period_start
period_end
filters
quality
calculation_version
```

サンプル数が少ない結果を強く表示しない。初期基準では、日次ペアが14未満なら係数を参考表示に留め、30未満なら「短期間」、30以上でも因果とは表示しない。しきい値は統計的有意性の保証ではなく、誤読を減らすUX基準である。

多くの組み合わせを自動探索した場合は、偶然の相関が増えることを明示する。初版は利用者が比較する2系列を選ぶ方式を優先する。

## 11. 研究ビュー

圃場詳細へ `研究` または `振り返り` ワークスペースを追加する。通常の概要画面へ統計表を大量に表示しない。

### 11.1 初期表示

1. 圃場、配置、定植、期間を選ぶ。
2. 気象、圃場環境、根域、作業、生育・収穫のレーンを縦に並べる。
3. 潅水、施肥、剪定、収穫、設備変更をイベントマーカーで示す。
4. 欠測、推定、外部気象、圃場実測を視覚的に区別する。
5. 画像がある日はサムネイルを表示する。

### 11.2 比較

利用者が「比較する」を押して2系列を選び、期間、生育段階、遅延日数を指定する。結果は係数より先に散布図、サンプル数、欠測、対象期間を表示する。

### 11.3 仮説を残す

分析結果から次を保存できる。

```text
research_hypothesis:
  id
  field_id
  planting_id
  title
  observation_summary
  hypothesis
  alternative_explanations[]
  selected_metrics[]
  period
  analysis_snapshot
  next_observation
  next_comparison
  status                   draft | observing | reviewed | supported | inconclusive | rejected
  created_by
  reviewed_by
```

`supported` は対象圃場の限定条件で支持されたことを意味し、一般的な農学的事実への昇格ではない。

## 12. 作業判断への段階的利用

### Phase 1: 研究・可視化

- 圃場別気象履歴
- センサー、作業、生育との重ね合わせ
- 探索的相関
- CSV/JSON出力
- 仮説保存

作業や機器設定を変更しない。

### Phase 2: 説明付き注意喚起

決定的な規則で次のような確認候補を作る。

- 今後の降雨前に潅水の必要性を再確認
- 強風・降雨前の散布作業を再確認
- 低温・高温予報時の作物確認
- ET0が高い期間の根域水分確認
- 降雨後も水分反応がない場所のセンサー・雨曝露確認
- 施肥直後の強い降雨と残効信頼度低下

注意喚起は、予報発表時刻、対象期間、場所、根拠、未確認事項、推奨する確認行動を持つ。作業実施を断定しない。

### Phase 3: 承認付き計画変更

- 利用者へ変更前後を提示する。
- 変更理由、使用予報、予報発表時刻、変更者を保存する。
- 承認後だけカレンダー期間または予定を変更する。
- 予報更新で変更を繰り返さないよう、安定時間と変更回数上限を設ける。
- 完了済み、作業中、確認待ちの作業を自動変更しない。

### Phase 4: 限定された閉ループ

潅水等の可逆性が比較的高い作業だけを対象に、別の安全仕様と実証を通す。予報は補助入力とし、対象根域の実測、安全上限、実行確認、欠測時停止を必須にする。

## 13. API案

| Method | URL | 用途 |
|---|---|---|
| GET/PATCH | `/local/api/fields/<field_id>/weather-location` | 気象取得地点の確認・更新 |
| GET | `/local/api/fields/<field_id>/weather/observations` | 期間・粒度・指標を指定して実績取得 |
| GET | `/local/api/fields/<field_id>/weather/forecasts` | 発表時刻と対象期間を指定して予報履歴取得 |
| GET | `/local/api/fields/<field_id>/research/dataset` | 配置・定植・期間・指標を指定した研究データセット |
| POST | `/local/api/fields/<field_id>/research/analyses` | 選択系列の決定的分析 |
| GET/POST/PATCH | `/local/api/fields/<field_id>/research/hypotheses` | 仮説の一覧、保存、更新 |
| GET | `/local/api/fields/<field_id>/research/export.csv` | 権限確認済みCSV出力 |

期間、粒度、指標数、最大行数を必須制限する。圃場権限外のデータを返さない。生のプロバイダー応答や正確な座標を通常の研究レスポンスへ含めない。

## 14. レイヤ分離

| レイヤ | 責務 |
|---|---|
| Weather connector | 外部プロバイダー取得、プロバイダー形式の変換 |
| Weather repository | 実績、予報スナップショット、地点、取得履歴の保存と期間検索 |
| Measurement repository | 圃場センサーの正規化時系列検索 |
| Field/plant repository | 配置、定植、作業、生育、収穫記録 |
| Research dataset service | 場所と時間を揃え、分析用行を生成 |
| Research analysis service | 決定的統計、遅延比較、品質評価 |
| Weather decision service | 注意喚起と根拠を生成。機器を直接操作しない |
| Plant/calendar service | 承認済み変更だけを計画へ反映 |
| Flask route | 入力検証、権限、サービス呼出し、レスポンス |
| React UI | 研究ビュー、比較、仮説、根拠表示 |

外部プロバイダー固有のフィールドを植物管理サービスへ渡さない。統計計算をReactへ重複実装しない。Weather connectorから機器制御を呼ばない。

## 15. 保存・性能・保持

- JSONLは現行小規模互換として読み取り可能にするが、新規の圃場別期間検索は索引を持つDB repositoryを正とする。
- 観測と予報は追記型とし、訂正は新しい版として保存する。
- 生データ、時間集計、日次集計を分ける。
- UIは日次集計を優先し、拡大時だけ時間値を取得する。
- 研究APIは期間と最大点数を必須にする。
- 予報スナップショットは作業判断の監査期間を満たす限り保持する。
- 外部プロバイダーの利用規約、再配布条件、レート制限、帰属表示を保存する。
- 同じ地点・期間・変数の取得をキャッシュし、圃場ごとに同一要求を重複送信しない。

## 16. 移行

既存 `weather_records.jsonl` は削除しない。

1. 既存レコードを読み取り、プロバイダー、地点、対象日、種別を正規化する。
2. 圃場IDがないレコードは `unassigned` として保持する。
3. Hub既定座標と圃場候補が一致しても、自動的に正式帰属させない。
4. 管理者が対象圃場と期間を確認して関連付ける。
5. 関連付け後も元レコードIDと取得地点を保持する。
6. 予報レコードを気象実績へ変換しない。
7. 新repositoryへの移行完了後も、移行manifestと件数・期間・checksumを保存する。

移行の失敗で現行気象記録タスクを停止させない。新旧二重書き期間を設ける場合は、同一ソースIDで重複を除去する。

## 17. データ品質

各系列に次を表示可能にする。

- 取得元
- 圃場実測か外部グリッドか
- 観測・予報・推定の区別
- 最終取得時刻
- 空間解像度
- 時間粒度
- 欠測率
- 外れ値候補
- 校正状態
- センサー交換・移設
- 計算バージョン

外れ値は自動削除せず、原値を保持したまま分析対象から除外する選択を提供する。除外条件と実行者を分析スナップショットへ残す。

## 18. プライバシーと公開研究

- 正確な圃場座標は機密性の高い圃場設定として扱う。
- 通常画面、SNS投稿、公開エクスポートでは市区町村または匿名地域へ丸める。
- 公開研究データは利用者が対象期間、指標、位置精度、画像、作物情報を確認して明示的に作成する。
- 複数利用者のデータを横断集計する場合は、同意、匿名化、最小集団数、削除要求、用途を別途定める。
- 外部気象プロバイダーの利用条件と帰属を守る。

## 19. 検証

### 19.1 単体試験

- 日付境界とタイムゾーン
- 欠測を0にしないこと
- 単位変換
- 予報と実績の分離
- 圃場・配置・定植の範囲検証
- 日次集計
- 積算温度、VPD、ET0関連計算
- Pearson、Spearman、遅延相関
- サンプル数と欠測率
- 計算バージョンと元データ参照

### 19.2 統合試験

- 複数圃場で別地点を取得する。
- 同じ地点の取得をキャッシュする。
- 外部気象とハウス内ENVを区別する。
- 畝AのSOIと畝Bの作業を誤結合しない。
- 予報取得時点と後日の実績を比較できる。
- 既存JSONLを未割当のまま移行できる。
- 圃場権限外の研究データを取得できない。

### 19.3 UI試験

- データが少ない場合に相関を強調しない。
- 観測、外部解析、予報、推定を色だけに依存せず識別できる。
- 欠測期間が線で連結されない。
- モバイルでは系列数を絞り、横スクロールだけに依存しない。
- グラフから元記録、作業、画像へ移動できる。
- 研究結果から仮説と次の観察を保存できる。

## 20. 受入条件

Phase 1の完了条件:

1. 二つの圃場へ別の気象地点を設定できる。
2. 外部気象の実績と予報スナップショットを同時に保存できる。
3. 気象、センサー、潅水、施肥、作業、生育、収穫を日次データセットへ結合できる。
4. 圃場、配置、定植を誤って横断結合しない。
5. 研究ビューで複数系列と作業イベントを同じ期間に表示できる。
6. 二系列を選び、サンプル数、欠測率、Pearson、Spearman、遅延相関を確認できる。
7. 結果を因果と断定せず、品質と追加観測を表示する。
8. 分析条件と結果を仮説として保存できる。
9. CSVまたはJSONへ元データ参照付きで出力できる。
10. 既存気象JSONLと現在のInstagram投稿を壊さない。
11. 作業カレンダーや機器設定を自動変更しない。

## 21. 関連文書

- [作物前提データと改善ループ](AGRI_IMPROVEMENT_LOOP.md)
- [植物管理カレンダー仕様](HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md)
- [デバイス非依存の圃場記録仕様](HUB_DEVICE_FREE_FIELD_RECORDING_SPEC.md)
- [施肥計画・肥料サジェスト実装方針](HUB_FERTILIZATION_RECOMMENDATION_POLICY.md)
- [点滴潅水の吐出量校正・潅水提案・培地リセット仕様](HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md)
- [エージェンティック農作業の実装方針](HUB_AGENTIC_FARM_OPERATIONS_POLICY.md)
- [INASアーキテクチャ レイヤ分離ポリシー](../../../docs/jp/ARCHITECTURE_LAYERING_POLICY.md)
