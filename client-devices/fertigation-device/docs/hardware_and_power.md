# Hardware And Power

## Power architecture

- Battery: six matched 18650 cells in 3S2P, nominal 11.1 V / 6 Ah / 66.6 Wh.
- Protection: balancing 3S BMS, main fuse, branch protection, temperature
  monitoring, and a 3S 12.6 V CC/CV solar charger.
- Regulated 12 V: a buck-boost rail sized for pump start current prevents flow
  and valve behavior from changing over the 3S discharge curve.
- Regulated 5 V: XIAO ESP32-S3 and A/B pumps. Pump driver power is separate from
  the ESP32 logic rail even when both are nominally 5 V.
- Every actuator driver has a physical gate/input pull-down. MCP23017 reset or
  disconnection must therefore mean OFF.

The initial budget is 5-8 Wh/day until installed hydraulic flow and whole-board
sleep current are measured. A 20 W panel is the baseline when installed outside
shade; it is not guaranteed by nameplate power alone.

## Default XIAO ESP32-S3 signals

| Function | XIAO | GPIO | Notes |
|---|---:|---:|---|
| MCP23017 SDA | D0 | 1 | Remapped I2C data |
| MCP23017 SCL | D1 | 2 | Remapped I2C clock |
| Reserved | D2 | 3 | Strapping GPIO; do not connect an actuator in v1 |
| Actuator master enable | D3 | 4 | Active high, hardware pull-down |
| RS485 DE/RE | D4 | 5 | Direction control |
| Inlet flow pulse | D5 | 6 | Interrupt-capable pulse input |
| RS485 TX | D6 | 43 | UART1 TX |
| RS485 RX | D7 | 44 | UART1 RX |
| RS485 sensor power | D8 | 7 | Existing switched sensor-power contract |
| Reserved safety input | D9 | 8 | Future direct full/leak input |
| Reserved safety input | D10 | 9 | Future direct emergency input |

## MCP23017 assignment

| MCP pin | Direction | Function |
|---:|---|---|
| GPA0 | output | Water inlet valve/pump |
| GPA1 | output | A concentrate pump |
| GPA2 | output | B concentrate pump |
| GPA3 | output | Mixing pump |
| GPA4 | output | Irrigation pump |
| GPB0 | input, pull-up | Tank empty, active low |
| GPB1 | input, pull-up | Tank full, active low |
| GPB2 | input, pull-up | Leak, active low |
| GPB3 | input, pull-up | Emergency stop, active low |

The master-enable signal removes permission from all five actuator drivers.
The MCP23017 only selects an actuator after the master signal is safe. A final
mechanical float valve remains independent of firmware.

## Plumbing

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
