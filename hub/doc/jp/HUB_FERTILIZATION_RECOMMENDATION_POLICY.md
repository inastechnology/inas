# 施肥計画・肥料サジェスト実装方針

## 1. 目的

本機能は、初心者に「施肥という管理作業がある」ことを分かりやすく伝えながら、経験者には施肥履歴、肥料成分、気象、土壌・培地検査、生育状態を根拠にした追肥判断を提供する。

単に施肥日からの日数を数えたり、LLM の一般知識だけで肥料を推薦したりしない。次の問いに順番に答える。

1. 今、施肥を検討する時期か。
2. すでに入れた肥料の効果が残っている可能性はあるか。
3. 雨、潅水、排水、温度等により、計算上の残効をそのまま信用できるか。
4. 土壌・培地検査や作物状態から、どの養分が不足または過剰と考えられるか。
5. 追加するなら、どの肥料候補が不足を補い、過剰を増やしにくいか。
6. 判断材料が足りない場合、何を測ればよいか。

## 2. 最上位原則

### 2.1 計算値と測定値を分離する

施肥履歴から計算した値は `model_estimate`、検査・センサーで確認した値は `observation` として別に保存する。検査値で計算履歴を上書きせず、両者の差を判断材料とする。

- 計算上の残効は、投入量と肥効モデルから求める推定値である。
- 土壌検査値は、その肥料だけでなく、元の土壌養分、過去の資材、土壌有機物由来の養分を含む。
- どちらも作物が今後吸収できる量を直接保証しない。
- UI は「計算上の残効」「検査で確認した養分」「判断の信頼度」を明確に分ける。

### 2.2 不明なときは施肥ではなく確認を提案する

次の場合、具体的な追加量を確定せず、検査、EC確認、葉色・樹勢確認、または見送りを優先する。

- 成分表示または投入量が不明
- 検査がない、古い、測定法が不明
- 強い雨、過剰潅水、排水異常の後
- ECが高い、または急上昇している
- 作物状態と計算結果が一致しない
- 公的な施肥基準を作物、地域、作型へ適用できない

### 2.3 LLM に計算と製品選定を任せない

養分量、肥効、気象集計、候補順位、信頼度はサーバーの決定的なサービスで計算する。LLM は、検証済みの計算結果と候補を初心者にも分かる文章へ変換し、観察方法と見送り条件を説明する。

LLM は、サーバーが渡していない肥料製品、成分率、使用量、出典を追加してはならない。

## 3. 初心者向けUX

初心者へ最初から N、P2O5、K2O、CEC 等を並べない。画面は次の順で説明する。

1. 「肥料は作物のごはんですが、多すぎても弱ります」
2. 「前に入れた肥料が残っていないか確認します」
3. 「雨や水やりで流れた可能性を確認します」
4. 「土や葉の状態を確認します」
5. 「今は追加する／検査してから決める／今回は見送る」を示す

初期表示は一つの結論と理由を優先する。

```text
今は肥料を追加せず、土の状態を確認しましょう

理由:
- 3週間前に8-8-8を施用しています
- 計算上は窒素とカリが残っている可能性があります
- 施肥後に強い雨があり、残効の確かさは「低め」です

次にすること:
- 土壌ECまたは硝酸態窒素を測る
- 下葉の色と新しい葉の伸びを確認する
```

「詳しい根拠」で養分kg、測定単位、肥効曲線、気象集計、出典を表示する。上級者設定では、肥効モデル、雨の当たり方、土質、成分別係数を編集できる。

## 4. 肥料カタログ

### 4.1 カタログの種類

- `builtin`: 公的資料等を根拠にした一般肥料テンプレート
- `user`: 利用者が製品ラベルや分析表から登録した独自肥料
- `shared`: 将来、組織管理者が承認して共有する肥料

一般肥料の値は「代表的な開始値」であり、特定製品の保証値ではない。実際に使うときは製品ラベルを優先する。

初期カタログは次を対象とする。

- 化成肥料 8-8-8、14-14-14
- 尿素、硫安、硫酸加里
- 牛ふん堆肥、豚ぷん堆肥、鶏ふん堆肥、乾燥鶏ふん
- 菜種油かす、魚かす、骨粉、米ぬか
- 植物性堆肥
- 緩効性・被覆肥料
- 液肥、養液用A液・B液
- 製品ラベルから入力する独自肥料

### 4.2 カタログ項目

```text
id
scope                       builtin | user | shared
owner_id
name
manufacturer
material_class              chemical | organic | manure | compost | liquid | controlled_release | custom
form                         granule | powder | pellet | liquid | compost | other
application_roles           basal | topdress | fertigation | soil_conditioning
nutrient_basis              product_weight | dry_weight
moisture_percent
nutrients:
  n_total_percent
  n_nitrate_percent
  n_ammonium_percent
  n_urea_percent
  n_organic_percent
  p2o5_percent
  p2o5_water_soluble_percent
  k2o_percent
  k2o_water_soluble_percent
  mgo_percent
release_profiles:
  n / p2o5 / k2o / mgo:
    model                    immediate | staged | linear | temperature_dependent | coated | unknown
    start_delay_days
    duration_days
    curve_parameters
mobility_risk:
  n / p2o5 / k2o / mgo      low | medium | high | unknown
recommended_conditions
avoid_conditions
label_source
source_url
source_checked_at
notes
revision
```

肥料区分だけで流亡を決めない。硝酸態窒素、アンモニア態窒素、リン酸、カリ等、成分形態ごとに移動性と放出特性を持つ。被覆肥料は化成肥料であっても別の溶出モデルを使用する。

### 4.3 独自肥料の登録

利用者は次の方法で独自肥料を追加できる。

- 製品名と成分率を手入力
- 製品ラベルの写真またはPDFを添付し、AI読み取り後に利用者が確定
- 既存の一般肥料を複製して上書き

AI読み取り値は未確認状態で保存し、利用者が保証成分、単位、重量基準を確認するまで施肥量計算へ使わない。組織内共有は管理者承認後とする。

## 5. 気象・水収支による残効信頼度

### 5.1 使用する実績値

施肥後の残効評価には予報ではなく、次の優先順位で実績値を使う。

1. 圃場の雨量計
2. 潅水デバイス・流量計の実績
3. 近隣観測地点の実績
4. Open-Meteo の解析・再解析日別値
5. 利用者の手入力

予報は「施肥直後の大雨を避ける」事前サジェストにだけ使い、過去に実際に降った量として扱わない。

既存の `OpenMeteoWeatherService` と `WeatherRecordRepository` を外部気象アダプターおよび保存層として再利用する。施肥判断サービスはプロバイダー固有形式を直接参照しない。

### 5.2 圃場と栽培場所

Hub 全体で一つの緯度経度を使う方式から、圃場ごとの緯度経度を優先する方式へ拡張する。位置情報がない圃場だけHub既定位置へフォールバックする。

栽培場所には初心者向けの `rain_exposure` を持たせる。

- `exposed`: 雨がそのまま当たる
- `partial`: 少し雨が入る
- `sheltered`: 屋根・軒下で雨がほぼ入らない
- `indoor`: 屋内・閉鎖施設

上級者設定で0〜1の係数を指定できる。ハウス、軒下、鉢では、地域降水量をそのまま根域流入量にしない。

### 5.3 集計項目

各施肥履歴について、施肥日から評価日まで次を集計する。

- 累積降水量・有効降雨量
- 施肥後24、48、72時間の降水量
- 最大日降水量
- 雨日数・降水時間
- 潅水量
- ET0
- 土壌水分の飽和・過湿時間
- 排水量が測れる場合は排水量
- データ取得率と欠測期間

初版では降水量から肥料kgを一意に減算しない。肥料の移動性、土質、栽培方法、雨の当たり方、施肥直後の雨を用いて `leaching_risk` と `estimate_confidence` を返す。

```text
leaching_risk              low | medium | high | unknown
estimate_confidence        high | medium | low
confidence_reasons         string[]
measurement_recommended    boolean
```

検査実績との比較が蓄積してから、圃場別・成分別の補正係数や推定範囲を導入する。研究根拠または圃場校正のない固定割合で残効を減算しない。

## 6. 土壌・培地検査

### 6.1 測定値の区分

- 常設センサー: 土壌水分、地温、EC等の連続的な傾向
- 簡易検査: pH、硝酸態窒素、水溶性リン酸・カリ等の現場確認
- 精密分析: 可給態窒素・リン酸、交換性カリ・石灰・苦土、CEC等
- 作物体診断: 葉色、搾汁液、葉分析等

ECをNPKの個別量へ変換しない。水溶性リン酸と可給態リン酸、水溶性カリと交換性カリを同じ項目として比較しない。

### 6.2 保存項目

```text
id
field_id / space_id / placement_id
sampled_at
sample_depth_cm
sampling_points
sampling_note
method_id
method_name
method_class                sensor | quick_kit | laboratory | plant_tissue
extraction_method
laboratory_name
results[]:
  analyte
  value
  unit
  basis
  detection_limit
  confidence
attachment_ids
confirmed_by_user
```

採取深さ、複数地点の混合、抽出法、単位が異なる値は、そのまま時系列比較しない。入力画面は使用したキット・分析機関を先に選び、必要項目と単位を自動設定する。

### 6.3 推奨運用

- 常設センサーは変化の検知に使う。
- 簡易検査は追肥前、強い雨の後、異常時の再確認に使う。
- 精密分析は作付前または年次の基準値として使う。
- 検査が古い、または検査後の施肥・強雨が多い場合は信頼度を下げる。

## 7. 施肥判断サービス

### 7.1 レイヤー

アーキテクチャ方針に従い、責務を次のように分ける。

- `FertilizerCatalogRepository`: 組み込み・独自肥料の保存と検索
- `SoilTestRepository`: 検査結果と添付参照の保存
- `WeatherHistoryAdapter`: Open-Meteo等の外部形式を正規化
- `WeatherExposureService`: 施肥後の降雨・潅水・曝露を集計
- `FertilizerReleaseService`: 成分別肥効曲線と理論残効を計算
- `FertilizationAssessmentService`: 残効、検査、作物目標、気象リスクから判断候補を作る
- `AIContentService`: 検証済み判断を利用者向け文章と作業候補へ変換

Flaskルートは入力検証とサービス呼び出しに限定する。UI、外部気象、計算式をリポジトリへ混在させない。

### 7.2 判断結果

```text
status                      apply | inspect_first | observe | skip
confidence                  high | medium | low
nutrient_balance[]
theoretical_remaining[]
observed_available[]
weather_exposure
leaching_risk[]
recommended_tests[]
validated_material_candidates[]
warnings[]
evidence[]
```

候補肥料は、作物・生育段階の目標量から、検査で確認した利用可能養分と計画期間中の推定供給量を差し引き、不足を補い過剰を増やしにくい順に並べる。

```text
必要養分
= 作物・生育段階の目標量
- 検査で確認した利用可能養分
- 既存肥料から計画期間中に供給される推定量
```

検査と適用可能な施肥基準がない場合、この式から具体量を確定しない。候補ごとに「不足への一致」「過剰になる成分」「EC・塩類リスク」「速効・緩効」「根拠」を表示する。

## 8. API案

- `GET /local/api/fertilizer-materials`
- `POST /local/api/fertilizer-materials`
- `PATCH /local/api/fertilizer-materials/<id>`
- `DELETE /local/api/fertilizer-materials/<id>`
- `GET /local/api/plantings/<id>/fertilizer-applications`
- `POST /local/api/plantings/<id>/fertilizer-applications`
- `GET /local/api/placements/<id>/soil-tests`
- `POST /local/api/placements/<id>/soil-tests`
- `GET /local/api/plantings/<id>/fertilization-assessment`

組み込み肥料は編集・削除不可とし、複製して独自肥料にできる。独自肥料は所有者または組織の権限で制御する。既存施肥履歴は保存時のカタログスナップショットを保持し、後からカタログが改訂されても過去の計算根拠を失わない。

## 9. 実装段階

### Phase 1: 肥料カタログと独自肥料

- UIに固定されたプリセットをサーバー側カタログへ移す
- 一般肥料、出典、改訂番号を登録する
- 独自肥料の追加・複製・編集・削除を実装する
- 施肥履歴へカタログスナップショットを保存する
- 現行DBを無移行で読める互換正規化を残す

### Phase 2: 検査結果と信頼度

- 土壌・培地検査結果の手入力と履歴表示
- キット・分析法ごとの単位と項目テンプレート
- PDF・画像添付
- 計算値と測定値の分離表示
- 検査日、施肥日、強雨から検査の鮮度を評価する

### Phase 3: 気象・潅水補正

- 圃場緯度経度と栽培場所の雨曝露を追加する
- 施肥日以降の実績気象をオンデマンドで補完・集計する
- 潅水実績、土壌水分、排水実績を統合する
- 成分別の流亡リスクと残効信頼度を算出する
- 施肥前の強雨予報と、施肥後の再検査候補を作る

### Phase 4: 成分別肥効と候補順位

- 現行の全成分共通・線形モデルを成分別放出曲線へ置き換える
- 作物、地域、作型、面積・株数の目標量を構造化する
- 不足と過剰を評価し、検証済み肥料候補を順位付けする
- 自動計画と一件ずつ承認する半自動計画へ統合する

### Phase 5: 圃場校正

- 同じ方法で測った検査結果と予測値を比較する
- 圃場・土質・季節・肥料別の誤差を蓄積する
- 十分な観測数と妥当性確認がある場合だけ補正係数を適用する
- 補正前後、使用データ、信頼区間を利用者へ表示する

## 10. テスト方針

### ドメイン試験

- 同じNPKでも速効性、緩効性、有機質で供給曲線が異なる
- 硝酸態、アンモニア態、リン酸、カリを同じ流亡係数にしない
- 軒下・ハウスでは地域降水量を根域流入へ直接加算しない
- 施肥前の雨を施肥後集計に含めない
- 予報値を実績降水として使わない
- 欠測時に信頼度が上がらない
- 検査法と単位が違う値を直接比較しない
- 検査なしでは具体的な施肥量を確定しない
- 高EC・過剰養分では追加候補より見送りを優先する

### リポジトリ・API試験

- 組み込み肥料は変更不可、独自肥料は所有範囲でCRUD可能
- カタログ改訂後も過去施肥履歴のスナップショットが変わらない
- 既存DBの施肥履歴を引き続き読み込める
- 気象バックフィルが日付・位置・タイムゾーン単位で重複しない
- 外部気象取得失敗時も栽培計画作成自体は失敗しない

### UI・E2E試験

- 初心者表示で結論、理由、次の行動が先に見える
- 詳細表示で計算値、測定値、信頼度、出典を区別できる
- 独自肥料のラベル確認前は計算へ採用されない
- 土壌検査登録後にサジェストと信頼度が変わる
- 強雨、軒下、欠測の各デモデータを画面キャプチャで確認する

## 11. 完了条件

初版は次を満たした時点で完了とする。

- 一般肥料カタログと独自肥料をサーバーで管理できる
- 施肥履歴へ選択した肥料のスナップショットを保存できる
- 土壌・培地検査を方法・単位付きで記録できる
- 施肥後の実績降水・潅水を集計できる
- 雨曝露、欠測、肥料成分から流亡リスクと信頼度を表示できる
- 判断材料が足りない場合は施肥ではなく検査を提案する
- AIは検証済み候補だけを説明する
- 回帰試験、管理UIビルド、デモ操作、画面キャプチャ確認が完了する

## 12. 参考資料

- 農林水産省「食品中の硝酸塩に関する基礎情報」: https://www.maff.go.jp/j/syouan/seisaku/risk_analysis/priority/syosanen/about/index.html
- 農林水産省「土壌診断と堆肥活用による肥料節減指針」: https://www.maff.go.jp/j/seisan/kankyo/hozen_type/h_sehi_kizyun/pdf/sisin0.pdf
- 農研機構「有機質資材肥効見える化アプリ」: https://www.naro.go.jp/publicity_report/press/laboratory/karc/169314.html
- JA全農「土壌診断について」: https://www.zennoh.or.jp/activity/hiryo_sehi/uketuke.html
- Siemens Healthineers「みどりくん」: https://www.siemens-healthineers.com/jp/environmental-test/midorikun
- HORIBA「LAQUAtwin NO3-11S」: https://www.horiba.com/jpn/water-quality/detail/action/show/Product/no3-11c-no3-11s-no3-11-794/
- Open-Meteo Historical Weather API: https://open-meteo.com/en/docs/historical-weather-api

