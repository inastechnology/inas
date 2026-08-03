# Rev A 部品仕様調査

調査日: 2026-08-01

この文書は、Rev A 回路図と発注BOMに採用した部品を、メーカーの
データシートまたはメーカー公式製品ページで照合した結果である。
同一メーカー型番・同一定数の受動部品は、設計番号をまとめて記載する。
LCSC番号は調達用識別子であり、電気仕様の根拠には使用しない。

## 1. 適用条件

- 太陽光充電器、12 Vバッテリー、BMS、バッテリー直近の主ヒューズは外付け。
- 基板入力は充電器の保護済み `LOAD` 出力。定常入力は16 V以下とする。
- MOSFET出力はすべて12 V、各負荷は100 W未満、定常電流は8.33 A未満。
- 通常は1出力だけをONにする。同時ONは最大2出力、合計200 W未満。
- センサー機種は固定しない。RS485端子は共通バス、接点端子は無電圧接点、
  流量端子はNPNオープンコレクタまたは無電圧接点を既定とする。
- 基板全体の温度範囲は、XIAO ESP32-C6、SN74HC14およびPPTCのうち最も狭い
  範囲に合わせ、暫定で `-40～+85 °C` とする。

## 2. 電源入力、逆接保護、5 V電源

| 設計番号 | 採用品 | メーカー仕様 | 回路での使用条件・判定 | 一次資料 |
|---|---|---|---|---|
| `J1` | Phoenix Contact `1720466` | PC 5/2、2極、7.62 mmピッチ、定格32 A、630 V、接触抵抗0.8 mΩ、使用温度-40～+100 °C | 基板入力最大20 Aに対して電流定格内。電線、プラグ`1718481`、圧着/締結条件も32 A相当にする | [Phoenix Contact](https://www.phoenixcontact.com/en-us/products/pcb-header-pc-5-2-g-762-1720466) |
| `F1`, `F10..F14` | Littelfuse `178.6165.0001` | PCB用ATOホルダ、連続22.5 A、最大30 A、32 V、UL94 V-0 | 主系統20 A、各分岐10 Aで使用可能。主系統を20 A連続で使用する場合は筐体内温度上昇を実測する | [Littelfuse](https://www.littelfuse.com/ja-jp/products/fuses-overcurrent-protection/fuse-holders-fuse-blocks-accessories/fuse-holders/in-line-fuse-holders/ato-flr/178-6165-0001) |
| `F1`挿入品 | Littelfuse `0287020.H` | ATOF、20 A、32 V、遮断容量1000 A @ 32 VDC、代表冷抵抗3.38 mΩ、代表電圧降下98 mV、代表I²t 520 A²s、推奨周囲温度上限125 °C | 2出力同時ON時の16.7 Aを許容する初期値。バッテリー側ヒューズ、配線許容電流、実測突入電流との保護協調が必要 | [ATOFデータシート](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_287_atof_r2.7.pdf?assetguid=43dcdce8-8ca2-426f-8998-7e566f048d40) |
| `Q1`, `Q2..Q6` | TI `CSD18540Q5B` | N-MOSFET、60 V、`RDS(on)`最大2.2 mΩ @ 10 V / 3.3 mΩ @ 4.5 V、総ゲート電荷41 nC、`VGS` ±20 V、`TJ`最大175 °C | 5 Vゲート駆動に適合。出力1回路8.33 Aで25 °C規格値による導通損失は最大約0.23 W。温度上昇、銅箔、突入/拘束電流は別途実測する | [TIデータシート](https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf) |
| `U13` | TI `LM74610QDGKRQ1` | 外付けN-MOSFET用逆接保護コントローラ、逆電圧-45 V、正側入力電圧の上限なし、ゲート駆動最大約5 V | 推奨範囲の2.2 µFチャージポンプ容量と100 pFアノード－カソードフィルタを実装。Q1のボディダイオード順方向電圧が起動条件を満たす | [TIデータシート](https://www.ti.com/lit/ds/symlink/lm74610-q1.pdf) |
| `C6` | Samsung `CL21B225KOFNNNE` | 2.2 µF、±10 %、16 VDC、X7R、0805、-55～+125 °C | `LM74610-Q1`の推奨220 nF～4.7 µF内。チャージポンプ両端は入力12 Vを直接受けない | [Samsung製品仕様](https://product.samsungsem.com/mlcc/CL21B225KOFNNN.do) |
| `C13` | Samsung `CL10C101JB8NNNC` | 100 pF、±5 %、50 VDC、C0G、0603 | `LM74610-Q1`データシートの入力フィルタ例と一致 | [Samsung Component Library](https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL10C101JB8NNN) |
| `D1` | Littelfuse `SMBJ18A` | 単方向TVS、`VRWM` 18 V、`VBR` 20～22.1 V、最大クランプ29.2 V @ 20.6 A、600 W | 充電器LOADの定常最大が16 V以下の場合だけ使用。クランプ最大29.2 VはAP63205の35 V絶対最大、C1の35 V、MOSFETの60 V未満 | [Littelfuseデータシート](https://origin-savvis.littelfuse.com/~/media/electronics/datasheets/tvs_diodes/littelfuse_tvs_diode_smbj_datasheet.pdf.pdf) |
| `C1` | Nichicon `UHE1V471MPD` | 470 µF、35 V、105 °C、10×20 mm、インピーダンス0.046 Ω @ 20 °C / 100 kHz、許容リプル1.4 Arms | 12 V入力の低周波バルク。TVS最大クランプ29.2 Vに対して約20 %の電圧余裕 | [Nichicon UHE](https://www.nichicon.co.jp/products/pdfs/uhe.pdf) |
| `U4` | Diodes Inc. `AP63205WU-7` | 固定5 V / 2 A同期整流降圧、入力推奨3.8～32 V、絶対最大35 V、1.1 MHz | 12 V系に適合。メーカー代表回路と同じ4.7 µH、10 µF入力、22 µF×2出力、100 nFブートストラップを採用 | [Diodes Inc.データシート](https://www.diodes.com/datasheet/download/AP63200-AP63201-AP63203-AP63205.pdf) |
| `L1` | Bourns `SRP5030TA-4R7M` | 4.7 µH ±20 %、DCR代表50 mΩ/最大53 mΩ、`Irms` 4.6 A、`Isat` 6 A、-55～+150 °C | AP63205の2 A出力とメーカー代表回路に適合 | [Bournsデータシート](https://www.bourns.com/docs/Product-Datasheets/SRP5030TA.pdf) |
| `C8` | Samsung `CL31B106KBHNNNE` | 10 µF、±10 %、50 VDC、X7R、1206 | 12 V入力デカップリング。DCバイアス後の実効容量を考慮してもAP63205の代表値を満たすか、試作時に波形確認する | [Samsung Component Library](https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL31B106KBHNNN) |
| `C9`, `C10`, `C2` | Samsung `CL31B226KPHNNNE` | 22 µF、±10 %、10 VDC、X7R、1206 | C9/C10はAP63205出力合計44 µFで推奨22～68 µF内。C2はPTC後の5 Vロジックバルク | [Samsung Component Library](https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL31B226KPHNNN) |
| `C7` | Samsung `CL10B104KB8NNNC` | 100 nF、±10 %、50 VDC、X7R、0603 | AP63205のBST-SW間推奨値と一致 | [Samsung製品仕様](https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do) |
| `F2` | Bourns `MF-NSMF075-2` | PPTC、`Ihold` 0.75 A、`Itrip` 1.5 A、最大6 V、初期抵抗0.10 Ω以上、トリップ後最大抵抗0.40 Ω、-40～+85 °C | 5 Vロジック専用。12 Vには使用不可。XIAO、制御IC、RS485の合計電流は0.75 A未満 | [Bournsデータシート](https://www.bourns.com/docs/product-datasheets/mf-nsmf.pdf) |

## 3. コントローラ、電池電圧測定

| 設計番号 | 採用品 | メーカー仕様 | 回路での使用条件・判定 | 一次資料 |
|---|---|---|---|---|
| `U1` | Seeed Studio XIAO ESP32-C6 | 5 V入力、3.3 Vロジック、21×17.8 mm、11本の側面GPIOと4本の裏面GPIO、動作温度-40～+85 °C | 5V端子へ`5V_LOGIC`を供給し、3V3端子は小電流ロジックの出力として使用。公式24パッドSMD形状を使用 | [Seeed Studio Wiki](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/) |
| `U1`内ESP32-C6 | Espressif ESP32-C6 | GPIO4/5はストラップ端子、GPIO8/9はブートモード端子。ストラップ値はリセット時にラッチされ、その後GPIOとして使用可能 | GPIO4/5出力に47 kΩプルダウンを実装して起動時OFFを保証。00設定によりSDIOサンプリングはfalling/fallingとなる。GPIO8/9は本用途で使用しない | [Espressifデータシート](https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf) |
| `R1`, `R2` | UNI-ROYAL `0603WAF1503T5E` / `0603WAF2702T5E` | 150 kΩ / 27 kΩ、±1 %、0603厚膜。0603 WAシリーズは0.1 W級 | 分圧比27/177 = 0.15254。18 V入力でADC約2.746 V、3.3 V相当の入力は約21.63 V | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `R3`, `C3` | 1 kΩ + 100 nF | R: ±1 %厚膜0603、C: Samsung 100 nF X7R 50 V | ADCの電流制限とRCフィルタ。分圧器のテブナン抵抗を含む時定数は約2.4 ms | [UNI-ROYAL](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf), [Samsung](https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do) |
| `D3` | Nexperia `BAT54S,215` | 30 V、200 mAデュアル直列Schottky。pin 1=A1、pin 2=K2、pin 3=K1/A2共通 | pin 1=GND、pin 3=`BATT_ADC`、pin 2=3V3として上下クランプを形成 | [Nexperiaデータシート](https://assets.nexperia.com/documents/data-sheet/BAT54S.pdf) |

## 4. RS485と低電流12 Vフィールド電源

| 設計番号 | 採用品 | メーカー仕様 | 回路での使用条件・判定 | 一次資料 |
|---|---|---|---|---|
| `U3` | TI `THVD1410DR` | 3～5.5 V、最大500 kbps、バス故障保護±18 V、コモンモード±15 V、IEC ESD ±18 kV接触、開放/短絡/アイドルfail-safe、最大256ノード、-40～+125 °C | 3.3 V動作。DEと`/RE`を共通化し47 kΩで受信側へプルダウン。非絶縁バスである | [TI製品ページ](https://www.ti.com/product/THVD1410) |
| `D2` | Bourns `CDSOT23-SM712` | RS485用TVS、400 W、17 A @ 8/20 µs、IEC ESD最大±30 kV。pin 1/2が信号、pin 3が共通 | pin 1=`RS485_A`、pin 2=`RS485_B`、pin 3=GND。メーカー指定ピン接続に修正済み | [Bournsデータシート](https://bourns.com/docs/product-datasheets/cdsot23-sm712.pdf?sfvrsn=4648d8e1_10) |
| `R10`, `R11` | UNI-ROYAL 10 Ω ±1 % | 0603、0.1 W級厚膜 | トランシーバとTVS/コネクタ間の直列ダンピング。両側合計20 Ωが終端振幅へ与える影響は実機波形で確認 | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `R12`, `JP1` | 120 Ω ±1 % + Sullins `PRPC002SAAN-RC` | Rは0805厚膜、JPは2.54 mmピッチ2極ヘッダ | RS485幹線の物理終端にある基板だけ短絡プラグを装着。中間ノードでは開放 | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `R13`, `R14` | 680 Ω ±1 % | 0603厚膜 | THVD1410の内部fail-safeを使うためRev AではDNP。外付けバイアスが必要な既存バスだけ評価後に実装 | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `F3` | Bourns `MF-MSMF075/24-2` | PPTC、`Ihold` 0.75 A、`Itrip` 1.5 A、最大24 V / 100 A、初期抵抗0.11 Ω以上、トリップ後最大0.40 Ω | RS485センサー用12 V共通電源。3端子合計で0.75 A未満。アクチュエータ電源には使用しない | [Bournsデータシート](https://www.bourns.com/docs/product-datasheets/mf-msmf.pdf) |
| `C11` | Nichicon `UHE1E470MDD` | 47 µF、25 V、105 °C、5×11 mm、インピーダンス0.58 Ω、許容リプル210 mArms | 長いフィールド配線による低周波変動を抑える。定常16 V以下の12 Vフィールド電源に適合 | [Nichicon UHE](https://www.nichicon.co.jp/products/pdfs/uhe.pdf) |
| `J2..J4` | Phoenix Contact `1757268` | MSTBA 2.5/4、4極、5.08 mm、12 A、320 V、接触抵抗1.4 mΩ、-40～+100 °C | 12V/GND/A/B。3コネクタは電気的に同一バス。外部配線を長いスター分岐にしない | [Phoenix Contact](https://www.phoenixcontact.com/us/products/1757268/pdf) |

## 5. 流量入力、接点入力、安全ロジック

| 設計番号 | 採用品 | メーカー仕様 | 回路での使用条件・判定 | 一次資料 |
|---|---|---|---|---|
| `J5` | Phoenix Contact `1757255` | MSTBA 2.5/3、3極、5.08 mm、12 A、320 V、-40～+100 °C | 12V/パルス/GND。パルス端子は12 Vプッシュプル入力ではなくNPNオープンコレクタまたは無電圧接点用 | [Phoenix Contact](https://www.phoenixcontact.com/en-fr/products/pcb-header-mstba-25-3-g-508-1757255) |
| `U12` | TI `TLV7031DBVR` | 1.6～6.5 V、rail-to-rail入力、push-pull出力、代表消費335 nA、入力オフセット最大8 mV、内部ヒステリシス代表7 mV、代表伝搬3 µs、-40～+125 °C。DBV pin 1=OUT、2=V-、3=IN+、4=IN-、5=V+ | 3.3 V動作、比較基準1.65 V。実部品ピン番号に合わせて回路シンボルを修正済み | [TIデータシート](https://www.ti.com/lit/ds/symlink/tlv7031.pdf) |
| `R16`, `R17`, `C12`, `R18`, `R19` | 10 kΩ、2.2 kΩ、100 nF、47 kΩ×2 | 0603厚膜±1 %、Samsung X7R | 開放時3.3 V、接点/NPN ON時LOW、閾値1.65 V。入力RCの代表時定数は約1.22 ms。R17はサージ時のコンパレータ入力電流を抑制 | [UNI-ROYAL](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf), [Samsung](https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do) |
| `D30..D34` | TI `TPD1E10B06DPYR` | 双方向ESD、`VRWM` 5.5 V、IEC ESD ±30 kV接触/気中、サージ6 A、クランプ10 V @ 1 A / 14 V @ 5 A、容量12 pF、-40～+125 °C | J5～J9の各ケーブル入口で信号-GND間を保護。D34を流量入力にも追加済み | [TIデータシート](https://www.ti.com/lit/ds/symlink/tpd1e10b06.pdf) |
| `J6..J9` | Phoenix Contact `1757242` | MSTBA 2.5/2、2極、5.08 mm、12 A、320 V、-40～+100 °C | GNDへ閉じる無電圧接点専用。J8漏水、J9非常停止はNCループ | [Phoenix Contact](https://www.phoenixcontact.com/en-us/products/pcb-header-mstba-25-2-g-508-1757242) |
| `U11` | TI `SN74HC14DR` | 2～6 V、6回路Schmitt inverter、-40～+85 °C、4.5 V時入力クランプ電流±20 mA | 3.3 V動作。10 kΩ pull-up / 1 kΩ series / 100 nFで、開線を異常側へする。未使用入力をGND固定 | [TIデータシート](https://www.ti.com/lit/ds/symlink/sn74hc14.pdf) |
| `U5`, `U6` | TI `SN74AHCT08DR` | 4.5～5.5 V、4回路AND、TTL入力互換、push-pull出力、-40～+125 °C | 5 V動作。3.3 V MCU/HC14のHIGHをTTL HIGHとして認識し、漏水・非常停止・master enableと各出力指令をハードウェアAND | [TIデータシート](https://www.ti.com/lit/ds/symlink/sn74ahct08.pdf) |

## 6. MOSFETゲート駆動、出力保護、出力コネクタ

| 設計番号 | 採用品 | メーカー仕様 | 回路での使用条件・判定 | 一次資料 |
|---|---|---|---|---|
| `U7..U9` | Microchip `TC4427AEOA` | 2回路非反転MOSFETドライバ、4.5～18 V、ピーク1.5 A、出力抵抗代表7 Ω、`VIH`最小2.4 V、`VIL`最大0.8 V | 5 V動作。AHCT出力に適合し、CSD18540の41 nCゲートを駆動。未使用入力はGND | [Microchipデータシート](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/TC4426A-TC4427A-TC4428A-1.5A-Dual-High-Speed-Power-MOSFET-Drivers-20001423.pdf) |
| `C32..C34` | Samsung `CL10B104KB8NNNC` | 100 nF、50 V、X7R、0603 | 各TC4427Aの高周波バイパス | [Samsung製品仕様](https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do) |
| `C35..C37` | Samsung `CL21B225KOFNNNE` | 2.2 µF、16 V、X7R、0805 | 各TC4427Aの局所ゲート電荷リザーバとして追加。理想容量で41 nCによる電圧低下は約19 mV | [Samsung製品仕様](https://product.samsungsem.com/mlcc/CL21B225KOFNNN.do) |
| `R50..R54` | UNI-ROYAL `0603WAF220JT5E` | 22 Ω、±1 %、0603厚膜 | TC4427Aの代表7 Ωと合わせてピークゲート電流とリンギングを制限。立上り/立下りとEMIは実測調整 | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `R55..R59`, `R40..R44`, `R8` | UNI-ROYAL `0603WAF4702T5E` | 47 kΩ、±1 %、0603厚膜 | MOSFETゲート、MCU出力指令、master enableを起動時LOW/OFFに固定 | [UNI-ROYAL厚膜抵抗](https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf) |
| `F10..F14`挿入品 | Littelfuse `0287010.H` | ATOF、10 A、32 V、遮断容量1000 A @ 32 VDC、代表冷抵抗7.7 mΩ、代表電圧降下109 mV、代表I²t 115 A²s | 12 V / 100 W未満の各分岐用初期値。負荷実測によりさらに低い定格を優先する | [Littelfuse製品ページ](https://www.littelfuse.com/ja-jp/products/fuses-overcurrent-protection/fuses/automotive-fuses/blade-fuses-shunt/atof/287/0287010-h) |
| `D10..D14` | ST `STPS30SM60SG-TR` | Schottky、60 V、平均順電流30 A（`TC` 125 °C条件）、サージ600 A、`VF`最大0.53 V @ 15 A / 25 °C、`TJ`最大150 °C | 誘導性12 V負荷のflyback。カソードを出力+、アノードをMOSFET drainへ接続。負荷のインダクタンスと遮断頻度から熱を実測する | [STデータシート](https://www.st.com/resource/en/datasheet/stps30sm60s.pdf) |
| `D20..D24` | 出力TVS用DNPランド | SMB/SMCJ候補、具体MPN未選定 | Rev AはDNP。長尺配線や高速遮断でMOSFET drainが許容範囲を超える場合だけ、負荷実測からスタンドオフ電圧とパルスエネルギーを選定 | — |
| `J10..J14` | Phoenix Contact `1720466` | PC 5/2、2極、7.62 mm、32 A、630 V、-40～+100 °C | 各出力最大10 Aに対して定格内。pin 1=+12 V、pin 2=switched GND | [Phoenix Contact](https://www.phoenixcontact.com/en-us/products/pcb-header-pc-5-2-g-762-1720466) |

## 7. 受動部品共通仕様

| 部品群 | 採用品と仕様 | 適用 |
|---|---|---|
| 0603抵抗 | UNI-ROYAL `0603WAF...T5E`、厚膜、±1 %、通常0.1 W級 | 10 Ω、22 Ω、680 Ω、1 kΩ、2.2 kΩ、4.7 kΩ、10 kΩ、27 kΩ、47 kΩ、150 kΩ |
| 0805抵抗 | UNI-ROYAL `0805W8F1200T5E`、120 Ω、±1 %、厚膜 | RS485終端 |
| 100 nF MLCC | Samsung `CL10B104KB8NNNC`、100 nF、±10 %、50 V、X7R、0603 | ICデカップリング、入力RC |
| 基板 | 4層、外層2 oz銅、内層1 oz銅、180×115 mm | In1を連続GND、In2を`12V_ACT`専用面とし、大電流配線はロックした銅配線と面で構成。20 A連続の最終保証は温度上昇試験による |

## 8. 調達時に再確認する項目

1. JLCPCB注文画面でLCSC番号、メーカー型番、パッケージ、実装面、回転を
   1行ずつ一致確認する。
2. `0287010.H`と`0287020.H`は旧257シリーズではなく、現行287 ATOFシリーズを
   発注する。
3. Phoenix Contactヘッダだけでなく、指定の嵌合プラグ、適合電線径、端子処理を
   同時に確認する。
4. XIAOは裏面パッドを使うため、手はんだ用ソケットではなく公式24パッド
   SMDランドへリフローまたはホットエア実装する。
5. 部品在庫とJLCPCB拡張部品料金は設計仕様ではないため、注文直前に別途確認する。
