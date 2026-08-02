#ifndef INAS_DEBUG_HAL_RS485_MODBUS_H
#define INAS_DEBUG_HAL_RS485_MODBUS_H

#include <stddef.h>
#include <stdint.h>

#define HAL_RS485_MODBUS_MAX_REQUEST_LENGTH 8U
#define HAL_RS485_MODBUS_MAX_RESPONSE_LENGTH 69U

typedef enum
{
    HAL_RS485_MODBUS_OK,
    HAL_RS485_MODBUS_TX_ERROR,
    HAL_RS485_MODBUS_TIMEOUT,
    HAL_RS485_MODBUS_SHORT_FRAME,
    HAL_RS485_MODBUS_CRC_ERROR,
    HAL_RS485_MODBUS_EXCEPTION,
    HAL_RS485_MODBUS_WRONG_SLAVE_ID,
    HAL_RS485_MODBUS_WRONG_FUNCTION,
    HAL_RS485_MODBUS_WRONG_BYTE_COUNT,
    HAL_RS485_MODBUS_LENGTH_MISMATCH,
    HAL_RS485_MODBUS_MALFORMED,
} hal_rs485_modbus_status_t;

typedef struct
{
    uint8_t uart_num;
    int tx_pin;
    int rx_pin;
    int de_re_pin;
    uint32_t baud;
    uint32_t response_timeout_ms;
    uint32_t turnaround_delay_us;
} hal_rs485_modbus_config_t;

typedef struct
{
    hal_rs485_modbus_status_t status;
    uint8_t exception_code;
    size_t request_length;
    size_t transmitted_length;
    int8_t direction_tx_level;
    int8_t direction_rx_level;
    uint8_t request[HAL_RS485_MODBUS_MAX_REQUEST_LENGTH];
    size_t expected_length;
    size_t received_length;
    uint8_t response[HAL_RS485_MODBUS_MAX_RESPONSE_LENGTH];
    uint16_t calculated_crc;
    uint16_t received_crc;
} hal_rs485_modbus_result_t;

bool hal_rs485_modbus_init(const hal_rs485_modbus_config_t *config);
void hal_rs485_modbus_deinit();
hal_rs485_modbus_result_t hal_rs485_modbus_read_holding_registers(
    uint8_t slave_id,
    uint16_t start_register,
    uint16_t register_count,
    uint16_t *out_registers,
    size_t out_register_count);
const char *hal_rs485_modbus_status_name(hal_rs485_modbus_status_t status);
uint16_t hal_rs485_modbus_crc16(const uint8_t *data, size_t length);

#endif
