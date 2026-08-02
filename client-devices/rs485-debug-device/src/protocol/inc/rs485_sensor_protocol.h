#ifndef INAS_DEBUG_RS485_SENSOR_PROTOCOL_H
#define INAS_DEBUG_RS485_SENSOR_PROTOCOL_H

#include <stdint.h>

#include "hal_rs485_modbus.h"

typedef enum
{
    RS485_SENSOR_SOIL,
    RS485_SENSOR_PAR,
} rs485_sensor_type_t;

typedef struct
{
    float moisture_percent;
    float temperature_c;
    uint16_t ec_us_cm;
    float ph;
    uint16_t nitrogen_mg_kg;
    uint16_t phosphorus_mg_kg;
    uint16_t potassium_mg_kg;
} rs485_soil_sample_t;

typedef struct
{
    uint16_t par_umol_m2_s;
} rs485_par_sample_t;

typedef struct
{
    uint16_t ec_factor;
    uint16_t salinity_factor;
    uint16_t tds_factor;
} rs485_soil_signature_t;

const char *rs485_sensor_type_name(rs485_sensor_type_t type);
hal_rs485_modbus_result_t rs485_sensor_primary_register_read(
    uint8_t slave_id,
    uint16_t *out_value);
hal_rs485_modbus_result_t rs485_soil_sensor_read(uint8_t slave_id,
                                                 rs485_soil_sample_t *out_sample);
hal_rs485_modbus_result_t rs485_soil_signature_read(
    uint8_t slave_id,
    rs485_soil_signature_t *out_signature);
hal_rs485_modbus_result_t rs485_par_sensor_read(uint8_t slave_id,
                                                rs485_par_sample_t *out_sample);
bool rs485_soil_sample_has_secondary_values(const rs485_soil_sample_t *sample);
bool rs485_soil_signature_is_present(const rs485_soil_signature_t *signature);
rs485_sensor_type_t rs485_sensor_classify(bool soil_registers_supported,
                                          bool soil_secondary_values_present,
                                          bool soil_signature_present);

#endif
