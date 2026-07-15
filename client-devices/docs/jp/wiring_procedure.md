# 配線要領書

新規製造または修理時の配線手順を定義する。device kind ごとの pin と端子は [esp32s3_wiring_tables.md](esp32s3_wiring_tables.md) を参照する。

## 必要工具

- continuity と DC voltage を測れる multimeter。
- 使用端子に合った crimp tool。
- heat shrink、ferrule、cable tie、wire label。
- 初回通電用の current limit 付き bench supply。
- firmware flash と serial log 用 USB cable。

## 基本配線順序

1. device kind を確認し、対応する配線表を開く。
2. cable を圧着する前に wire label を付ける。
3. power input と GND を先に配線する。
4. 12V device では XIAO ESP32S3 を挿す前に 12V input と 5V output を測る。`SOI` では battery 極性と 3.3V sensor power を確認する。battery 駆動の WTR H/W profile では、承認済み WTR profile の検査に従う。
5. 内部 GPIO signal を配線する。
6. 外部端子を配線する。
7. 通電前に continuity と short を確認する。
8. current limit 付きで通電し boot を確認する。
9. sensor と actuator は group ごとに 1 つずつ接続して確認する。
10. device-specific functional test を行う。

## RS485 配線

- `RS485_A` と `RS485_B` は twisted pair を使う。
- 圃場配線では `RS485_GND` も bus と一緒に通す。
- 長い bus では必要に応じて物理端に termination を入れる。
- 全 driver idle 時に bus が不安定な場合は bias resistor を入れる。
- 同じ bus 上で Modbus slave ID を重複させない。
- 全 sensor が無応答の場合は、A/B 極性、baud rate、GND を最初に疑う。
- 5V MAX485 module を使う場合は、`RO` から ESP32S3 RX への信号を 3.3V へ level shift する。5V 出力を GPIO へ直結しない。
- SEN0641 は brown=VCC、black=GND、yellow=485-A、blue=485-B とし、既定 `4800bps / slave 1 / FC03 / register 0x0000` で検査する。

## ポンプ・バルブ配線

- 接続前に pump と valve の電圧・電流を確認する。
- inductive load には flyback protection を入れる。driver board 側に内蔵されている場合は仕様を確認する。
- pump/valve wiring は analog soil sensor wiring から離す。
- enclosure 引き込み部には strain relief を入れる。
- 圃場投入前に、水を外した状態または管理できる container 内で動作試験する。

低電圧 WTR H/W profile では、承認済み profile の WTR output pin と端子 label を使う。負荷電圧が違うだけで別 pin assignment を作らない。

## Analog Soil Sensor 配線

- `SOI` は `A0` を使う。
- WTR の analog soil moisture は `A5/D5` を使う。
- analog signal wire は短くし、motor wiring から離す。
- enclosure を閉じる前に乾燥/湿潤 raw ADC 値を確認する。

## 最終配線確認

| 検査 | 期待結果 |
|---|---|
| XIAO `VBUS` | 4.75-5.25V |
| XIAO GPIO | 12V が出ていない |
| GND | device と sensors で共通 |
| RS485 A/B | short なし、twisted pair 使用 |
| pump / valve | boot 時 OFF、command 時のみ ON |
| WTR profile output | boot 時 OFF、command 時のみ ON |
| sensor 12V switch | sleep 中 OFF、WTR/WRS の RS485 read 中 ON |
| BOOT button | 押下時だけ GPIO0 を Low にする |

逸脱があれば記録し、解消するまで enclosure を閉じない。
