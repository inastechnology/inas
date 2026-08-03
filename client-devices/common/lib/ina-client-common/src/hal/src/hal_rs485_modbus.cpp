#include "hal_rs485_modbus.h"

#include <Arduino.h>
#include <HardwareSerial.h>
#include <string.h>

static HardwareSerial *s_serial = nullptr;
static uint8_t s_uart_num = 0xFF;
static hal_rs485_modbus_config_t s_config = {};
static bool s_ready = false;

static void hal_rs485_set_transmit(bool enabled)
{
    if (s_config.de_pin >= 0)
    {
        digitalWrite(s_config.de_pin, enabled ? HIGH : LOW);
    }
}

hal_rs485_modbus_config_t hal_rs485_modbus_default_config()
{
    hal_rs485_modbus_config_t config = {};
    config.uart_num = APP_RS485_UART_NUM;
    config.tx_pin = APP_RS485_TX_PIN;
    config.rx_pin = APP_RS485_RX_PIN;
    config.de_pin = APP_RS485_DE_PIN;
    config.baud = APP_RS485_BAUD;
    config.response_timeout_ms = APP_RS485_RESPONSE_TIMEOUT_MS;
    config.turnaround_delay_us = APP_RS485_TURNAROUND_DELAY_US;
    return config;
}

bool hal_rs485_modbus_init(const hal_rs485_modbus_config_t *config)
{
    s_config = config != nullptr ? *config : hal_rs485_modbus_default_config();
    if (s_config.baud == 0 || s_config.tx_pin < 0 || s_config.rx_pin < 0)
    {
        Serial.println("RS485 Modbus config is invalid");
        return false;
    }

    if (s_serial == nullptr || s_uart_num != s_config.uart_num)
    {
        delete s_serial;
        s_serial = new HardwareSerial(s_config.uart_num);
        s_uart_num = s_config.uart_num;
    }

    if (s_config.de_pin >= 0)
    {
        pinMode(s_config.de_pin, OUTPUT);
        digitalWrite(s_config.de_pin, LOW);
    }

    s_serial->begin(s_config.baud, SERIAL_8N1, s_config.rx_pin, s_config.tx_pin);
    s_ready = true;
    Serial.printf("RS485 Modbus initialized: uart=%u baud=%lu tx=%d rx=%d de=%d timeout=%lu ms\n",
                  static_cast<unsigned int>(s_config.uart_num),
                  static_cast<unsigned long>(s_config.baud),
                  s_config.tx_pin,
                  s_config.rx_pin,
                  s_config.de_pin,
                  static_cast<unsigned long>(s_config.response_timeout_ms));
    return true;
}

void hal_rs485_modbus_deinit()
{
    if (s_serial != nullptr)
    {
        s_serial->end();
    }
    if (s_config.de_pin >= 0)
    {
        digitalWrite(s_config.de_pin, LOW);
    }
    s_ready = false;
}

bool hal_rs485_modbus_read_registers(uint8_t slave_id,
                                     uint8_t function_code,
                                     uint16_t start_register,
                                     uint16_t register_count,
                                     uint16_t *out_registers,
                                     size_t out_register_count)
{
    if (!s_ready || s_serial == nullptr || out_registers == nullptr || register_count == 0 || out_register_count < register_count)
    {
        return false;
    }
    if (function_code != 0x03 && function_code != 0x04)
    {
        Serial.printf("Unsupported Modbus function code: 0x%02X\n", function_code);
        return false;
    }
    if (register_count > 32)
    {
        Serial.println("Modbus register_count is too large");
        return false;
    }

    while (s_serial->available() > 0)
    {
        s_serial->read();
    }

    uint8_t request[8] = {
        slave_id,
        function_code,
        static_cast<uint8_t>(start_register >> 8),
        static_cast<uint8_t>(start_register & 0xFF),
        static_cast<uint8_t>(register_count >> 8),
        static_cast<uint8_t>(register_count & 0xFF),
        0,
        0,
    };
    const uint16_t request_crc = hal_rs485_modbus_crc16(request, 6);
    request[6] = static_cast<uint8_t>(request_crc & 0xFF);
    request[7] = static_cast<uint8_t>(request_crc >> 8);

    hal_rs485_set_transmit(true);
    delayMicroseconds(50);
    s_serial->write(request, sizeof(request));
    s_serial->flush();
    delayMicroseconds(s_config.turnaround_delay_us);
    hal_rs485_set_transmit(false);

    const size_t expected_length = 5 + static_cast<size_t>(register_count) * 2;
    uint8_t response[69] = {};
    size_t response_length = 0;
    const uint32_t start_ms = millis();
    while (millis() - start_ms < s_config.response_timeout_ms)
    {
        while (s_serial->available() > 0 && response_length < sizeof(response))
        {
            response[response_length++] = static_cast<uint8_t>(s_serial->read());
        }
        if (response_length >= expected_length)
        {
            break;
        }
        if (response_length >= 5 && response[1] == (function_code | 0x80))
        {
            break;
        }
        delay(1);
    }

    if (response_length < 5)
    {
        Serial.printf("Modbus response timeout: slave=%u function=0x%02X register=0x%04X count=%u bytes=%u\n",
                      static_cast<unsigned int>(slave_id),
                      function_code,
                      start_register,
                      register_count,
                      static_cast<unsigned int>(response_length));
        return false;
    }

    const uint16_t actual_crc = static_cast<uint16_t>(response[response_length - 2]) |
                                (static_cast<uint16_t>(response[response_length - 1]) << 8);
    const uint16_t expected_crc = hal_rs485_modbus_crc16(response, response_length - 2);
    if (actual_crc != expected_crc)
    {
        Serial.printf("Modbus CRC mismatch: actual=0x%04X expected=0x%04X\n", actual_crc, expected_crc);
        return false;
    }
    if (response[0] != slave_id)
    {
        Serial.printf("Modbus slave mismatch: actual=%u expected=%u\n",
                      static_cast<unsigned int>(response[0]),
                      static_cast<unsigned int>(slave_id));
        return false;
    }
    if (response[1] == (function_code | 0x80))
    {
        Serial.printf("Modbus exception: function=0x%02X code=0x%02X\n", function_code, response[2]);
        return false;
    }
    if (response[1] != function_code || response[2] != register_count * 2 || response_length < expected_length)
    {
        Serial.printf("Malformed Modbus response: function=0x%02X byte_count=%u length=%u expected=%u\n",
                      response[1],
                      static_cast<unsigned int>(response[2]),
                      static_cast<unsigned int>(response_length),
                      static_cast<unsigned int>(expected_length));
        return false;
    }

    for (uint16_t i = 0; i < register_count; ++i)
    {
        const size_t offset = 3 + static_cast<size_t>(i) * 2;
        out_registers[i] = (static_cast<uint16_t>(response[offset]) << 8) | response[offset + 1];
    }
    return true;
}

bool hal_rs485_modbus_write_single_register(uint8_t slave_id,
                                            uint16_t register_address,
                                            uint16_t value)
{
    if (!s_ready || s_serial == nullptr || slave_id == 0 || slave_id > 247)
    {
        return false;
    }

    while (s_serial->available() > 0)
    {
        s_serial->read();
    }

    uint8_t request[8] = {
        slave_id,
        0x06,
        static_cast<uint8_t>(register_address >> 8),
        static_cast<uint8_t>(register_address & 0xFF),
        static_cast<uint8_t>(value >> 8),
        static_cast<uint8_t>(value & 0xFF),
        0,
        0,
    };
    const uint16_t request_crc = hal_rs485_modbus_crc16(request, 6);
    request[6] = static_cast<uint8_t>(request_crc & 0xFF);
    request[7] = static_cast<uint8_t>(request_crc >> 8);

    hal_rs485_set_transmit(true);
    delayMicroseconds(50);
    const size_t transmitted = s_serial->write(request, sizeof(request));
    s_serial->flush();
    delayMicroseconds(s_config.turnaround_delay_us);
    hal_rs485_set_transmit(false);
    if (transmitted != sizeof(request))
    {
        Serial.println("Modbus FC06 transmit failed");
        return false;
    }

    uint8_t response[8] = {};
    size_t response_length = 0;
    const uint32_t start_ms = millis();
    while (millis() - start_ms < s_config.response_timeout_ms)
    {
        while (s_serial->available() > 0 && response_length < sizeof(response))
        {
            response[response_length++] = static_cast<uint8_t>(s_serial->read());
        }
        if (response_length >= sizeof(response) ||
            (response_length >= 5 && response[1] == 0x86))
        {
            break;
        }
        delay(1);
    }

    if (response_length != sizeof(response))
    {
        Serial.printf("Modbus FC06 response length error: slave=%u register=0x%04X bytes=%u\n",
                      static_cast<unsigned int>(slave_id),
                      register_address,
                      static_cast<unsigned int>(response_length));
        return false;
    }
    const uint16_t actual_crc = static_cast<uint16_t>(response[6]) |
                                (static_cast<uint16_t>(response[7]) << 8);
    const uint16_t expected_crc = hal_rs485_modbus_crc16(response, 6);
    if (actual_crc != expected_crc)
    {
        Serial.printf("Modbus FC06 CRC mismatch: actual=0x%04X expected=0x%04X\n",
                      actual_crc,
                      expected_crc);
        return false;
    }
    if (memcmp(request, response, sizeof(request)) != 0)
    {
        Serial.printf("Modbus FC06 echo mismatch: slave=%u register=0x%04X value=%u\n",
                      static_cast<unsigned int>(slave_id),
                      register_address,
                      static_cast<unsigned int>(value));
        return false;
    }
    return true;
}

uint16_t hal_rs485_modbus_crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i)
    {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit)
        {
            if ((crc & 0x0001) != 0)
            {
                crc = (crc >> 1) ^ 0xA001;
            }
            else
            {
                crc >>= 1;
            }
        }
    }
    return crc;
}
