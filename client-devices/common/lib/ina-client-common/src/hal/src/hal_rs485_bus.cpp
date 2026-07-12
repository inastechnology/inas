#include "hal_rs485_bus.h"

#include <Arduino.h>

bool hal_rs485_bus_init(const hal_rs485_modbus_config_t *config)
{
    return hal_rs485_modbus_init(config);
}

void hal_rs485_bus_deinit()
{
    hal_rs485_modbus_deinit();
}

bool hal_rs485_bus_read_registers(const hal_rs485_register_request_t *request,
                                  uint16_t *out_registers,
                                  size_t out_register_count,
                                  hal_rs485_register_result_t *out_result)
{
    if (out_result != nullptr)
    {
        *out_result = {};
    }
    if (request == nullptr)
    {
        return false;
    }

    const uint32_t start_ms = millis();
    const bool ok = hal_rs485_modbus_read_registers(request->slave_id,
                                                   request->function_code,
                                                   request->start_register,
                                                   request->register_count,
                                                   out_registers,
                                                   out_register_count);
    if (out_result != nullptr)
    {
        out_result->ok = ok;
        out_result->slave_id = request->slave_id;
        out_result->function_code = request->function_code;
        out_result->start_register = request->start_register;
        out_result->register_count = request->register_count;
        out_result->elapsed_ms = millis() - start_ms;
    }
    return ok;
}
