# INA Soil Sensor Docs

Document the fixed `SOI` hardware contract here:
Layer boundaries follow
[../../docs/firmware_layering_policy.md](../../docs/firmware_layering_policy.md).

- pin assignment
- connected sensors and actuators
- MQTT status payload
- runtime config payload
- OTA and release checklist

Current contract:

- `A0`: analog soil moisture sensor
- 18650 battery / deep sleep operation
- No 12V RS485 sensors
