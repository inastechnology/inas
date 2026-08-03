# Rev A 試作発注・組立ガイド

> **現在は発注・製造に使用しないこと。**
>
> この基板は将来候補として開発中のCADであり、物理基板はまだ存在しません。
> 現在のFGTはこの基板を使用していません。この文書と生成済み発注ファイルは
> 将来の試作検討用ドラフトとして保持しています。

回路図ERCと基板DRCはともに0件で、未配線も0件ですが、これはCAD上の整合性を
示すだけで、実装・通電・負荷試験済みであることを意味しません。発注を再開する
場合は、設計レビューと明示的な試作承認を改めて行います。

## 1. 発注ファイル

### PCB製造

- `exports/esp32c6-solar-controller-rev-a-gerbers.zip`
- `exports/drc-final.json`
- `exports/fabrication/drill-report.txt`

### JLCPCB SMT実装

- `exports/assembly/jlcpcb-smt-bom.csv`
- `exports/assembly/jlcpcb-smt-cpl.csv`
- `exports/assembly/dnp-list.csv`

BOMとCPLは90個のトップ面SMT部品について参照番号を自動照合しています。
JLCPCBの部品認識画面では、特に`Q1..Q6`、`U13`、`D30..D34`のピン1方向を
データシートおよび組立図と照合してから確定します。自動回転補正を無確認で
承認しません。`U1` XIAO ESP32-C6はCPLから意図的に除外しています。

### 後実装・調達

- `exports/assembly/post-assembly-bom.csv`
- `exports/assembly/procurement-bom.csv`
- `exports/assembly/top-assembly.pdf`
- `exports/esp32c6-solar-controller.pdf`

高電流端子、ATOヒューズホルダ、電解コンデンサ、XIAO本体など23点は
JLCPCB SMT発注に含めず、基板到着後に後実装します。XIAOはソケットでは
なく、公式24パッドSMDランドへペーストと熱風またはリフローで実装します。

### 機構

- `exports/mechanical/controller-board-only-rev-a.step`
- `enclosure/bmp3040z-mounting-plate-rev-a.dxf`
- `enclosure/connector-cutout-coupons-rev-a.dxf`
- `enclosure/output-panel-cutouts-rev-a.dxf`
- `enclosure/mechanical-dimensions.csv`

基板取付穴はリリース済みです。画像から採寸したMPPTの`134 x 70 mm`、
穴ピッチ`126 x 50 mm`はDXFの`MPPT_VERIFY`層に分離してあります。現物を
ノギスで測るまで、この4穴だけは加工指示へ含めません。

## 2. JLCPCB PCB設定

| 項目 | 指定 |
|---|---|
| Base material | FR-4 |
| Dimensions | 180 x 115 mm |
| Layers | 4 |
| Thickness | 1.6 mm |
| Outer copper | 2 oz |
| Inner copper | 1 oz |
| Solder mask | Green |
| Silkscreen | White |
| Surface finish | Lead-free HASL |
| Impedance control | No |
| Via type | Through-hole only |
| Gold fingers / edge plating | No |
| Remove order number | 任意。シルク機能表示へ重ねないこと |
| Flying probe / electrical test | Yes |

設計最小値は配線幅・間隔とも0.20 mm以上、標準ビアは
`0.8/0.4 mm`、電力ビアは`1.2/0.6 mm`です。JLCPCBの現行能力では、
4層2 ozの最小配線幅/間隔は0.15/0.15 mm、マルチレイヤのドリルは
0.15 mm以上です。この設計はそれより大きい値を使用しています。

層順は次のとおりです。

1. `F.Cu`: 部品・信号・高電流配線
2. `In1.Cu`: GND
3. `In2.Cu`: `12V_ACT`
4. `B.Cu`: 信号・GNDポア

## 3. JLCPCB PCBA設定

1. Gerber ZIPをPCBとしてアップロードします。
2. PCB設定を上表と一致させます。
3. PCBAはトップ面のみを選択します。
4. `jlcpcb-smt-bom.csv`と`jlcpcb-smt-cpl.csv`をアップロードします。
5. 90点すべてがBOM/CPLに存在し、DNP 8点と手実装の`U1`が含まれないことを
   確認します。
6. 部品代替はメーカー型番とパッケージが一致するものだけを個別承認します。
7. 3Dプレビューで極性・ピン1・回転を確認します。

初回は5枚のPCB、2枚のSMT実装を推奨します。1枚を破壊検査・温度試験に
使い、1枚を機能試験に使えるためです。THT部品はJLCPCBへ依頼せず、
`post-assembly-bom.csv`に従って手実装します。

## 4. 筐体・取付板の発注

Rev Aの基準筐体は次です。

| 品目 | 型番 | 数量 | 備考 |
|---|---|---:|---|
| 屋外屋根付きIP65ポリカーボネート筐体 | Takachi `BCPR304012S` | 1 | 外形300 x 400 x 120 mm、内寸274.5 x 374.5 x 103.6 mm |
| 亜鉛めっき鋼板取付板 | Takachi `BMP3040Z` | 1 | 265 x 365 x 1.6 mm、取付ピッチ228 x 325 mm |
| 外壁取付金具 | Takachi `BFL-2S`または`CK-26P` | 1組 | 設置方法に合わせて選択 |

`bmp3040z-mounting-plate-rev-a.dxf`ではPCBを下側へ配置し、上側に
外付けMPPT用の候補領域、間に70 mmの配線・ヒューズ保守領域を確保して
います。

Amphenol X-Lok 3極 `CC-03RMMS-QC800P` / `CC-03RMFS-QC800P`の
公式パネル形状は`Ø20.8 / 19.4 mm D-cut`です。Phoenix `1237436`は
M16 x 1.5後面取付です。
実際の筐体壁はテーパーとリブがあるため、個別切抜きDXFを使い、筐体を
受領して内側のナット・リブ・曲面クリアランスを確認した後に穴位置を
転記します。`output-panel-cutouts-rev-a.dxf`は平板上の配置参考であり、
筐体そのものへの無確認加工データではありません。

## 5. 後実装順

1. SMT実装面を拡大確認し、短絡・浮き・極性を検査します。
2. XIAOを載せる前に、電流制限付き12 V電源で`12V_ACT`、`5V_RAW`、
   `5V_LOGIC`を確認し、XIAOの全パッドで短絡がないことを確認します。
3. XIAOの24パッドはF.Paste Gerberから意図的に除外されています。基板受領後、
   適量のはんだペーストを手動で薄く塗布し、位置を合わせて熱風または
   リフローで実装します。裏面パッド15、16、19、20を使用するため、
   側面キャスタレーションだけの手はんだで済ませません。
4. USB接続、3.3 V、GPIO起動状態を確認した後、低い部品から`JP1`、
   端子台、電解コンデンサ、ATOホルダの順に実装します。
5. Phoenix `1720466`は1電位3本、Littelfuse `178.6165.0001`は
   1接点4本の全ピンへ十分にはんだを流します。
6. フラックスを洗浄し、端子内部へ洗浄液を残しません。
7. 初期ヒューズは入力20 A、各出力10 Aですが、実負荷の測定値が小さい
   場合は適切な低い定格へ変更します。

## 6. 初回通電

1. XIAO実装前に全ヒューズと外部機器を外します。
2. 電源端子の極性、12 V-GND短絡、各出力-GND短絡を確認します。
3. 電流制限を0.2 Aにした12 Vベンチ電源を接続します。
4. 逆接保護後の`12V_ACT`、`5V_RAW`、`5V_LOGIC`を測定します。
5. 電源を切ってXIAOをSMD実装し、USB給電だけで3.3 Vと起動を確認してから
   12 V系を再通電します。
6. GPIO直接接続版のファームウェアで起動・再起動・通信断の各状態を試し、
   全ゲートがOFFであることを
   確認します。
7. 各出力は抵抗性ダミー負荷から開始し、1 A、3 A、5 A、実負荷電流の順で
   電圧降下と温度を記録します。
8. 誘導負荷でフライバック波形を確認します。
9. 通常1出力、最大2出力、A/B同時禁止、2台同時始動禁止を確認します。
10. 筐体を閉じた状態で、日射・周囲温度を含む最悪条件の温度試験を行います。

異臭、発煙、ヒューズ・端子・MOSFET・銅箔の異常温度、5 V降下、意図しない
出力ONがあれば直ちに電源を切り、実負荷での使用へ進みません。

## 7. 現場投入前に確定する値

PCB発注を止める項目ではありませんが、実ポンプ・肥料・屋外運用を許可する
前に次を実測・記録します。

- 充電コントローラLOADの最小/最大電圧
- バッテリー化学系、BMS連続/ピーク電流、バッテリー直近ヒューズ
- 各12 V負荷の定常、始動、ロック電流とケーブル長
- RS485の配線長、終端、接地、サージ、絶縁要否
- 密閉筐体内のMOSFET、端子、ヒューズ、Buck温度
- MPPT現物の外形と穴ピッチ
- パネルコネクタ取付後の防水検査

最初の液肥試験は、水だけで全シーケンス、流量、空運転、漏水、非常停止を
確認した後に実施します。
