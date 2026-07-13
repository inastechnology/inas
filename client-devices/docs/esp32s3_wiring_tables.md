# ESP32S3 Wiring Tables

Japanese version:

- [jp/esp32s3_wiring_tables.md](jp/esp32s3_wiring_tables.md)

This document is the manufacturing-facing wiring table for INAS devices using
the Seeed XIAO ESP32S3. For board image previews, see
[pin_assignments.md](pin_assignments.md).

## Common Rules

- Keep ESP32S3 logic at 3.3V. Use a 3.3V-compatible RS485 transceiver such as
  MAX3485, SP3485, or SN65HVD-series parts.
- For 12V-powered devices, feed XIAO `VBUS` from a regulated 5V output. Do not
  feed 12V directly into the XIAO board.
- For battery-powered profiles, connect the protected cell to `BAT+` / `BAT-`
  and keep external sensor and output wiring within the documented profile.
- Tie ESP32S3 GND, RS485 transceiver GND, 12V sensor GND, pump/valve supply GND,
  and DC/DC converter GND together at the device ground point.
- Switch only the RS485 sensor 12V branch with the sensor power MOSFET. Do not
  place ESP32S3 power behind that switch.
- Use unique Modbus slave IDs on each RS485 bus.
- Treat missing optional RS485 sensors as timeout or `*_ok=false`; do not change
  XIAO pin assignments for each sensor combination.

## Wire Color Convention

| Signal class | Recommended color | Notes |
|---|---|---|
| 12V input / switched 12V | Red | Label switched 12V separately from always-on 12V |
| 5V regulated output | Orange | DC/DC output to XIAO `VBUS` |
| 3.3V sensor power | Violet | SOI and low-voltage WTR profile analog sensor only |
| GND / 0V | Black | Common ground |
| RS485 A / D+ | Yellow | Keep twisted with RS485 B |
| RS485 B / D- | Green | Keep twisted with RS485 A |
| UART TX / RX / DE | Blue / White / Gray | Internal short wiring |
| MOSFET gate | Blue | Internal signal wire from XIAO |
| Analog signal | White | Keep away from pump and valve wiring |

## WTR

All-in-one watering device. WTR controls irrigation and can also read analog
soil moisture and optional RS485 sensors.

| XIAO pin | GPIO | Connect to | External terminal | Wire | Inspection |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DC/DC output | Power `5V_OUT` | Orange 22-24 AWG | 4.75-5.25V at XIAO before plugging in |
| `GND` | - | Device ground | Power `GND` | Black 20-24 AWG | Continuity to 12V negative and RS485 GND |
| `D2` | `GPIO3` | Valve MOSFET gate | Valve output channel 1 | Blue 24-26 AWG | Gate changes when valve command is active |
| `D3` | `GPIO4` | Pump MOSFET gate | Pump output | Blue 24-26 AWG | Pump output follows active valve channel |
| `A5` / `D5` | `GPIO6` | Analog soil moisture signal | Soil analog `SIG` | White 24-26 AWG | ADC changes between dry and wet reference |
| `D4` | `GPIO5` | RS485 transceiver DE and RE | Internal RS485 driver | Gray 24-26 AWG | Direction pin toggles during Modbus TX |
| `D6` | `GPIO43` | RS485 transceiver DI | Internal RS485 TX | Blue 24-26 AWG | UART TX visible during request |
| `D7` | `GPIO44` | RS485 transceiver RO | Internal RS485 RX | White 24-26 AWG | UART RX visible during response |
| `D8` | `GPIO7` | 12V sensor power MOSFET gate | RS485 sensor power switch | Blue 24-26 AWG | Switched 12V appears only during sensor read |
| `BOOT` | `GPIO0` | Setup AP button | Enclosure service button | Two-wire signal | Active-low, no short to 3.3V |
| `USER_LED` | `GPIO21` | Board LED | Internal only | - | Firmware status LED works |

External terminals:

| Terminal | Connects to | Notes |
|---|---|---|
| `12V_IN+` | 12V supply positive | Fuse before board if possible |
| `12V_IN-` | 12V supply negative | Common ground |
| `VALVE+` / `VALVE-` | Solenoid valve or valve driver | Match voltage and current rating |
| `PUMP+` / `PUMP-` | Pump or pump relay/MOSFET output | Do not exceed MOSFET rating |
| `RS485_A` / `RS485_B` | Sensor bus A/B | Swap A/B if all Modbus reads time out |
| `RS485_GND` | Sensor bus ground | Required for stable field wiring |
| `SENSOR_12V_SW+` | Switched sensor 12V | Sensor power branch only |
| `SOIL_SIG` / `SOIL_3V3` / `SOIL_GND` | Analog soil moisture sensor | Optional when RS485 soil sensor is used |

### WTR Low-Voltage Hardware Profile

Use this profile when the device still behaves as WTR but the irrigation load
is a small low-voltage pump, valve driver input, or relay input instead of a 12V
field output. Keep `APP_DEVICE_KIND="WTR"` and keep the WTR firmware pin
contract.

| XIAO pin | GPIO | Connect to | External terminal | Wire | Inspection |
|---|---:|---|---|---|---|
| `BAT+` or `VBUS` | - | Approved battery or regulated input | Power input | Red/Orange 22-24 AWG | Voltage within XIAO input limits |
| `GND` | - | Device ground | `GND` terminal | Black 22-24 AWG | Common with sensor and output GND |
| `D2` | `GPIO3` | WTR valve/irrigation enable MOSFET gate | `IRR1` or driver enable | Blue 24-26 AWG | Gate changes when WTR irrigation channel is active |
| `D3` | `GPIO4` | WTR pump/output MOSFET gate | `IRR2` or pump output | Blue 24-26 AWG | Output follows WTR watering behavior |
| `A5` / `D5` | `GPIO6` | Analog soil moisture signal | Soil analog `SIG` | White 24-26 AWG | ADC changes between dry and wet reference |

Leave RS485 and `D8` sensor power unpopulated if the low-voltage profile does
not use RS485 sensors. Do not move the analog soil sensor to `A0`; that is the
SOI pin contract, not WTR.

## WRS

RS485-first all-in-one watering device. WRS exposes two generic irrigation
outputs and RS485 wiring. The device does not distinguish pump and valve roles;
the installer assigns irrigation output 1/2 to the field hardware. The analog
soil pin is reserved for diagnostics unless a build explicitly uses it.

| XIAO pin | GPIO | Connect to | External terminal | Wire | Inspection |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DC/DC output | Power `5V_OUT` | Orange 22-24 AWG | 4.75-5.25V at XIAO before plugging in |
| `GND` | - | Device ground | Power `GND` | Black 20-24 AWG | Continuity to 12V negative and RS485 GND |
| `D2` | `GPIO3` | Irrigation output 1 MOSFET gate | `IRR1+` / `IRR1-` | Blue 24-26 AWG | Gate changes when channel mask includes bit 0 |
| `D3` | `GPIO4` | Irrigation output 2 MOSFET gate | `IRR2+` / `IRR2-` | Blue 24-26 AWG | Gate changes when channel mask includes bit 1 |
| `A5` / `D5` | `GPIO6` | Reserved diagnostic analog input | Internal test pad | White 24-26 AWG | Leave unconnected unless documented |
| `D4` | `GPIO5` | RS485 transceiver DE and RE | Internal RS485 driver | Gray 24-26 AWG | Direction pin toggles during Modbus TX |
| `D6` | `GPIO43` | RS485 transceiver DI | Internal RS485 TX | Blue 24-26 AWG | UART TX visible during request |
| `D7` | `GPIO44` | RS485 transceiver RO | Internal RS485 RX | White 24-26 AWG | UART RX visible during response |
| `D8` | `GPIO7` | 12V sensor power MOSFET gate | RS485 sensor power switch | Blue 24-26 AWG | Switched 12V appears only during sensor read |
| `BOOT` | `GPIO0` | Setup AP button | Enclosure service button | Two-wire signal | Active-low, no short to 3.3V |
| `USER_LED` | `GPIO21` | Board LED | Internal only | - | Firmware status LED works |

External terminals:

| Terminal | Connects to | Notes |
|---|---|---|
| `12V_IN+` / `12V_IN-` | 12V supply | Common with irrigation outputs, RS485, and 5V DC/DC |
| `IRR1+` / `IRR1-` | Irrigation output 1 load or driver | `channel_mask` bit 0 |
| `IRR2+` / `IRR2-` | Irrigation output 2 load or driver | `channel_mask` bit 1 |
| `RS485_A` / `RS485_B` | Soil, PAR, and irradiance sensors | Unique Modbus slave ID per sensor |
| `RS485_GND` | Sensor bus ground | Required for long cable stability |
| `SENSOR_12V_SW+` | RS485 sensor 12V branch | Sensor branch only, not ESP32S3 power |

## ENV

12V-powered RS485 environmental sensor hub.

| XIAO pin | GPIO | Connect to | External terminal | Wire | Inspection |
|---|---:|---|---|---|---|
| `VBUS` | - | 5V DC/DC output | Power `5V_OUT` | Orange 22-24 AWG | 4.75-5.25V at XIAO before plugging in |
| `GND` | - | Device ground | Power `GND` | Black 20-24 AWG | Continuity to 12V negative and RS485 GND |
| `D4` | `GPIO5` | RS485 transceiver DE and RE | Internal RS485 driver | Gray 24-26 AWG | Direction pin toggles during Modbus TX |
| `D6` | `GPIO43` | RS485 transceiver DI | Internal RS485 TX | Blue 24-26 AWG | UART TX visible during request |
| `D7` | `GPIO44` | RS485 transceiver RO | Internal RS485 RX | White 24-26 AWG | UART RX visible during response |
| `BOOT` | `GPIO0` | Setup AP button | Enclosure service button | Two-wire signal | Active-low, no short to 3.3V |
| `USER_LED` | `GPIO21` | Board LED | Internal only | - | Firmware status LED works |

External terminals:

| Terminal | Connects to | Notes |
|---|---|---|
| `12V_IN+` / `12V_IN-` | 12V supply | Feeds sensors and 5V DC/DC |
| `RS485_A` / `RS485_B` | PAR, soil, EC/pH/NPK, irradiance sensors | Unique Modbus slave ID per sensor |
| `RS485_GND` | Sensor bus ground | Required for stable field wiring |
| `SENSOR_12V+` | Sensor 12V supply | Always-on unless a future switch is added |

## SOI

Battery-powered soil moisture node.

| XIAO pin | GPIO | Connect to | External terminal | Wire | Inspection |
|---|---:|---|---|---|---|
| `BAT+` | - | Protected 18650 positive | Battery holder `+` | Red 22-24 AWG | Correct polarity before inserting battery |
| `BAT-` | - | Battery negative | Battery holder `-` | Black 22-24 AWG | Common with sensor GND |
| `3.3V-OUT` | - | Analog soil sensor VCC | Soil sensor `VCC` | Violet 24-26 AWG | 3.3V only |
| `GND` | - | Sensor ground | Soil sensor `GND` | Black 24-26 AWG | Continuity to battery negative |
| `A0` / `D0` | `GPIO1` | Analog soil sensor signal | Soil sensor `SIG` | White 24-26 AWG | ADC changes between dry and wet reference |
| `BOOT` | `GPIO0` | Setup AP button | Enclosure service button | Two-wire signal | Active-low, no short to 3.3V |
| `USER_LED` | `GPIO21` | Board LED | Internal only | - | Firmware status LED works |

Do not attach 12V RS485 sensors to SOI. Use ENV or WRS when the sensor requires
12V or RS485 Modbus.
