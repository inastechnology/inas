# WRS HAL

WRS does not define a device-specific HAL wrapper.

Use the common HAL modules directly from the App layer:

- `hal_power_switch` for irrigation output 1/2 and switched 12V sensor power.
- `hal_rs485_bus` for the RS485 hardware boundary.
- `hal_rs485_sensor_protocol` for soil/PAR Modbus register mapping.
