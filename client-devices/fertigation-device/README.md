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
- scan selected Modbus IDs at 2400, 4800, or 9600 bps;
- read holding or input registers; and
- change a sensor address with a read-before-write and read-after-write check.

Only one MOSFET output can be on. Every output is turned off automatically, and
a guard interval is enforced before another output can turn on. Modbus
operations are blocked while an actuator output is active.

Address changes are intentionally not a bulk operation. If two sensors already
have the same address, disconnect every sensor except the one being changed.
The firmware sends the address write only once and does not retry an ambiguous
write. Register `0x07D0` is offered as the default address register for the
currently verified ComWinTop CWT-SOIL and DFRobot SEN0641 devices; use the
connected sensor's verified manual for any other model.
