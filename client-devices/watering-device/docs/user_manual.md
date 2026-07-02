# INA Water Controller ユーザ説明書

この説明書は、INA Water Controllerを設置・初期設定・運用するユーザ向けのものです。

## 1. 概要

INA Water Controllerは、土壌水分を測定し、MQTTから受け取ったスケジュールに従って灌水を行うデバイスです。

主な機能:

- Wi-Fi経由でMQTT brokerに接続
- MQTTから灌水スケジュールを取得
- NTPで時刻同期
- 受信済みruntime configを保存し、通信障害時はDeep Sleep復帰時の時刻で継続運用
- 土壌水分がしきい値未満の場合のみ灌水
- 灌水後、次回スケジュールまでdeep sleep
- Wi-Fi/MQTT設定用の初期設定AP
- BOOTボタンによる設定APの強制起動

## 2. 初回起動前に準備するもの

- INA Water Controller本体
- 電源
- Wi-Fi SSIDとパスワード
- MQTT brokerのアドレスとポート
- MQTT認証情報。認証なしの場合は不要
- スマートフォンまたはPC

## 3. 初期設定AP

デバイスがWi-Fiへ接続できず、保存済みruntime configもない場合、設定用のアクセスポイントを起動します。

設定APのSSIDは、ファームウェア作成時の以下の値で決まります。

```ini
APP_INITIAL_SETTING_SSID
```

設定APのパスワードは標準で`12345678`です。

標準の設定画面URL:

```text
http://192.168.4.1/
```

設定画面には、設定APが起動した理由が表示されます。表示される理由は、Wi-Fi/MQTT設定未保存、BOOTボタン操作、Wi-Fi接続失敗、MQTT broker接続失敗などです。通常動作中はこの表示は出ません。

### 初期設定手順

1. デバイスの電源を入れます。
2. Wi-Fi/MQTT設定が未保存の場合、設定APが起動します。
3. スマートフォンまたはPCで、設定APのSSIDへ接続します。
4. ブラウザで`http://192.168.4.1/`を開きます。
5. 以下の項目を入力します。
6. `Save and Restart`を押します。
7. デバイスが設定を保存して再起動します。

設定画面の入力項目:

| 項目 | 必須 | 説明 |
|---|---:|---|
| Wi-Fi SSID | 必須 | 接続先Wi-FiのSSID |
| Wi-Fi Password | 必須 | 接続先Wi-Fiのパスワード。空欄の場合は保存済み値を維持 |
| MQTT Broker | 必須 | MQTT brokerのホスト名またはIPアドレス |
| MQTT Port | 必須 | MQTT brokerのポート。通常は`1883` |
| MQTT Username | 任意 | MQTT認証ユーザ名 |
| MQTT Password | 任意 | MQTT認証パスワード。空欄の場合は保存済み値を維持 |

MQTT認証を使わない場合は、MQTT UsernameとMQTT Passwordの両方を空欄にします。片方だけ設定した状態は無効です。

## 4. 通常動作

通常起動時、デバイスは以下の順で動作します。

1. 保存済み設定を読み込みます。
2. Wi-Fiへ接続します。
3. MQTT brokerへ接続します。
4. MQTTでruntime configを要求します。
5. NTPで時刻同期します。
6. 現在時刻に該当する灌水スケジュールがあるか確認します。
7. 土壌水分がしきい値未満の場合、指定チャンネルを指定秒数だけ動作させます。
8. ネットワーク接続中であれば、statusをMQTTへpublishします。
9. `debug_log_on_wake`が有効な場合、debug logをMQTTへpublishします。
10. 次回スケジュールまでdeep sleepします。

Wi-FiまたはMQTTへ接続できない場合でも、保存済みruntime configがあり、Deep Sleep復帰時の時刻が有効であれば、保存済みスケジュールで灌水判定を続けます。電源断後の冷起動など、時刻を信頼できない場合は灌水判定を行わず、短い間隔でネットワーク復帰を再試行します。

## 5. MQTT runtime config

デバイスは起床後、runtime configをMQTTで要求します。

要求topic:

```text
/<device_id>/kinds/config/request
```

要求payload:

```json
{"request":"runtime_config"}
```

設定を返すtopic:

```text
/<device_id>/kinds/config/reply
```

または、broker側からpushするtopic:

```text
/<device_id>/kinds/config/push
```

`<device_id>`はシリアルログに表示される`INADS-...`形式のIDです。

### payload例

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 40,
  "force_watering": false,
  "debug_log_on_wake": false,
  "ota_check_interval_sec": 21600,
  "schedules": [
    {
      "hour": 7,
      "minute": 30,
      "duration_sec": 60,
      "channel_mask": 1
    },
    {
      "hour": 18,
      "minute": 0,
      "duration_sec": 90,
      "channel_mask": 1
    }
  ]
}
```

### runtime config項目

| 項目 | 必須 | 値 | 説明 |
|---|---:|---|---|
| `ntp_server` | 任意 | 文字列 | NTPサーバ。省略時はMQTT brokerアドレスを使用 |
| `timezone_offset_sec` | 任意 | 整数 | UTCからの時差秒。日本時間は`32400` |
| `moisture_threshold` | 任意 | `0`から`100` | 土壌水分しきい値。土壌水分がこの値未満の場合に灌水 |
| `force_watering` | 任意 | `true` / `false` | `true`の場合、土壌水分センサ値に関係なくスケジュール時刻に灌水 |
| `debug_log_on_wake` | 任意 | `true` / `false` | `true`の場合、起床サイクル末尾にdebug logをMQTTへpublish |
| `ota_check_interval_sec` | 任意 | `3600`から`86400` | OTA確認のための最大deep sleep時間。省略時は`21600`秒、つまり6時間 |
| `schedules` | 必須 | 配列 | 灌水スケジュール。最低1件の有効なscheduleが必要 |

schedule項目:

| 項目 | 必須 | 値 | 説明 |
|---|---:|---|---|
| `hour` | 必須 | `0`から`23` | ローカル時刻の時 |
| `minute` | 必須 | `0`から`59` | ローカル時刻の分 |
| `duration_sec` | 必須 | `1`以上 | 灌水時間、秒 |
| `channel_mask` | 必須 | `1`以上 | valve channelのbit mask。pumpは有効なvalve channelがある場合に自動でON |

`channel_mask`の例:

| 値 | 意味 |
|---:|---|
| `1` | valve ch0 |

現在のファームウェアでは、valve ch0は`VALVE_PIN`に対応します。`PUMP_PIN`は、有効なvalve channelが選択されたときに自動で同時ONになります。

制限:

- `schedules`は最大8件までです。
- payloadは512 bytes未満にしてください。
- 無効なschedule entryは無視されます。
- 有効なscheduleが1件もない場合、runtime configは適用されません。
- 有効なruntime configはデバイス内に保存され、次回以降の通信障害時にも利用されます。
- runtime configの応答待ちは起床後5秒です。
- schedule時刻から15分を超えて遅れた場合、そのscheduleは古いものとして灌水せずに処理済みにします。
- センサ異常時などに強制灌水したい場合は、サーバ側で`force_watering: true`を返してください。

## 6. status publish

デバイスは動作結果をMQTTへpublishします。

topic形式:

```text
/<device_id>/kinds/<APP_MQTT_PUB_KIND>/<APP_MQTT_PUB_MODE>
```

標準設定では以下です。

```text
/<device_id>/kinds/agri/immediate
```

payload例:

```json
{
  "seq": 123,
  "network_connected": true,
  "runtime_config_valid": true,
  "config_received": true,
  "time_synced": true,
  "watering_due": true,
  "watering_started": true,
  "watering_duration_sec": 60,
  "channel_mask": 1,
  "schedule_epoch_utc": 1714529400,
  "next_sleep_sec": 21600,
  "ota_check_interval_sec": 21600,
  "last_soil_moisture": 32,
  "threshold": 40,
  "force_watering": true,
  "debug_log_on_wake": true
}
```

主な意味:

| 項目 | 説明 |
|---|---|
| `network_connected` | status送信時にMQTT接続が有効だったか |
| `runtime_config_valid` | デバイス内に有効なruntime configがあるか |
| `config_received` | 今回起床時にruntime configを受信できたか |
| `time_synced` | NTP時刻同期に成功したか |
| `watering_due` | 実行対象スケジュールがあったか |
| `watering_started` | 実際に灌水を開始したか。土壌水分が十分な場合は`false` |
| `ota_check_interval_sec` | OTA確認のための最大deep sleep時間 |
| `last_soil_moisture` | 最後に読み取った土壌水分 |
| `threshold` | 使用した土壌水分しきい値 |
| `force_watering` | 強制灌水設定が有効か |
| `debug_log_on_wake` | debug log publish設定が有効か |

## 7. debug log publish

runtime configで`debug_log_on_wake: true`を指定すると、デバイスは起床サイクル末尾にdebug logをMQTTへpublishします。

topic:

```text
/<device_id>/kinds/debug/log
```

payloadはバイナリです。重要度の高い順に、1回のMQTT publishに収まる分だけ格納されます。

Header:

```text
offset size description
0      3    magic "DLG"
3      1    format version (=1)
4      4    seq, little-endian uint32
8      2    total records in memory, little-endian uint16
10     2    sent records in this payload, little-endian uint16
12     2    dropped/replaced records, little-endian uint16
14     1    record size (=13)
15     1    flags, reserved (=0)
```

Recordは13 bytesです。

```text
offset size description
0      1    file id
1      2    line number, little-endian uint16
3      1    level: 1=INFO, 2=WARNING, 3=ERROR
4      1    event code
5      4    arg0, little-endian int32
9      4    arg1, little-endian int32
```

file idとevent codeの対応はファームウェアの`app_debug_log.h`を参照してください。payloadにはSSID、password、MQTT passwordなどの文字列秘密情報は含めません。

詳細なフォーマット、event code、argの意味、decoder例は[debug_log_format.md](debug_log_format.md)を参照してください。

## 8. 保存済み設定の変更

保存済みWi-Fi/MQTT設定を途中で変更したい場合、BOOTボタンで設定APを強制起動できます。通常の長押しでは既存の設定は消去されず、設定画面に現在値が入った状態で開きます。さらに長く押し続けると、device IDは維持したままWi-Fi/MQTT接続情報をクリアしてから設定APを起動します。

手順:

1. デバイスの電源を入れます。
2. ファームウェア起動後、`APP_SETUP_PORTAL_ARM_WINDOW_MS`以内にBOOTボタンを押します。
3. LEDが速く点滅するので、BOOTボタンを押し続けます。
4. `APP_SETUP_PORTAL_HOLD_MS`以上で離すと、既存設定を保持したまま設定APを起動します。
5. `APP_SETUP_PORTAL_RESET_HOLD_MS`まで押し続けると、Wi-Fi/MQTT接続情報をクリアしてから設定APを起動します。
6. 設定APが起動したら、スマートフォンまたはPCで接続します。
7. ブラウザで`http://192.168.4.1/`を開きます。
8. 変更したい項目を編集して`Save and Restart`を押します。
9. 保存後、デバイスは自動で再起動します。

LED表示:

| 状態 | LED |
|---|---|
| BOOT長押し受付中 | 速い点滅 |
| 設定AP起動中 | ゆっくり点滅 |
| 通常起動 | 消灯 |

標準値:

| 設定 | 標準値 |
|---|---:|
| `APP_SETUP_PORTAL_ARM_WINDOW_MS` | `3000` ms |
| `APP_SETUP_PORTAL_HOLD_MS` | `5000` ms |
| `APP_SETUP_PORTAL_RESET_HOLD_MS` | `10000` ms |
| `APP_SETUP_PORTAL_BUTTON_PIN` | `0` |
| `APP_SETUP_PORTAL_REQUEST_LED_BLINK_MS` | `100` ms |
| `APP_SETUP_PORTAL_ACTIVE_LED_BLINK_MS` | `500` ms |
| `APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS` | `120000` ms |

注意:

- XIAO ESP32S3のBOOTボタンはGPIO0です。
- XIAO ESP32S3のRESETボタンはハードウェアリセット用で、ファームウェアから通常の入力ボタンとして読むことはできません。
- BOOTを押したままハードウェアリセットを解除すると、ROM bootloaderに入る場合があります。
- そのため、BOOTはファームウェア起動後に押し始めてください。
- 長押しリセットで消えるのはWi-Fi SSID/password、MQTT broker/port/username/passwordです。device IDは維持されます。
- Wi-Fi PasswordとMQTT Passwordは空欄のまま保存すると、保存済み値を維持します。
- MQTT認証を無効化したい場合は、MQTT Usernameを空欄にします。
- Wi-Fi/MQTT接続失敗時でも保存済みruntime configがある場合、設定APには入らず保存済みスケジュールで継続運用します。
- 保存済みruntime configがない状態でWi-Fi/MQTT接続失敗により設定APに入った場合、標準ではAP接続端末がない状態が2分続くと自動再起動して通常接続を再試行します。
- スマートフォンやPCが設定APに接続している間は、復帰タイムアウトは進みません。
- Wi-Fi/MQTT設定が未保存の場合とBOOTボタンで強制起動した場合、設定APは自動終了しません。

## 9. トラブルシュート

### 設定APが見つからない

- デバイスの電源を入れ直してください。
- 既存Wi-Fiへ接続できている場合、設定APは起動しません。
- Wi-Fi/MQTT設定が未保存の場合、起動直後に設定APが起動します。
- 保存済みruntime configがある場合、Wi-Fi/MQTT接続に失敗しても設定APは自動起動せず、保存済みスケジュールで継続運用します。
- 既存設定を変更したい場合は、BOOTボタンで設定APを強制起動してください。

### 設定画面が開けない

- スマートフォンまたはPCが設定APに接続されているか確認してください。
- ブラウザで`http://192.168.4.1/`を直接開いてください。
- モバイル回線やVPNを一時的に無効にしてください。

### MQTT configが反映されない

- topicの`device_id`が一致しているか確認してください。
- topicが`/<device_id>/kinds/config/reply`または`/<device_id>/kinds/config/push`になっているか確認してください。
- payloadが512 bytes未満か確認してください。
- `schedules`に有効なentryが1件以上あるか確認してください。
- 起床後5秒以内にreplyを返せているか確認してください。

### 灌水されない

- runtime configのschedule時刻と`timezone_offset_sec`を確認してください。
- `duration_sec`が1以上か確認してください。
- `channel_mask`が1以上か確認してください。
- 土壌水分が`moisture_threshold`以上の場合、灌水は開始されません。
- Wi-Fi/MQTT障害時は、保存済みruntime configとDeep Sleep復帰時の有効な時刻が必要です。電源断後は時刻が失われるため、ネットワーク復帰まで灌水判定は行われません。
- status payloadの`watering_due`と`watering_started`を確認してください。

### BOOTボタンで設定APを起動できない

- BOOTを押したまま電源投入またはハードウェアリセットすると、bootloaderへ入る場合があります。
- 電源投入後、ファームウェアが起動してからBOOTを押してください。
- 押し始めが遅すぎると受付時間を過ぎます。標準では起動後3秒以内です。
- RESETボタンだけでは設定APへ遷移できません。RESETで再起動した後、BOOTを受付時間内に押してください。

## 10. 運用上の注意

- 設定APのパスワードは8文字以上にしてください。
- MQTT brokerはデバイスから到達できるネットワーク上に置いてください。
- runtime configのNTPサーバは、インターネット接続がない環境ではローカルNTPサーバを指定してください。
- `.env.user.ini`では設定APのSSIDだけを指定します。通常接続先のWi-Fi/MQTT設定は初期設定画面で保存され、`/.config`に保存されます。
