#pragma once

#include <Arduino.h>
#include <time.h>
#include <stddef.h>

constexpr uint8_t APP_RUNTIME_MAX_SCHEDULES = 8;
constexpr uint32_t APP_RUNTIME_DEFAULT_OTA_CHECK_INTERVAL_SEC = 6UL * 60UL * 60UL;
constexpr uint32_t APP_RUNTIME_MIN_OTA_CHECK_INTERVAL_SEC = 60UL * 60UL;
constexpr uint32_t APP_RUNTIME_MAX_OTA_CHECK_INTERVAL_SEC = 24UL * 60UL * 60UL;
constexpr uint8_t APP_SCHEDULE_FREQUENCY_DAILY = 0;
constexpr uint8_t APP_SCHEDULE_FREQUENCY_INTERVAL = 1;
constexpr uint8_t APP_SCHEDULE_FREQUENCY_WEEKDAYS = 2;

#ifndef APP_ENV_PAR_ENABLED
#define APP_ENV_PAR_ENABLED 0
#endif

#ifndef APP_ENV_PAR_MODBUS_SLAVE_ID
#define APP_ENV_PAR_MODBUS_SLAVE_ID 1
#endif

#ifndef APP_ENV_PAR_MODBUS_FUNCTION
#define APP_ENV_PAR_MODBUS_FUNCTION 3
#endif

#ifndef APP_ENV_PAR_REGISTER
#define APP_ENV_PAR_REGISTER 0
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

#ifndef APP_SENSOR_12V_POWER_SETTLE_MS
#define APP_SENSOR_12V_POWER_SETTLE_MS 800
#endif

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
    uint8_t hour;
    uint8_t minute;
    uint16_t duration_sec;
    uint32_t channel_mask;
    uint8_t frequency_type;
    uint8_t interval_days;
    uint8_t weekdays_mask;
    int32_t anchor_epoch_day;
} app_schedule_entry_t;

typedef struct
{
    bool enabled;
    uint16_t on_sec;
    uint16_t off_sec;
    uint8_t repeat_count;
} app_watering_pattern_config_t;

typedef struct
{
    bool enabled;
    uint8_t duration_sec;
    uint32_t channel_mask;
} app_startup_watering_test_config_t;

typedef struct
{
    bool auto_mode_enabled;
    bool apply_auto_calibration;
    bool drift_check_enabled;
    uint16_t dry_raw;
    uint16_t wet_raw;
    uint16_t min_delta_raw;
    uint16_t drift_tolerance_raw;
} app_soil_calibration_config_t;

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
    app_env_par_sensor_config_t par;
    app_env_soil_sensor_config_t soil;
    uint32_t power_settle_ms;
} app_env_sensor_config_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint8_t moisture_threshold;
    bool force_watering;
    uint8_t schedule_count;
    bool debug_log_on_wake;
    uint32_t ota_check_interval_sec;
    app_watering_pattern_config_t watering_pattern;
    app_soil_calibration_config_t soil_calibration;
    app_env_sensor_config_t env_sensors;
    app_env_calibration_config_t env_calibration;
    app_schedule_entry_t schedules[APP_RUNTIME_MAX_SCHEDULES];
} app_runtime_config_t;

static_assert(offsetof(app_runtime_config_t, schedules) > offsetof(app_runtime_config_t, ota_check_interval_sec),
              "Unexpected app_runtime_config_t layout; check packing pragmas");

void app_runtime_config_init();
void app_runtime_config_mark_waiting();
bool app_runtime_config_apply_json(const uint8_t *payload, size_t length);
bool app_runtime_config_load_saved();
bool app_runtime_config_save_current();
bool app_runtime_config_update_soil_calibration(uint16_t dry_raw, uint16_t wet_raw);
bool app_runtime_config_update_env_metric_calibration(const char *metric,
                                                      float scale,
                                                      float offset,
                                                      bool calibrated,
                                                      const char *last_request_id);
bool app_runtime_config_is_valid();
bool app_runtime_config_is_received();
bool app_runtime_config_env_metric_is_supported(const char *metric);
const app_env_metric_calibration_t &app_runtime_config_env_metric_calibration(const app_runtime_config_t &config,
                                                                              const char *metric);
const app_runtime_config_t &app_runtime_config_get();
const app_startup_watering_test_config_t &app_runtime_config_get_startup_watering_test();
bool app_runtime_config_find_due_schedule(time_t now_utc,
                                          time_t last_executed_schedule_utc,
                                          app_schedule_entry_t *schedule_out,
                                          time_t *schedule_epoch_utc_out);
uint32_t app_runtime_config_seconds_until_next_schedule(time_t now_utc);
