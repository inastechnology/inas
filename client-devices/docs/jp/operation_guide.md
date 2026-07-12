# 運用手引き

この手引きは、設置後の日常運用を定義する。

## 日次確認

- active device が期待 interval 内に status を送っていることを確認する。
- `network_connected`、wake history、battery または supply voltage、RSSI を確認する。
- 接続予定の sensor について `*_ok` flag を確認する。
- threshold や schedule を変更する前に灌水履歴を確認する。
- `WTR` と `WRS` は、灌水後に土壌水分が反応しているか確認する。

## Calibration

| device kind | calibration |
|---|---|
| `SOI` | dry/wet reference を capture する。必要なら `dry_raw` と `wet_raw` を手動設定する |
| `WTR` | analog soil moisture を使う場合は校正する。RS485 値は env calibration で校正する |
| `WRS` | RS485 soil/PAR/日射値を校正する。analog soil input は通常未使用 |
| `ENV` | PAR、EC、pH などの RS485 値を既知 reference に合わせて校正する |

calibration record には日付、作業者、reference value、device の観測値を残す。

## 灌水運用

- 圃場での挙動が分かるまでは manual approval を標準にする。
- automation 前に最大灌水時間と最小灌水間隔を設定する。
- 灌水対象に近い soil moisture feedback を使う。
- 灌水後に水分が増えない場合は automation を停止する。
- pump runtime は action record であり、根域に水が届いた証明ではない。

## RS485 Sensor 運用

- sensor 追加は unique slave ID の割当で行い、XIAO pin は変えない。
- 1 台だけ失敗する場合は、その sensor の power、address、baud rate、A/B wiring を確認する。
- 全台失敗する場合は、bus power、common GND、A/B polarity、termination を確認する。
- 任意の未接続 sensor は `*_ok=false` として見える状態にする。

## 保守

| 間隔 | 作業 |
|---|---|
| 試験運用中は毎日 | status、灌水結果、sensor value の妥当性を確認 |
| 毎週 | cable gland、connector、腐食、enclosure seal を確認 |
| 毎月 | pump/valve 動作と filter 詰まりを確認 |
| 作期変更時 | placement、calibration、threshold、Modbus ID を見直す |
| 大雨後・修理後 | enclosure、power、RS485 bus、actuator output を確認 |

## 障害対応

| 症状 | 最初に見る場所 |
|---|---|
| device offline | power、battery、Wi-Fi、MQTT、antenna placement |
| sensor `*_ok=false` | sensor power、Modbus ID、baud、A/B、GND |
| pump が動かない | schedule approval、MOSFET output、fuse、pump wiring |
| valve が開かない | valve polarity、current rating、stuck valve、output command |
| 土壌水分が上がらない | water source、詰まり、sensor position、灌水時間不足 |
| 値が急に飛ぶ | wiring 緩み、浸水、calibration drift、sensor damage |

## 停止手順

1. hub で automatic irrigation を disable にする。
2. pump power source を OFF または unplug する。
3. 必要なら水源を閉じる。
4. pump と valve output が OFF であることを確認する。
5. automation を再開する前に、停止理由と復旧作業を記録する。
