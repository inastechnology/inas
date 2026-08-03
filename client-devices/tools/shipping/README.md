# INAS Shipping Tool

ESP32-S3デバイスの出荷時F/W書込みを行うPython GUIです。各デバイスが生成する
`.inasfw` F/Wパッケージを読み込むと、manifestの配置とSHA-256を検証し、bootloader、
partition table、OTA metadata、firmwareを自動設定します。個別BINやmerged full
imageにも対応します。USB Debug COMのログ確認とコマンド送信も同じツールで
行えます。

## 設計判断

- NVSは通常F/Wの必須領域として扱いません。
- NVSとLittleFSは個体情報や接続設定を含む可能性があるため、初期無効の機密領域
  として表示し、選択した場合は書込み前に警告します。
- coredumpは出荷時に投入する成果物ではないため表示しません。
- OTA metadataには`boot_app0.bin`または明示的な`otadata.bin`を割り当てます。
- partition CSVではbootloader、merged image、必須区分を表現できないため、
  shipping tool固有のFlash layout JSONを使用します。
- Shipping Tool本体へ特定デバイスのF/Wを同梱しません。F/Wはデバイスごとの
  `.inasfw` F/Wパッケージとして独立して配布します。

## セットアップ

### Windows

ZIPを展開して`setup-windows.bat`を実行します。

```bat
setup-windows.bat
```

次を自動で準備します。

- Python 3.12。未導入の場合はwingetを使用
- 専用Python venv
- esptool
- pyserial
- tkinterdnd2
- PlatformIO Core 6.1.18
- PlatformIO espressif32 6.10.0

準備後は`start-windows.bat`で起動します。初期セットアップ前に
`start-windows.bat`を実行した場合も、自動的にセットアップへ進みます。

### Linux

```bash
chmod +x setup-linux.sh start-linux.sh
./setup-linux.sh
./start-linux.sh
```

LinuxではPython 3、venv、TkがOS側に必要です。Ubuntu系では
`python3 python3-venv python3-tk`を先に導入してください。

## 他のPCへ渡すZIP

リポジトリ側で次を実行します。

```bash
cd client-devices/tools/shipping
make package
```

`release/INAS-Shipping-Tool.zip`が生成されます。このZIPは汎用flasherのみを
含み、デバイスF/Wは含みません。

デバイスF/Wは各プロジェクトで生成します。

```bash
cd client-devices/rs485-debug-device
make package
```

ENV、SOI、WTR、WRS、FGTでも同様に、各デバイスディレクトリで`make package`を
実行すると`release/*.inasfw`へF/Wパッケージが生成されます。形式の詳細は
`client-devices/docs/firmware_release_module_spec.md`を参照してください。

`tkinterdnd2`がない環境でもクリックによるファイル選択は動作します。D&Dを使う
には`requirements.txt`をすべてインストールしてください。LinuxではOSパッケージ
の`python3-tk`が別途必要な場合があります。

## 使い方

1. USBでESP32-S3を接続する。
2. ポートを選択し、必要なら「接続確認」を押す。
3. 「F/Wパッケージを開く」を押すか、`.inasfw`をD&Dする。
4. manifestからbootloader、partition table、OTA metadata、firmwareが自動設定
   されたことを確認する。
5. 有効になっている領域とアドレスを確認する。
6. 「書込み開始」を押す。
7. 必要に応じて「検証」を押す。

画面に全項目が収まらない場合は、各タブ右側のスクロールバーまたは
マウスホイールで縦スクロールできます。

配置定義:

- `configs/xiao_esp32s3_ota.json`: INASのOTA対応8MB構成。領域単位書込み
- `configs/xiao_esp32s3_merged.json`: merged imageを`0x0`へ書込み
- `configs/xiao_esp32c6_ota.json`: FGTのOTA対応4MB構成。領域単位書込み
- `configs/xiao_esp32c6_merged.json`: FGTの4MB factory imageを`0x0`へ書込み

一括D&Dではファイル名から書込み先を自動判定します。

| ファイル | 自動設定先 |
|---|---|
| `bootloader.bin` | Bootloader / `0x0` |
| `partitions.bin` | Partition table / `0x8000` |
| `boot_app0.bin`、`otadata.bin` | OTA boot metadata / `0xE000` |
| `firmware.bin`、`app.bin` | app0とapp1の両方 |
| `littlefs.bin`、`spiffs.bin` | LittleFS storage |
| `nvs.bin` | NVS初期値 |
| `firmware.factory.bin` | factory image / `0x0` |

旧`flash_merged.bin`と`rs485-debug-device-esp32s3.bin`も移行期間中は読み込めます。

個別の領域行にも推奨ファイル名を常時表示します。異なる名前のBINを個別行へ
D&Dした場合は、誤配置を防ぐ確認メッセージが表示されます。

## コンソール

「コンソール」タブでは、上部で選択したCOMポートをTera Termの代わりに開けます。

- 標準ログ速度: 115200bps
- 受信ログのリアルタイム表示と自動スクロール
- テキストコマンド送信
- Enterキーによる送信
- CRLF付加の有無
- Modbusなどの16進バイト列送信
- ログ消去

テキスト送信例:

```text
scan
```

16進送信例:

```text
01 03 00 00 00 07 04 08
```

F/W書込み、検証、esptool接続確認を開始するときは、COMポート競合を避けるため
コンソールを自動切断します。書込み後に「コンソール接続」を押すと、そのまま
起動ログと動作ログを確認できます。

## ステータス診断

「ステータス診断」タブでF/W種別を選ぶと、コンソールログを一般向けの状態表示へ
変換します。

- Wi-Fi接続状態
- MQTT接続状態
- runtime configの有効状態
- RS485土壌センサー／PARセンサーの認識状態とslave ID
- センサー値
- RS485 Debug Deviceが自動認識した機種、ID、baud rate
- timeout、CRC、Modbus例外、そのほかのエラー

診断内容はGUIコードへ埋め込まず、各F/Wプロジェクトの次のファイルで定義します。

```text
client-devices/<device>/shipping/diagnostic-profile.json
```

現在の対応F/W:

- RS485 Debug Device
- WRS センサー統合水やり機
- ENV 環境センサー
- WTR 水やり機
- SOI 土壌水分センサー
- FGT 液肥づくり・潅水装置

配布ZIP生成時に各プロジェクトの診断プロファイルが`profiles/`へ自動収集されます。
新しいF/Wを追加するときは、そのF/W側へ診断プロファイルを追加すればShipping
ToolのF/W種別一覧へ追加できます。

## テスト

```bash
python -m unittest discover -s tests -v
```

## レイヤ

- `domain/`: Flash layoutと選択ファイルの検証
- `services/`: COMポート列挙、esptool実行、シリアルコンソール
- `ui/`: Tkinter画面、D&D、非同期実行、ログ表示

将来のRS485設定機能は別serviceとして追加し、Flash layoutやesptool書込み処理へ
混在させません。
