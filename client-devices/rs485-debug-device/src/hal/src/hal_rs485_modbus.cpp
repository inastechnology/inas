#include "hal_rs485_modbus.h"

#include <Arduino.h>
#include <HardwareSerial.h>
#include <cstring>

namespace
{

HardwareSerial *s_serial = nullptr;
hal_rs485_modbus_config_t s_config = {};
bool s_ready = false;

void setTransmitMode(bool enabled)
{
    if (s_config.de_re_pin >= 0)
    {
        digitalWrite(s_config.de_re_pin, enabled ? HIGH : LOW);
    }
}

void clearReceiveBuffer()
{
    while (s_serial != nullptr && s_serial->available() > 0)
    {
        s_serial->read();
    }
}

} // namespace

bool hal_rs485_modbus_init(const hal_rs485_modbus_config_t *config)
{
    if (config == nullptr || config->baud == 0 || config->tx_pin < 0 || config->rx_pin < 0)
    {
        return false;
    }

    hal_rs485_modbus_deinit();
    s_config = *config;
    s_serial = new HardwareSerial(s_config.uart_num);
    if (s_serial == nullptr)
    {
        return false;
    }

    if (s_config.de_re_pin >= 0)
    {
        pinMode(s_config.de_re_pin, OUTPUT);
        setTransmitMode(false);
    }
    s_serial->begin(s_config.baud, SERIAL_8N1, s_config.rx_pin, s_config.tx_pin);
    s_ready = true;
    delay(20);
    return true;
}

void hal_rs485_modbus_deinit()
{
    if (s_serial != nullptr)
    {
        s_serial->end();
        delete s_serial;
        s_serial = nullptr;
    }
    if (s_ready && s_config.de_re_pin >= 0)
    {
        setTransmitMode(false);
    }
    s_ready = false;
}

hal_rs485_modbus_result_t hal_rs485_modbus_read_holding_registers(
    uint8_t slave_id,
    uint16_t start_register,
    uint16_t register_count,
    uint16_t *out_registers,
    size_t out_register_count)
{
    hal_rs485_modbus_result_t result = {};
    result.status = HAL_RS485_MODBUS_MALFORMED;
    result.direction_tx_level = -1;
    result.direction_rx_level = -1;
    if (!s_ready || s_serial == nullptr || out_registers == nullptr ||
        register_count == 0 || register_count > 32 || out_register_count < register_count)
    {
        return result;
    }

    clearReceiveBuffer();
    result.request_length = HAL_RS485_MODBUS_MAX_REQUEST_LENGTH;
    uint8_t *request = result.request;
    const uint8_t request_bytes[HAL_RS485_MODBUS_MAX_REQUEST_LENGTH] = {
        slave_id,
        0x03,
        static_cast<uint8_t>(start_register >> 8),
        static_cast<uint8_t>(start_register & 0xFF),
        static_cast<uint8_t>(register_count >> 8),
        static_cast<uint8_t>(register_count & 0xFF),
        0,
        0,
    };
    memcpy(request, request_bytes, sizeof(request_bytes));
    const uint16_t request_crc = hal_rs485_modbus_crc16(request, 6);
    request[6] = static_cast<uint8_t>(request_crc & 0xFF);
    request[7] = static_cast<uint8_t>(request_crc >> 8);
    result.expected_length = 5U + register_count * 2U;

    setTransmitMode(true);
    if (s_config.de_re_pin >= 0)
    {
        result.direction_tx_level = static_cast<int8_t>(digitalRead(s_config.de_re_pin));
    }
    delayMicroseconds(100);
    result.transmitted_length = s_serial->write(request, result.request_length);
    s_serial->flush();
    delayMicroseconds(s_config.turnaround_delay_us);
    setTransmitMode(false);
    if (s_config.de_re_pin >= 0)
    {
        result.direction_rx_level = static_cast<int8_t>(digitalRead(s_config.de_re_pin));
    }
    if (result.transmitted_length != result.request_length)
    {
        result.status = HAL_RS485_MODBUS_TX_ERROR;
        return result;
    }

    uint8_t *response = result.response;
    size_t response_length = 0;
    uint32_t last_byte_ms = millis();
    const uint32_t started_ms = millis();

    while (millis() - started_ms < s_config.response_timeout_ms)
    {
        while (s_serial->available() > 0 &&
               response_length < HAL_RS485_MODBUS_MAX_RESPONSE_LENGTH)
        {
            response[response_length++] = static_cast<uint8_t>(s_serial->read());
            last_byte_ms = millis();
        }
        if (response_length >= result.expected_length ||
            (response_length >= 5 && response[1] == 0x83))
        {
            break;
        }
        if (response_length > 0 && millis() - last_byte_ms >= 20)
        {
            break;
        }
        delay(1);
    }

    result.received_length = response_length;
    if (response_length == 0)
    {
        result.status = HAL_RS485_MODBUS_TIMEOUT;
        return result;
    }
    if (response_length < 5)
    {
        result.status = HAL_RS485_MODBUS_SHORT_FRAME;
        return result;
    }

    result.received_crc = static_cast<uint16_t>(response[response_length - 2]) |
                          (static_cast<uint16_t>(response[response_length - 1]) << 8);
    result.calculated_crc = hal_rs485_modbus_crc16(response, response_length - 2);
    if (result.received_crc != result.calculated_crc)
    {
        result.status = HAL_RS485_MODBUS_CRC_ERROR;
        return result;
    }
    if (response[0] != slave_id)
    {
        result.status = HAL_RS485_MODBUS_WRONG_SLAVE_ID;
        return result;
    }
    if (response[1] == 0x83)
    {
        result.status = HAL_RS485_MODBUS_EXCEPTION;
        result.exception_code = response[2];
        return result;
    }
    if (response[1] != 0x03)
    {
        result.status = HAL_RS485_MODBUS_WRONG_FUNCTION;
        return result;
    }
    if (response[2] != register_count * 2)
    {
        result.status = HAL_RS485_MODBUS_WRONG_BYTE_COUNT;
        return result;
    }
    if (response_length != result.expected_length)
    {
        result.status = HAL_RS485_MODBUS_LENGTH_MISMATCH;
        return result;
    }

    for (uint16_t i = 0; i < register_count; ++i)
    {
        const size_t offset = 3U + static_cast<size_t>(i) * 2U;
        out_registers[i] =
            (static_cast<uint16_t>(response[offset]) << 8) | response[offset + 1];
    }
    result.status = HAL_RS485_MODBUS_OK;
    return result;
}

const char *hal_rs485_modbus_status_name(hal_rs485_modbus_status_t status)
{
    switch (status)
    {
    case HAL_RS485_MODBUS_OK:
        return "ok";
    case HAL_RS485_MODBUS_TX_ERROR:
        return "tx_error";
    case HAL_RS485_MODBUS_TIMEOUT:
        return "timeout";
    case HAL_RS485_MODBUS_SHORT_FRAME:
        return "short_frame";
    case HAL_RS485_MODBUS_CRC_ERROR:
        return "crc_error";
    case HAL_RS485_MODBUS_EXCEPTION:
        return "exception";
    case HAL_RS485_MODBUS_WRONG_SLAVE_ID:
        return "wrong_slave_id";
    case HAL_RS485_MODBUS_WRONG_FUNCTION:
        return "wrong_function";
    case HAL_RS485_MODBUS_WRONG_BYTE_COUNT:
        return "wrong_byte_count";
    case HAL_RS485_MODBUS_LENGTH_MISMATCH:
        return "length_mismatch";
    case HAL_RS485_MODBUS_MALFORMED:
        return "malformed";
    }
    return "unknown";
}

uint16_t hal_rs485_modbus_crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i)
    {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit)
        {
            crc = (crc & 1U) != 0U ? (crc >> 1U) ^ 0xA001U : crc >> 1U;
        }
    }
    return crc;
}
