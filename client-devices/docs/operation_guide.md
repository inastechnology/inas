# Operation Guide

Japanese version:

- [jp/operation_guide.md](jp/operation_guide.md)

This guide explains routine operation after installation.

## Daily Checks

- Confirm each active device reported status within the expected interval.
- Check `network_connected`, wake history, battery or supply voltage, and RSSI.
- Check `*_ok` flags for sensors expected to be connected.
- Review irrigation history before changing thresholds or schedules.
- For `WTR` and `WRS`, confirm soil moisture response after irrigation or
  output activation.

## Calibration

| Device kind | Calibration |
|---|---|
| `SOI` | Capture dry and wet references, or manually set `dry_raw` and `wet_raw` |
| `WTR` | Calibrate analog soil moisture if used; calibrate RS485 values through env calibration when enabled |
| `WRS` | Calibrate RS485 soil/PAR/irradiance values; analog soil input is normally unused |
| `ENV` | Calibrate PAR, EC, pH, and other RS485 values against known references |

Keep calibration records with date, operator, reference value, and observed
device value.

## Irrigation Operation

- Keep default operation in manual approval until field behavior is understood.
- Set maximum watering duration and minimum watering interval before automation.
- Use soil moisture feedback near the irrigation target.
- Stop automation if moisture does not increase after watering.
- Treat pump runtime as an action record, not proof that water reached the root
  zone.
- For a low-voltage WTR hardware profile, keep automation disabled until the
  load, MOSFET, flyback protection, and water path are verified.

## RS485 Sensor Operation

- Add sensors by assigning unique slave IDs, not by changing XIAO pins.
- If one sensor fails, check its power, address, baud rate, and A/B wiring.
- If all sensors fail, check bus power, common GND, A/B polarity, and termination.
- Optional missing sensors should be visible as `*_ok=false`.

## Maintenance

| Interval | Work |
|---|---|
| Daily during trial | Confirm status, watering result, and sensor plausibility |
| Weekly | Inspect cable glands, connectors, corrosion, and enclosure seal |
| Monthly | Check pump/valve operation and clean filters |
| Crop cycle change | Review placement, calibration, thresholds, and Modbus IDs |
| After heavy rain or repair | Inspect enclosure, power, RS485 bus, and actuator outputs |

## Fault Handling

| Symptom | First checks |
|---|---|
| Device offline | Power, battery, Wi-Fi, MQTT, antenna placement |
| Sensor `*_ok=false` | Sensor power, Modbus ID, baud, A/B, GND |
| Pump does not run | Schedule approval, MOSFET output, fuse, pump wiring |
| Valve does not open | Valve polarity, current rating, stuck valve, output command |
| Soil moisture does not rise | Water source, clogging, sensor position, insufficient duration |
| Values jump suddenly | Loose wiring, water ingress, calibration drift, sensor damage |

## Stop Procedure

1. Disable automatic irrigation in the hub.
2. Turn off or unplug the pump power source.
3. Close the water source if needed.
4. Confirm pump and valve outputs are off.
5. Record the reason and recovery action before re-enabling automation.
