# ComWinTop CWT-SOIL NPKPHCTH-S RS485 土壌センサー仕様

## 文書の位置づけ

ComWinTop の 5 本プローブ、RS485 出力、土壌水分・温度・EC・pH・N・P・K
対応モデルを INAS の `ENV` / `WRS` へ接続するための製品別仕様である。
メーカー配布 ZIP の `NPK type (5Pin probe) manual_V1.4.pdf` と同梱資料を
2026-08-01 に再取得し、配線、電源、Modbus レジスタ、測定上の注意を確認した。

対象候補は `NPKPHCTH-S` である。販売ページには複数仕様が同居しているため、
通電前に実機ラベルで次を確認する。

- Output が `RS485`
- Power が `5-30V DC`
- Temperature、Moisture、Conductivity、pH、Nitrogen、Phosphorus、
  Potassium の 7 項目が対象
- 5 本プローブ

上記と異なる実機には、このプロファイルを適用しない。

この文書の状態は「メーカー資料確認済み、実機ベンチ試験未実施」である。

## 原本と追跡情報

| 項目 | 値 |
|---|---|
| メーカー製品ページ | [ComWinTop CWT-SOIL sensor](https://store.comwintop.com/products/rs485-4-20ma-soil-temperature-humidity-moisture-conductivity-ec-ph-sensor) |
| 購入品を特定した販売ページ | [AliExpress item 1005005684119688](https://www.aliexpress.com/item/1005005684119688.html) |
| メーカー配布資料 | [CWT soil sensor_2 manual.zip](https://wiki20210805.oss-cn-hongkong.aliyuncs.com/download/sensors/Smart_Agriculture/CWT%20soil%20sensor_2%20manual.zip) |
| 取得日 | 2026-08-01 |
| ZIP 更新日時 | 2024-06-02 06:14:12 GMT |
| ZIP サイズ | 17,373,044 bytes |
| ZIP SHA-256 | `a6fd3e69ed2804882c20a795db2575f82109c16b299014b29c38d56d0325abe2` |
| 対象 PDF | `CWT soil sensor_2 manual/CWT soil sensor (RS485 type) manual/NPK type (5Pin probe) manual_V1.4.pdf` |
| 対象 PDF SHA-256 | `8790291e89e83419e91a2d825c115b345221a789c77a464900126a99c614b7aa` |

原本を再取得するときは、次の URL と SHA-256 を使う。

```bash
curl -L --fail \
  'https://wiki20210805.oss-cn-hongkong.aliyuncs.com/download/sensors/Smart_Agriculture/CWT%20soil%20sensor_2%20manual.zip' \
  -o CWT-soil-sensor-manual.zip
sha256sum CWT-soil-sensor-manual.zip
```

製品ページとマニュアルで数値が異なる箇所は、対象モデルを明示している
5 本プローブ用 V1.4 マニュアルを優先した。実機ラベルや個体付属資料が異なる
場合は、実機側を優先して差分をこの文書へ追記する。

## 12V と RS485 の配線

### V1.4 マニュアル記載の現行配線

`Yellow/Green` は黄と緑の 2 本ではなく、黄緑色または黄/緑ストライプの
1 本を表す。合計 4 芯である。

| センサー線 | 信号 | WRS 接続先 | ENV 接続先 |
|---|---|---|---|
| 茶 `Brown` | 電源＋ | `SENSOR_12V_SW+` | `SENSOR_12V+` |
| 黒 `Black` | 電源－ / 0V | `RS485_GND` | `RS485_GND` |
| 黄緑 `Yellow/Green` | RS485 A+ | `RS485_A` | `RS485_A` |
| 青 `Blue` | RS485 B- | `RS485_B` | `RS485_B` |

12V 電源を使うときは、非絶縁構成では GND も接続する。

```text
12V電源（－）
  ├─ センサー 黒 / Power -
  ├─ RS485_GND
  ├─ RS485トランシーバ GND
  └─ XIAO ESP32S3 GND
```

ポンプやバルブの大電流を細いセンサー GND 線へ流さず、装置内の共通 GND
ポイントで合流させる。XIAO の `VBUS` や GPIO へ 12V を直接接続しない。
ガルバニック絶縁された RS485 と絶縁電源を使う構成は、この共通 GND 配線の
例外である。

### 同梱設定ツールに残る別配線

ZIP 内の `Config Tool (NPK type_5pin probe)_V1.3` には、次の別ロットと
みられる配線表示も残っている。

| 実機の 4 芯がこの色の場合 | 信号 |
|---|---|
| 赤 `Red` | DC 12V |
| 黒 `Black` | GND |
| 黄 `Yellow` | RS485 A+ |
| 緑 `Green` | RS485 B- |

茶・黒・黄緑・青のロットと、赤・黒・黄・緑のロットを混ぜて解釈しない。
線色がどちらにも一致しない場合は通電せず、個体ラベルまたは販売元へ確認する。

## 電気・筐体仕様

| 項目 | V1.4 マニュアル値 |
|---|---|
| 電源 | DC 4.5-30V。配線表と製品ラベルは DC 5-30V 表記。INAS では DC 12V を使用 |
| 最大消費電力 | 0.5W @ 24V DC |
| 出力 | RS485、Modbus RTU |
| 保護等級 | IP68 |
| ケーブル | 2m |
| 使用温度 | -40～80℃ |
| 外形 | 45 × 15 × 123mm |
| 測定範囲の目安 | プローブ周辺直径 約 5cm |

電源下限には資料内で 4.5V と 5V の差があるが、12V 運用には影響しない。
初回通電は電流制限付き電源を使う。センサーを外した状態で装置側の
`RS485_GND` を基準に電源端子が +12V であることを確認し、電源を切ってから
茶線と黒線を接続する。

## 測定仕様

| 測定項目 | 範囲 | 精度 | 分解能 / 応答時間 |
|---|---:|---:|---:|
| 土壌温度 | -40～80℃ | ±0.5℃ @ 25℃ | 応答 15秒以下 |
| 土壌水分 `Humidity` | 0～100% | 0～50%で ±3%、50～100%で ±5% | 応答 4秒以下 |
| EC | 0～20,000µS/cm | 0～10,000で ±3%、10,000～20,000で ±5% | 1µS/cm、応答 1秒以下 |
| pH | 3～9 | ±0.3pH | 0.1pH、応答 10秒以下 |
| N / P / K | 1～2,999mg/kg（mg/L） | メーカーは参考値として扱うよう明記 | 1mg/kg、応答 1秒未満 |

N/P/K の上限は V1.4 PDF では `2999`、現行製品ページでは `1999` と異なる。
自動施肥判断には上限値を含めて実機確認が必要である。

## Modbus RTU プロファイル

| 項目 | 設定 |
|---|---|
| 物理層 | RS485 2-wire |
| 通信方式 | Modbus RTU |
| 工場出荷 slave ID | `1` |
| slave ID 設定範囲 | `1`～`254`。INAS では標準範囲の `1`～`247` を使用 |
| baud rate | `4800bps` |
| フレーム | 8 data bits、parity none、1 stop bit（8N1） |
| 読み出し | Function `0x03`、Read Holding Registers |
| 1 register 書き込み | Function `0x06`、Write Single Register |
| CRC | Modbus CRC-16。送信順は Low byte、High byte |

V1.4 PDF の表見出しには read `0x30`、write `0x60` とあるが、同 PDF の全
フレーム例と同梱設定ツールの実装は `0x03` / `0x06` で一致する。`0x30` /
`0x60` は桁順の誤記として扱う。

### 測定レジスタ

アドレスは Modbus PDU 上の 0-based register address である。PLC 表記では
それぞれ `40001` から始まる。

| Address | PLC address | 値 | 変換 | Access |
|---:|---:|---|---|---|
| `0x0000` | 40001 | 土壌水分 | raw × 0.1% | Read |
| `0x0001` | 40002 | 土壌温度 | signed int16 raw × 0.1℃ | Read |
| `0x0002` | 40003 | EC | raw × 1µS/cm | Read |
| `0x0003` | 40004 | pH | raw × 0.1 | Read |
| `0x0004` | 40005 | 窒素 N | raw × 1mg/kg | Read / Write |
| `0x0005` | 40006 | リン P | raw × 1mg/kg | Read / Write |
| `0x0006` | 40007 | カリウム K | raw × 1mg/kg | Read / Write |
| `0x0007` | 40008 | 塩分 | raw × 1mg/L | Read |
| `0x0008` | 40009 | TDS | raw × 1mg/L | Read |

INAS が使う 7 項目は `0x0000` から 7 registers を 1 回の FC03 で読む。
工場出荷 ID `1` の要求フレームは次のとおり。

```text
01 03 00 00 00 07 04 08
```

### 補正・設定レジスタ

| Address | 値 | 表現 / 初期値 |
|---:|---|---|
| `0x0022` | EC factor | raw `0`～`100` = 0.0～10.0%、初期値 0.0% |
| `0x0023` | Salinity factor | raw `0`～`100` = 0.00～1.00、初期値 `55` = 0.55 |
| `0x0024` | TDS factor | raw `0`～`100` = 0.00～1.00、初期値 `50` = 0.50 |
| `0x0050` | Temperature offset | signed raw × 0.1 |
| `0x0051` | Humidity offset | signed raw × 0.1 |
| `0x0052` | EC offset | signed raw × 1 |
| `0x0053` | pH offset | signed raw × 1 |
| `0x04E8` / `0x04E9` | N factor | 2 registers の float |
| `0x04EA` | N offset | signed raw × 1 |
| `0x04F2` / `0x04F3` | P factor | 2 registers の float |
| `0x04F4` | P offset | signed raw × 1 |
| `0x04FC` / `0x04FD` | K factor | 2 registers の float |
| `0x04FE` | K offset | signed raw × 1 |
| `0x07D0` | Slave ID | `1`～`254` |
| `0x07D1` | Baud rate | `0`=2400、`1`=4800、`2`=9600 |

センサー内部補正は `Y = A × X + B` で、`A` が factor、`B` が offset。
基準器なしで factor / offset を変更しない。

N/P/K の register に基準器の測定値を書き込むと値が固定される。自動測定へ
戻すには、N/P/K の各 register へ `0xFFFF` を書き込んでリセットする。

## INAS の固定 Slave ID

RS485 bus の ID は、センサーの有無によって詰めず、用途ごとに固定する。

| Slave ID | 用途 | 初期設定 |
|---:|---|---|
| `1` | 土壌センサー 1 | CWT の工場出荷値をそのまま使用 |
| `2` | 土壌センサー 2 | 対象を単独接続して `1` から `2` へ変更 |
| `3` | PAR センサー | SEN0641 を単独接続して `1` から `3` へ変更 |

土壌センサー 2 が未設置でも、PAR センサーは `2` ではなく `3` とする。
これにより、設置構成が変わってもセンサーの役割と ID の対応が変わらない。

2 台目の CWT を ID `2` へ変更するときは、次の手順で行う。

1. ほかの CWT、PAR センサー、そのほかの RS485 機器を bus から外す。
2. 2 台目にする CWT だけを 4800bps / 8N1、ID `1` で接続する。
3. 次の FC06 フレームを 1 回送る。
4. センサーから同じフレームが返ることを確認する。
5. ID `2` で 7 registers を読めることを確認してからほかの機器を戻す。

```text
# ID 1 の設定 register 0x07D0 へ ID 2 を書く
01 06 07 D0 00 02 08 86

# ID 2 で 0x0000 から 7 registers を読む
02 03 00 00 00 07 04 3B
```

DFRobot の
[SEN0641 Modbus リファレンス](https://wiki.dfrobot.com/sen0641/docs/20337)
でも、device address は read/write register `0x07D0`、書込みは FC06 と
定義されている。SEN0641 を ID `1` から `3` へ変更する場合も、ほかの機器を
外して次のフレームを 1 回だけ送り、同じ応答が返った後に ID `3` で読める
ことを確認する。

```text
# SEN0641: ID 1 の register 0x07D0 へ ID 3 を書く
01 06 07 D0 00 03 C9 46

# ID 3 で PAR register 0x0000 を読む
03 03 00 00 00 01 85 E8
```

現在 ID が分からない場合、マニュアルは broadcast address `0xFF` で次の
問い合わせを示している。bus 上に対象センサー 1 台だけを接続して実行する。

```text
FF 03 07 D0 00 01 91 59
```

## INAS 接続プロファイル

| 項目 | ENV | WRS |
|---|---|---|
| 電源端子 | `SENSOR_12V+` | `SENSOR_12V_SW+` |
| GND | `RS485_GND` | `RS485_GND` |
| 通信 | 4800bps / 8N1 / FC03 | 4800bps / 8N1 / FC03 |
| 土壌センサー ID | 1 台目 `1`、2 台目 `2` | 1 台目 `1`、2 台目 `2` |
| PAR センサー ID | `3` | `3` |
| Start register | `0x0000` | `0x0000` |
| Register count | `7` | `7` |

CWT 土壌センサー 1 用 runtime config は次の値にする。

```json
{
  "soil": {
    "enabled": true,
    "modbus_slave_id": 1,
    "modbus_function": 3,
    "start_register": 0
  }
}
```

2026-08-01 時点の ENV/WRS firmware と Hub runtime config は `soil` を 1 枠
だけ持つ。したがって土壌センサー 1 は ID `1` で使用できるが、ID `2` を予約
しても、2 台を同時に読み分けるには設定、測定 payload、散水判定を複数土壌
センサー対応へ拡張する必要がある。

また、一部 firmware と Hub の初期値には旧割当の `soil=2 / PAR=1` と、
マニュアル確認前の FC04 が残っている。現行機へこの CWT を接続するときは
runtime config で `soil.modbus_slave_id=1` と `modbus_function=3` を明示する。
PAR を併設する場合は `par.modbus_slave_id=3` も明示する。初期値の一括変更は
既設機へ影響するため、実機試験と対象範囲の承認後に別変更として行う。

## Tera Term 初期設定・読取テスト

初期設定・読取テスト兼用マクロ
[comwintop_cwt_soil_sensor_setup_and_test.ttl](../../tools/comwintop_cwt_soil_sensor_setup_and_test.ttl)
を用意している。Tera Term 5.5.2 以降で `[Control] > [Macro]` から実行する。

1. 外部 12V と USB-RS485 adapter を配線し、電源マイナス、センサー GND、
   adapter GND を共通化する。adapter の 5V 出力は外部 12V へ接続しない。
2. Tera Term で USB-RS485 の COM port を 8N1 で開き、`[Control] > [Macro]`
   から実行する。開いている serial 接続をそのまま使用するため、COM port の
   再選択は行わない。未接続でマクロを直接起動した場合だけ COM 番号を尋ねる。
   baud rate と flow control none はマクロが設定する。
3. 「初期設定してからテスト」または「読取専用テスト」を選ぶ。
4. 初期設定では対象センサー 1 台だけを bus へ接続する。現在値を確認してから
   `0x07D1` の baud、`0x07D0` の slave ID の順に必要な項目だけを書き、
   各変更後に再読取りする。目標は土壌センサー 1 が `ID=1`、土壌センサー 2
   が `ID=2`、いずれも 4800bps。マクロの初期値は 1 台目用の `ID=1`。
5. 読取テストは FC03 で `0x0000` から 7 registers を読み、CRC、Modbus 例外、
   timeout を検査する。
6. 正常値はマクロ実行 directory の
   `cwt-soil-test-日時-idN-bps.csv` へ保存される。

読取専用モードは register を一切書き換えない。初期設定モードも書き込み対象を
slave ID `0x07D0` と baud `0x07D1` に限定し、現在設定の確認と最終確認なしには
書き込まない。書込み応答が曖昧な場合は自動再送せず停止する。

## 測定・設置上の注意

- 石や硬い異物を避け、プローブを垂直に挿す。左右へこじらない。
- 同一測定点の狭い範囲で複数回測り、平均する。
- 長期測定は直径 20cm より大きい縦穴を掘り、所定深度の側壁へ水平に挿し、
  土を締め戻して安定させる。
- EC は可溶性塩類を測るため、メーカーは土壌水分が概ね 20% を超える状態を
  推奨している。散水や降雨が十分浸透した後の方が代表値を得やすい。
- 黒い筐体は直射日光で加熱されるため、露出設置では日よけを行う。
- pH は挿入後 5 分以上、ほかの項目も 1～2 分以上待つようメーカー FAQ に
  記載されている。測定表の「応答時間」は、現場での安定時間とは分けて扱う。
- N/P/K は一般的な迅速測定法による傾向値であり、メーカー自身が誤差の大きさ
  を注意喚起している。N/P/K だけを根拠に自動施肥量を決定しない。

WRS の現行 `power_settle_ms` は既定 800ms、設定上限 30秒であり、pH の
5分安定条件を満たさない。WRS の電源を毎回切る運用は通信確認や迅速値には
使えるが、安定した pH を必要とする場合は ENV の常時 12V、または WRS の
電源保持方式と待機上限の再設計が必要である。

## 実機受入チェック

1. 実機ラベルの Output、Power、7 測定項目、5 本プローブを写真で記録する。
2. 4 芯の色を確認し、V1.4 配線または別ロット配線のどちらか一方へ分類する。
3. 非通電で黒線と装置 `RS485_GND` の導通、A/B 間と電源間の短絡なしを確認する。
4. センサーを外した状態で電源端子が 12V、XIAO `VBUS` が 4.75～5.25V
   であることを確認する。
5. 土壌センサー 1 を 4800bps / 8N1 / ID `1` / FC03 で読めることを確認する。
6. 2 台目を使う場合は、その CWT だけを接続して ID `2` へ変更し、ID `2` で
   読めることを確認する。
7. PAR を使う場合は PAR センサー側を ID `3` へ設定し、ID `1`、`2`、`3`
   がそれぞれ衝突せず応答することを確認する。
8. `0x0000`～`0x0006` の raw 値と換算値を保存し、温度の負値処理も確認する。
9. 5 分以上安定させた pH と、基準器で測った EC / pH を比較する。
10. N/P/K は基準分析との比較結果が得られるまで、表示を参考値として扱う。
