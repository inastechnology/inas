# INA Environment Sensor Docs

Document the fixed `ENV` hardware contract here:
Layer boundaries follow
[../../docs/firmware_layering_policy.md](../../docs/firmware_layering_policy.md).

- pin assignment
- connected sensors and actuators
- MQTT status payload
- runtime config payload
- OTA and release checklist

Current contract:

- RS485 Modbus RTU on UART1
- PAR/light sensor enabled by default
- ComWinTop CWT-SOIL 12V soil EC/pH/NPK manual and FC03 register profile are
  confirmed in
  [../../docs/jp/comwintop_cwt_soil_npkphcth_s_spec.md](../../docs/jp/comwintop_cwt_soil_npkphcth_s_spec.md)
- soil support remains build-flag gated until the FC04 defaults are aligned and
  the selected sensor lot is bench-tested
