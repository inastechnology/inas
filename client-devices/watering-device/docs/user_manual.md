# INA Water Controller User Manual

Japanese version:

- [jp/user_manual.md](jp/user_manual.md)

This manual explains setup and operation for the INA Water Controller firmware.

## Overview

The INA Water Controller connects to Wi-Fi and MQTT, receives runtime
configuration from the hub, synchronizes time with NTP, measures soil moisture,
optionally reads RS485 environmental sensors, runs irrigation schedules, and
then returns to deep sleep.

Main features:

- Wi-Fi and MQTT setup portal.
- Runtime config request/reply/push over MQTT.
- NTP time synchronization.
- Soil moisture based irrigation gating.
- Optional RS485 Modbus measurements on each wake.
- MOSFET-switched 12V sensor power for RS485 sensors.
- Status and compact debug log publishing.
- OTA firmware update support.
- BOOT button setup portal entry.

## First Setup

Prepare:

- INA Water Controller hardware.
- Power supply.
- Wi-Fi SSID and password.
- MQTT broker host and port.
- MQTT credentials if authentication is enabled.
- Smartphone or PC.

If Wi-Fi/MQTT settings are missing, the device starts setup AP mode. Connect to
the setup AP and open:

```text
http://192.168.4.1/
```

Enter Wi-Fi and MQTT values, then press `Save and Restart`.

## Normal Wake Cycle

1. Load saved setup and runtime config.
2. Connect to Wi-Fi.
3. Connect to MQTT.
4. Request runtime config.
5. Synchronize time with NTP.
6. Measure soil moisture.
7. If RS485 sensors are enabled, turn on the 12V sensor branch, wait for settle
   time, read sensors, and turn the branch off.
8. Evaluate irrigation schedules.
9. Run irrigation only when schedule and soil moisture rules allow it.
10. Publish status and optional debug log.
11. Sleep until the next wake.

If network connection fails but a valid saved runtime config and usable wake
time are available, the device can continue schedule evaluation from saved
config. If time is not reliable after cold boot, the device retries network
recovery instead of irrigating.

## Runtime Config Topics

`startup_watering_test` is only for supervised installation testing. Set `duration_sec` from 1 to 30 and `channel_mask` to 1, 2, or 3. After a power-on or reset, the device retrieves fresh MQTT configuration and completes its OTA check before running the selected output once. It never runs from saved configuration, during an OTA attempt, or after a normal deep-sleep timer wake. Disable the mode immediately after confirming the wiring and water path.

Request topic:

```text
/<device_id>/kinds/config/request
```

Reply topic:

```text
/<device_id>/kinds/config/reply
```

Push topic:

```text
/<device_id>/kinds/config/push
```

`<device_id>` is the `INADS-...` id shown in serial logs.

## Key Runtime Config Fields

| Field | Required | Purpose |
|---|---|---|
| `ntp_server` | No | NTP server. Defaults to MQTT broker address when omitted |
| `timezone_offset_sec` | No | Local timezone offset seconds |
| `moisture_threshold` | No | Irrigate only when soil moisture is below this value |
| `force_watering` | No | Irrigate on schedule regardless of soil moisture |
| `startup_watering_test` | No | On a supervised cold boot, run the selected irrigation output once for 1–30 seconds; never runs on deep-sleep wake |
| `debug_log_on_wake` | No | Publish compact debug log at the end of the wake cycle |
| `ota_check_interval_sec` | No | Maximum deep sleep interval for OTA checks |
| `env_sensors.par.enabled` | No | Enable RS485 light/PAR sensor |
| `env_sensors.soil.enabled` | No | Enable RS485 soil EC/pH/NPK sensor |
| `env_sensors.power_settle_ms` | No | Wait time after enabling 12V sensor power |
| `env_calibration` | No | Scale/offset calibration for RS485 environmental values |
| `mosfet_switches` | No | Hub-managed names, terminals, controlled loads, and channel masks for MOSFET-switched outputs |
| `schedules` | Yes | Irrigation schedules |

Valid runtime config must include at least one valid schedule. The payload should
stay below 4096 bytes.

## Status

The device publishes status to MQTT after each wake when network is available.
Important fields include:

- `network_connected`
- `runtime_config_valid`
- `config_received`
- `time_synced`
- `watering_due`
- `watering_started`
- `last_soil_moisture`
- `sensor_12v_power_requested`
- `sensor_12v_power_configured`
- `sensor_12v_power_error`
- `par_ok`
- `soil_rs485_ok`
- `par_umol_m2_s`
- `soil_moisture_percent`
- `soil_temperature_c`
- `soil_ec_us_cm`
- `soil_ph`
- `soil_n_mg_kg`
- `soil_p_mg_kg`
- `soil_k_mg_kg`

## Debug Log

When `debug_log_on_wake: true`, the device publishes a compact binary debug log
at the end of the wake cycle. See [debug_log_format.md](debug_log_format.md).

## Setup Portal Button

Press BOOT during the setup portal arm window after firmware boot. A normal hold
starts setup AP while keeping existing credentials. A longer reset hold clears
Wi-Fi/MQTT connection settings while preserving the device id.

Do not hold BOOT while releasing hardware reset; that can enter the ROM
bootloader.

## Troubleshooting

- Setup AP not visible: restart the device, check whether saved Wi-Fi is already
  working, or use BOOT to force setup AP.
- Setup page unreachable: connect to the setup AP and open
  `http://192.168.4.1/` directly. Disable VPN or mobile data if needed.
- MQTT config not applied: verify device id in topic, reply/push topic name,
  payload size, valid schedules, and reply timing after wake.
- No irrigation: check schedule time, timezone, duration, channel mask, soil
  moisture threshold, and `watering_due` / `watering_started` status.
- BOOT does not open setup AP: press BOOT after firmware starts and within the
  arm window. RESET alone does not enter setup AP.

## Operational Notes

- The setup AP password must be at least 8 characters.
- The MQTT broker must be reachable from the device network.
- Use a local NTP server when the field network has no internet access.
- Wi-Fi/MQTT setup is stored on the device, not in `.env.user.ini`.
