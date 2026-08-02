#include "rs485_sensor_protocol.h"

namespace
{

constexpr rs485_sensor_type_t classifySensorProfile(
    bool soil_registers_supported,
    bool soil_secondary_values_present,
    bool soil_signature_present)
{
    return soil_registers_supported &&
                   (soil_secondary_values_present || soil_signature_present)
               ? RS485_SENSOR_SOIL
               : RS485_SENSOR_PAR;
}

static_assert(
    classifySensorProfile(true, false, false) == RS485_SENSOR_PAR,
    "A PAR sensor returning zeros for extra registers must not be classified as soil");
static_assert(
    classifySensorProfile(true, false, true) == RS485_SENSOR_SOIL,
    "A CWT soil configuration signature must identify a soil sensor");
static_assert(
    classifySensorProfile(true, true, false) == RS485_SENSOR_SOIL,
    "Non-zero soil secondary measurements must identify a soil sensor");

} // namespace

const char *rs485_sensor_type_name(rs485_sensor_type_t type)
{
    return type == RS485_SENSOR_SOIL
               ? "ComWinTop CWT-SOIL"
               : "DFRobot SEN0641 PAR";
}

hal_rs485_modbus_result_t rs485_sensor_primary_register_read(
    uint8_t slave_id,
    uint16_t *out_value)
{
    return hal_rs485_modbus_read_holding_registers(
        slave_id, 0x0000, 1, out_value, 1);
}

hal_rs485_modbus_result_t rs485_soil_sensor_read(uint8_t slave_id,
                                                 rs485_soil_sample_t *out_sample)
{
    uint16_t values[7] = {};
    hal_rs485_modbus_result_t result =
        hal_rs485_modbus_read_holding_registers(slave_id, 0x0000, 7, values, 7);
    if (result.status != HAL_RS485_MODBUS_OK || out_sample == nullptr)
    {
        return result;
    }

    out_sample->moisture_percent = values[0] * 0.1F;
    out_sample->temperature_c = static_cast<int16_t>(values[1]) * 0.1F;
    out_sample->ec_us_cm = values[2];
    out_sample->ph = values[3] * 0.1F;
    out_sample->nitrogen_mg_kg = values[4];
    out_sample->phosphorus_mg_kg = values[5];
    out_sample->potassium_mg_kg = values[6];
    return result;
}

hal_rs485_modbus_result_t rs485_soil_signature_read(
    uint8_t slave_id,
    rs485_soil_signature_t *out_signature)
{
    uint16_t values[3] = {};
    hal_rs485_modbus_result_t result =
        hal_rs485_modbus_read_holding_registers(slave_id, 0x0022, 3, values, 3);
    if (result.status == HAL_RS485_MODBUS_OK && out_signature != nullptr)
    {
        out_signature->ec_factor = values[0];
        out_signature->salinity_factor = values[1];
        out_signature->tds_factor = values[2];
    }
    return result;
}

hal_rs485_modbus_result_t rs485_par_sensor_read(uint8_t slave_id,
                                                rs485_par_sample_t *out_sample)
{
    uint16_t value = 0;
    hal_rs485_modbus_result_t result =
        rs485_sensor_primary_register_read(slave_id, &value);
    if (result.status == HAL_RS485_MODBUS_OK && out_sample != nullptr)
    {
        out_sample->par_umol_m2_s = value;
    }
    return result;
}

bool rs485_soil_sample_has_secondary_values(const rs485_soil_sample_t *sample)
{
    return sample != nullptr &&
           (sample->temperature_c != 0.0F ||
            sample->ec_us_cm != 0 ||
            sample->ph != 0.0F ||
            sample->nitrogen_mg_kg != 0 ||
            sample->phosphorus_mg_kg != 0 ||
            sample->potassium_mg_kg != 0);
}

bool rs485_soil_signature_is_present(const rs485_soil_signature_t *signature)
{
    return signature != nullptr &&
           (signature->salinity_factor != 0 || signature->tds_factor != 0);
}

rs485_sensor_type_t rs485_sensor_classify(bool soil_registers_supported,
                                          bool soil_secondary_values_present,
                                          bool soil_signature_present)
{
    return classifySensorProfile(soil_registers_supported,
                                 soil_secondary_values_present,
                                 soil_signature_present);
}
