# ESP32-S3 / ESP32-C6 RS485 Debug Firmware

XIAO ESP32-S3またはXIAO ESP32-C6とMAX3485を使って、RS485 Modbus RTUセンサーを検出し、
USB Debug COM に測定値を表示する診断用 PlatformIO プロジェクトです。

現在対応するセンサー:

- ComWinTop CWT-SOIL NPKPHCTH-S
- DFRobot SEN0641 PAR センサー

このファームウェアはセンサーの設定レジスタを書き換えません。読み取り専用です。

## ソフトウェア構造

INASのFirmware Layering Policyに従って責務を分離しています。

| Layer | Directory | 責務 |
|---|---|---|
| Entry point | `src/main.cpp` | Arduinoの`setup()` / `loop()`からAppを呼ぶだけ |
| Device App | `src/app/` | baud・ID走査、機種判別順序、定期読取、USB表示、再走査判断 |
| Protocol driver | `src/protocol/` | CWT-SOIL／SEN0641のレジスタマップと単位変換 |
| Firmware HAL | `src/hal/` | UART、MAX3485 DE/RE、Modbus RTUフレーム、CRC、timeout |

App層はHALとprotocol driverを利用しますが、HALとprotocol driverはApp層に依存
しません。センサー固有のレジスタや単位はAppおよびHALへ持ち込みません。

## 配線

対象は商品ページの `RS485 V2.05` moduleのうち、3.3V動作の`MAX3485`
バリエーションです。同じ商品ページには5Vの`MAX485`と`MAX13487`もあるため、
実装ICまたは注文バリエーションが`MAX3485`であることを確認してください。

| XIAO ESP32-S3 | MAX3485 V2.05 module | 用途 |
|---|---|---|
| `3V3` | `VCC` | MAX3485 の電源。5Vを接続しない |
| `GND` | `GND`（どちらか一方） | 共通GND |
| `D6 / GPIO43` | `RXD` | UART TX。module内部でMAX3485の`DI`へ接続 |
| `D7 / GPIO44` | `TXD` | UART RX。module内部でMAX3485の`RO`へ接続 |
| `D4 / GPIO5` | `EN` | `HIGH`で送信、`LOW`で受信 |
| - | `A` | センサーの A / A+ |
| - | `B` | センサーの B / B- |

XIAO ESP32-C6で同じ最小F/Wを使用する場合は次のピンへ読み替える。

| XIAO ESP32-C6 | MAX3485 V2.05 module | 用途 |
|---|---|---|
| `3V3` | `VCC` | MAX3485の電源 |
| `GND` | `GND` | 共通GND |
| `D6 / GPIO16` | `RXD` | UART1 TX |
| `D7 / GPIO17` | `TXD` | UART1 RX |
| `D8 / GPIO19` | `EN` | `HIGH`で送信、`LOW`で受信 |

このmoduleの`TXD` / `RXD`表記はmodule側から見た方向であるため、
`GPIO43/TX -> module RXD`、`GPIO44/RX <- module TXD`とクロス接続する。
実機でこの接続による送受信を確認済みである。moduleの2つのGND端子は基板内で
共通です。
商品ページと付属PDFは基板上のLEDの役割を明記していないため、LEDの点灯だけで
送信・受信の有無を判定しません。

センサーは仕様範囲内の別電源で給電します。今回の2機種は5Vで試験できます。
センサーGND、MAX3485 GND、ESP32-S3 GNDを共通にしてください。

短い机上配線では、すでにモジュールやセンサーに終端抵抗がある場合、追加の
120ohm終端は不要です。応答がない場合は一度だけA/Bを入れ替えて確認します。

## 自動検出

起動時に次を走査します。

- baud rate: 2400 / 4800 / 9600bps、8N1
- Modbus slave ID: 1～10
- 土壌センサー: FC03、`0x0000`から7レジスタ
- PARセンサー: FC03、`0x0000`から1レジスタ

両機種は`FC03 / 0x0000`が重複し、SEN0641は仕様外の7レジスタ要求にも
ゼロ埋めで応答する個体があるため、応答レジスタ数だけでは機種を判別しません。
次の順で読み取り専用プローブを行います。

1. `0x0000`を1レジスタ読み、機器の存在を確認
2. `0x0000`から7レジスタ読み、土壌センサーの副測定値を確認
3. CWT-SOIL固有の係数`0x0022`～`0x0024`を読み、土壌プロファイルを確認

CWT-SOILの工場既定ではsalinity factor=`55`、TDS factor=`50`です。これらの
係数または温度・EC・pH・N/P/Kの副測定値があればSOILと判定します。追加
レジスタがすべて0で土壌固有係数もない場合はPARと判定し、ログに
`reason=no_soil_signature confidence=heuristic`を出します。土壌固有
レジスタがModbus exception `0x02`で拒否された場合は、PARを高確度で判定します。
CWT-SOILの係数を意図的にすべて0へ変更し、かつ副測定値もすべて0の場合は
プロトコルだけで一意に区別できないため、PARのheuristic判定になります。

検出後は5秒間隔で測定値を表示します。3回連続で読取に失敗すると自動的に
再走査します。機器が見つからない場合は10秒後に再走査します。

複数機器を同時接続するときは、すべて異なるslave IDに設定してください。同一ID
の機器が同時に応答するとフレームが衝突するため、ソフトウェアから機種を判別
できません。INASの割当は土壌センサー1=`1`、土壌センサー2=`2`、PAR=`3`です。

## 詳細診断ログ

すべての要求について、UARTへの書込み、EN端子のGPIO読戻し、送信フレーム、
受信フレーム、判定結果を表示します。

無応答の例:

```text
[TX] profile="ComWinTop CWT-SOIL" baud=4800 id=1 written=8/8 en_readback=HIGH->LOW function=0x03 register=0x0000 count=7 bytes=01 03 00 00 00 07 04 08
[RX] profile="ComWinTop CWT-SOIL" baud=4800 id=1 received=0 expected=19 bytes=<none>
[RESULT] profile="ComWinTop CWT-SOIL" baud=4800 id=1 status=timeout
```

`written=8/8`はESP32-S3のUARTへ要求全体を書き込めたことを示します。
`en_readback=HIGH->LOW`は、GPIO5が送信時HIGH、送信完了後LOWへ戻ったことを
ESP32-S3側で読み返した結果です。どちらも正常でも、moduleまでの配線やA/B上の
物理波形までは保証しません。

応答を受信した場合は`bytes=`へ16進数をそのまま表示します。

```text
[RX] profile="DFRobot SEN0641 PAR" baud=4800 id=1 received=7 expected=7 bytes=01 03 02 03 44 B8 87
[RESULT] profile="DFRobot SEN0641 PAR" baud=4800 id=1 status=ok
```

主な`status`:

| status | 意味 | 主な確認箇所 |
|---|---|---|
| `ok` | 期待したModbus応答 | 正常 |
| `tx_error` | UARTへ要求全体を書けなかった | F/W、UART初期化 |
| `timeout` | 受信0バイト | センサー電源、GND、EN、A/B、baud、ID |
| `short_frame` | 1～4バイトだけ受信 | ノイズ、配線、baud |
| `crc_error` | 受信したがCRC不一致 | RX浮き、ノイズ、baud、衝突 |
| `exception` | センサーがModbus例外を返信 | function、register、count |
| `wrong_slave_id` | 返信IDが要求と不一致 | 複数機器、残留・混在フレーム |
| `wrong_function` | 返信functionが要求と不一致 | プロトコル、残留・混在フレーム |
| `wrong_byte_count` | データ長フィールドが期待と不一致 | センサープロファイル |
| `length_mismatch` | 実フレーム長が期待と不一致 | 不完全応答、連結フレーム |
| `malformed` | F/W内部の要求条件または初期化不正 | F/W設定 |

## Makeによるビルドと書込み

```bash
cd client-devices/rs485-debug-device
make
```

`make` は次の2種類のF/Wを生成します。

- `.pio/build/seeed_xiao_esp32s3/firmware.bin`
  - PlatformIOまたはOTA用のアプリケーションイメージ
- `.pio/build/seeed_xiao_esp32s3/firmware.factory.bin`
  - bootloaderとpartition tableを含む、アドレス`0x0`から書ける完全イメージ

通常のUSB書込みとデバッグ表示:

```bash
make upload
make monitor
```

完全イメージを書き込む場合:

```bash
make flash-merged
```

別のPCで書き込むための配布用ZIP:

```bash
make package
```

`release/rs485-debug-device-0.1.0-seeed_xiao_esp32s3.inasfw`に、`bootloader.bin`、
`partitions.bin`、`boot_app0.bin`、`firmware.bin`、診断プロファイル、
配置・バージョン・SHA-256を記載した`release-module.json`がまとめられます。
このZIPをINAS Shipping Toolへそのまま読み込んで書き込みます。

PlatformIOのUpload PortとMonitor Portが自動選択されない場合:

```bash
make ports
make upload UPLOAD_PORT=/dev/ttyACM0
make monitor UPLOAD_PORT=/dev/ttyACM0
```

Windowsではポートを `COM44` などに読み替えます。

PlatformIOを直接使用することもできます。

```bash
pio run
pio run --target upload
pio device monitor
```

XIAO ESP32-C6向けの最小診断F/Wは次の環境でビルドする。

```bash
make build PIO_ENV=seeed_xiao_esp32c6
```

配布用ファイルは
`release/rs485-debug-device-0.1.0-seeed_xiao_esp32c6.inasfw`である。FGTの
AP、Wi-Fi、MQTT、ポンプ制御を含まないため、同じC6・同じD6/D7/D8配線で
RS485だけを切り分けられる。

## 出力例

```text
[TX] profile="ComWinTop CWT-SOIL" baud=4800 id=1 written=8/8 en_readback=HIGH->LOW function=0x03 register=0x0000 count=7 bytes=01 03 00 00 00 07 04 08
[RX] profile="ComWinTop CWT-SOIL" baud=4800 id=1 received=19 expected=19 bytes=01 03 0E 01 60 00 F1 01 A2 00 40 00 12 00 0C 00 3F A0 FD
[RESULT] profile="ComWinTop CWT-SOIL" baud=4800 id=1 status=ok
[DETECTED] model="ComWinTop CWT-SOIL" id=1 baud=4800 8N1 reason=cwt_configuration_signature confidence=high
[DETECTED] model="DFRobot SEN0641 PAR" id=3 baud=4800 8N1 reason=no_soil_signature confidence=heuristic
[SCAN] Complete: 2 supported device(s)

[DATA] model="ComWinTop CWT-SOIL" id=1 baud=4800 moisture=35.2 % temperature=24.1 C EC=418 uS/cm pH=6.4 N=18 mg/kg P=12 mg/kg K=63 mg/kg
[DATA] model="DFRobot SEN0641 PAR" id=3 baud=4800 PAR=836 umol/m2/s
```

## 走査範囲・周期の変更

`platformio.ini` のbuild flagで変更できます。

| Flag | 初期値 | 内容 |
|---|---:|---|
| `RS485_SCAN_ID_MIN` | 1 | 走査する最小slave ID |
| `RS485_SCAN_ID_MAX` | 10 | 走査する最大slave ID |
| `RS485_RESPONSE_TIMEOUT_MS` | 120 | 1要求の応答待ち時間 |
| `RS485_POLL_INTERVAL_MS` | 5000 | 定期読取間隔 |
| `RS485_RESCAN_INTERVAL_MS` | 10000 | 未検出時の再走査間隔 |

ID 1～247をすべて探す場合は `RS485_SCAN_ID_MAX=247` にできますが、未接続ID
ごとにtimeoutを待つため、走査完了まで時間がかかります。
