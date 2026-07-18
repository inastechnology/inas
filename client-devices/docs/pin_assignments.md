# XIAO ESP32S3 Pin Assignments

This document summarizes the XIAO ESP32S3 pin assignments used by INAS client
devices.

Japanese version:

- [jp/pin_assignments.md](jp/pin_assignments.md)

Manufacturing-facing wiring tables:

- [esp32s3_wiring_tables.md](esp32s3_wiring_tables.md)

Related procedures:

- [manufacturing_procedure.md](manufacturing_procedure.md)
- [wiring_procedure.md](wiring_procedure.md)
- [installation_procedure.md](installation_procedure.md)
- [operation_guide.md](operation_guide.md)

draw.io source:

- [xiao_esp32s3_pin_assignments.drawio](xiao_esp32s3_pin_assignments.drawio)

SVG previews:

- [WTR](xiao_esp32s3_pin_assignment_wtr.svg)
- [ENV](xiao_esp32s3_pin_assignment_env.svg)
- [SOI](xiao_esp32s3_pin_assignment_soi.svg)

Update command:

```sh
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

The highlight frames are aligned with the pin-name labels inside the source
board image. Do not edit the generated SVG or draw.io files directly. Update
`TOP_RECTS` / `BACK_RECTS` in
[generate_xiao_pin_assignment_diagrams.py](generate_xiao_pin_assignment_diagrams.py)
and regenerate.

## WTR

All-in-one watering device. WTR handles irrigation control, soil moisture ADC,
RS485 sensors, and a MOSFET-switched sensor power branch. Hardware profiles may
change supply voltage or load rating, but they keep the same WTR pin contract.

![WTR pin assignment](xiao_esp32s3_pin_assignment_wtr.svg)

| Purpose | XIAO pin | GPIO | Notes |
|---|---|---:|---|
| Valve MOSFET | `D2` | `GPIO3` | Irrigation line 1 |
| Pump MOSFET | `D3` | `GPIO4` | Automatically turns on while a valve line is on |
| Soil moisture ADC | `A5` / `D5` | `GPIO6` | Avoids the old `A2/D2` conflict |
| RS485 DE/RE | `D4` | `GPIO5` | Transmit/receive direction control |
| RS485 TX | `D6` | `GPIO43` | UART1 TX |
| RS485 RX | `D7` | `GPIO44` | UART1 RX |
| 12V sensor power MOSFET | `D8` | `GPIO7` | Switches only the 12V branch going to RS485 sensors |
| 5V input | `VBUS` | - | Input after 12V -> 5V DC/DC conversion |
| GND | `GND` | - | Common ground for 12V system, RS485, and ESP32S3 |
| Setup AP | `BOOT` | `GPIO0` | Active-low |

Do not place ESP32S3 board power behind the `D8` switch. `D8` switches only the
12V branch feeding external RS485 sensors.

For a low-voltage WTR hardware profile, keep `A5/D5` for analog soil moisture
and keep `D2`/`D3` as WTR irrigation outputs. Do not move the sensor to `A0` or
create another device kind only for voltage or MOSFET rating differences.

## ENV

12V RS485 Modbus sensor hub. ENV connects PAR, EC/pH/NPK, and similar RS485
sensors on the same bus.

![ENV pin assignment](xiao_esp32s3_pin_assignment_env.svg)

| Purpose | XIAO pin | GPIO | Notes |
|---|---|---:|---|
| RS485 DE/RE | `D4` | `GPIO5` | Transmit/receive direction control |
| RS485 TX | `D6` | `GPIO43` | UART1 TX |
| RS485 RX | `D7` | `GPIO44` | UART1 RX |
| 5V input | `VBUS` | - | Input after 12V -> 5V DC/DC conversion |
| GND | `GND` | - | Common with RS485 ground |
| Setup AP | `BOOT` | `GPIO0` | Active-low |

## WRS

RS485-first all-in-one watering device. WRS reuses the WTR irrigation and RS485
pin assignment, but treats RS485 soil/PAR/irradiance sensors as the primary
feedback path. The WTR diagram applies to WRS except that the analog soil
moisture ADC can be unused or reserved for diagnostics.

Use the same RS485 bus for additional sensors. Missing or uninstalled sensors
are detected by Modbus timeout, CRC failure, or no response and reported as
`*_ok=false`; adding a sensor should not require a new XIAO pin assignment.

## FGT

FGT uses remapped I2C on `D0/D1` for an MCP23017, `D3` as the
hardware-pulled-down actuator master enable, `D5` as the inlet flow pulse,
`D4/D6/D7` for RS485, and `D8` for switched RS485 sensor power. `D2/GPIO3` is
reserved because it is a strapping pin. The five actuator selects and four
safety inputs are on the MCP23017. See the complete assignment and OFF-on-reset
wiring rules in
[fertigation-device/docs/hardware_and_power.md](../fertigation-device/docs/hardware_and_power.md).

## SOI

Battery-powered soil moisture node. SOI currently has no RS485 bus.

![SOI pin assignment](xiao_esp32s3_pin_assignment_soi.svg)

| Purpose | XIAO pin | GPIO | Notes |
|---|---|---:|---|
| Soil moisture ADC | `A0` / `D0` | `GPIO1` | `APP_SOI_MOISTURE_PIN=A0` |
| Sensor VCC | `3.3V-OUT` | - | Soil moisture sensor power |
| Sensor GND | `GND` | - | Sensor ground |
| Battery + | `BAT+` | - | 18650 battery + |
| Battery - | `BAT-` | - | 18650 battery - |
| Setup AP | `BOOT` | `GPIO0` | Active-low |

## Common

| Purpose | XIAO pin | GPIO | Notes |
|---|---|---:|---|
| Setup portal / reset entry | `BOOT` | `GPIO0` | Common firmware default |
| Status LED | `USER_LED` | `GPIO21` | Board LED |
