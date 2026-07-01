# inas sensor sense

A simple sensor device that can be used to measure temperature, tds, and more. This device is based on the INAS sensor and the ESP32 microcontroller.

## Features

- Measure voltage
- Measure temperature
- Measure TDS (Total Dissolved Solids)

## Hardware

- ESP32S3 Sense

## Setup

1. Clone this repository
2. copy default.env.user.ini to .env.user.ini
   And change `APP_INITIAL_SETTING_SSID` to match the setup AP name you want.
3. And you can use Makefile to build and upload the firmware

```bash
make build
make upload
```

To create a single flashable image for another PC, use:

```bash
make merged-bin
```

This creates `.pio/build/seeed_xiao_esp32s3/flash_merged.bin`, which can be
written to the device at offset `0x0`. To flash it directly from the current
machine:

```bash
make flash-merged UPLOAD_PORT=/dev/ttyACM0
```

See more details in the [Makefile](Makefile) or `make help` command. 

User-facing setup and operation instructions are available in
[docs/user_manual.md](docs/user_manual.md).

MQTT server integration requirements are available in
[docs/mqtt_server_spec.md](docs/mqtt_server_spec.md).
Compact debug log format details are available in
[docs/debug_log_format.md](docs/debug_log_format.md).
OTA firmware update requirements are available in
[docs/ota_update_spec.md](docs/ota_update_spec.md).
Implementation traceability is available in
[docs/ota_implementation_traceability.md](docs/ota_implementation_traceability.md).

## Initial setup AP

Wi-Fi and MQTT connection settings are stored in LittleFS at `/.config`.
On first boot, or when saved Wi-Fi/MQTT settings are missing, the firmware
starts the setup AP instead of trying build-time STA credentials.

If the device cannot connect to Wi-Fi within `APP_WIFI_CONNECT_TIMEOUT_MS` and
no saved runtime configuration is available, it starts a setup access point:

```text
SSID: APP_INITIAL_SETTING_SSID
PASS: APP_INITIAL_SETTING_PASS
URL:  http://192.168.4.1/
```

The setup page accepts Wi-Fi SSID/password, MQTT broker/port, and optional MQTT
username/password. Saving the form writes `/.config` and restarts the device.
When a saved runtime configuration is available, Wi-Fi or MQTT failure does not
immediately force the setup AP. The device continues with the saved schedule and
existing RTC time only when waking from deep sleep, then sleeps until the next
schedule. After power loss or a cold boot, the device does not trust RTC time
for offline watering. If no saved runtime configuration is available, the setup
AP starts; in that case it automatically restarts after
`APP_SETUP_PORTAL_RECOVERY_TIMEOUT_MS` of idle time with no AP clients so a
remote device can retry normal operation. The timeout is paused while a phone or
PC is connected to the setup AP. The setup AP stays up indefinitely when
settings are missing or when it was explicitly requested with the BOOT button.

To change saved settings later, force the setup AP from the BOOT button. Press
BOOT within `APP_SETUP_PORTAL_ARM_WINDOW_MS` milliseconds after firmware startup
and keep holding it for `APP_SETUP_PORTAL_HOLD_MS` milliseconds. To clear saved
Wi-Fi/MQTT connection settings first, keep holding BOOT until
`APP_SETUP_PORTAL_RESET_HOLD_MS`. On XIAO ESP32S3 the default button pin is
GPIO0 (`APP_SETUP_PORTAL_BUTTON_PIN=0`). The RESET button is a hardware reset
line and is not readable as a firmware GPIO. Holding BOOT before releasing
hardware reset can enter the ROM bootloader, so start the press after the
firmware begins booting. The existing settings are kept and shown on the setup
form for normal setup AP entry; reset entry blanks the Wi-Fi/MQTT fields while
keeping the device ID. The status LED blinks quickly while the BOOT hold is
being accepted, then blinks slowly while the setup AP is active.

## Demo

Soon...

<!-- ![Demo](demo.gif) -->

## MQTT runtime configuration

The firmware now requests runtime configuration from MQTT after each wake-up,
syncs time with the configured NTP server, saves valid runtime configuration to
LittleFS, runs watering only for due schedules, and then goes back to deep sleep
until the next schedule. If Wi-Fi or MQTT is unavailable on a later wake cycle,
the saved runtime configuration is used only when the device woke from deep
sleep and the RTC time is still synchronized.

Request topic:

```text
/<device_id>/kinds/config/request
```

Response topic:

```text
/<device_id>/kinds/config/reply
```

Push update topic:

```text
/<device_id>/kinds/config/push
```

Payload example:

```json
{
  "ntp_server": "my_device.local",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 35,
  "force_watering": false,
  "debug_log_on_wake": false,
  "schedules": [
    {
      "hour": 6,
      "minute": 30,
      "duration_sec": 20,
      "channel_mask": 1
    },
    {
      "hour": 18,
      "minute": 0,
      "duration_sec": 30,
      "channel_mask": 1
    }
  ]
}
```

Notes:

- `ntp_server` should point to the NTP server running on the same PC as MQTT.
- `channel_mask` uses valve-channel bit flags. `1` means valve ch0. The pump output is enabled automatically whenever at least one valve channel is selected.
- Current firmware maps valve ch0 to `VALVE_PIN` and drives `PUMP_PIN` automatically in [`app_watering.cpp`](src/app/src/app_watering.cpp).
- Up to 8 schedules are accepted.
- Set `force_watering` to `true` to water on due schedules even when the soil sensor reports enough moisture.
- Set `debug_log_on_wake` to `true` to publish one compact binary debug log payload for each wake cycle to `/DEVICE_ID/kinds/debug/log`.
  See [docs/debug_log_format.md](docs/debug_log_format.md) for the binary format.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
