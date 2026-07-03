# OTA Update Specification

この文書は、INA Water ControllerにOTA firmware updateを実装するための仕様です。

Status: implemented initial version. HTTP firmware download, MQTT OTA control/status, Hub-side update decision, and OTA-capable partition layout are implemented.

## 1. Scope

対象:

- Firmware image OTA更新
- MQTTを使った更新指示、状態通知、監査用イベント
- Hubまたは管理サーバからのfirmware binary HTTP配信
- 既存のdeep sleep起床サイクルに組み込む更新フロー

対象外:

- Bootloader OTA更新
- Partition table OTA更新
- LittleFS image OTA更新
- MQTT payloadによるfirmware binary分割配信

LittleFSには`/.config`と`/.runtime_config`が保存されます。filesystem image更新は設定消失リスクがあるため、初期実装では扱いません。

## 2. Key Decisions

- OTA transportはHTTP downloadとする。
- MQTTではfirmware本体を送らず、更新有無の照会、更新offer、進捗/statusだけを扱う。
- 更新有無はHubまたは管理サーバが判断し、デバイスはHubから返された`action`に従う。
- OTAはruntime config取得後、灌水判定前に実行する。
- OTA更新を開始した起床サイクルでは灌水しない。更新成功後に再起動し、次回起床サイクルから通常動作する。
- Firmware binaryは必ずSHA-256で検証する。
- deep sleepは次回灌水予定時刻までを基本とするが、OTA確認遅延に上限を持たせるため、runtime configの`ota_check_interval_sec`で最大sleep時間をcapする。defaultは`21600`秒、つまり6時間。

## 3. Required Partition Layout

OTA-capable firmware uses the following 8MB flash layout.

```csv
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x5000,
otadata,  data, ota,     0xe000,  0x2000,
app0,     app,  ota_0,   0x10000, 0x330000,
app1,     app,  ota_1,   0x340000,0x330000,
storage,  data, spiffs,  0x670000,0x180000,
coredump, data, coredump,0x7F0000,0x10000,
```

Rationale:

| Partition | Size | Purpose |
|---|---:|---|
| `otadata` | 8 KB | ESP32 OTA boot selection metadata |
| `app0` | 3.1875 MB | Active or inactive firmware slot |
| `app1` | 3.1875 MB | Active or inactive firmware slot |
| `storage` | 1.5 MB | LittleFS data partition |
| `coredump` | 64 KB | Crash dump area |

Current reference build:

| Artifact | Size |
|---|---:|
| `firmware.bin` | 895,216 bytes |
| Current `storage` image | 1,572,864 bytes |

The current firmware has enough headroom for the OTA app slots. `APP_LITTLEFS_PARTITION_LABEL` must remain `storage`.

## 4. Provisioning Image Layout

OTA updates rewrite only the inactive app partition. They do not rewrite the bootloader, partition table, or LittleFS. A full provisioning image for the OTA-capable layout uses the following offsets.

Provisioning image contents:

| Offset | Artifact |
|---:|---|
| `0x0` | `bootloader.bin` |
| `0x8000` | `partitions.bin` |
| `0xe000` | `boot_app0.bin` |
| `0x10000` | `firmware.bin` |
| `0x670000` | `littlefs.bin` |

Normal OTA artifacts use only `.pio/build/seeed_xiao_esp32s3/firmware.bin`.

## 5. Firmware Versioning

The firmware must expose a version in MQTT status and OTA requests.

Recommended build flags:

```ini
-D APP_DEVICE_KIND=\"WTR\"
-D APP_FIRMWARE_VERSION=\"1.0.0\"
-D APP_FIRMWARE_BUILD_ID=\"2026-07-01T00:00:00Z+abcdef0\"
```

Required version rules:

- `APP_FIRMWARE_VERSION` must be stable for a released binary.
- `APP_FIRMWARE_BUILD_ID` should include build time or git commit.
- `APP_DEVICE_KIND` must be stable for the firmware target hardware family.
  Watering-device defines `APP_DEVICE_KIND="WTR"` in `platformio.ini`; the
  common library only provides a generic fallback.
- Server-side rollout decisions must use `firmware_version`, not only `device_id`.
- Downgrade is rejected unless the offer explicitly sets `allow_downgrade: true`.

Normal status payload should add:

```json
{
  "device_kind": "WTR",
  "firmware_version": "1.0.0",
  "firmware_build_id": "2026-07-01T00:00:00Z+abcdef0"
}
```

## 6. Device Kind

OTA compatibility is scoped by a three-letter uppercase device kind code.

| Device | `device_kind` |
|---|---|
| Watering device | `WTR` |

Rules:

- `device_kind` must be exactly three uppercase alphabetic characters: `^[A-Z]{3}$`.
- Device OTA requests, normal status, OTA status, and firmware artifacts must include `device_kind`.
- Hub must not offer an artifact whose `device_kind` differs from the requesting device.
- Device firmware must reject an OTA offer whose `device_kind` differs from its built-in `APP_DEVICE_KIND`.
- New device projects must assign their own three-letter code in their local
  `platformio.ini`.

## 7. MQTT Topics

All OTA control topics use the existing application topic shape:

```text
/<device_id>/kinds/<kind>/<mode>
```

OTA topics:

| kind | mode | Direction | Retain | Purpose |
|---|---|---|---:|---|
| `ota` | `request` | Device -> Server | No | Device asks whether an update is available |
| `ota` | `reply` | Server -> Device | No | Server replies to an OTA request |
| `ota` | `push` | Server -> Device | Optional | Server offers an update without waiting for request |
| `ota` | `status` | Device -> Server | No | Device reports OTA progress/result |

The device already subscribes to wildcard topics. OTA implementation must extend the subscribe callback to process only `ota/reply` and `ota/push` messages addressed to its own `device_id`.

The Hub replies immediately to each OTA request. When the reply is an
`action: "update"` offer, the Hub also republishes the same reply with short
backoff delays in the same wake window. This mitigates transient MQTT timing
races without increasing the device wake frequency or adding another
device-side retry cycle.

The device treats OTA as a separate phase before normal operation. It accepts
`ota/reply` and `ota/push` only while it is explicitly waiting for an offer
after publishing `ota/request`. Once the wait deadline expires or an offer has
been received, the OTA phase is closed. Late OTA replies received during
watering or other operation are ignored and logged as
`APP_DEBUG_EVENT_OTA_LATE_OFFER_IGNORED`; they must not alter the current wake
cycle.

While the OTA phase is open, the device republishes `ota/request` with bounded
backoff inside the same wake window. The default is three request attempts
within `APP_OTA_OFFER_WAIT_MS`. This creates multiple reply opportunities
without scheduling extra wakes or keeping the device awake beyond the OTA wait
deadline.

## 8. OTA Request Payload

The device publishes this after runtime config handling and before watering evaluation.

Topic:

```text
/<device_id>/kinds/ota/request
```

Payload:

```json
{
  "request": "firmware_update",
  "schema_version": 1,
  "device_kind": "WTR",
  "firmware_version": "1.0.0",
  "firmware_build_id": "2026-07-01T00:00:00Z+abcdef0",
  "running_partition": "app0",
  "free_heap": 123456
}
```

Fields:

| Field | Required | Type | Description |
|---|---:|---|---|
| `request` | Yes | string | Must be `firmware_update` |
| `schema_version` | Yes | integer | OTA protocol version. Current value: `1` |
| `device_kind` | Yes | string | Three-letter device kind. Watering device uses `WTR` |
| `firmware_version` | Yes | string | Current firmware version |
| `firmware_build_id` | No | string | Current firmware build identifier |
| `running_partition` | No | string | Current OTA slot name if available |
| `free_heap` | No | integer | Diagnostic value |

## 9. OTA Reply / Push Payload

No update:

```json
{
  "schema_version": 1,
  "action": "none"
}
```

Update offer:

```json
{
  "schema_version": 1,
  "action": "update",
  "device_kind": "WTR",
  "update_id": "watering-device-1.1.0-abcdef0",
  "version": "1.1.0",
  "build_id": "2026-07-01T03:00:00Z+abcdef0",
  "url": "http://<hubのドメイン名またはIPアドレス>:39151/firmware/WTR/1.1.0/firmware.bin",
  "size": 892704,
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "min_version": "1.0.0",
  "allow_downgrade": false,
  "force": false
}
```

Required fields for `action: "update"`:

| Field | Required | Type | Description |
|---|---:|---|---|
| `schema_version` | Yes | integer | Must be `1` |
| `action` | Yes | string | `update` or `none` |
| `device_kind` | Yes | string | Must match the requesting device kind |
| `update_id` | Yes | string | Unique release/update identifier |
| `version` | Yes | string | Target firmware version |
| `url` | Yes | string | HTTP URL for `firmware.bin`. Current device firmware accepts `http://` only. HTTPS requires adding certificate validation before enabling on-device. |
| `size` | Yes | integer | Exact binary size in bytes |
| `sha256` | Yes | string | Lowercase 64-character hex SHA-256 digest |
| `min_version` | No | string | Minimum current version allowed for this update |
| `allow_downgrade` | No | boolean | Default `false` |
| `force` | No | boolean | Server wants update even if normal rollout gates would skip |

### Update Availability Decision

The device does not decide whether an update is available. It reports its current firmware metadata in `ota/request`; the Hub or management server compares that metadata with the desired state for the device and replies with `action: "update"` or `action: "none"`.

Recommended server-side decision inputs:

| Input | Description |
|---|---|
| `device_id` | Device identity from the MQTT topic |
| `device_kind` | Three-letter kind reported by the device, such as `WTR` |
| `firmware_version` | Current version reported by the device |
| `firmware_build_id` | Current build identifier reported by the device |
| `device_state` | Device lifecycle state such as `active`, `pending`, `disabled`, or `retired` |
| `target_firmware_version` | Desired firmware version assigned to the device |
| `artifact` | Registered firmware artifact for the `device_kind` and target version |
| `rollout_state` | Release state such as `active`, `paused`, or `revoked` |
| `ota_attempt_count` | Retry counter for this update/device |

Recommended decision rules:

- Return `action: "none"` when the device is not `active`.
- Return `action: "none"` when `device_kind` is invalid or does not match the device record.
- Return `action: "none"` when no `target_firmware_version` is assigned.
- Return `action: "none"` when the reported `firmware_version` already equals `target_firmware_version`.
- Return `action: "none"` when no artifact exists for the tuple of `device_kind` and `target_firmware_version`.
- Return `action: "none"` when the target artifact is missing `url`, `size`, or `sha256`.
- Return `action: "none"` when the target artifact `device_kind` differs from the request `device_kind`.
- Return `action: "none"` when rollout is `paused` or the artifact is `revoked`.
- Return `action: "none"` when the target version is older than the current version unless `allow_downgrade` is explicitly enabled.
- Return `action: "update"` only when the target artifact is valid and rollout policy allows this device to receive it.

Pseudocode:

```text
if device.state != "active":
  return {"schema_version": 1, "action": "none"}

if request.device_kind is invalid or request.device_kind != device.device_kind:
  return {"schema_version": 1, "action": "none"}

target = device.target_firmware_version
if target is empty or request.firmware_version == target:
  return {"schema_version": 1, "action": "none"}

artifact = firmware_artifact(request.device_kind, target)
if artifact missing or artifact.revoked or rollout.paused:
  return {"schema_version": 1, "action": "none"}

return update_offer(device, artifact)
```

Payload size should stay below 512 bytes to match the current MQTT receive guard. Keep URLs short.

## 10. Device Update Algorithm

Recommended wake-cycle order:

1. Mount LittleFS and load saved config.
2. Connect Wi-Fi and MQTT.
3. Request and apply runtime config.
4. Request OTA offer.
5. If no valid OTA offer is received within the OTA wait timeout, continue normal watering flow.
6. If an OTA offer is valid and eligible, publish `ota/status` with `state: "started"`.
7. Download `firmware.bin` over HTTP.
8. Verify `Content-Length` matches `size` when provided.
9. Stream the binary into the inactive OTA partition.
10. Compute SHA-256 while streaming and compare with `sha256`.
11. If verification fails, abort update, publish `state: "failed"`, and continue normal flow unless `force` requires retry-only behavior.
12. If verification succeeds, set the next boot partition, persist pending OTA metadata, publish `state: "rebooting"`, flush MQTT, and restart.
13. On next boot, publish normal status with the new firmware version and an OTA result status.
14. When normal flow continues to deep sleep, set the sleep duration to the earlier of the next watering schedule and `ota_check_interval_sec`.

Timeout defaults:

| Setting | Recommended default |
|---|---:|
| OTA offer wait | 3 seconds |
| HTTP connect timeout | 10 seconds |
| HTTP read timeout | 30 seconds |
| Whole OTA operation timeout | 180 seconds |
| OTA check interval cap | 21,600 seconds |

If OTA starts, watering is skipped in that cycle. This avoids running actuators while flash is being rewritten or immediately before a reboot.

## 11. OTA Status Payload

Topic:

```text
/<device_id>/kinds/ota/status
```

Payload examples:

```json
{
  "schema_version": 1,
  "device_kind": "WTR",
  "update_id": "watering-device-1.1.0-abcdef0",
  "state": "started",
  "from_version": "1.0.0",
  "to_version": "1.1.0"
}
```

```json
{
  "schema_version": 1,
  "device_kind": "WTR",
  "update_id": "watering-device-1.1.0-abcdef0",
  "state": "failed",
  "error": "sha256_mismatch",
  "detail": "downloaded digest did not match offer"
}
```

Allowed states:

| State | Meaning |
|---|---|
| `offered` | A syntactically valid offer was received |
| `skipped` | Offer was ignored because it was not eligible |
| `started` | Device started OTA update |
| `downloading` | HTTP download is in progress |
| `written` | New image was written to inactive partition |
| `rebooting` | Device will reboot into the new image |
| `booted` | Device booted after a pending OTA update |
| `confirmed` | New firmware passed startup self-check |
| `failed` | OTA update failed and old firmware continues |

The device must publish a `failed` OTA status before deep sleep when the OTA
control exchange itself fails. This makes the difference between “no offer
arrived” and “download/write failed” visible in remote logs.

Recommended error codes:

| Error | Meaning |
|---|---|
| `request_publish_failed` | Device could not publish `ota/request` |
| `offer_timeout_<wait_ms>ms` | Device published `ota/request` but did not receive `ota/reply` or `ota/push` before the wait deadline |
| `invalid_payload` | JSON or required fields invalid |
| `unsupported_schema` | `schema_version` not supported |
| `device_kind_mismatch` | Offer device kind did not match this firmware |
| `downgrade_rejected` | Offer target version is older than current |
| `already_running` | Target version/update_id already installed |
| `url_rejected` | URL scheme or host is not allowed |
| `size_too_large` | Firmware does not fit the inactive slot |
| `http_connect_failed` | Could not connect to firmware URL |
| `http_status_invalid` | HTTP status was not `200` |
| `download_timeout` | HTTP read timed out |
| `content_length_mismatch` | Downloaded length did not match `size` |
| `flash_write_failed` | OTA partition write failed |
| `sha256_mismatch` | Digest check failed |
| `set_boot_partition_failed` | Boot partition switch failed |

## 12. Server Requirements

The Hub or management server must provide:

- Per-device firmware target version storage
- Firmware artifact storage under `WORK_DIR/firmware/<device_kind>/<version>/firmware.bin`
- HTTP endpoint `GET /firmware/<device_kind>/<version>/firmware.bin`
- OTA offer URL generation from `FIRMWARE_HOSTNAME` or OS hostname and `FIRMWARE_PORT`, for example `http://<hubのドメイン名またはIPアドレス>:39151`
- Optional `FIRMWARE_BASE_URL` override when the full base URL must be fixed explicitly
- SHA-256 digest generation and validation before publishing an offer
- OTA request handling and reply publishing
- OTA status storage and monitoring
- Audit log for who assigned an update to which device

Recommended device record fields:

| Field | Description |
|---|---|
| `device_kind` | Three-letter device kind such as `WTR` |
| `firmware_version` | Last reported firmware version |
| `firmware_build_id` | Last reported build ID |
| `target_firmware_version` | Desired version for this device |
| `ota_update_id` | Current pending or latest update ID |
| `ota_state` | Last OTA status state |
| `ota_error` | Last OTA error code |
| `ota_attempt_count` | Retry counter |
| `ota_last_attempt_at` | Last OTA attempt time |
| `ota_confirmed_at` | Time when updated firmware was confirmed |

HTTP firmware endpoint requirements:

| Item | Requirement |
|---|---|
| Method | `GET` |
| Status | `200` for valid artifact |
| Content-Type | `application/octet-stream` |
| Content-Length | Exact firmware size |
| Cache | Immutable versioned paths preferred |
| Lifetime | URL must stay valid for at least one device wake cycle plus retry margin |

## 13. Rollout Policy

Recommended rollout states:

| State | Description |
|---|---|
| `active` | Eligible active devices with the target version assigned receive the offer |
| `paused` | No new offers; existing pending updates may be cancelled |
| `revoked` | Artifact must not be offered anymore |

Server-side safeguards:

- Do not offer OTA to `pending`, `disabled`, or `retired` devices by default.
- Limit retry frequency after `failed`.
- Stop rollout when failure rate exceeds the configured threshold.
- Keep old firmware artifact available until the new version is confirmed stable.
- Never reuse an `update_id` for a different binary.

## 14. Security Requirements

Minimum:

- MQTT broker authentication must be enabled for production.
- OTA offer must include SHA-256.
- Device must verify SHA-256 before booting the new image.
- Device must reject unsupported URL schemes.
- Device should allow only configured Hub hosts or the MQTT broker host for firmware download.
- Server must reject unknown or disabled devices.
- Server must keep an audit log of firmware assignment and publish actions.

Recommended:

- Use HTTPS where certificate validation is practical.
- Use per-device MQTT credentials.
- Add detached signature verification in a later phase.
- Add monotonic build number or signed manifest to strengthen downgrade protection.

HTTP without TLS is acceptable only on a trusted local network and only with mandatory SHA-256 verification. It protects integrity against accidental corruption, but not against an attacker who can modify both payload and MQTT offer.

## 15. Build and Release Workflow

Build firmware:

```bash
cd client-devices/watering-device
make build
```

Artifact for OTA:

```text
.pio/build/seeed_xiao_esp32s3/firmware.bin
```

Do not use `flash_merged.bin` for OTA. The merged image contains bootloader, partition table, app, and filesystem and is only for provisioning or lab reflashing.

Generate digest:

```bash
sha256sum .pio/build/seeed_xiao_esp32s3/firmware.bin
```

Release checklist:

1. Set `APP_DEVICE_KIND`, `APP_FIRMWARE_VERSION`, and `APP_FIRMWARE_BUILD_ID`.
2. Run `make build`.
3. Confirm `firmware.bin` size is smaller than the OTA app slot.
4. Upload `firmware.bin` with the Hub upload/register API so size and SHA-256 are calculated by the Hub.
5. Confirm the registered artifact URL is `http://<hubのドメイン名またはIPアドレス>:39151/firmware/WTR/1.1.0/firmware.bin` or the equivalent resolved firmware base URL.
6. Confirm artifact metadata includes `device_kind: "WTR"`.
7. Assign `target_firmware_version` to selected active devices.
8. Monitor `ota/status` and normal status after reboot.
9. Expand rollout.

## 16. Test Plan

Hardware tests:

- Provisioning image boots with the OTA partition layout.
- Successful OTA from `app0` to `app1`.
- Successful OTA from `app1` to `app0`.
- Offer with `action: "none"` continues normal watering flow.
- Invalid JSON offer is rejected.
- SHA-256 mismatch fails without switching firmware.
- Oversized `size` fails before download.
- HTTP 404 fails and reports `http_status_invalid`.
- Power loss during download boots the old firmware.
- Power loss after partition write but before boot switch boots the old firmware.
- New firmware reports its version after reboot.
- OTA-started cycle does not run watering.

Server tests:

- Unknown device is not offered production firmware.
- Disabled device is not offered firmware.
- `firmware.bin` digest in metadata matches the stored artifact.
- Retry backoff prevents repeated update loops.
- Rollout can be paused without publishing new offers.

## 17. Compatibility Notes

- Current firmware rejects MQTT payloads of 512 bytes or more. OTA control payloads must remain below this limit unless the receive guard is changed.
- Firmware metadata is included in normal status, OTA request, and OTA status payloads.
- Current `Makefile` uses a fixed LittleFS offset. OTA-capable provisioning must write LittleFS at `0x670000`.
- OTA-capable partition layout is a prerequisite because app OTA does not rewrite the partition table.
- Current Hub validation requires `device_kind` to be exactly three uppercase letters, keeps `version` under 32 characters, `update_id` and `build_id` under 64 characters, and artifact `url` under 256 characters so OTA offers fit the device receive limit.
