#include "app.h"

#include <Arduino.h>

#include <array>

#include "hal_rs485_modbus.h"
#include "rs485_sensor_protocol.h"

#ifndef RS485_UART_NUM
#define RS485_UART_NUM 1
#endif
#ifndef RS485_TX_PIN
#define RS485_TX_PIN 43
#endif
#ifndef RS485_RX_PIN
#define RS485_RX_PIN 44
#endif
#ifndef RS485_DE_RE_PIN
#define RS485_DE_RE_PIN 5
#endif
#ifndef RS485_SCAN_ID_MIN
#define RS485_SCAN_ID_MIN 1
#endif
#ifndef RS485_SCAN_ID_MAX
#define RS485_SCAN_ID_MAX 10
#endif
#ifndef RS485_RESPONSE_TIMEOUT_MS
#define RS485_RESPONSE_TIMEOUT_MS 120
#endif
#ifndef RS485_POLL_INTERVAL_MS
#define RS485_POLL_INTERVAL_MS 5000
#endif
#ifndef RS485_RESCAN_INTERVAL_MS
#define RS485_RESCAN_INTERVAL_MS 10000
#endif

namespace
{

constexpr uint32_t kDebugBaud = 115200;
constexpr uint8_t kFailureThreshold = 3;
constexpr uint32_t kInterRequestDelayMs = 30;
constexpr size_t kMaxDevices = 16;
constexpr std::array<uint32_t, 3> kBaudRates = {2400, 4800, 9600};

struct DetectedDevice
{
    rs485_sensor_type_t type = RS485_SENSOR_PAR;
    uint8_t slave_id = 0;
    uint32_t baud = 0;
    uint8_t consecutive_failures = 0;
};

std::array<DetectedDevice, kMaxDevices> s_devices = {};
size_t s_device_count = 0;
uint32_t s_active_baud = 0;
uint32_t s_last_poll_ms = 0;
uint32_t s_last_scan_ms = 0;

void printHexBytes(const uint8_t *bytes, size_t length)
{
    if (bytes == nullptr || length == 0)
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
        Serial.printf("%02X", static_cast<unsigned>(bytes[i]));
    }
}

void printTransaction(const char *profile,
                      uint32_t baud,
                      const hal_rs485_modbus_result_t &result)
{
    const unsigned expected_id =
        result.request_length > 0 ? static_cast<unsigned>(result.request[0]) : 0;

    Serial.printf("[TX] profile=\"%s\" baud=%lu id=%u written=%u/%u",
                  profile,
                  static_cast<unsigned long>(baud),
                  expected_id,
                  static_cast<unsigned>(result.transmitted_length),
                  static_cast<unsigned>(result.request_length));
    if (result.direction_tx_level >= 0 && result.direction_rx_level >= 0)
    {
        Serial.printf(" en_readback=%s->%s",
                      result.direction_tx_level == HIGH ? "HIGH" : "LOW",
                      result.direction_rx_level == HIGH ? "HIGH" : "LOW");
    }
    if (result.request_length >= 6)
    {
        const uint16_t start_register =
            (static_cast<uint16_t>(result.request[2]) << 8) | result.request[3];
        const uint16_t register_count =
            (static_cast<uint16_t>(result.request[4]) << 8) | result.request[5];
        Serial.printf(" function=0x%02X register=0x%04X count=%u",
                      static_cast<unsigned>(result.request[1]),
                      static_cast<unsigned>(start_register),
                      static_cast<unsigned>(register_count));
    }
    Serial.print(" bytes=");
    printHexBytes(result.request, result.request_length);
    Serial.println();

    Serial.printf("[RX] profile=\"%s\" baud=%lu id=%u received=%u expected=%u bytes=",
                  profile,
                  static_cast<unsigned long>(baud),
                  expected_id,
                  static_cast<unsigned>(result.received_length),
                  static_cast<unsigned>(result.expected_length));
    printHexBytes(result.response, result.received_length);
    Serial.println();

    Serial.printf("[RESULT] profile=\"%s\" baud=%lu id=%u status=%s",
                  profile,
                  static_cast<unsigned long>(baud),
                  expected_id,
                  hal_rs485_modbus_status_name(result.status));
    switch (result.status)
    {
    case HAL_RS485_MODBUS_TX_ERROR:
        Serial.printf(" written=%u expected=%u",
                      static_cast<unsigned>(result.transmitted_length),
                      static_cast<unsigned>(result.request_length));
        break;
    case HAL_RS485_MODBUS_SHORT_FRAME:
        Serial.printf(" received=%u minimum=5",
                      static_cast<unsigned>(result.received_length));
        break;
    case HAL_RS485_MODBUS_CRC_ERROR:
        Serial.printf(" calculated=0x%04X received=0x%04X",
                      static_cast<unsigned>(result.calculated_crc),
                      static_cast<unsigned>(result.received_crc));
        break;
    case HAL_RS485_MODBUS_EXCEPTION:
        Serial.printf(" exception=0x%02X",
                      static_cast<unsigned>(result.exception_code));
        break;
    case HAL_RS485_MODBUS_WRONG_SLAVE_ID:
        Serial.printf(" expected=%u received=%u",
                      expected_id,
                      static_cast<unsigned>(result.response[0]));
        break;
    case HAL_RS485_MODBUS_WRONG_FUNCTION:
        Serial.printf(" expected=0x%02X received=0x%02X",
                      static_cast<unsigned>(result.request[1]),
                      static_cast<unsigned>(result.response[1]));
        break;
    case HAL_RS485_MODBUS_WRONG_BYTE_COUNT:
    {
        const uint16_t register_count =
            (static_cast<uint16_t>(result.request[4]) << 8) | result.request[5];
        Serial.printf(" expected=%u received=%u",
                      static_cast<unsigned>(register_count * 2U),
                      static_cast<unsigned>(result.response[2]));
        break;
    }
    case HAL_RS485_MODBUS_LENGTH_MISMATCH:
        Serial.printf(" expected=%u received=%u",
                      static_cast<unsigned>(result.expected_length),
                      static_cast<unsigned>(result.received_length));
        break;
    case HAL_RS485_MODBUS_OK:
    case HAL_RS485_MODBUS_TIMEOUT:
    case HAL_RS485_MODBUS_MALFORMED:
        break;
    }
    Serial.println();
}

bool configureBus(uint32_t baud)
{
    if (s_active_baud == baud)
    {
        return true;
    }

    const hal_rs485_modbus_config_t config = {
        RS485_UART_NUM,
        RS485_TX_PIN,
        RS485_RX_PIN,
        RS485_DE_RE_PIN,
        baud,
        RS485_RESPONSE_TIMEOUT_MS,
        250,
    };
    if (!hal_rs485_modbus_init(&config))
    {
        return false;
    }
    s_active_baud = baud;
    return true;
}

bool deviceAlreadyRecorded(uint8_t slave_id, uint32_t baud)
{
    for (size_t i = 0; i < s_device_count; ++i)
    {
        if (s_devices[i].slave_id == slave_id && s_devices[i].baud == baud)
        {
            return true;
        }
    }
    return false;
}

void addDevice(rs485_sensor_type_t type,
               uint8_t slave_id,
               uint32_t baud,
               const char *reason,
               const char *confidence)
{
    if (s_device_count >= s_devices.size() || deviceAlreadyRecorded(slave_id, baud))
    {
        return;
    }

    DetectedDevice &device = s_devices[s_device_count++];
    device.type = type;
    device.slave_id = slave_id;
    device.baud = baud;
    device.consecutive_failures = 0;
    Serial.printf("[DETECTED] model=\"%s\" id=%u baud=%lu 8N1 reason=%s confidence=%s\n",
                  rs485_sensor_type_name(type),
                  static_cast<unsigned>(slave_id),
                  static_cast<unsigned long>(baud),
                  reason,
                  confidence);
}

void scanBus()
{
    s_device_count = 0;
    Serial.printf("\n[SCAN] baud=2400/4800/9600 id=%u..%u\n",
                  static_cast<unsigned>(RS485_SCAN_ID_MIN),
                  static_cast<unsigned>(RS485_SCAN_ID_MAX));
    Serial.println("[SCAN] Every connected device must have a unique Modbus ID.");

    for (const uint32_t baud : kBaudRates)
    {
        if (!configureBus(baud))
        {
            Serial.printf("[ERROR] Failed to initialize RS485 at %lu bps\n",
                          static_cast<unsigned long>(baud));
            continue;
        }
        Serial.printf("[SCAN] Testing %lu bps\n", static_cast<unsigned long>(baud));

        for (uint16_t id = RS485_SCAN_ID_MIN; id <= RS485_SCAN_ID_MAX; ++id)
        {
            uint16_t primary_value = 0;
            const hal_rs485_modbus_result_t primary_result =
                rs485_sensor_primary_register_read(static_cast<uint8_t>(id),
                                                   &primary_value);
            printTransaction("Primary register probe", baud, primary_result);
            if (primary_result.status != HAL_RS485_MODBUS_OK)
            {
                delay(kInterRequestDelayMs);
                continue;
            }

            delay(kInterRequestDelayMs);
            rs485_soil_sample_t soil = {};
            const hal_rs485_modbus_result_t soil_result =
                rs485_soil_sensor_read(static_cast<uint8_t>(id), &soil);
            printTransaction(rs485_sensor_type_name(RS485_SENSOR_SOIL), baud, soil_result);
            if (soil_result.status == HAL_RS485_MODBUS_EXCEPTION &&
                soil_result.exception_code == 0x02)
            {
                addDevice(RS485_SENSOR_PAR,
                          static_cast<uint8_t>(id),
                          baud,
                          "soil_registers_rejected",
                          "high");
                delay(kInterRequestDelayMs);
                continue;
            }
            if (soil_result.status != HAL_RS485_MODBUS_OK)
            {
                Serial.printf("[PROBE] id=%u baud=%lu status=inconclusive "
                              "reason=soil_measurement_%s primary=%u\n",
                              static_cast<unsigned>(id),
                              static_cast<unsigned long>(baud),
                              hal_rs485_modbus_status_name(soil_result.status),
                              static_cast<unsigned>(primary_value));
                delay(kInterRequestDelayMs);
                continue;
            }

            delay(kInterRequestDelayMs);
            rs485_soil_signature_t signature = {};
            const hal_rs485_modbus_result_t signature_result =
                rs485_soil_signature_read(static_cast<uint8_t>(id), &signature);
            printTransaction("CWT-SOIL signature", baud, signature_result);
            if (signature_result.status == HAL_RS485_MODBUS_EXCEPTION &&
                signature_result.exception_code == 0x02)
            {
                addDevice(RS485_SENSOR_PAR,
                          static_cast<uint8_t>(id),
                          baud,
                          "soil_signature_rejected",
                          "high");
                delay(kInterRequestDelayMs);
                continue;
            }
            if (signature_result.status != HAL_RS485_MODBUS_OK)
            {
                Serial.printf("[PROBE] id=%u baud=%lu status=inconclusive "
                              "reason=soil_signature_%s primary=%u\n",
                              static_cast<unsigned>(id),
                              static_cast<unsigned long>(baud),
                              hal_rs485_modbus_status_name(signature_result.status),
                              static_cast<unsigned>(primary_value));
                delay(kInterRequestDelayMs);
                continue;
            }

            const bool secondary_values_present =
                rs485_soil_sample_has_secondary_values(&soil);
            const bool soil_signature_present =
                rs485_soil_signature_is_present(&signature);
            const rs485_sensor_type_t detected_type =
                rs485_sensor_classify(true,
                                      secondary_values_present,
                                      soil_signature_present);
            if (detected_type == RS485_SENSOR_SOIL)
            {
                addDevice(RS485_SENSOR_SOIL,
                          static_cast<uint8_t>(id),
                          baud,
                          soil_signature_present
                              ? "cwt_configuration_signature"
                              : "soil_secondary_values",
                          soil_signature_present ? "high" : "medium");
            }
            else
            {
                addDevice(RS485_SENSOR_PAR,
                          static_cast<uint8_t>(id),
                          baud,
                          "no_soil_signature",
                          "heuristic");
            }
            delay(kInterRequestDelayMs);
        }
    }

    Serial.printf("[SCAN] Complete: %u supported device(s)\n",
                  static_cast<unsigned>(s_device_count));
    for (size_t i = 0; i < s_device_count; ++i)
    {
        Serial.printf("  #%u model=\"%s\" id=%u baud=%lu\n",
                      static_cast<unsigned>(i + 1),
                      rs485_sensor_type_name(s_devices[i].type),
                      static_cast<unsigned>(s_devices[i].slave_id),
                      static_cast<unsigned long>(s_devices[i].baud));
    }
    if (s_device_count == 0)
    {
        Serial.printf("[SCAN] No device; retrying in %lu ms\n",
                      static_cast<unsigned long>(RS485_RESCAN_INTERVAL_MS));
    }
    s_last_scan_ms = millis();
    s_last_poll_ms = millis();
}

void printReadError(DetectedDevice &device, const hal_rs485_modbus_result_t &result)
{
    ++device.consecutive_failures;
    Serial.printf("[ERROR] model=\"%s\" id=%u baud=%lu status=%s",
                  rs485_sensor_type_name(device.type),
                  static_cast<unsigned>(device.slave_id),
                  static_cast<unsigned long>(device.baud),
                  hal_rs485_modbus_status_name(result.status));
    if (result.status == HAL_RS485_MODBUS_EXCEPTION)
    {
        Serial.printf(" exception=0x%02X", result.exception_code);
    }
    Serial.printf(" received=%u failure=%u/%u\n",
                  static_cast<unsigned>(result.received_length),
                  static_cast<unsigned>(device.consecutive_failures),
                  static_cast<unsigned>(kFailureThreshold));
}

void pollDevice(DetectedDevice &device)
{
    if (!configureBus(device.baud))
    {
        hal_rs485_modbus_result_t result = {};
        result.status = HAL_RS485_MODBUS_MALFORMED;
        printReadError(device, result);
        return;
    }

    if (device.type == RS485_SENSOR_SOIL)
    {
        rs485_soil_sample_t sample = {};
        const hal_rs485_modbus_result_t result =
            rs485_soil_sensor_read(device.slave_id, &sample);
        printTransaction(rs485_sensor_type_name(device.type), device.baud, result);
        if (result.status != HAL_RS485_MODBUS_OK)
        {
            printReadError(device, result);
            return;
        }
        device.consecutive_failures = 0;
        Serial.printf("[DATA] model=\"%s\" id=%u baud=%lu moisture=%.1f %% "
                      "temperature=%.1f C EC=%u uS/cm pH=%.1f N=%u mg/kg "
                      "P=%u mg/kg K=%u mg/kg\n",
                      rs485_sensor_type_name(device.type),
                      static_cast<unsigned>(device.slave_id),
                      static_cast<unsigned long>(device.baud),
                      sample.moisture_percent,
                      sample.temperature_c,
                      static_cast<unsigned>(sample.ec_us_cm),
                      sample.ph,
                      static_cast<unsigned>(sample.nitrogen_mg_kg),
                      static_cast<unsigned>(sample.phosphorus_mg_kg),
                      static_cast<unsigned>(sample.potassium_mg_kg));
        return;
    }

    rs485_par_sample_t sample = {};
    const hal_rs485_modbus_result_t result =
        rs485_par_sensor_read(device.slave_id, &sample);
    printTransaction(rs485_sensor_type_name(device.type), device.baud, result);
    if (result.status != HAL_RS485_MODBUS_OK)
    {
        printReadError(device, result);
        return;
    }
    device.consecutive_failures = 0;
    Serial.printf("[DATA] model=\"%s\" id=%u baud=%lu PAR=%u umol/m2/s\n",
                  rs485_sensor_type_name(device.type),
                  static_cast<unsigned>(device.slave_id),
                  static_cast<unsigned long>(device.baud),
                  static_cast<unsigned>(sample.par_umol_m2_s));
}

void pollDevices()
{
    bool rescan_required = false;
    Serial.printf("\n[POLL] Reading %u device(s)\n", static_cast<unsigned>(s_device_count));
    for (size_t i = 0; i < s_device_count; ++i)
    {
        pollDevice(s_devices[i]);
        rescan_required |= s_devices[i].consecutive_failures >= kFailureThreshold;
        delay(kInterRequestDelayMs);
    }
    s_last_poll_ms = millis();
    if (rescan_required)
    {
        Serial.println("[POLL] Repeated read failure; rescanning bus");
        scanBus();
    }
}

} // namespace

bool app_init()
{
    Serial.begin(kDebugBaud);
    const uint32_t wait_started_ms = millis();
    while (!Serial && millis() - wait_started_ms < 5000)
    {
        delay(10);
    }

    Serial.println("\nINAS ESP32-S3 RS485 debugger");
    Serial.printf("USB=%lu TX=GPIO%d RX=GPIO%d EN=GPIO%d (HIGH=TX LOW=RX)\n",
                  static_cast<unsigned long>(kDebugBaud),
                  RS485_TX_PIN,
                  RS485_RX_PIN,
                  RS485_DE_RE_PIN);
    Serial.println("Module wiring: GPIO43/TX->TXD GPIO44/RX<-RXD GPIO5->EN");
    Serial.println("Supported: ComWinTop CWT-SOIL, DFRobot SEN0641 PAR");
    scanBus();
    return true;
}

void app_loop()
{
    const uint32_t now = millis();
    if (s_device_count == 0)
    {
        if (now - s_last_scan_ms >= RS485_RESCAN_INTERVAL_MS)
        {
            scanBus();
        }
        delay(10);
        return;
    }
    if (now - s_last_poll_ms >= RS485_POLL_INTERVAL_MS)
    {
        pollDevices();
    }
    delay(10);
}
