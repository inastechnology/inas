# FGT Fertigation Device

Device kind: `FGT`

FGT is the liquid-fertilizer preparation and irrigation member of the WRS
family. It reuses the common network, MQTT, OTA, deep-sleep, RS485, and sensor
protocol layers, while owning a fail-safe batch state machine for water, A/B
concentrate, mixing, irrigation, and clean-water rinsing.

The farmer-facing product name is **液肥づくり・潅水装置**. `FGT`, GPIO names,
MCP23017 pins, and electrical switch terminology are implementation details and
belong only in advanced diagnostics.

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
# After connecting the XIAO ESP32-S3:
make upload UPLOAD_PORT=/dev/ttyACM0
make monitor UPLOAD_PORT=/dev/ttyACM0
```

The first Make invocation copies `default.env.user.ini` to the ignored local
`.env.user.ini`. Edit that file if the setup AP name needs to change; Wi-Fi and
MQTT secrets are provisioned through the common setup flow and are not committed.
