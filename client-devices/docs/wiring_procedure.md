# Wiring Procedure

Japanese version:

- [jp/wiring_procedure.md](jp/wiring_procedure.md)

Use this procedure when wiring a new device or repairing an existing one. Device
specific pin and terminal tables are in
[esp32s3_wiring_tables.md](esp32s3_wiring_tables.md).

## Required Tools

- Multimeter with continuity and DC voltage modes.
- Crimp tool matching the selected terminals.
- Heat shrink, ferrules, cable ties, and wire labels.
- Current-limited bench supply for first power-up.
- USB cable for firmware flash and serial log.

## General Wiring Order

1. Confirm the device kind and open the matching wiring table.
2. Attach wire labels before terminating cables.
3. Wire power input and GND first.
4. Verify 12V input and 5V output before inserting the XIAO ESP32S3.
5. Wire internal GPIO signals.
6. Wire external terminals.
7. Check continuity and shorts before powering the device.
8. Power up with current limit and confirm boot.
9. Connect sensors and actuators one group at a time.
10. Run the device-specific functional test.

## RS485 Wiring

- Use twisted pair for `RS485_A` and `RS485_B`.
- Carry `RS485_GND` with the bus in field wiring.
- Put termination at the physical ends of a long bus when required.
- Use bias resistors if the bus floats while all drivers are idle.
- Do not duplicate Modbus slave IDs on the same bus.
- If every sensor is silent, check A/B polarity, baud rate, and GND first.

## Pump And Valve Wiring

- Confirm the pump and valve voltage and current before connecting.
- Put flyback protection across inductive loads or use a driver board that
  already includes it.
- Keep pump and valve wiring away from analog soil sensor wiring.
- Use strain relief at enclosure entry.
- Test with water disconnected or in a controlled container before field use.

## Analog Soil Sensor Wiring

- Use `A0` for `SOI`.
- Use `A5/D5` for WTR analog soil moisture.
- Keep the analog signal wire short and away from motor wiring.
- Verify dry and wet raw ADC values before sealing the enclosure.

## Final Wiring Check

| Check | Expected result |
|---|---|
| XIAO `VBUS` | 4.75-5.25V |
| XIAO GPIO | No 12V present |
| GND | Common across device and sensors |
| RS485 A/B | Not shorted, twisted pair used |
| Pump / valve | Off at boot, on only during command |
| Sensor 12V switch | Off during sleep, on during RS485 read for WTR/WRS |
| BOOT button | Pulls GPIO0 low only when pressed |

Record any deviation and do not close the enclosure until it is resolved.
