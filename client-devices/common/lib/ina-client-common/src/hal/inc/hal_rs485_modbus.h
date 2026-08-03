#ifndef __HAL_RS485_MODBUS_H__
#define __HAL_RS485_MODBUS_H__

#include <stddef.h>
#include <stdint.h>

#ifndef APP_RS485_UART_NUM
#define APP_RS485_UART_NUM 1
#endif

#ifndef APP_RS485_TX_PIN
#define APP_RS485_TX_PIN 43
#endif

#ifndef APP_RS485_RX_PIN
#define APP_RS485_RX_PIN 44
#endif

#ifndef APP_RS485_DE_PIN
#define APP_RS485_DE_PIN 5
#endif

#ifndef APP_RS485_BAUD
#define APP_RS485_BAUD 4800
#endif

#ifndef APP_RS485_RESPONSE_TIMEOUT_MS
#define APP_RS485_RESPONSE_TIMEOUT_MS 1000
#endif

#ifndef APP_RS485_TURNAROUND_DELAY_US
#define APP_RS485_TURNAROUND_DELAY_US 200
#endif

#ifdef __cplusplus
extern "C"
{
#endif

typedef struct
{
    uint8_t uart_num;
    int tx_pin;
    int rx_pin;
    int de_pin;
    uint32_t baud;
    uint32_t response_timeout_ms;
    uint32_t turnaround_delay_us;
} hal_rs485_modbus_config_t;

hal_rs485_modbus_config_t hal_rs485_modbus_default_config();
bool hal_rs485_modbus_init(const hal_rs485_modbus_config_t *config);
void hal_rs485_modbus_deinit();
bool hal_rs485_modbus_read_registers(uint8_t slave_id,
                                     uint8_t function_code,
                                     uint16_t start_register,
                                     uint16_t register_count,
                                     uint16_t *out_registers,
                                     size_t out_register_count);
bool hal_rs485_modbus_write_single_register(uint8_t slave_id,
                                            uint16_t register_address,
                                            uint16_t value);
uint16_t hal_rs485_modbus_crc16(const uint8_t *data, size_t length);

#ifdef __cplusplus
}
#endif

#endif // __HAL_RS485_MODBUS_H__
