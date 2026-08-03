# 部品選定（Revision 1 prototype）

更新日: 2026-07-27

> **状態:** 将来候補基板の部品選定資料です。物理基板はまだ存在せず、
> 現在のFGTでは使用していません。部品が選定済みであることは、発注承認や
> 実機検証済みであることを意味しません。

この文書は、ESP32-C6 太陽光液肥混入・灌水コントローラの試作1号で
使用する主要部品を型番まで固定するものです。JLCPCBでSMT実装できる
部品を優先し、高電流コネクタと交換式ヒューズはTHT/手実装とします。
XIAOは裏面GPIOを使うため、公式24パッドSMDランドへペーストを手動塗布後、
リフローまたは熱風で手実装します。JLCPCB工程で空ランドへはんだだけ載るのを
避けるため、XIAOのペースト開口は製造Gerberから除外します。

Rev A CADでは主要部品、基板フットプリント、配線、BOM/CPLの候補を固定
していますが、現在は試作発注しません。外付け充電コントローラの実測電圧、
各モータの始動・ロック電流、密閉筐体内の温度上昇を確認し、設計レビューと
明示的な試作承認を行ってから発注可否を判断します。

## 1. 選定結果

| 用途 | 数量 | 採用部品 | LCSC | 実装 | 選定理由 |
|---|---:|---|---|---|---|
| MCUモジュール | 1 | Seeed Studio XIAO ESP32-C6 | - | 24パッドSMD、手実装 | 側面11 GPIOと裏面4 GPIOを直接使用 |
| RS485 | 1 | TI `THVD1410DR` | `C2671345` | SOIC-8 | 3.3 V、500 kbps、1個で汎用RS485バスを構成 |
| RS485 TVS | 1 | Bourns `CDSOT23-SM712` | `C404012` | SOT-23 | RS485 A/B用クランプ |
| 安全入力反転 | 1 | TI `SN74HC14DR` | `C6820` | SOIC-14 | Schmitt入力で接点ノイズに強い |
| 出力許可AND | 2 | TI `SN74AHCT08DR` | `C7480` | SOIC-14 | 3.3 V入力を5 Vロジックで確実に受ける |
| ゲートドライバ | 3 | Microchip `TC4427AEOA` | `C18690` | SOIC-8 | 4.5～18 V電源、3.3 V制御を受けられるデュアルドライバ |
| 出力MOSFET | 5 | TI `CSD18540Q5B` | `C86513` | DNK 5 x 6 mm | 60 V、`VGS=4.5 V`で最大3.3 mΩ |
| 逆接MOSFET | 1 | TI `CSD18540Q5B` | `C86513` | DNK 5 x 6 mm | 出力段と共通化、20 A共通経路の損失を抑える |
| 逆接/理想ダイオード制御 | 1 | TI `LM74610QDGKRQ1` | `C2649431` | VSSOP-8 | 外付けN-MOSFETで低損失逆接保護 |
| 入力TVS | 1 | Littelfuse `SMBJ18A` | `C151256` | SMB | 12 Vバッテリ系の初期値。充電器LOADが常時16 V以下の場合に採用 |
| 入力電解コンデンサ | 1 | Nichicon `UHE1V471MPD` | `C116237` | THT D10 x 20 | 470 uF、35 V、105 ℃、低ESR |
| 5 V Buck | 1 | Diodes Inc. `AP63205WU-7` | `C2071056` | TSOT23-6 | 3.8～32 V入力、固定5 V、2 A |
| Buckインダクタ | 1 | Bourns `SRP5030TA-4R7M` | `C2047088` | 5 x 5 mm SMT | 4.7 uH、Irms 4.6 A、Isat 6 A |
| Buck入力コンデンサ | 1 | Samsung `CL31B106KBHNNNE` | `C89632` | 1206 | 10 uF、50 V、X7R |
| Buck出力コンデンサ | 2+1 | Samsung `CL31B226KPHNNNE` | `C87996` | 1206 | 22 uF、10 V、X7R。Buck側2個、PTC後1個 |
| 5 V PTC | 1 | Bourns `MF-NSMF075-2` | `C89653` | 1206 | 0.75 A hold / 1.5 A trip |
| バッテリーADCクランプ | 1 | Nexperia `BAT54S,215` | `C47546` | SOT-23 | ADCをGND/3.3 VへSchottkyクランプ |
| RS485/フィールド12 V PTC | 1 | Bourns `MF-MSMF075/24-2` | `C208467` | 1812 | 0.75 A hold / 1.5 A trip、24 V |
| RS485/フィールド電源bulk | 1 | Nichicon `UHE1E470MDD` | `C134230` | THT D5 x 11 | 47 uF、25 V、105 ℃ |
| フロー入力比較器 | 1 | TI `TLV7031DBVR` | `C2869832` | SOT-23-5 | 1.6～6.5 V、ヒステリシス内蔵、push-pull出力 |
| ケーブル入力ESD | 5 | TI `TPD1E10B06DPYR` | `C48260` | X1SON-2 | 流量および接点入力の基板入口に配置 |
| ゲートドライバ局所bulk | 3 | Samsung `CL21B225KOFNNNE` | `C28234` | 0805 | 各TC4427Aに2.2 uFを追加し、ゲート電荷による5 V低下を抑制 |
| 逆起電力ダイオード | 5 | ST `STPS30SM60SG-TR` | `C2935135` | D2PAK | 60 V、30 A Schottky。ON/OFF制御の誘導負荷用 |

LCSC番号は2026-07-27時点の調達候補です。発注直前に在庫、JLCPCBの
Basic/Extended区分、末尾品番、パッケージを再確認します。単価を理由に
メーカー型番の異なる互換品へ自動置換しません。

`GPIO4`と`GPIO5`はストラップ端子のため、47 kohmプルダウン付きの
出力指令に限定し、起動時LOW/OFFを維持します。

### 標準受動部品

| 値/用途 | 採用部品 | LCSC |
|---|---|---|
| 100 nF、50 V、X7R、0603 | Samsung `CL10B104KB8NNNC` | `C1591` |
| 100 pF、50 V、C0G、0603 | Samsung `CL10C101JB8NNNC` | `C14858` |
| 2.2 uF、16 V、X7R、0805 | Samsung `CL21B225KOFNNNE` | `C28234` |
| 1 kohm、0603、1% | UNI-ROYAL `0603WAF1001T5E` | `C21190` |
| 4.7 kohm、0603、1% | UNI-ROYAL `0603WAF4701T5E` | `C23162` |
| 10 kohm、0603、1% | UNI-ROYAL `0603WAF1002T5E` | `C25804` |
| 27 kohm、0603、1% | UNI-ROYAL `0603WAF2702T5E` | `C22967` |
| 47 kohm、0603、1% | UNI-ROYAL `0603WAF4702T5E` | `C25819` |
| 150 kohm、0603、1% | UNI-ROYAL `0603WAF1503T5E` | `C22807` |
| 10 ohm、0603、1% | UNI-ROYAL `0603WAF100JT5E` | `C22859` |
| 22 ohm、0603、1% | UNI-ROYAL `0603WAF220JT5E` | `C23345` |
| 680 ohm、0603、1%（RS485 bias、DNP） | UNI-ROYAL `0603WAF6800T5E` | `C23228` |
| 120 ohm、0805、1%（RS485終端） | UNI-ROYAL `0805W8F1200T5E` | `C17437` |

## 2. 電源・出力定格

各アクチュエータは12 V、100 W未満なので定常電流は8.33 A未満です。
出力回路は1系統10 A連続を目標にします。

`CSD18540Q5B`は5 Vゲート駆動に対し、データシート保証条件に近い
`VGS=4.5 V`で最大3.3 mΩです。25 ℃の単純な導通損失上限は次の通りです。

- 出力1系統10 A: `10² x 0.0033 = 0.33 W`
- 共通逆接MOSFET 20 A: `20² x 0.0033 = 1.32 W`

これは接合温度上昇による `RDS(on)` 増加、基板銅箔、熱ビア、密閉筐体、
モータ始動電流を含まないため、発注可否の熱計算ではありません。
メーカーDNK0008Aのピン割当と外形へ合わせた専用ランド、電力配線、
GNDスティッチングビアをRev A PCBへ反映済みです。筐体を閉じた状態で
温度を測り、10 A目標を実測で承認します。

物理端子は`MOSFET OUT 1..5`の汎用名にします。現在のFGT Runtime Config
では通常1出力だけをON、絶対上限は2出力です。初期許可ペアは
`A PUMP + MIXER`と`B PUMP + MIXER`だけで、A/B同時ON、2台同時始動、
3出力目は異常として全OFFにします。これは端子に固定した機能名ではなく、
Runtime Configで割り当てた役割に対する安全条件です。

## 3. ヒューズと基板コネクタ

| 用途 | 基板側 | 相手側/挿入部品 | 初期定格 |
|---|---|---|---:|
| 充電器LOAD入力 | Phoenix Contact `PC 5/2-G-7,62` (`1720466`) | `SPC 5/2-STCL-7,62` (`1718481`) | コネクタ32 A |
| 汎用MOSFET OUT 1..5 | Phoenix Contact `1720466` x 5 | `1718481` x 5 | コネクタ32 A |
| メインヒューズ | Littelfuse `178.6165.0001` | ATOF `0287020.H` | 20 A |
| 5分岐ヒューズ | Littelfuse `178.6165.0001` x 5 | ATOF `0287010.H` x 5 | 10 A |
| RS485 4極 | Phoenix Contact `1757268` x 2、増設1個DNP | `1757035` | 12 Aクラス |
| FLOW 3極 | Phoenix Contact `1757255` | `1757022` | 信号用 |
| 安全入力 2極 | Phoenix Contact `1757242` x 4 | `1757019` x 4 | 信号用 |

Littelfuse 4端子ATO基板ホルダは最大30 A、連続定格22.5 Aです。メインを
20 Aで使う場合も、基板温度と接触温度を実測します。各10 A分岐は実負荷の
定常・始動電流に合わせて下げてよく、ヒューズが切れるからという理由だけで
10 Aより大きくしません。

基板用Phoenix `1720466`は1電位あたり3本のはんだピンを持つため、
一般的な2ピン端子台フットプリントは使用できません。Rev Aではメーカー
図面どおり、1電位3本、合計6本の専用フットプリントを実装しています。

## 4. 筐体外コネクタ

| 接続 | 採用シリーズ/型番 | 備考 |
|---|---|---|
| 制御筐体 `POWER IN` | Amphenol LTW X-Lok Middle C `CC-03RMMS-QC800P` | 3極中2極を使用、20 A、IP68。ケーブル側はメス接点 `CC-03BFFB-QL8LPP` |
| バッテリー直近ヒューズ | Littelfuse `FHAC0002ZXJA` + ATOF `0287020.H` | IP67、12 AWGリード、ホルダ30 A、初期ヒューズ20 A |
| MOSFET OUT 1..5 | Amphenol LTW X-Lok Middle C `CC-03RMFS-QC800P` x 5 | 3極中2極を使用、20 A、IP68。ケーブル側は `CC-03BFMB-QL8LPP`。1=`+12V_ACT`、2=`SW_RETURN`、3=`NC` |
| 外部機器 `POWER IN` | Amphenol LTW X-Lok Middle C `CC-03RMMS-QC800P` | 機器を加工する場合のみ。ケーブル側は `CC-03BFFB-QL8LPP` |
| RS485 PORT 1/2 | Phoenix Contact M12 A-coded `1237436` x 2 | 4極、ケーブル側は `1413993`。1=12 V、2=A、3=GND、4=B |

X-Lokの3番ピンは予約とし、配線しません。`SW_RETURN`は低側MOSFETで
スイッチされる戻り線であり、筐体内や機器側で常時GNDへ短絡しません。
バッテリー正極のメインヒューズはコネクタよりバッテリー側のできるだけ
近くに別置きします。

## 5. 汎用端子の適用範囲

RS485端子とMOSFET出力は接続機器の種類を固定しません。土壌、PARなどの
名称やレジスタマップは基板ではなく、Runtime ConfigとDevice Definitionで
扱います。ただし、接続する機器は次の電気的条件を満たす必要があります。

- `TLV7031`フロー入力は、10 kohmの3.3 V pull-up、1 kohm/100 nF入力
  フィルタ、47 kohm/47 kohmの1.65 V基準で、12 V給電のNPN
  オープンコレクタまたは無電圧接点を初期対象とします。12 V push-pull、
  PNP、5 V専用センサは同じ配線のまま接続しません。
- `12V_FIELD`はソフトウェアでON/OFFする専用センサ電源ではなく、0.75 A
  holdのPTCを通した常時給電です。接続機器の合計定常電流、突入電流、
  ケーブル電圧降下がこの共通経路に収まることを確認します。電源制御が必要な
  機器は、電圧・極性・電流を確認したうえで汎用MOSFET出力を使用します。
- RS485バイアス抵抗はDNP開始です。`THVD1410`のfail-safe動作と現場配線を
  確認し、必要な場合だけ680 ohmを実装します。終端120 ohmはバス末端1か所
  だけを有効にします。
- 入力TVS `SMBJ18A`は充電コントローラLOADの常時最大が16 V以下という
  条件付きです。最大値がそれを超える場合はTVSと5 V Buck入力部を再選定します。

## 6. 一次資料

- [TI CSD18540Q5B](https://www.ti.com/product/CSD18540Q5B)
- [Seeed Studio XIAO ESP32-C6](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/)
- [Espressif ESP32-C6 GPIO](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c6/api-reference/peripherals/gpio.html)
- [TI LM74610-Q1 datasheet](https://www.ti.com/lit/ds/symlink/lm74610-q1.pdf)
- [Diodes AP63205](https://www.diodes.com/part/view/AP63205)
- [Microchip TC4427A](https://www.microchip.com/en-us/product/TC4427A)
- [Phoenix Contact 1720466](https://www.phoenixcontact.com/en-us/products/pcb-header-pc-5-2-g-762-1720466)
- [Littelfuse 178.6165.0001](https://www.littelfuse.com/ja-jp/products/fuses-overcurrent-protection/fuse-holders-fuse-blocks-accessories/fuse-holders/in-line-fuse-holders/ato-flr/178-6165-0001)
- [Amphenol LTW X-Lok Middle C](https://amphenolltw.com/product-info/X-Lok/X-Lok.MiddleSize/CC-03RMFS-QC800P.html)
- [Phoenix Contact 1237436](https://www.phoenixcontact.com/ja-jp/products/device-connector-rear-mounting-sacc-dsi-m12fs-4con-m16-05x-1237436)
