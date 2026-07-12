# WRS Watering RS485 Device

Device kind: `WRS`

Project status: design stub. Firmware has not been forked from
`watering-device` yet.

`WRS` is the RS485-first all-in-one watering device. It keeps the practical
parts of `WTR`: local irrigation outputs, pump/valve control, and switched 12V
sensor power. The difference is that the main sensor expansion boundary is the
RS485 bus, not fixed analog pins.

## Role

- Execute irrigation locally, like `WTR`.
- Measure root-zone feedback through RS485 soil sensors.
- Measure PAR and optional irradiance on the same RS485 bus.
- Publish the same measurement names as `ENV` and `WTR` so the hub can store
  values in `sensor_measurements` without a separate schema.

## Hardware Boundary

Reuse the WTR pin assignment for the first WRS revision:

| Signal | XIAO pin | GPIO | Purpose |
|---|---:|---:|---|
| Valve MOSFET | `D2` | `GPIO3` | Irrigation line 1 |
| Pump MOSFET | `D3` | `GPIO4` | Pump output while irrigation is active |
| RS485 DE/RE | `D4` | `GPIO5` | Transmit/receive direction control |
| RS485 TX | `D6` | `GPIO43` | UART TX |
| RS485 RX | `D7` | `GPIO44` | UART RX |
| 12V sensor power MOSFET | `D8` | `GPIO7` | Switches the 12V branch going to RS485 sensors |

The analog soil moisture ADC may remain unused or reserved for diagnostics.

## RS485 Composition

Add sensors by assigning each Modbus device a unique slave ID. Do not create a
new pin assignment for every sensor combination. When an expected sensor is not
connected, the firmware should treat timeout, CRC failure, or no response as a
missing sensor and publish the related status flag as `*_ok=false`.

Initial sensor groups:

- RS485 soil sensor: `soil_moisture_percent`, `soil_temperature_c`,
  `soil_ec_us_cm`, `soil_ph`, `soil_n_mg_kg`, `soil_p_mg_kg`,
  `soil_k_mg_kg`.
- RS485 PAR sensor: `par_umol_m2_s`.
- Optional RS485 irradiance sensor: `solar_radiation_w_m2`.

## Hub Contract

The hub treats `WRS` as a watering-capable device. Strawberry drip cultivation
and similar crop systems should be modeled as hub-orchestrated compositions of
field context, sensor feedback, and actuator devices rather than as monolithic
crop-specific device kinds.

Example status payload:

```json
{
  "device_kind": "WRS",
  "sensor_model": "RS485-WATERING-AIO",
  "watering_due": true,
  "watering_started": true,
  "soil_rs485_ok": true,
  "soil_moisture_percent": 42.1,
  "soil_temperature_c": 21.5,
  "soil_ec_us_cm": 820,
  "soil_ph": 6.5,
  "par_ok": true,
  "par_umol_m2_s": 1234.0,
  "solar_radiation_ok": false
}
```

## Implementation Note

Start firmware implementation by reusing the WTR irrigation output behavior and
the ENV/WTR RS485 sensor reading behavior. Split shared code only when the copy
would otherwise duplicate meaningful watering or RS485 logic.
