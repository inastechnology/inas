#pragma once

#include <Arduino.h>
#include <stdint.h>

#ifndef APP_ENV_PAR_ENABLED
#define APP_ENV_PAR_ENABLED 1
#endif

#ifndef APP_ENV_PAR_MODBUS_SLAVE_ID
#ifdef APP_ENV_MODBUS_SLAVE_ID
#define APP_ENV_PAR_MODBUS_SLAVE_ID APP_ENV_MODBUS_SLAVE_ID
#else
#define APP_ENV_PAR_MODBUS_SLAVE_ID 1
#endif
#endif

#ifndef APP_ENV_PAR_MODBUS_FUNCTION
#ifdef APP_ENV_MODBUS_FUNCTION
#define APP_ENV_PAR_MODBUS_FUNCTION APP_ENV_MODBUS_FUNCTION
#else
#define APP_ENV_PAR_MODBUS_FUNCTION 3
#endif
#endif

#ifndef APP_ENV_PAR_REGISTER
#define APP_ENV_PAR_REGISTER 0
#endif

#ifndef APP_ENV_PAR_SCALE
#define APP_ENV_PAR_SCALE 1.0f
#endif

#ifndef APP_ENV_SOIL_RS485_ENABLED
#define APP_ENV_SOIL_RS485_ENABLED 0
#endif

#ifndef APP_ENV_SOIL_MODBUS_SLAVE_ID
#define APP_ENV_SOIL_MODBUS_SLAVE_ID 2
#endif

#ifndef APP_ENV_SOIL_MODBUS_FUNCTION
#define APP_ENV_SOIL_MODBUS_FUNCTION 4
#endif

#ifndef APP_ENV_SOIL_MODBUS_START_REGISTER
#define APP_ENV_SOIL_MODBUS_START_REGISTER 0
#endif

#ifndef APP_ENV_SLEEP_SEC
#define APP_ENV_SLEEP_SEC 300
#endif

constexpr uint32_t APP_ENV_MIN_SLEEP_SEC = 60UL;
constexpr uint32_t APP_ENV_MAX_SLEEP_SEC = 24UL * 60UL * 60UL;
constexpr uint32_t APP_ENV_DEFAULT_OTA_CHECK_INTERVAL_SEC = 6UL * 60UL * 60UL;
constexpr uint32_t APP_ENV_MIN_OTA_CHECK_INTERVAL_SEC = 60UL * 60UL;
constexpr uint32_t APP_ENV_MAX_OTA_CHECK_INTERVAL_SEC = 24UL * 60UL * 60UL;

constexpr const char *APP_ENV_CALIBRATION_MODE_NORMAL = "normal";
constexpr const char *APP_ENV_CALIBRATION_MODE_CAPTURE_REFERENCE = "capture_reference";
constexpr const char *APP_ENV_CALIBRATION_MODE_RESET = "reset";

constexpr const char *APP_ENV_METRIC_PAR = "par_umol_m2_s";
constexpr const char *APP_ENV_METRIC_SOIL_MOISTURE = "soil_moisture_percent";
constexpr const char *APP_ENV_METRIC_SOIL_TEMPERATURE = "soil_temperature_c";
constexpr const char *APP_ENV_METRIC_SOIL_EC = "soil_ec_us_cm";
constexpr const char *APP_ENV_METRIC_SOIL_PH = "soil_ph";
constexpr const char *APP_ENV_METRIC_SOIL_N = "soil_n_mg_kg";
constexpr const char *APP_ENV_METRIC_SOIL_P = "soil_p_mg_kg";
constexpr const char *APP_ENV_METRIC_SOIL_K = "soil_k_mg_kg";

typedef struct
{
    bool calibrated;
    float scale;
    float offset;
} app_env_metric_calibration_t;

typedef struct
{
    char mode[24];
    char request_id[40];
    char last_request_id[40];
    char target[40];
    float reference_value;
    app_env_metric_calibration_t par_umol_m2_s;
    app_env_metric_calibration_t soil_moisture_percent;
    app_env_metric_calibration_t soil_temperature_c;
    app_env_metric_calibration_t soil_ec_us_cm;
    app_env_metric_calibration_t soil_ph;
    app_env_metric_calibration_t soil_n_mg_kg;
    app_env_metric_calibration_t soil_p_mg_kg;
    app_env_metric_calibration_t soil_k_mg_kg;
} app_env_calibration_config_t;

typedef struct
{
    bool enabled;
    uint8_t modbus_slave_id;
    uint8_t modbus_function;
    uint16_t register_address;
} app_env_par_sensor_config_t;

typedef struct
{
    bool enabled;
    uint8_t modbus_slave_id;
    uint8_t modbus_function;
    uint16_t start_register;
} app_env_soil_sensor_config_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint32_t ota_check_interval_sec;
    uint32_t sleep_sec;
    app_env_par_sensor_config_t par;
    app_env_soil_sensor_config_t soil;
    app_env_calibration_config_t calibration;
} app_env_runtime_config_t;

void app_env_runtime_config_init();
void app_env_runtime_config_mark_waiting();
bool app_env_runtime_config_apply_json(const uint8_t *payload, size_t length);
bool app_env_runtime_config_load_saved();
bool app_env_runtime_config_save_current();
bool app_env_runtime_config_update_metric_calibration(const char *metric,
                                                      float scale,
                                                      float offset,
                                                      bool calibrated,
                                                      const char *last_request_id);
bool app_env_runtime_config_is_valid();
bool app_env_runtime_config_is_received();
bool app_env_metric_is_supported(const char *metric);
const app_env_metric_calibration_t &app_env_runtime_config_metric_calibration(const app_env_runtime_config_t &config,
                                                                              const char *metric);
const app_env_runtime_config_t &app_env_runtime_config_get();
