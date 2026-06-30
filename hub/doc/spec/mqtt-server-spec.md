# MQTT Server Integration Specification

この文書は、INA Water Controllerと連携するMQTTサーバ実装者向けの仕様です。

## 1. 役割

MQTTサーバ側は、以下を実装してください。

- デバイスからのruntime config要求を受信する
- 対象デバイスへruntime configを返す
- 必要に応じてruntime configをpush配信する
- デバイスがpublishするstatusを受信・保存・監視する

MQTT broker自体は標準的なMQTT brokerで構いません。アプリケーションサーバはbrokerに接続し、下記topicをsubscribe/publishしてください。

## 2. MQTT接続条件

デバイス側のMQTT clientはArduino `PubSubClient`です。

想定条件:

| 項目 | 仕様 |
|---|---|
| Protocol | MQTT 3.1.1相当 |
| QoS | QoS 0前提 |
| Retain | 任意。config pushでは利用可能 |
| Client ID | デバイスの`device_id` |
| Authentication | 任意。username/passwordなし、または両方あり |
| TLS | 現状未対応。平文MQTT想定 |
| Default port | `1883` |

デバイスはusernameが空の場合、username/passwordなしで接続します。usernameが空でない場合、username/passwordありで接続します。

## 3. Topic形式

すべてのアプリケーションtopicは以下の形式です。

```text
/<device_id>/kinds/<kind>/<mode>
```

例:

```text
/INADS-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx/kinds/config/request
```

### device_id

`device_id`はデバイスごとに生成されるIDです。

形式:

```text
INADS-<uuid>
```

MQTTサーバは、topic内の`device_id`をデバイス識別子として扱ってください。

### kind/mode

| kind | mode | 方向 | 用途 |
|---|---|---|---|
| `config` | `request` | Device -> Server | runtime config要求 |
| `config` | `reply` | Server -> Device | requestに対するruntime config応答 |
| `config` | `push` | Server -> Device | サーバ起点のruntime config配信 |
| `agri` | `immediate` | Device -> Server | status publish。`agri`/`immediate`は標準build設定 |

`agri`と`immediate`はbuild flagで変更可能です。標準値は以下です。

```text
APP_MQTT_PUB_KIND=agri
APP_MQTT_PUB_MODE=immediate
```

## 4. Server Subscribe要件

サーバアプリケーションは、少なくとも以下をsubscribeしてください。

```text
/+/kinds/config/request
/+/kinds/+/+
```

実装上は、以下のように用途を分けることを推奨します。

| subscribe topic | 用途 |
|---|---|
| `/+/kinds/config/request` | runtime config要求処理 |
| `/+/kinds/agri/immediate` | status受信 |

複数デバイスを扱う場合、`+` wildcardで受信し、topicから`device_id`を取り出してください。

## 5. Device Registration

現状のデバイスファームウェアには、MQTTとは別の明示的な登録APIはありません。
MQTTサーバ側で、初回接続・初回messageを登録契機として扱ってください。

推奨する登録方式:

1. サーバが`/+/kinds/config/request`をsubscribeする。
2. 未登録の`device_id`から`config/request`を受信する。
3. サーバはその`device_id`を`pending`状態で仮登録する。
4. サーバはsafe default configを`/<device_id>/kinds/config/reply`へ返す。
5. 管理画面または管理APIで、運用者が設置場所・名称・正式runtime configを設定して`active`へ変更する。
6. 次回以降、サーバは保存済みruntime configを返す。

登録状態の例:

| State | Meaning | Server behavior |
|---|---|---|
| `pending` | 初回requestを受けたが、運用者が未承認 | safe default configを返す。statusは保存する |
| `active` | 運用対象として承認済み | deviceごとのruntime configを返す |
| `disabled` | 利用停止または不審なdevice | 原則configを返さない、または灌水しないsafe configのみ返す |

推奨デバイス管理項目:

| Field | Description |
|---|---|
| `device_id` | MQTT topicから取得する`INADS-...` |
| `state` | `pending` / `active` / `disabled` |
| `name` | 管理画面上の表示名 |
| `location` | 設置場所 |
| `runtime_config` | deviceごとの最新runtime config |
| `first_seen_at` | 初回message受信時刻 |
| `last_seen_at` | 最終message受信時刻 |
| `last_status` | 最終status payload |

MQTT brokerの接続イベントだけで登録する方式は推奨しません。brokerによって接続イベントの取得方法が異なり、アプリケーションサーバが必ず検知できるとは限らないためです。
サーバアプリケーションが確実に受信できる`config/request`を登録契機にしてください。

認証を使う場合でも、初期運用では以下のどちらかにしてください。

- 全デバイス共通の初期MQTT username/passwordでbroker接続を許可し、初回`config/request`で`pending`登録する。
- デバイス出荷時に個別credentialを設定し、credentialと`device_id`を事前登録する。

前者は導入が簡単です。後者はセキュリティ上は強いですが、製造・出荷時のcredential管理が必要です。

## 6. Runtime Config Request

デバイスは起床後、MQTT接続完了後にruntime configを要求します。

topic:

```text
/<device_id>/kinds/config/request
```

payload:

```json
{"request":"runtime_config"}
```

サーバはこのmessageを受信したら、同じ`device_id`宛てにruntime configをpublishしてください。

応答topic:

```text
/<device_id>/kinds/config/reply
```

重要なタイミング要件:

- デバイスはrequest publish後、約5秒だけruntime configを待ちます。
- サーバはrequest受信後、可能な限り即時にreplyしてください。
- 5秒以内にreplyできない場合、その起床サイクルではデバイスが古い設定またはdefault設定で動作する可能性があります。

## 7. Runtime Config Push

サーバはrequestを待たずに、runtime configをpushできます。

topic:

```text
/<device_id>/kinds/config/push
```

用途:

- 次回起床時に新しい設定を届けたい
- retained messageとして最新configをbrokerに置きたい

retain利用:

- `config/push`はretainしても構いません。
- デバイスはsubscribe後に受信した`config/push`をruntime configとして処理します。
- ただし、requestに対する確実な同期を取りたい場合は`config/reply`も実装してください。

推奨:

- サーバは`config/request`に必ず`config/reply`で応答する
- 最新設定をbrokerに保持したい場合のみ、追加でretained `config/push`を使う

## 8. Runtime Config Payload

payloadはJSONです。

例:

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 40,
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
      "channel_mask": 3
    }
  ]
}
```

### Top-level fields

| Field | Required | Type | Range / Default | Description |
|---|---:|---|---|---|
| `ntp_server` | No | string | default: MQTT broker address | NTP server hostname or IP |
| `timezone_offset_sec` | No | integer | default: `0` | Local timezone offset from UTC in seconds. Japan: `32400` |
| `moisture_threshold` | No | integer | `0..100`, default: previous value or `40` | Watering starts only when soil moisture is below this value |
| `schedules` | Yes | array | 1 to 8 valid entries | Daily watering schedules |

### Schedule fields

| Field | Required | Type | Range | Description |
|---|---:|---|---|---|
| `hour` | Yes | integer | `0..23` | Local hour |
| `minute` | Yes | integer | `0..59` | Local minute |
| `duration_sec` | Yes | integer | `1..65535` recommended | Watering duration in seconds |
| `channel_mask` | Yes | integer | `1..4294967295` | Output channel bit mask |

### channel_mask

Current firmware mapping:

| Bit | Value | Channel | Hardware |
|---:|---:|---|---|
| 0 | `1` | ch0 | `PUMP_PIN` |
| 1 | `2` | ch1 | `VALVE_PIN` |

Examples:

| `channel_mask` | Meaning |
|---:|---|
| `1` | ch0 only |
| `2` | ch1 only |
| `3` | ch0 and ch1 |

## 9. Payload Validation Requirements

サーバは、publish前に以下を検証してください。

- JSONとしてvalidであること
- MQTT payloadが512 bytes未満であること
- `schedules`が配列であること
- 有効なscheduleが1件以上あること
- schedule数が8件以下であること
- `hour`が`0..23`
- `minute`が`0..59`
- `duration_sec`が`1`以上
- `channel_mask`が`1`以上
- `moisture_threshold`が`0..100`
- `timezone_offset_sec`が運用地域に対して正しいこと

デバイス側は無効なschedule entryを無視します。有効なscheduleが1件も残らない場合、config全体を適用しません。

## 10. Status Publish

デバイスは各起床サイクルの最後にstatusをpublishします。

標準topic:

```text
/<device_id>/kinds/agri/immediate
```

payload例:

```json
{
  "seq": 123,
  "config_received": true,
  "time_synced": true,
  "watering_due": true,
  "watering_started": true,
  "watering_duration_sec": 60,
  "channel_mask": 1,
  "schedule_epoch_utc": 1714529400,
  "next_sleep_sec": 37800,
  "last_soil_moisture": 32,
  "threshold": 40
}
```

### Status fields

| Field | Type | Description |
|---|---|---|
| `seq` | integer | Random sequence ID for this status |
| `config_received` | boolean | Whether runtime config was received in this wake cycle |
| `time_synced` | boolean | Whether NTP time sync succeeded |
| `watering_due` | boolean | Whether a schedule was due |
| `watering_started` | boolean | Whether watering output actually started |
| `watering_duration_sec` | integer | Scheduled watering duration. `0` when no schedule was due |
| `channel_mask` | integer | Scheduled output channel mask. `0` when no schedule was due |
| `schedule_epoch_utc` | integer | Due schedule time as UTC epoch. `0` when no schedule was due |
| `next_sleep_sec` | integer | Planned sleep duration until next wake-up |
| `last_soil_moisture` | integer | Last measured soil moisture percent |
| `threshold` | integer | Moisture threshold used for this cycle |

### Status interpretation

| Condition | Meaning |
|---|---|
| `config_received=false` | サーバ応答が5秒以内に届かなかった、またはpayloadが無効 |
| `time_synced=false` | NTP同期に失敗。schedule実行判定は行われない |
| `watering_due=true`, `watering_started=false` | scheduleは到来したが、土壌水分がしきい値以上、または出力開始に失敗 |
| `watering_due=false` | 現在時刻で実行対象scheduleなし |

サーバはstatusを保存し、少なくとも以下を監視することを推奨します。

- `config_received=false`が連続する
- `time_synced=false`が連続する
- `watering_due=true`かつ`watering_started=false`が連続する
- `last_soil_moisture`が長期間しきい値未満
- statusが想定時刻に届かない

## 11. Recommended Server Behavior

### Per-device config storage

サーバは`device_id`ごとに最新runtime configを保存してください。

推奨データモデル:

```json
{
  "device_id": "INADS-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx",
  "runtime_config": {
    "ntp_server": "pool.ntp.org",
    "timezone_offset_sec": 32400,
    "moisture_threshold": 40,
    "schedules": []
  },
  "updated_at": "2026-05-04T00:00:00Z"
}
```

### Request handling

疑似コード:

```text
on_message(topic, payload):
  device_id, kind, mode = parse_topic(topic)

  if kind == "config" and mode == "request":
    config = load_latest_config(device_id)
    if config exists and config is valid:
      publish("/" + device_id + "/kinds/config/reply", config_json, qos=0, retain=false)
    else:
      publish_safe_default_config(device_id)

  if kind == "agri" and mode == "immediate":
    save_status(device_id, payload)
    update_device_health(device_id, payload)
```

### Safe default config

デバイスに設定が未登録の場合でも、サーバは有効なconfigを返すことを推奨します。
安全側に倒す場合は、`moisture_threshold`を`0`にして通常は灌水が開始されないようにしてください。

例:

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 0,
  "schedules": [
    {
      "hour": 7,
      "minute": 0,
      "duration_sec": 1,
      "channel_mask": 1
    }
  ]
}
```

注意: 空の`schedules`はデバイス側で無効です。未登録デバイスで灌水させたくない場合でも、有効なscheduleを1件入れたうえで`moisture_threshold`を`0`にしてください。

## 12. Error Handling

サーバは以下をログに残してください。

- 不正なtopic形式
- 未登録deviceからのrequest
- config生成失敗
- config payloadが512 bytes以上
- config validation failure
- status payload parse failure
- deviceごとの最終status受信時刻

未登録deviceの扱いは運用ポリシーに合わせてください。

推奨:

- 未登録deviceからのrequestは記録する
- 管理画面でdevice登録を促す
- 登録前でもsafe default configを返し、デバイスが無限に失敗しないようにする

## 13. Management Requirements

この章は、MQTTサーバに付随する管理画面または管理APIの推奨仕様です。
MQTT連携だけでなく、デバイス登録、設定配信、状態監視を運用できるようにしてください。

### 13.1 Device lifecycle

デバイスは以下の状態で管理してください。

| State | Description | Allowed server behavior |
|---|---|---|
| `pending` | 初回`config/request`を受けた未承認device | safe default configを返す。statusは保存する |
| `active` | 承認済みで運用中 | deviceごとのruntime configを返す |
| `disabled` | 利用停止 | 原則runtime configを返さない、または灌水しないsafe configのみ返す |
| `retired` | 廃止済み | request/statusは記録するが、通常運用対象から除外する |

推奨状態遷移:

```text
unknown --first config/request--> pending
pending --operator approves--> active
active --operator disables--> disabled
disabled --operator enables--> active
active/disabled --operator retires--> retired
```

`retired`は物理的に廃棄・交換したdeviceの履歴保持用です。再利用する可能性がある場合は`disabled`にしてください。

### 13.2 Device record

管理DBでは、deviceごとに以下の情報を保持してください。

| Field | Required | Description |
|---|---:|---|
| `device_id` | Yes | `INADS-...`形式のID。primary key推奨 |
| `state` | Yes | `pending` / `active` / `disabled` / `retired` |
| `name` | No | 管理画面上の表示名 |
| `location` | No | 設置場所 |
| `memo` | No | 任意メモ |
| `runtime_config` | Yes for active | 次回request時に返すruntime config |
| `first_seen_at` | Yes | 初回message受信時刻 |
| `last_seen_at` | No | 最終message受信時刻 |
| `last_config_request_at` | No | 最終`config/request`受信時刻 |
| `last_config_reply_at` | No | 最終`config/reply`送信時刻 |
| `last_status_at` | No | 最終status受信時刻 |
| `last_status` | No | 最終status payload |
| `created_at` | Yes | 管理レコード作成時刻 |
| `updated_at` | Yes | 管理レコード更新時刻 |
| `approved_at` | No | `active`承認時刻 |
| `approved_by` | No | 承認した管理ユーザ |

`runtime_config`は最新値だけでなく、変更履歴も保持することを推奨します。

### 13.3 Management UI

管理画面は最低限以下の画面を提供してください。

| Screen | Required features |
|---|---|
| Device list | device一覧、状態、名称、設置場所、最終受信時刻、最新health表示 |
| Pending devices | 未承認device一覧、承認、無効化、safe default送信状況 |
| Device detail | device基本情報、最新status、runtime config、履歴 |
| Runtime config editor | schedule編集、しきい値編集、NTP/timezone設定、validation |
| Status history | status payload履歴、絞り込み、異常状態の確認 |
| Audit log | 管理操作履歴、誰が何を変更したか |

Device listで表示する推奨項目:

| Column | Description |
|---|---|
| Device ID | `INADS-...` |
| Name | 管理名 |
| State | `pending` / `active` / `disabled` / `retired` |
| Location | 設置場所 |
| Last seen | 最終message受信時刻 |
| Config received | 最新statusの`config_received` |
| Time synced | 最新statusの`time_synced` |
| Last moisture | 最新statusの`last_soil_moisture` |
| Threshold | 最新statusの`threshold` |
| Next wake | 最新statusの`next_sleep_sec`から推定した次回起床時刻 |

### 13.4 Management API

管理画面以外から操作できるよう、以下のAPI相当の機能を用意することを推奨します。
HTTP APIである必要はありませんが、同等の操作ができるようにしてください。

| Operation | Method example | Description |
|---|---|---|
| List devices | `GET /devices` | device一覧取得 |
| Get device | `GET /devices/{device_id}` | device詳細取得 |
| Approve device | `POST /devices/{device_id}/approve` | `pending`から`active`へ変更 |
| Disable device | `POST /devices/{device_id}/disable` | deviceを無効化 |
| Retire device | `POST /devices/{device_id}/retire` | deviceを廃止扱いにする |
| Update metadata | `PATCH /devices/{device_id}` | name/location/memo更新 |
| Get config | `GET /devices/{device_id}/runtime-config` | runtime config取得 |
| Update config | `PUT /devices/{device_id}/runtime-config` | runtime config更新 |
| Push config | `POST /devices/{device_id}/runtime-config/push` | `config/push`をpublish |
| List statuses | `GET /devices/{device_id}/statuses` | status履歴取得 |
| Get audit logs | `GET /audit-logs` | 監査ログ取得 |

`Update config`では、MQTTへpublishする前に必ず`Payload Validation Requirements`と同じvalidationを行ってください。

`Push config`は任意機能です。通常は次回`config/request`への`config/reply`で十分です。

### 13.5 Runtime config versioning

runtime configはversion管理してください。

推奨フィールド:

| Field | Description |
|---|---|
| `config_version` | 単調増加する整数、またはUUID |
| `device_id` | 対象device |
| `config_json` | デバイスへ送るruntime config |
| `created_at` | 作成時刻 |
| `created_by` | 作成者 |
| `comment` | 変更理由 |
| `is_active` | 次回reply対象か |

現状のデバイスpayloadには`config_version`フィールドは必須ではありません。
サーバ内部ではversionを持ち、deviceへ送るJSONには含めても含めなくても構いません。
含める場合、現状ファームウェアは未使用フィールドとして無視します。

### 13.6 Validation rules for management

管理画面/APIでは以下を防いでください。

- `schedules`が空のactive config
- 9件以上のschedule
- 512 bytes以上のMQTT payload
- `duration_sec <= 0`
- `channel_mask == 0`
- `hour` / `minute`が範囲外
- MQTT username/passwordの片方だけ設定
- `timezone_offset_sec`未設定のまま意図しないUTC運用になること

UIではpayload sizeを表示し、512 bytesに近づいたら警告してください。

### 13.7 Health monitoring

サーバはdeviceごとのhealth状態を計算してください。

推奨health:

| Health | Condition example |
|---|---|
| `ok` | 直近statusが正常、次回起床予定内 |
| `warning` | `config_received=false`、`time_synced=false`、またはstatus遅延が1回 |
| `critical` | status未受信が複数回、NTP失敗が連続、config失敗が連続 |
| `disabled` | device stateが`disabled`または`retired` |

status遅延判定:

```text
expected_next_seen_at = last_status_at + last_status.next_sleep_sec + grace_period
```

`grace_period`は運用環境に合わせて設定してください。例: 5分から30分。

監視すべき主な異常:

- statusが想定時刻を過ぎても届かない
- `config_received=false`が連続する
- `time_synced=false`が連続する
- `watering_due=true`なのに`watering_started=false`が連続する
- `last_soil_moisture`が長時間しきい値未満
- `next_sleep_sec`が極端に短い、または長い

### 13.8 Audit log

管理操作は監査ログに残してください。

記録対象:

- device承認
- device無効化
- device廃止
- metadata変更
- runtime config作成・更新・有効化
- manual config push
- safe default config送信

推奨フィールド:

| Field | Description |
|---|---|
| `audit_id` | 監査ログID |
| `actor` | 操作ユーザまたはsystem |
| `action` | 操作種別 |
| `device_id` | 対象device |
| `before` | 変更前JSON |
| `after` | 変更後JSON |
| `created_at` | 操作時刻 |

### 13.9 Access control

管理機能には認証・認可を入れてください。

推奨ロール:

| Role | Permissions |
|---|---|
| `viewer` | device/status/config閲覧 |
| `operator` | pending承認、metadata更新、config更新 |
| `admin` | device無効化・廃止、ユーザ管理、broker credential管理 |

runtime config変更とdevice無効化は、少なくとも`operator`以上に制限してください。

### 13.10 Registration UX

pending deviceを運用者が識別しやすいよう、管理画面では以下を表示してください。

- `device_id`
- `first_seen_at`
- `last_seen_at`
- 初回request payload
- 最新status
- 接続元情報。取得できる場合のみ

現状ファームウェアの初回request payloadは以下だけです。

```json
{"request":"runtime_config"}
```

そのため、設置場所やデバイス名は管理画面で運用者が入力してください。
QRコードやラベルで`device_id`を現物に貼る運用を推奨します。

## 14. mosquitto Examples

config requestを監視:

```bash
mosquitto_sub -h <broker> -t '/+/kinds/config/request' -v
```

statusを監視:

```bash
mosquitto_sub -h <broker> -t '/+/kinds/agri/immediate' -v
```

config replyを送信:

```bash
mosquitto_pub -h <broker> \
  -t '/INADS-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx/kinds/config/reply' \
  -m '{"ntp_server":"pool.ntp.org","timezone_offset_sec":32400,"moisture_threshold":40,"schedules":[{"hour":7,"minute":30,"duration_sec":60,"channel_mask":1}]}'
```

retained config pushを送信:

```bash
mosquitto_pub -h <broker> -r \
  -t '/INADS-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx/kinds/config/push' \
  -m '{"ntp_server":"pool.ntp.org","timezone_offset_sec":32400,"moisture_threshold":40,"schedules":[{"hour":7,"minute":30,"duration_sec":60,"channel_mask":1}]}'
```

## 15. Compatibility Notes

- デバイスは受信payloadが512 bytes以上の場合、破棄します。
- デバイスは`/<device_id>/kinds/config/reply`と`/<device_id>/kinds/config/push`のみruntime configとして処理します。
- topic内の`device_id`が自分のIDと一致しないmessageは無視します。
- `config/request`はデバイスからserverへの要求であり、デバイス側はrequest topicをruntime configとして処理しません。
- 現状、デバイス側からconfig適用成功/失敗だけを直接ackする専用topicはありません。`status.config_received`で結果を判断してください。

