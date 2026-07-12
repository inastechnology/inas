#ifndef __HAL_RS485_BUS_H__
#define __HAL_RS485_BUS_H__

#include <stddef.h>
#include <stdint.h>

#include "hal_rs485_modbus.h"

#ifdef __cplusplus
extern "C"
{
#endif

typedef struct
{
    uint8_t slave_id;
    uint8_t function_code;
    uint16_t start_register;
    uint16_t register_count;
} hal_rs485_register_request_t;

typedef struct
{
    bool ok;
    uint8_t slave_id;
    uint8_t function_code;
    uint16_t start_register;
    uint16_t register_count;
    uint32_t elapsed_ms;
} hal_rs485_register_result_t;

bool hal_rs485_bus_init(const hal_rs485_modbus_config_t *config);
void hal_rs485_bus_deinit();
bool hal_rs485_bus_read_registers(const hal_rs485_register_request_t *request,
                                  uint16_t *out_registers,
                                  size_t out_register_count,
                                  hal_rs485_register_result_t *out_result);

#ifdef __cplusplus
}
#endif

#endif // __HAL_RS485_BUS_H__
