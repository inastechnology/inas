# OTA Implementation Traceability

この文書は、[ota_update_spec.md](ota_update_spec.md)の仕様項目がどのレイヤ・ファイルで実装されているかを追跡するための対応表です。

## Layer Structure

| Layer | Responsibility | Files |
|---|---|---|
| Common lifecycle | 起動、AP mode設定、network/reconnect、runtime config request、OTA、time sync、debug log、deep sleep | `../common/lib/ina-client-common/src/app/inc/app_device.h`, `../common/lib/ina-client-common/src/app/src/app_device.cpp` |
| Device orchestration | `AppDevice`具象実装、灌水判定、OTA後の灌水skip、通常status publish | `src/app/src/app.cpp` |
| Device adapter | common transportからdevice固有runtime config処理への橋渡し | `src/app/src/app.cpp`, `../common/lib/ina-client-common/src/app/inc/app_device_adapter.h` |
| Common OTA app | device kind検証、retained offer検証、OTA status payload、HTTP download、SHA-256検証、inactive slot書き込み、再起動後confirm | `../common/lib/ina-client-common/src/app/inc/app_ota.h`, `../common/lib/ina-client-common/src/app/src/app_ota.cpp` |
| Common MQTT transport | topic routing、retained OTA offer wait、status topic mapping | `../common/lib/ina-client-common/src/app/inc/app_network.h`, `../common/lib/ina-client-common/src/app/src/app_network.cpp` |
| Device build/platform | OTA partition layout、merged image offsets、firmware version macros/device kind macro | `partitions.csv`, `Makefile`, `platformio.ini`, `../common/lib/ina-client-common/src/app/inc/app_def.h` |
| Hub MQTT parsing | `/<device_id>/kinds/<kind>/<mode>` parsing and handler dispatch | `hub/src/ina_device_hub/hub_mqtt_client.py` |
| Hub OTA decision | device kind compatibility、artifact validation、target comparison、`update`/`none` offer、OTA status handling | `hub/src/ina_device_hub/ota_update_service.py` |
| Hub device state | device kind、firmware metadata、target firmware、OTA state/history persistence | `hub/src/ina_device_hub/device_config_repository.py` |
| Hub integration/API | MQTT subscribe/handler registration、artifact/target/status local APIs | `hub/src/ina_device_hub/serve.py`, `hub/src/ina_device_hub/web_server.py` |

## Specification Mapping

| Spec section | Requirement | Implementation | Verification |
|---|---|---|---|
| 2. Key Decisions | Firmware body is downloaded over HTTP; MQTT only carries request/offer/status | common `app_ota.cpp` uses `HTTPClient`; common `app_network.cpp` handles `ota/*` control topics only | `make build`; `make merged-bin` |
| 2. Key Decisions | Hub decides update availability | `OTAUpdateService.decide_offer()` compares device state, `target_firmware_version`, current firmware, artifact, and rollout state | `hub/tests/test_ota_update_service.py` |
| 2. Key Decisions | OTA runs after runtime config and before watering | `app.cpp` requests runtime config first, then waits for retained OTA offer before NTP/schedule watering decision | `make build` |
| 2. Key Decisions | Deep sleep duration is capped for periodic OTA checks | `app_runtime_config_t.ota_check_interval_sec`; `WateringDevice::run_device_cycle()` uses the earlier of next watering schedule and OTA check interval | `make build` |
| 2. Key Decisions | Common transport does not depend on device runtime config headers | common `app_network.cpp` calls `AppDeviceAdapter`; `AppDevice::initialize()` registers watering-device `WateringDevice` | `make build` |
| 2. Key Decisions | Watering is skipped when OTA starts | `app_ota_handle_offer()` returns attempted state; `app.cpp` skips watering when `ota_update_attempted` is true | `make build` |
| 2. Key Decisions | SHA-256 is mandatory | `app_ota_download_and_install()` computes SHA-256 while downloading and rejects mismatches | `make build` |
| 3. Required Partition Layout | `otadata`, `app0`, `app1`, `storage`, `coredump` layout | `partitions.csv` | `make build`; `make merged-bin` |
| 4. Provisioning Image Layout | Full image offsets use `0xe000` for `boot_app0.bin` and `0x670000` for LittleFS | `Makefile` `merged-bin` target | `make merged-bin` |
| 5. Firmware Versioning | Device reports `firmware_version` and `firmware_build_id` | common `app_def.h`, device `app.cpp`, common `app_ota.cpp` | Hub tests record firmware metadata from status |
| 6. Device Kind | Watering device uses `WTR`; Hub offers only matching artifacts; device rejects mismatched offers | `platformio.ini` `APP_DEVICE_KIND`, common `app_ota_apply_offer_json()`, `OTAUpdateService.decide_offer()` | `test_artifact_for_other_device_kind_is_not_offered`; `make build` |
| 7. MQTT Topics | Device processes only retained `ota/offer` | common `app_network_sub_callback()` checks exact retained offer topic and routes OTA offers to `app_ota_apply_offer_json()` | `make build` |
| 8. OTA Offer Payload | Hub publishes retained `action=update` with device kind, update id, version, URL, size, sha256 or clears retained offer when no update is needed | `OTAUpdateService.decide_offer()` and `publish_retained_offer()` | `test_set_firmware_target_publishes_retained_offer_without_device_request`, `test_attach_mqtt_client_syncs_existing_retained_offers` |
| 9. Update Availability Decision | Do not offer to non-active devices; skip mismatched-kind, missing/paused/revoked artifacts and already-target devices | `OTAUpdateService.decide_offer()` | `test_pending_device_does_not_receive_update_offer`, `test_paused_artifact_returns_none_offer`, `test_artifact_for_other_device_kind_is_not_offered` |
| 10. Device Update Algorithm | Validate offer, download, write inactive partition, set boot partition, restart | common `app_ota_handle_offer()` and `app_ota_download_and_install()` | `make build`; device-in-loop test still required |
| 11. OTA Status | Publish `offered`, `started`, `downloading`, `written`, `rebooting`, `booted`, `confirmed`, `failed` states with `device_kind` | common `app_ota_publish_status()` and `app_ota_publish_pending_boot_status()` | `make build`; Hub status persistence test |
| 12. Server Requirements | Store device kind, firmware metadata, target, OTA state, attempts, status history | `DeviceConfigRepository` OTA fields and methods | `test_ota_status_updates_device_record` |
| 12. Server Requirements | Provide APIs for artifact registration and target assignment | `web_server.py` local APIs for firmware artifacts and firmware target | API smoke test still required |
| 13. Rollout Policy | Artifact state gates offers | `rollout_state` accepts `active`, `paused`, `revoked`; paused/revoked return `none` | `test_paused_artifact_returns_none_offer` |
| 16. Test Plan | Build, filesystem, merged image, Hub decision tests | Commands listed below | Completed locally |

## Verification Record

| Command | Result |
|---|---|
| `make build` in `client-devices/watering-device/` | Passed. Program used: 894,789 bytes; `firmware.bin`: 895,216 bytes; app slot: 3,342,336 bytes. |
| `make buildfs` in `client-devices/watering-device/` | Passed. LittleFS image: 1,572,864 bytes. |
| `make merged-bin` in `client-devices/watering-device/` | Passed. `littlefs.bin` merged at `0x670000`. |
| `PYTHONPATH=src python -m unittest discover -s tests` in `hub/` | Passed. 28 tests. |

## Current Constraints

- Device-side download currently accepts `http://` URLs only. HTTPS requires certificate trust handling before enabling.
- OTA covers firmware image only. Bootloader, partition table, and LittleFS OTA remain out of scope.
- Device-in-loop testing is still required for actual reboot/boot-confirm behavior on hardware.
