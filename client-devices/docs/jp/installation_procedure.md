# 設置要領書

この要領書は、製造検査に合格した device を圃場へ設置する手順を定義する。

## 事前確認

1. 作物、圃場、区画、畝、ベッド、測点の名称を確認する。
2. hub 上の device placement scope を決める。field、section、ridge/bed、point のいずれか。
3. 電源を確認する。標準 `WTR`、`WRS`、`ENV` は 12V DC、`SOI` は充電済み 18650 battery、WTR H/W profile は承認済み電源。
4. setup AP、Wi-Fi、MQTT 到達性を確認する。
5. sensor 設置位置と Modbus slave ID 予定を記録する。
6. 水源、pump 方向、valve 方向、安全な排水を確認する。

## 固定

- enclosure は水跳ね・冠水高さより上に取り付ける。
- cable gland は上向きにしない。下向きまたは横向きにする。
- pump、valve、sensor、power cable に strain relief を入れる。
- 可能なら sensor cable は pump motor cable から離す。
- sensor と actuator の近くに service loop を残す。

## Sensor 配置

| device kind | 配置 |
|---|---|
| `SOI` | 畝・ベッド内の root-zone 代表測点 |
| `ENV` | 圃場全体または区画の代表環境点 |
| `WTR` | pump/valve と灌水対象の近く。local soil feedback と低電圧出力を同居させる WTR H/W profile は畝・ベッド・自動給水鉢にも配置できる |
| `WRS` | 灌水出力配線の近く。同じ RS485 bus に soil/PAR/日射 sensor を接続 |

イチゴ点滴栽培では、drip line の影響を受ける root-zone 近くに土壌フィードバックを置く。pump runtime だけで灌水成功を判断しない。

## 試運転

1. device に通電し boot を確認する。
2. Wi-Fi/MQTT 設定がない場合は setup AP mode に入る。
3. hub で device ID を登録または確認する。
4. field model に device placement を割り当てる。
5. 最新 status payload が hub に届くことを確認する。
6. RS485 sensor は、期待する sensor ごとに `*_ok=true` を確認する。
7. 任意 sensor の未接続は、pin assignment を変えずに `*_ok=false` と表示されることを確認する。
8. `WTR`、`WRS` は短時間の manual irrigation または output test を行う。
9. 灌水後に土壌水分が増えることを確認する。増えない場合は理由を記録する。
10. 設置メモ、写真、sensor ID、Modbus slave ID を保存する。

## 合格基準

- hub 上で正しい `device_kind` として表示される。
- device placement が、代表する作物・圃場単位と一致している。
- sensor value が現地として妥当である。
- pump/valve output は command 時以外 OFF である。
- unattended use 前に灌水時間上限と間隔制限が設定されている。
- enclosure が閉じられ、label が貼られ、防水保護されている。

## 引き渡し

運用者へ次を渡す。

- device ID と device kind。
- 設置場所と placement scope。
- sensor 一覧と Modbus slave ID。
- calibration status。
- manual stop procedure。
- 初回点検日。
