#include "hal_rs485_modbus.h"

#include <Arduino.h>
#include <HardwareSerial.h>
#include <string.h>

#if APP_RS485_USE_IDF_HALF_DUPLEX != 0
#include "driver/uart.h"
#endif

#if defined(CONFIG_IDF_TARGET_ESP32C6)
#include "hal/uart_ll.h"
#endif

static HardwareSerial *s_serial = nullptr;
static uint8_t s_uart_num = 0xFF;
static hal_rs485_modbus_config_t s_config = {};
static bool s_ready = false;
static bool s_diagnostics = false;
static bool s_has_completed_transaction = false;
static uint32_t s_last_transaction_finished_ms = 0;

static void hal_rs485_set_transmit(bool enabled)
{
#if APP_RS485_USE_IDF_HALF_DUPLEX != 0
    (void)enabled;
#else
    if (s_config.de_pin >= 0)
    {
        digitalWrite(s_config.de_pin, enabled ? HIGH : LOW);
    }
#endif
}

static const char *hal_rs485_level_name(int level)
{
    return level == HIGH ? "HIGH" : "LOW";
}

static void hal_rs485_wait_inter_request()
{
    if (!s_has_completed_transaction ||
        APP_RS485_INTER_REQUEST_DELAY_MS == 0)
    {
        return;
    }
    const uint32_t elapsed_ms =
        millis() - s_last_transaction_finished_ms;
    if (elapsed_ms < APP_RS485_INTER_REQUEST_DELAY_MS)
    {
        delay(APP_RS485_INTER_REQUEST_DELAY_MS - elapsed_ms);
    }
}

static void hal_rs485_mark_transaction_finished()
{
    s_last_transaction_finished_ms = millis();
    s_has_completed_transaction = true;
}

static void hal_rs485_print_bytes(
    const uint8_t *data,
    size_t length)
{
    if (data == nullptr || length == 0)
    {
        Serial.print("<none>");
        return;
    }
    for (size_t i = 0; i < length; ++i)
    {
        if (i > 0)
        {
            Serial.print(' ');
        }
        Serial.printf("%02X", data[i]);
    }
}

static void hal_rs485_log_tx(
    uint8_t slave_id,
    uint8_t function_code,
    uint16_t register_address,
    uint16_t register_count_or_value,
    const uint8_t *request,
    size_t request_length,
    size_t transmitted,
    int direction_tx_level,
    int direction_rx_level)
{
    if (!s_diagnostics)
    {
        return;
    }
    Serial.printf(
        "[RS485 TX] uart=%u baud=%lu id=%u written=%u/%u ",
        static_cast<unsigned int>(s_config.uart_num),
        static_cast<unsigned long>(s_config.baud),
        static_cast<unsigned int>(slave_id),
        static_cast<unsigned int>(transmitted),
        static_cast<unsigned int>(request_length));
#if APP_RS485_USE_IDF_HALF_DUPLEX != 0
    (void)direction_tx_level;
    (void)direction_rx_level;
    Serial.print("en_control=idf_uart_rts ");
#else
    Serial.printf(
        "en_readback=%s->%s ",
        hal_rs485_level_name(direction_tx_level),
        hal_rs485_level_name(direction_rx_level));
#endif
    Serial.printf(
        "function=0x%02X register=0x%04X value_or_count=%u bytes=",
        function_code,
        register_address,
        static_cast<unsigned int>(register_count_or_value));
    hal_rs485_print_bytes(request, request_length);
    Serial.println();
}

static void hal_rs485_log_rx(
    uint8_t slave_id,
    uint8_t function_code,
    size_t expected_length,
    const uint8_t *response,
    size_t response_length)
{
    if (!s_diagnostics)
    {
        return;
    }
    Serial.printf(
        "[RS485 RX] uart=%u baud=%lu id=%u function=0x%02X received=%u expected=%u bytes=",
        static_cast<unsigned int>(s_config.uart_num),
        static_cast<unsigned long>(s_config.baud),
        static_cast<unsigned int>(slave_id),
        function_code,
        static_cast<unsigned int>(response_length),
        static_cast<unsigned int>(expected_length));
    hal_rs485_print_bytes(response, response_length);
    Serial.println();
}

static bool hal_rs485_loopback_exchange(bool internal_loopback)
{
    if (!s_ready || s_serial == nullptr)
    {
        return false;
    }
#if !defined(CONFIG_IDF_TARGET_ESP32C6)
    if (internal_loopback)
    {
        Serial.println(
            "[RS485 LOOPBACK] mode=internal result=UNSUPPORTED");
        return false;
    }
#endif

    static constexpr uint8_t pattern[] = {
        0x55, 0xAA, 0x00, 0xFF, 0xC3, 0x3C, 0x96, 0x69,
    };
    uint8_t response[sizeof(pattern)] = {};
    size_t response_length = 0;

    hal_rs485_set_transmit(false);
    while (s_serial->available() > 0)
    {
        s_serial->read();
    }

#if defined(CONFIG_IDF_TARGET_ESP32C6)
    if (internal_loopback)
    {
        uart_ll_set_loop_back(
            UART_LL_GET_HW(s_config.uart_num), true);
    }
#endif

    const size_t transmitted =
        s_serial->write(pattern, sizeof(pattern));
    s_serial->flush();
    const uint32_t started_ms = millis();
    while (millis() - started_ms < 100 &&
           response_length < sizeof(response))
    {
        while (s_serial->available() > 0 &&
               response_length < sizeof(response))
        {
            response[response_length++] =
                static_cast<uint8_t>(s_serial->read());
        }
        delay(1);
    }

#if defined(CONFIG_IDF_TARGET_ESP32C6)
    if (internal_loopback)
    {
        uart_ll_set_loop_back(
            UART_LL_GET_HW(s_config.uart_num), false);
    }
#endif

    const bool passed =
        transmitted == sizeof(pattern) &&
        response_length == sizeof(pattern) &&
        memcmp(pattern, response, sizeof(pattern)) == 0;
    Serial.printf(
        "[RS485 LOOPBACK] mode=%s uart=%u baud=%lu written=%u/%u received=%u/%u result=%s bytes=",
        internal_loopback ? "internal" : "external_d6_d7",
        static_cast<unsigned int>(s_config.uart_num),
        static_cast<unsigned long>(s_config.baud),
        static_cast<unsigned int>(transmitted),
        static_cast<unsigned int>(sizeof(pattern)),
        static_cast<unsigned int>(response_length),
        static_cast<unsigned int>(sizeof(pattern)),
        passed ? "PASS" : "FAIL");
    hal_rs485_print_bytes(response, response_length);
    Serial.println();
    return passed;
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

    // ESP-IDF 5.x can leave UART RX unable to receive on some targets unless
    // the pin is first configured as a pulled-up GPIO input. Modbus RTU is
    // idle-high, so keeping the pull-up enabled is also the safe idle state.
    if (APP_RS485_RX_PULLUP != 0)
    {
        pinMode(s_config.rx_pin, INPUT_PULLUP);
        delay(1);
    }

    s_serial->begin(s_config.baud, SERIAL_8N1, s_config.rx_pin, s_config.tx_pin);
#if APP_RS485_USE_IDF_HALF_DUPLEX != 0
    if (s_config.de_pin < 0)
    {
        Serial.println(
            "RS485 IDF half-duplex mode requires an RTS/EN pin");
        s_serial->end();
        return false;
    }
    const uart_port_t uart_port =
        static_cast<uart_port_t>(s_config.uart_num);
    const esp_err_t pin_result = uart_set_pin(
        uart_port,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE,
        s_config.de_pin,
        UART_PIN_NO_CHANGE);
    const esp_err_t flow_result = uart_set_hw_flow_ctrl(
        uart_port,
        UART_HW_FLOWCTRL_DISABLE,
        0);
    const esp_err_t mode_result = uart_set_mode(
        uart_port,
        UART_MODE_RS485_HALF_DUPLEX);
    if (pin_result != ESP_OK ||
        flow_result != ESP_OK ||
        mode_result != ESP_OK)
    {
        Serial.printf(
            "RS485 IDF half-duplex setup failed: pin=%s flow=%s mode=%s\n",
            esp_err_to_name(pin_result),
            esp_err_to_name(flow_result),
            esp_err_to_name(mode_result));
        s_serial->end();
        pinMode(s_config.de_pin, OUTPUT);
        digitalWrite(s_config.de_pin, LOW);
        return false;
    }
#endif
    if (APP_RS485_INIT_SETTLE_MS > 0)
    {
        delay(APP_RS485_INIT_SETTLE_MS);
    }
    s_has_completed_transaction = false;
    s_ready = true;
    const int rx_idle_level = digitalRead(s_config.rx_pin);
    Serial.printf("RS485 Modbus initialized: uart=%u baud=%lu tx=%d rx=%d de=%d direction=%s timeout=%lu ms init_settle=%lu ms inter_request=%lu ms rx_pullup=%s rx_idle=%s\n",
                  static_cast<unsigned int>(s_config.uart_num),
                  static_cast<unsigned long>(s_config.baud),
                  s_config.tx_pin,
                  s_config.rx_pin,
                  s_config.de_pin,
                  APP_RS485_USE_IDF_HALF_DUPLEX != 0
                      ? "idf_uart_rts"
                      : "manual_gpio",
                  static_cast<unsigned long>(s_config.response_timeout_ms),
                  static_cast<unsigned long>(APP_RS485_INIT_SETTLE_MS),
                  static_cast<unsigned long>(APP_RS485_INTER_REQUEST_DELAY_MS),
                  APP_RS485_RX_PULLUP != 0 ? "true" : "false",
                  hal_rs485_level_name(rx_idle_level));
    if (rx_idle_level != HIGH)
    {
        Serial.println(
            "RS485 RX warning: idle level is LOW; check module power, "
            "module TXD to MCU RX wiring, and A/B bus bias.");
    }
    return true;
}

void hal_rs485_modbus_deinit()
{
    if (s_serial != nullptr)
    {
#if APP_RS485_USE_IDF_HALF_DUPLEX != 0
        if (s_ready)
        {
            uart_set_mode(
                static_cast<uart_port_t>(s_config.uart_num),
                UART_MODE_UART);
        }
#endif
        s_serial->end();
    }
    if (s_config.de_pin >= 0)
    {
        pinMode(s_config.de_pin, OUTPUT);
        digitalWrite(s_config.de_pin, LOW);
    }
    s_ready = false;
    s_has_completed_transaction = false;
}

void hal_rs485_modbus_set_diagnostics(bool enabled)
{
    s_diagnostics = enabled;
}

bool hal_rs485_modbus_internal_loopback_test()
{
    return hal_rs485_loopback_exchange(true);
}

bool hal_rs485_modbus_external_loopback_test()
{
    return hal_rs485_loopback_exchange(false);
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

    hal_rs485_wait_inter_request();
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
    const int direction_tx_level =
        s_config.de_pin >= 0
            ? digitalRead(s_config.de_pin)
            : LOW;
#if APP_RS485_USE_IDF_HALF_DUPLEX == 0
    delayMicroseconds(APP_RS485_DRIVER_ENABLE_DELAY_US);
#endif
    const size_t transmitted =
        s_serial->write(request, sizeof(request));
    s_serial->flush();
#if APP_RS485_USE_IDF_HALF_DUPLEX == 0
    delayMicroseconds(s_config.turnaround_delay_us);
#endif
    hal_rs485_set_transmit(false);
    const int direction_rx_level =
        s_config.de_pin >= 0
            ? digitalRead(s_config.de_pin)
            : LOW;
    hal_rs485_log_tx(
        slave_id,
        function_code,
        start_register,
        register_count,
        request,
        sizeof(request),
        transmitted,
        direction_tx_level,
        direction_rx_level);
    if (transmitted != sizeof(request))
    {
        hal_rs485_mark_transaction_finished();
        Serial.printf(
            "Modbus transmit failed: slave=%u written=%u/%u\n",
            static_cast<unsigned int>(slave_id),
            static_cast<unsigned int>(transmitted),
            static_cast<unsigned int>(sizeof(request)));
        return false;
    }

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
    hal_rs485_mark_transaction_finished();
    hal_rs485_log_rx(
        slave_id,
        function_code,
        expected_length,
        response,
        response_length);

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

    hal_rs485_wait_inter_request();
    hal_rs485_set_transmit(true);
    const int direction_tx_level =
        s_config.de_pin >= 0
            ? digitalRead(s_config.de_pin)
            : LOW;
#if APP_RS485_USE_IDF_HALF_DUPLEX == 0
    delayMicroseconds(APP_RS485_DRIVER_ENABLE_DELAY_US);
#endif
    const size_t transmitted = s_serial->write(request, sizeof(request));
    s_serial->flush();
#if APP_RS485_USE_IDF_HALF_DUPLEX == 0
    delayMicroseconds(s_config.turnaround_delay_us);
#endif
    hal_rs485_set_transmit(false);
    const int direction_rx_level =
        s_config.de_pin >= 0
            ? digitalRead(s_config.de_pin)
            : LOW;
    hal_rs485_log_tx(
        slave_id,
        0x06,
        register_address,
        value,
        request,
        sizeof(request),
        transmitted,
        direction_tx_level,
        direction_rx_level);
    if (transmitted != sizeof(request))
    {
        hal_rs485_mark_transaction_finished();
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
    hal_rs485_mark_transaction_finished();
    hal_rs485_log_rx(
        slave_id,
        0x06,
        sizeof(response),
        response,
        response_length);

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
