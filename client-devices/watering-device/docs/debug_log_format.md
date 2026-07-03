# Debug Log Format

この文書は、デバイスがMQTTで送信するcompact debug logの仕様です。

## Purpose

遠隔設置デバイスの起床サイクルで発生した重要イベントを、1回のMQTT payloadに収まる固定長バイナリ形式で送信します。

このログは、通常のstatusだけでは判断しにくい以下の原因切り分けを目的にします。

- Wi-Fi / MQTT接続失敗
- runtime config未受信または無効
- NTP同期失敗
- schedule判定結果
- 灌水開始、スキップ、出力開始失敗
- OTA request publish、offer受信、offer timeout
- status publish成否
- 次回sleep秒数

SSID、Wi-Fi password、MQTT passwordなどの文字列秘密情報はpayloadに含めません。

## Enable

runtime configで以下を指定します。

```json
{
  "debug_log_on_wake": true
}
```

有効なruntime configを受信または保存済みruntime configから読み込んだ起床サイクルで、network接続中の場合のみ送信されます。

## MQTT Topic

```text
/<device_id>/kinds/debug/log
```

payloadはUTF-8文字列ではなく、binary bytesとして扱ってください。

## Constants

| Name | Value | Source |
|---|---:|---|
| Format version | `1` | `APP_DEBUG_LOG_FORMAT_VERSION` |
| Header size | `16` bytes | `APP_DEBUG_LOG_HEADER_SIZE` |
| Record size | `13` bytes | `APP_DEBUG_LOG_RECORD_SIZE` |
| Max payload size | `512` bytes | `APP_DEBUG_LOG_PAYLOAD_SIZE` |
| Max in-memory events | `128` records | `APP_DEBUG_LOG_MAX_EVENTS` |

512 bytes payloadでは、header 16 bytes + record 13 bytesのため、最大38 recordsを1回で送れます。

## Header

All multi-byte integers are little-endian.

| Offset | Size | Type | Field | Description |
|---:|---:|---|---|---|
| 0 | 3 | bytes | `magic` | ASCII `DLG` |
| 3 | 1 | uint8 | `version` | Format version, currently `1` |
| 4 | 4 | uint32 | `seq` | Wake-cycle sequence id, same style as status `seq` |
| 8 | 2 | uint16 | `total_records` | Records retained in device RAM before publish |
| 10 | 2 | uint16 | `sent_records` | Records included in this payload |
| 12 | 2 | uint16 | `dropped` | Records dropped or replaced due to capacity/priority |
| 14 | 1 | uint8 | `record_size` | Must be `13` |
| 15 | 1 | uint8 | `flags` | Reserved, currently `0` |

## Record

All multi-byte integers are little-endian.

| Offset | Size | Type | Field | Description |
|---:|---:|---|---|---|
| 0 | 1 | uint8 | `file_id` | Source file id |
| 1 | 2 | uint16 | `line` | Source line where the event was recorded |
| 3 | 1 | uint8 | `level` | `1=INFO`, `2=WARNING`, `3=ERROR` |
| 4 | 1 | uint8 | `event` | Event code |
| 5 | 4 | int32 | `arg0` | Event-specific numeric argument |
| 9 | 4 | int32 | `arg1` | Event-specific numeric argument |

The payload is ordered by priority: `ERROR`, then `WARNING`, then `INFO`. It is not a full chronological trace.

## Priority And Dropping

The device keeps up to `APP_DEBUG_LOG_MAX_EVENTS` records in RAM.

When the RAM buffer is full:

- Higher-priority events can replace older lower-priority events.
- If no lower-priority event can be replaced, the new event is dropped.
- `dropped` is incremented for both replacements and drops.

At publish time, records are packed until `APP_DEBUG_LOG_PAYLOAD_SIZE` would be exceeded. Remaining records are omitted from this payload.

## Levels

| Value | Name | Meaning |
|---:|---|---|
| `1` | INFO | Normal progress or successful operation |
| `2` | WARNING | Degraded path, fallback, skipped action, weak signal, or no due schedule |
| `3` | ERROR | Operation failed or required state unavailable |

## File IDs

| Value | Symbol | Source |
|---:|---|---|
| `1` | `APP_DEBUG_FILE_APP` | `src/app/src/app.cpp` |
| `2` | `APP_DEBUG_FILE_NETWORK` | `../common/lib/ina-client-common/src/app/src/app_network.cpp` |
| `3` | `APP_DEBUG_FILE_RUNTIME_CONFIG` | `src/app/src/app_runtime_config.cpp` |
| `4` | `APP_DEBUG_FILE_WATERING` | `src/app/src/app_watering.cpp` |

Line numbers are generated with `__LINE__`. They are valid for the firmware build that produced the log. The server should associate decoded logs with the firmware version or commit used on the device.

## Common Packed Fields

### runtime flags

Used by:

- `APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE`
- `APP_DEBUG_EVENT_RUNTIME_CONFIG_UPDATED`

`arg0` layout:

| Bits | Meaning |
|---:|---|
| 0..7 | `moisture_threshold` |
| 8 | `force_watering`, `1=true` |
| 9 | `debug_log_on_wake`, `1=true` |
| 16..23 | `schedule_count` |

### watering decision flags

Used by `APP_DEBUG_EVENT_WATERING_DECISION`.

`arg0` layout:

| Bits | Meaning |
|---:|---|
| 0..7 | soil moisture percent |
| 8..15 | threshold percent |
| 16 | `force_watering`, `1=true` |

## Event Codes

### App events

| Code | Symbol | Typical level | arg0 | arg1 |
|---:|---|---|---|---|
| 1 | `APP_DEBUG_EVENT_BOOT` | INFO | ESP reset reason | `0` |
| 2 | `APP_DEBUG_EVENT_LITTLEFS_MOUNTED` | INFO | `0` | `0` |
| 3 | `APP_DEBUG_EVENT_CONFIG_LOADED` | INFO | network configured: `1/0` | config CRC32 raw bits |
| 4 | `APP_DEBUG_EVENT_RUNTIME_CONFIG_INIT` | INFO | runtime config valid: `1/0` | `debug_log_on_wake`: `1/0` |
| 5 | `APP_DEBUG_EVENT_NETWORK_START` | INFO or ERROR | network start result: `1/0` | MQTT connected: `1/0` |
| 6 | `APP_DEBUG_EVENT_NETWORK_UNAVAILABLE` | ERROR | `0` | `0` |
| 7 | `APP_DEBUG_EVENT_RUNTIME_CONFIG_REQUEST` | INFO or WARNING | request published: `1/0` | config received: `1/0` |
| 8 | `APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE` | INFO | runtime flags | `0` |
| 9 | `APP_DEBUG_EVENT_TIME_SYNC_NTP_FAILED_RTC` | WARNING | using RTC: `1` | `0` |
| 10 | `APP_DEBUG_EVENT_TIME_SYNC_OFFLINE_RTC` | WARNING | using RTC: `1` | `0` |
| 11 | `APP_DEBUG_EVENT_TIME_SYNC_UNAVAILABLE` | ERROR | woke from deep sleep: `1/0` | `0` |
| 12 | `APP_DEBUG_EVENT_TIME_SYNC_OK` | INFO | current epoch seconds | `0` |
| 13 | `APP_DEBUG_EVENT_SCHEDULE_CHECK` | INFO or WARNING | bit0 `watering_due`, bit1 `runtime_config_valid` | `last_executed_schedule_utc` |
| 14 | `APP_DEBUG_EVENT_WATERING_DUE_RESULT` | INFO or WARNING | bits 0..15 `duration_sec`, bit16 `watering_started` | `channel_mask` |
| 15 | `APP_DEBUG_EVENT_SLEEP_PLANNED` | INFO | sleep seconds | `0` |
| 16 | `APP_DEBUG_EVENT_STATUS_SENT` | INFO | `0` | `0` |
| 17 | `APP_DEBUG_EVENT_STATUS_FAILED` | ERROR | `0` | `0` |
| 18 | `APP_DEBUG_EVENT_STATUS_SKIPPED` | WARNING | `0` | `0` |
| 19 | `APP_DEBUG_EVENT_DEBUG_LOG_PUBLISH_ENABLED` | INFO | status sent: `1/0` | sleep seconds |

### OTA events

| Code | Symbol | Typical level | arg0 | arg1 |
|---:|---|---|---|---|
| 80 | `APP_DEBUG_EVENT_OTA_REQUEST_SENT` | INFO | request published: `1` | offer wait timeout ms |
| 81 | `APP_DEBUG_EVENT_OTA_REQUEST_FAILED` | ERROR | request published: `0` | offer wait timeout ms |
| 82 | `APP_DEBUG_EVENT_OTA_OFFER_TIMEOUT` | WARNING | offer wait timeout ms | `0` |
| 83 | `APP_DEBUG_EVENT_OTA_OFFER_RECEIVED` | INFO | offer received: `1` | offer wait timeout ms |
| 84 | `APP_DEBUG_EVENT_OTA_HANDLE_RESULT` | INFO or WARNING | update attempted: `1/0` | `0` |
| 85 | `APP_DEBUG_EVENT_OTA_LATE_OFFER_IGNORED` | WARNING | payload length bytes | `0` |

### Network events

`context id` values:

| Value | Meaning |
|---:|---|
| `1` | startup |
| `2` | reconnect |

| Code | Symbol | Typical level | arg0 | arg1 |
|---:|---|---|---|---|
| 30 | `APP_DEBUG_EVENT_MQTT_DNS_FAILED` | ERROR | context id | `0` |
| 31 | `APP_DEBUG_EVENT_MQTT_CONNECTED` | INFO | context id | MQTT port |
| 32 | `APP_DEBUG_EVENT_MQTT_FAILED` | ERROR | context id | PubSubClient `state()` |
| 33 | `APP_DEBUG_EVENT_WIFI_FAILED` | ERROR | `wl_status_t` | `0` |
| 34 | `APP_DEBUG_EVENT_WIFI_CONNECTED` | INFO or WARNING | RSSI dBm | `0` |
| 35 | `APP_DEBUG_EVENT_WIFI_RECONNECT_FAILED` | ERROR | `wl_status_t` | `0` |
| 36 | `APP_DEBUG_EVENT_WIFI_RECONNECTED` | INFO or WARNING | RSSI dBm | `0` |

Wi-Fi connected/reconnected is WARNING when RSSI is below `-85 dBm`.

### Runtime config events

| Code | Symbol | Typical level | arg0 | arg1 |
|---:|---|---|---|---|
| 50 | `APP_DEBUG_EVENT_RUNTIME_CONFIG_UPDATED` | INFO | runtime flags | `timezone_offset_sec` |

### Watering events

| Code | Symbol | Typical level | arg0 | arg1 |
|---:|---|---|---|---|
| 70 | `APP_DEBUG_EVENT_WATERING_OUTPUT_MAP` | INFO | valve mask | pump mask |
| 71 | `APP_DEBUG_EVENT_WATERING_DECISION` | INFO | watering decision flags | output mask |
| 72 | `APP_DEBUG_EVENT_WATERING_OUTPUT_START_FAILED` | ERROR | duration seconds | output mask |
| 73 | `APP_DEBUG_EVENT_WATERING_STARTED` | INFO | duration seconds | output mask |
| 74 | `APP_DEBUG_EVENT_WATERING_SKIPPED_MOISTURE` | WARNING | soil moisture percent | threshold percent |
| 75 | `APP_DEBUG_EVENT_WATERING_COMPLETED` | INFO | `0` | `0` |

## Decoder Example

Python example:

```python
import struct

def decode_debug_log(payload: bytes):
    if len(payload) < 16:
        raise ValueError("payload too short")
    if payload[:3] != b"DLG":
        raise ValueError("bad magic")

    version = payload[3]
    seq, total, sent, dropped = struct.unpack_from("<IHHH", payload, 4)
    record_size = payload[14]
    flags = payload[15]

    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    if record_size != 13:
        raise ValueError(f"unsupported record size: {record_size}")

    records = []
    offset = 16
    for _ in range(sent):
        if offset + record_size > len(payload):
            raise ValueError("truncated payload")
        file_id, line, level, event, arg0, arg1 = struct.unpack_from("<BHBBii", payload, offset)
        records.append({
            "file_id": file_id,
            "line": line,
            "level": level,
            "event": event,
            "arg0": arg0,
            "arg1": arg1,
        })
        offset += record_size

    return {
        "version": version,
        "seq": seq,
        "total_records": total,
        "sent_records": sent,
        "dropped": dropped,
        "flags": flags,
        "records": records,
    }
```

## Server Handling Recommendations

- Store raw payload bytes for later re-decoding when firmware mappings change.
- Store decoded records together with firmware version or source commit.
- Treat `ERROR` records as immediate investigation signals.
- Treat `dropped > 0` or `sent_records < total_records` as evidence that the wake cycle produced more logs than were transmitted.
- Do not assume payload order is chronological; it is priority-oriented.
