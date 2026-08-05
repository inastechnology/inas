#ifndef __HAL_RS485_SENSOR_PROTOCOL_H__
#define __HAL_RS485_SENSOR_PROTOCOL_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C"
{
#endif

typedef struct
{
    bool enabled;
    uint8_t modbus_slave_id;
    uint8_t modbus_function;
    uint16_t start_register;
} hal_rs485_soil_sensor_config_t;

typedef struct
{
    bool ok;
    uint16_t raw_moisture;
    uint16_t raw_temperature;
    uint16_t raw_ec;
    uint16_t raw_ph;
    uint16_t raw_nitrogen;
    uint16_t raw_phosphorus;
    uint16_t raw_potassium;
    float moisture_percent;
    float temperature_c;
    float ec_us_cm;
    float ph;
    float n_mg_kg;
    float p_mg_kg;
    float k_mg_kg;
} hal_rs485_soil_sample_t;

typedef struct
{
    bool enabled;
    uint8_t modbus_slave_id;
    uint8_t modbus_function;
    uint16_t register_address;
    float scale;
} hal_rs485_par_sensor_config_t;

typedef struct
{
    bool ok;
    uint16_t raw_par;
    float par_umol_m2_s;
} hal_rs485_par_sample_t;

bool hal_rs485_soil_sensor_read(const hal_rs485_soil_sensor_config_t *config,
                                hal_rs485_soil_sample_t *out_sample);
bool hal_rs485_soil_moisture_temperature_ec_sensor_read(
    const hal_rs485_soil_sensor_config_t *config,
    hal_rs485_soil_sample_t *out_sample);
bool hal_rs485_par_sensor_read(const hal_rs485_par_sensor_config_t *config,
                               hal_rs485_par_sample_t *out_sample);

#ifdef __cplusplus
}
#endif

#endif // __HAL_RS485_SENSOR_PROTOCOL_H__
