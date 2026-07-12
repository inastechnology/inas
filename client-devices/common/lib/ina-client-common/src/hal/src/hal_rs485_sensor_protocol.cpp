#include "hal_rs485_sensor_protocol.h"

#include <Arduino.h>

#include "hal_rs485_bus.h"

static float scaled_tenths(uint16_t value)
{
    return static_cast<float>(value) / 10.0f;
}

static float scaled_signed_tenths(uint16_t value)
{
    return static_cast<float>(static_cast<int16_t>(value)) / 10.0f;
}

bool hal_rs485_soil_sensor_read(const hal_rs485_soil_sensor_config_t *config,
                                hal_rs485_soil_sample_t *out_sample)
{
    if (out_sample != nullptr)
    {
        *out_sample = {};
    }
    if (config == nullptr || out_sample == nullptr || !config->enabled)
    {
        return false;
    }

    uint16_t registers[7] = {};
    const hal_rs485_register_request_t request = {
        config->modbus_slave_id,
        config->modbus_function,
        config->start_register,
        7,
    };
    hal_rs485_register_result_t result = {};
    const bool ok = hal_rs485_bus_read_registers(&request, registers, 7, &result);
    if (!ok)
    {
        Serial.printf("RS485 soil sensor read failed: slave=%u function=0x%02X start=0x%04X elapsed=%lu ms\n",
                      static_cast<unsigned int>(request.slave_id),
                      request.function_code,
                      request.start_register,
                      static_cast<unsigned long>(result.elapsed_ms));
        return false;
    }

    out_sample->ok = true;
    out_sample->raw_moisture = registers[0];
    out_sample->raw_temperature = registers[1];
    out_sample->raw_ec = registers[2];
    out_sample->raw_ph = registers[3];
    out_sample->raw_nitrogen = registers[4];
    out_sample->raw_phosphorus = registers[5];
    out_sample->raw_potassium = registers[6];
    out_sample->moisture_percent = scaled_tenths(out_sample->raw_moisture);
    out_sample->temperature_c = scaled_signed_tenths(out_sample->raw_temperature);
    out_sample->ec_us_cm = static_cast<float>(out_sample->raw_ec);
    out_sample->ph = scaled_tenths(out_sample->raw_ph);
    out_sample->n_mg_kg = static_cast<float>(out_sample->raw_nitrogen);
    out_sample->p_mg_kg = static_cast<float>(out_sample->raw_phosphorus);
    out_sample->k_mg_kg = static_cast<float>(out_sample->raw_potassium);
    return true;
}

bool hal_rs485_par_sensor_read(const hal_rs485_par_sensor_config_t *config,
                               hal_rs485_par_sample_t *out_sample)
{
    if (out_sample != nullptr)
    {
        *out_sample = {};
    }
    if (config == nullptr || out_sample == nullptr || !config->enabled)
    {
        return false;
    }

    uint16_t registers[1] = {};
    const hal_rs485_register_request_t request = {
        config->modbus_slave_id,
        config->modbus_function,
        config->register_address,
        1,
    };
    hal_rs485_register_result_t result = {};
    const bool ok = hal_rs485_bus_read_registers(&request, registers, 1, &result);
    if (!ok)
    {
        Serial.printf("RS485 PAR sensor read failed: slave=%u function=0x%02X register=0x%04X elapsed=%lu ms\n",
                      static_cast<unsigned int>(request.slave_id),
                      request.function_code,
                      request.start_register,
                      static_cast<unsigned long>(result.elapsed_ms));
        return false;
    }

    out_sample->ok = true;
    out_sample->raw_par = registers[0];
    out_sample->par_umol_m2_s = static_cast<float>(out_sample->raw_par) * config->scale;
    return true;
}
