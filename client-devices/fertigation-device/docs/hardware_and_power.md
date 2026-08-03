# Hardware And Power

## Current hardware status

There is no fabricated dedicated FGT PCB. The KiCad project under
`hardware/esp32c6-solar-controller` is an in-progress future design and is not
used for the current FGT bring-up.

The current firmware contract is the direct-wiring pin table below: a XIAO
ESP32-C6, five discrete MOSFET switch inputs, one RS485 transceiver, and one
RS485 sensor-power enable. This table, not the development KiCad PCB, is
authoritative for the current prototype.

## Power architecture

- Battery: six matched 18650 cells in 3S2P, nominal 11.1 V / 6 Ah / 66.6 Wh.
- Protection: balancing 3S BMS, main fuse, branch protection, temperature
  monitoring, and a 3S 12.6 V CC/CV solar charger.
- Regulated 12 V: a buck-boost rail sized for pump start current prevents flow
  and valve behavior from changing over the 3S discharge curve.
- Regulated 5 V: XIAO ESP32-C6 and logic only.
- Actuator power: all current pumps, including A/B peristaltic pumps, use the
  12 V actuator rail.
- Every actuator command is connected directly to an ESP32-C6 GPIO and has a
  physical 47 kohm pull-down. Reset or MCU disconnection must therefore mean
  OFF.

The initial budget is 5-8 Wh/day until installed hydraulic flow and whole-board
sleep current are measured. A 20 W panel is the baseline when installed outside
shade; it is not guaranteed by nameplate power alone.

## XIAO ESP32-C6 direct-GPIO signals

| Function | XIAO pad | GPIO | Reset/safety rule |
|---|---:|---:|---|
| Battery voltage ADC | D0 / A0 / pad 1 | 0 | Two equal 200 kohm resistors, 1:2 divider |
| Water inlet command | D1 / pad 2 | 1 | 47 kohm pull-down, reset OFF |
| A concentrate command | D2 / pad 3 | 2 | 47 kohm pull-down, reset OFF |
| B concentrate command | D3 / pad 4 | 21 | 47 kohm pull-down, reset OFF |
| Mixing command | D4 / pad 5 | 22 | 47 kohm pull-down, reset OFF |
| Irrigation command | D5 / pad 6 | 23 | 47 kohm pull-down, reset OFF |
| RS485 TX | D6 / pad 7 | 16 | 3.3 V UART |
| RS485 RX | D7 / pad 8 | 17 | 3.3 V UART |
| RS485 DE/RE | D8 / pad 9 | 19 | Pull-down selects receive mode |
| RS485 sensor 12 V enable | D9 / pad 10 | 20 | 47 kohm pull-down, reset OFF |
| Reserved | D10 / pad 11 | 18 | Not connected |

The five MOSFET commands each use a 100 ohm series gate resistor and a physical
47 kohm gate-to-GND pull-down. A reset or unpowered MCU therefore leaves every
actuator OFF. D0/A0 is reserved for ADC measurement and must never drive a
MOSFET.

The RS485 sensor rail is switched by a protected 12 V high-side load switch.
GPIO20 drives only its 3.3 V-compatible enable input and never supplies sensor
power directly.

The battery monitor divides BAT+ by two before GPIO0:

```text
BAT+ ---- 200 kohm ----+---- D0 / A0 / GPIO0
                       |
                     200 kohm
                       |
BAT- / GND ------------+
```

Firmware averages 16 calibrated `analogReadMilliVolts()` samples and multiplies
the result by 2.0. Keep the ADC node within the ESP32-C6 input range.

The matching Japanese wiring procedure is
[`docs/jp/minimal_wiring.md`](jp/minimal_wiring.md). The generated KiCad design
is development material only and must not be substituted for this current pin
contract.

## Plumbing

The plumbing and safety behavior below describe the target FGT product. The
current direct-wiring pin contract has no dedicated flow, tank-level, leak, or
emergency-stop input. It must therefore remain a supervised bench prototype
until those protections are implemented separately or in a future hardware
revision.

- Flow meter is on the clean-water inlet and measures initial, final, and rinse
  fill volumes.
- Tank-empty input stops irrigation and protects mixing/irrigation pumps.
- Tank-full input is a high-level safety check; normal volume control uses the
  inlet flow meter.
- A and B outlets enter the high-flow return region but remain physically
  separate.
- Mixer and irrigation pumps must have fertilizer-compatible wetted materials.
- The irrigation line includes a serviceable filter and check valve where the
  selected pump/plumbing requires it.

### Residual liquid and rinse sizing

Do not compensate for unavoidable tank residue by making the fertilizer batch
arbitrarily weaker. First reduce and measure the dead volume: use a sloped or
bottom-drained tank, keep the irrigation pickup at the low point without
running the pump dry, and measure the liquid left when the empty input stops the
pump. Configure rinse water from that measured value and the line volume.

The clean-water rinse is mixed and sent through the same irrigation path. Its
volume therefore belongs in the crop's irrigation budget. The v1 default is a
4.5 L nutrient-water batch followed by 0.5 L rinse water, for approximately
5.0 L delivered. Validate that one rinse clears visible/conductivity carryover;
increase it only when the measured dead volume requires it. If concentrated
residue remains after a rinse, improve drainage or add a separate waste/service
drain rather than silently delivering an unknown extra dose to the crop.
