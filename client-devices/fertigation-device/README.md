# FGT Fertigation Device

Device kind: `FGT`

FGT is the liquid-fertilizer preparation and irrigation member of the WRS
family. It reuses the common network, MQTT, OTA, deep-sleep, RS485, and sensor
protocol layers, while owning a fail-safe batch state machine for water, A/B
concentrate, mixing, irrigation, and clean-water rinsing.

The farmer-facing product name is **液肥づくり・潅水装置**. `FGT`, GPIO names,
and electrical switch terminology are implementation details and belong only
in advanced diagnostics.

There is currently no fabricated, dedicated FGT controller PCB. The current
firmware and first bring-up use a directly wired XIAO ESP32-C6 with discrete
MOSFET switches and an RS485 transceiver. The authoritative current pin
contract is documented in
[`docs/jp/minimal_wiring.md`](docs/jp/minimal_wiring.md).

The KiCad files under `hardware/esp32c6-solar-controller` are an in-progress
future hardware design. That PCB does not currently exist and is not used by
the FGT firmware bring-up or operating procedure.

## Documents

- [日本語設計概要](docs/jp/README.md)
- [Requirements](docs/requirements.md)
- [Hardware and power](docs/hardware_and_power.md)
- [Runtime configuration and status contract](docs/mqtt_contract.md)
- [Implementation plan](docs/implementation_plan.md)
- [Verification plan](docs/verification_plan.md)

## Commands

```bash
cd client-devices/fertigation-device
make test
make build
make check-firmware
# After connecting the XIAO ESP32-C6:
make upload UPLOAD_PORT=/dev/ttyACM0
make monitor UPLOAD_PORT=/dev/ttyACM0
```

The first Make invocation copies `default.env.user.ini` to the ignored local
`.env.user.ini`. Edit that file if the setup AP name needs to change; Wi-Fi and
MQTT secrets are provisioned through the common setup flow and are not committed.

## AP commissioning

The setup portal includes an FGT commissioning page for initial wiring and
shipment checks. Press the XIAO ESP32-C6 BOOT button within three seconds after
reset, hold it for at least five seconds but less than ten seconds, connect to
the setup AP, and open `http://192.168.4.1/`. Select **FGT 出荷動作確認**.

The commissioning page can:

- pulse one of the five MOSFET outputs for a bounded duration;
- turn the switched 12 V sensor supply on or off;
- automatically power, scan, and identify the supported soil and PAR sensors;
- display measurements with product names and physical units;
- repeat a value acquisition test for each detected sensor; and
- register each detected sensor with a human-readable name and installation
  location;
- edit, disable, or remove registered sensors; and
- change a sensor address with a read-before-write and read-after-write check;
  and
- install an extracted FGT `firmware.bin` from the local setup AP.

Only one MOSFET output can be on. Every output is turned off automatically, and
a guard interval is enforced before another output can turn on. Modbus
operations are blocked while an actuator output is active.

Automatic detection checks IDs 1 through 10 at 2400, 4800, and 9600 bps. It
currently identifies **ComWinTop CWT-SOIL NPKPHCTH-S** and **DFRobot SEN0641
PAR**. A successful test requires a CRC-valid Modbus response. Soil moisture,
temperature, and pH also receive a basic protocol-range check. A PAR value of
zero remains valid because darkness can legitimately produce zero irradiance.
The firmware advances the scan one address at a time in the setup portal loop;
the HTTP callback only starts the operation and reports progress. This keeps
the captive portal responsive even when every address reaches the Modbus
response timeout.

### Local firmware update

Open **F/Wアップデート** from the commissioning page, select the extracted
`firmware.bin`, and press **更新を開始**. Do not upload the `.inasfw` bundle,
the release ZIP, a merged factory image, or firmware for another device.

Before flash writing starts, the firmware cancels sensor detection and turns
all five MOSFET outputs and the switched 12 V sensor supply off. Commissioning
operations remain blocked until restart. The uploaded image must have an ESP
application-image header and an embedded INAS manifest matching all of:

- `project=fertigation-device`
- `device_kind=FGT`
- `target=seeed_xiao_esp32c6`
- `framework=arduino`

The application image is streamed into the inactive OTA partition. It does not
write the LittleFS partition, so Wi-Fi/MQTT settings and the local RS485 device
registry remain in place. A rejected or interrupted upload leaves the current
boot partition selected. After a successful update, the device restarts
automatically.

Keep both USB and 12 V power stable for the entire update. The setup status LED
uses a 100 ms blink interval while writing, 50 ms after completion while
waiting to restart, and 1000 ms after a rejected or failed update. Normal setup
AP blinking is restored on the next portal start.

### Persistent RS485 device registry

Connect and register new sensors one at a time. A registration records the
sensor type, name, installation location, Modbus address, baud rate, function
code, start register, register count, and scale. Up to eight devices can be
stored. The registry rejects two devices with the same address at the same
baud rate.

The registry is stored separately from Hub-delivered Runtime Config in
LittleFS with a version, size, and CRC. Updates are written through a temporary
file and a backup so an interrupted write does not silently replace the last
valid registry. The same registry is loaded by both the setup AP and normal
operation.

Once a local registry has been saved, it is authoritative for physical RS485
topology. Normal operation powers and reads every enabled registered device,
switching UART baud rates as required, and includes a `rs485_devices` array in
the published status. The legacy Runtime Config `soil` and `par` fields remain
as a fallback only until the first local registry is saved. A deliberately
saved empty registry therefore disables RS485 sensor reads instead of
re-enabling compiled defaults.

Address changes are intentionally not a bulk operation. If two sensors already
have the same address, disconnect every sensor except the one being changed.
The firmware sends the address write only once and does not retry an ambiguous
write. The verified `0x07D0` address register is applied automatically and is
not exposed as a user setting. New devices default to “unregistered” during an
address change. Select an existing registry entry only when changing the
physical address of that exact registered sensor; its saved address is then
updated after read-back verification.
