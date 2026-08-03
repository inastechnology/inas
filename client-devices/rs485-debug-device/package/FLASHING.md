# RS485 Debug Firmware 書込み手順

対象ボードは Seeed Studio XIAO ESP32-S3 です。

## 1. USBドライバー

XIAO ESP32-S3をUSB接続し、PCにCOMポートまたは`/dev/ttyACM*`として認識
されることを確認します。このF/WはESP32-S3内蔵USBを使用するため、通常は
CP210xドライバーを使用しません。

認識されない場合は、BOOTボタンを押しながらRESETボタンを押し、先にRESET、
次にBOOTを離してダウンロードモードへ入れてください。

## 2. esptoolのインストール

Python 3が入っているPCで次を実行します。

```text
python -m pip install esptool
```

Windowsで`python`が見つからない場合は、Python公式インストーラーでPython 3
をインストールし、`Add Python to PATH`を有効にします。

## 3. 書込み

Windows:

```text
flash-windows.bat COM44
```

Linux:

```text
chmod +x flash-linux.sh
./flash-linux.sh /dev/ttyACM0
```

この完全イメージはアドレス`0x0`へ書き込みます。

## 4. ログ確認

USB Debug COMを115200bpsで開きます。Tera TermやPlatformIO Monitorなどが
使用できます。

正常起動時は、次のような表示から始まります。

```text
INAS ESP32-S3 RS485 debugger
[SCAN] baud=2400/4800/9600 id=1..10
```
