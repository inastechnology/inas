# 製造要領書

この要領書は、INAS の ESP32S3 client device を同じ品質で製造するための手順である。対象は `WTR`、`WRS`、`ENV`、`SOI` とする。

## 入力資料

- 対象 device kind: `WTR`、`WRS`、`ENV`、`SOI`。
- 承認済み配線表: [esp32s3_wiring_tables.md](esp32s3_wiring_tables.md)。
- 対象 firmware project と `APP_DEVICE_KIND`。
- 筐体図、端子ラベル、部品表。
- センサーの manual。特に Modbus address、baud rate、function code、register map、scale、電源電圧。

## 安全境界

- INAS の自作 device enclosure 内で AC mains 配線を改造しない。
- 有資格者の確認がない限り、device enclosure 内は DC 低電圧配線だけにする。
- XIAO ESP32S3 を接続する前に 12V rail と 5V rail を確認する。
- soldering、crimp、端子変更の前に必ず電源を外す。
- pump、valve、cable に合った fuse または current limit を入れる。

## 製造手順

1. lot ID、日付、device kind、firmware version、firmware build ID、作業者、検査者を製造記録に作る。
2. 部品の破損、電圧定格違い、connector 緩み、端子ラベル不足を確認する。
3. 12V input 端子、DCDC、XIAO ESP32S3 carrier、MOSFET/driver board、RS485 transceiver、外部端子を固定する。
4. まず電源を配線する。`12V_IN`、5V DCDC output、XIAO `VBUS`、common GND を接続する。
5. XIAO board 未装着の状態で voltage rail を測定する。
6. XIAO board を装着し、配線表どおりに signal line を接続する。
7. device kind に応じて pump、valve、RS485 A/B/GND、sensor 12V、analog soil sensor、battery holder を外部端子へ配線する。
8. enclosure を閉じる前に terminal label と device label を貼る。
9. 対象 device kind の firmware を書き込む。
10. 下記の電気検査と機能検査を行う。

## 電気検査

| 検査 | 合格基準 |
|---|---|
| 12V input 極性 | input terminal で正しい |
| 5V rail | XIAO `VBUS` で 4.75-5.25V |
| GND 導通 | XIAO GND、RS485 GND、12V negative、DCDC GND が共通 |
| GPIO への 12V 混入 | XIAO GPIO に 12V が出ていない |
| MOSFET off state | boot 時に pump、valve、switched sensor 12V が OFF |
| RS485 A/B | A/B 間、A/B と電源間に short がない |
| SOI battery 極性 | `BAT+` と `BAT-` が holder label と一致 |

## 機能検査

| device kind | 必須検査 |
|---|---|
| `WTR` | boot、status publish、analog soil moisture 読み取り、valve/pump output、enabled RS485 sensor 読み取り |
| `WRS` | boot、status publish、valve/pump output、RS485 soil/PAR/日射 sensor 読み取り、未接続 sensor の `*_ok=false` |
| `ENV` | boot、status publish、configured RS485 sensor の読み取り、未接続 sensor の `*_ok=false` |
| `SOI` | boot、analog soil moisture 読み取り、sleep、再 wake、calibration config 反映 |

## 出荷記録

device と一緒に次を残す。

- device ID と device kind。
- firmware version と build ID。
- RS485 sensor に割り当てた Modbus slave ID。
- 配線検査結果。
- 機能検査結果。
- 逸脱、修理履歴。

## 不適合品の扱い

次の場合は出荷しない。

- XIAO GPIO に 12V が出ている。
- 必要な GND が共通化されていない。
- pump または valve output が ON 固着している。
- RS485 bus が short している。
- firmware の device kind と device label が一致しない。

該当品は hold とし、不良内容を記録し、修理後に電気検査と機能検査を最初からやり直す。
