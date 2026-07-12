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
- 12V soil EC/pH/NPK sensor support is build-flag gated until the sensor manual is confirmed
