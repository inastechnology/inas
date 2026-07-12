# Manufacturing Procedure

Japanese version:

- [jp/manufacturing_procedure.md](jp/manufacturing_procedure.md)

This procedure defines how to build INAS ESP32S3 client devices consistently.
It applies to `WTR`, `WRS`, `ENV`, and `SOI`.

## Inputs

- Target device kind: `WTR`, `WRS`, `ENV`, or `SOI`.
- Approved wiring table:
  [esp32s3_wiring_tables.md](esp32s3_wiring_tables.md).
- Firmware project and `APP_DEVICE_KIND` for the target.
- Enclosure drawing, terminal label sheet, and bill of materials for the build
  lot.
- Sensor manuals, especially Modbus address, baud rate, function code, register
  map, scale, and power requirement.

## Safety Boundary

- Do not modify AC mains wiring inside an INAS custom device enclosure.
- Use only DC low-voltage wiring inside the device enclosure unless a qualified
  electrical worker has reviewed the design.
- Confirm 12V and 5V rails before plugging in the XIAO ESP32S3.
- Disconnect power before soldering, crimping, or changing terminals.
- Use fusing or current limiting appropriate for the pump, valve, and cable.

## Build Steps

1. Create a build record with lot ID, date, device kind, firmware version,
   firmware build ID, operator, and inspector.
2. Inspect all parts for visible damage, wrong voltage rating, loose connectors,
   or missing terminal labels.
3. Mount the 12V input terminal, DC/DC converter, XIAO ESP32S3 carrier,
   MOSFET/driver board, RS485 transceiver, and external terminals.
4. Wire power first: `12V_IN`, 5V DC/DC output, XIAO `VBUS`, and common GND.
5. Verify voltage rails without the XIAO board installed.
6. Install the XIAO board and wire signal lines according to the wiring table.
7. Wire external terminals: pump, valve, RS485 A/B/GND, sensor 12V, analog soil
   sensor, and battery holder as applicable.
8. Apply terminal labels and device labels before closing the enclosure.
9. Flash firmware for the target device kind.
10. Run the electrical inspection and functional inspection below.

## Electrical Inspection

| Check | Acceptance |
|---|---|
| 12V input polarity | Correct at input terminal |
| 5V rail | 4.75-5.25V at XIAO `VBUS` |
| GND continuity | XIAO GND, RS485 GND, 12V negative, and DC/DC GND are common |
| No 12V on GPIO | No XIAO GPIO has 12V |
| MOSFET off state | Pump, valve, and switched sensor 12V are off at boot |
| RS485 A/B | A/B are not shorted to each other or to power |
| SOI battery polarity | `BAT+` and `BAT-` match holder labels |

## Functional Inspection

| Device kind | Required checks |
|---|---|
| `WTR` | Boots, publishes status, reads analog soil moisture if connected, toggles valve and pump outputs, reads enabled RS485 sensors |
| `WRS` | Boots, publishes status, toggles irrigation output 1/2, reads RS485 soil/PAR/irradiance sensors or reports `*_ok=false` for missing sensors |
| `ENV` | Boots, publishes status, reads each configured RS485 sensor or reports `*_ok=false` |
| `SOI` | Boots, reads analog soil moisture, enters sleep, wakes again, and accepts calibration config |

## Output Artifacts

Keep these records with the device:

- Device ID and device kind.
- Firmware version and build ID.
- Modbus slave IDs assigned to RS485 sensors.
- Wiring inspection result.
- Functional inspection result.
- Known deviations and repair history.

## Nonconforming Unit Handling

Do not ship a unit when:

- 12V appears on any XIAO GPIO.
- GND is not common across required terminals.
- Pump or valve output is stuck on.
- RS485 bus is shorted.
- Device kind in firmware does not match the device label.

Mark the unit as hold, record the defect, repair it, and repeat the full
electrical and functional inspection before release.
