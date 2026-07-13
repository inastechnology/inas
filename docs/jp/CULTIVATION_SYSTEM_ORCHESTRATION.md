# 栽培システムのオーケストレーション方針

英語版:

- [../CULTIVATION_SYSTEM_ORCHESTRATION.md](../CULTIVATION_SYSTEM_ORCHESTRATION.md)

## 目的

この文書は、イチゴ点滴栽培システムのような作物別システムを INAS でどう扱うかを記録する。作物別システムは、巨大な単一デバイスではなく、device hub が複数の単純なデバイスを束ねる system profile として扱う。

device の境界は安定させる。作物固有のふるまいは、hub の制御方針、圃場前提、デバイス配置、アクション履歴、評価ループに置く。

## 基本方針

作物別の栽培システムは、複数要素の組み合わせである。

```text
strawberry-drip-system-01
  圃場 / ベッド / 測点の前提
  環境センサデバイス
  灌水指示デバイス
  灌水フィードバック用の土壌水分センサー
  hub のオーケストレーション方針
```

hub がオーケストレーションを担当する。デバイスは測定または実行を担当する。固定のハードウェア構成や payload 契約が変わらない限り、デバイス自身が「イチゴを育てている」ことを知る必要はない。

## デバイスの役割

| 役割 | 責務 | 例 |
|---|---|---|
| 環境センサデバイス | 判断に使う広域の環境値を観測する | PAR/PPFD、気温、湿度、土壌 EC/pH/NPK を読む `ENV` |
| 土壌フィードバックデバイス | 灌水対象地点で水分反応を測る | `SOI`、WTR 内蔵の土壌水分、WRS の RS485 土壌センサー、同じベッドに置いた別プローブ |
| 灌水指示デバイス | 水源の ON/OFF を実行する | WTR/WRS 出力、WTR の低電圧 H/W profile 出力、AC/DC アダプタやポンプを制御する SwitchBot Plug Mini |
| device hub | 前提と測定値を比較し、判断、指示、検証、記録を行う | local hub の policy と action plan |

イチゴ点滴栽培では、灌水指示デバイスは同じベッド、畝、または代表測点の土壌水分センサーとセットで扱うべきである。プラグやポンプスイッチだけでは、水が根域へ届いたことを証明できない。

## 灌水フィードバックのルール

灌水は、期待されるセンサー反応を持つアクションである。hub はその反応を記録し、評価する。

最小シーケンス:

1. 灌水前に土壌水分を読む。
2. 上限時間付きで灌水を開始する。
3. 後続の検証に失敗しても、灌水停止を先に実行する。
4. 安定待ちの途中または後に土壌水分を読む。
5. 灌水前後の差分を記録し、結果を分類する。

反応分類:

| 結果 | 意味 | hub の扱い |
|---|---|---|
| `expected_response` | 土壌水分が期待範囲で増えた | 灌水成功の根拠として保存する |
| `weak_response` | 増えたが期待より弱い | 灌水時間不足、点滴詰まり、センサー位置ずれ、培地の乾きすぎを疑う |
| `no_response` | 土壌水分が増えない | 自動の連続灌水を止め、空タンク、ポンプ故障、プラグ故障、チューブ詰まり、センサー位置ずれを通知する |
| `excessive_response` | 増え方が大きすぎる、または速すぎる | 過剰灌水、漏水、排水不良、灌水時間の不適合を通知する |

期待差分は、作物、培地、センサー、設置位置に依存する。全圃場共通の固定値としてハードコードしない。最初は保守的なしきい値から始め、圃場履歴で調整する。

## SwitchBot Plug を灌水指示デバイスとして使う場合

SwitchBot Plug Mini は、AC 電源の制御を ESP32 リレーで自作するより安く安全に始められる場合がある。INAS では、これを完全な灌水デバイスではなく、外部アクチュエータアダプタとして扱う。

推奨境界:

```text
device hub
  -> SwitchBot Plug command: turn on/off
  -> AC/DC アダプタまたはポンプ電源
  -> 点滴チューブ
  -> 土壌フィードバックセンサーが根域の反応を確認
```

運用ルール:

- hub は必ず上限時間付きの灌水指示を送る。予定された `turnOff` を伴わない単純な `turnOn` は、灌水指示として扱わない。
- hub は `turnOff` をリトライし、可能ならプラグの状態または電流を確認する。
- hub はプラグと土壌水分センサーの配置をペアにする。例: `strawberry-irrigation-plug-01` と `strawberry-soil-bed-a-01`。
- タンク容量、漏水検知、最大運転時間、最小間隔、手動停止などの物理的な安全制限も使う。
- API 依存のアクチュエータは個人向け小規模運用では有効だが、それだけを唯一の安全境界にしない。

## System Profile 例

```json
{
  "system_id": "strawberry-drip-system-01",
  "crop": "strawberry",
  "field_unit": "bed-a",
  "devices": {
    "environment": ["env-field-01"],
    "irrigation_actuator": "switchbot-plug-drip-01",
    "irrigation_feedback": ["soil-bed-a-01"]
  },
  "policy": {
    "automation_level": "manual_approval",
    "max_duration_sec": 120,
    "min_interval_min": 90,
    "require_moisture_response": true,
    "response_settle_sec": 300
  }
}
```

具体的な保存スキーマは今後変わってよい。ただし、作物前提、対象圃場単位、アクチュエータ、フィードバックセンサー、制御方針の関係は保持する。

## 障害時の扱い

灌水アクションでは、先に水を止め、その後で不確実性を説明する。

- `turnOn` 後にアクチュエータ状態を確認できない場合は、`turnOff` を送り、アクションを不確実として記録し、通知する。
- `turnOff` が失敗する、または状態が ON のままなら、リトライして即時通知する。
- プラグに電流が出ているのに土壌水分が上がらない場合、センサー異常だけでなく水路側の故障を疑う。
- 指示していないのに土壌水分が上がる場合、漏水、手動灌水、別水源を疑い、観測イベントとして記録する。
- 土壌センサーが未設置または stale の場合、手動灌水は許可してよいが、検証済みの自動灌水として扱わない。

## Device Kind との関係

`WTR` は灌水出力と土壌フィードバックを同じ筐体で持つため、個人用の全部入り水やり機として有用である。`WRS` は、土壌、PAR、日射などのセンサーを pin assignment を変えずに同じ RS485 bus へ増やしていくための RS485 前提の上位版である。土壌フィードバックと低電圧出力を 1 台の小型 device に置く場合でも、hub 挙動と payload contract が WTR のままなら WTR の H/W profile として扱う。`SOI` と `ENV` は、hub が専用センサーデバイスと外部アクチュエータを組み合わせて作物別システムを作る方向を支える。

作物がイチゴである、または WTR の電源電圧や MOSFET 定格が違うという理由だけで新しい device kind を作らない。H/W role、payload schema、hub 挙動が大きく変わる場合に新しい device kind を作る。

関連ドキュメント:

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md)
- [hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md](../../hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md)
- [client-devices/docs/jp/rs485_sensor_device_spec.md](../../client-devices/docs/jp/rs485_sensor_device_spec.md)
