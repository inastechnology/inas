#pragma once

#include <Arduino.h>
#include <stdint.h>
#include <time.h>

#include "hal_rs485_sensor_protocol.h"

constexpr uint8_t APP_WRS_MAX_SCHEDULES = 8;
constexpr uint8_t APP_WRS_SCHEDULE_FREQUENCY_DAILY = 0;
constexpr uint8_t APP_WRS_SCHEDULE_FREQUENCY_INTERVAL = 1;
constexpr uint8_t APP_WRS_SCHEDULE_FREQUENCY_WEEKDAYS = 2;

constexpr uint32_t APP_WRS_MIN_SLEEP_SEC = 60UL;
constexpr uint32_t APP_WRS_DEFAULT_SLEEP_SEC = 300UL;
constexpr uint32_t APP_WRS_MAX_SLEEP_SEC = 24UL * 60UL * 60UL;
constexpr uint32_t APP_WRS_DEFAULT_OTA_CHECK_INTERVAL_SEC = 6UL * 60UL * 60UL;
constexpr uint32_t APP_WRS_MIN_OTA_CHECK_INTERVAL_SEC = 60UL * 60UL;
constexpr uint32_t APP_WRS_MAX_OTA_CHECK_INTERVAL_SEC = 24UL * 60UL * 60UL;

#ifndef APP_WRS_SOIL_RS485_ENABLED
#define APP_WRS_SOIL_RS485_ENABLED 1
#endif

#ifndef APP_WRS_SOIL_MODBUS_SLAVE_ID
#define APP_WRS_SOIL_MODBUS_SLAVE_ID 2
#endif

#ifndef APP_WRS_SOIL_MODBUS_FUNCTION
#define APP_WRS_SOIL_MODBUS_FUNCTION 4
#endif

#ifndef APP_WRS_SOIL_MODBUS_START_REGISTER
#define APP_WRS_SOIL_MODBUS_START_REGISTER 0
#endif

#ifndef APP_WRS_PAR_ENABLED
#define APP_WRS_PAR_ENABLED 0
#endif

#ifndef APP_WRS_PAR_MODBUS_SLAVE_ID
#define APP_WRS_PAR_MODBUS_SLAVE_ID 1
#endif

#ifndef APP_WRS_PAR_MODBUS_FUNCTION
#define APP_WRS_PAR_MODBUS_FUNCTION 3
#endif

#ifndef APP_WRS_PAR_REGISTER
#define APP_WRS_PAR_REGISTER 0
#endif

#ifndef APP_WRS_PAR_SCALE
#define APP_WRS_PAR_SCALE 1.0f
#endif

#ifndef APP_WRS_SENSOR_POWER_SETTLE_MS
#define APP_WRS_SENSOR_POWER_SETTLE_MS 800
#endif

#ifndef APP_WRS_WATERING_MAX_DURATION_SEC
#define APP_WRS_WATERING_MAX_DURATION_SEC 60
#endif

#ifndef APP_WRS_WATERING_CHECK_INTERVAL_SEC
#define APP_WRS_WATERING_CHECK_INTERVAL_SEC 10
#endif

#ifndef APP_WRS_WATERING_STOP_MOISTURE_PERCENT
#define APP_WRS_WATERING_STOP_MOISTURE_PERCENT 55
#endif

#ifndef APP_WRS_WATERING_CHANNEL_MASK
#define APP_WRS_WATERING_CHANNEL_MASK 0x1
#endif

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
} app_wrs_schedule_entry_t;

typedef struct
{
    bool enabled;
    bool auto_on_low_moisture;
    bool require_soil_feedback;
    bool force_watering;
    uint8_t moisture_threshold_percent;
    uint8_t stop_moisture_percent;
    uint16_t max_duration_sec;
    uint16_t check_interval_sec;
    uint32_t channel_mask;
} app_wrs_watering_config_t;

typedef struct
{
    hal_rs485_soil_sensor_config_t soil;
    hal_rs485_par_sensor_config_t par;
    uint32_t power_settle_ms;
} app_wrs_sensor_config_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint32_t sleep_sec;
    uint32_t ota_check_interval_sec;
    bool debug_log_on_wake;
    app_wrs_watering_config_t watering;
    app_wrs_sensor_config_t sensors;
    uint8_t schedule_count;
    app_wrs_schedule_entry_t schedules[APP_WRS_MAX_SCHEDULES];
} app_wrs_runtime_config_t;

void app_wrs_runtime_config_init();
void app_wrs_runtime_config_mark_waiting();
bool app_wrs_runtime_config_apply_json(const uint8_t *payload, size_t length);
bool app_wrs_runtime_config_load_saved();
bool app_wrs_runtime_config_save_current();
bool app_wrs_runtime_config_is_valid();
bool app_wrs_runtime_config_is_received();
const app_wrs_runtime_config_t &app_wrs_runtime_config_get();
bool app_wrs_runtime_config_find_due_schedule(time_t now_utc,
                                              time_t last_executed_schedule_utc,
                                              app_wrs_schedule_entry_t *schedule_out,
                                              time_t *schedule_epoch_utc_out);
uint32_t app_wrs_runtime_config_seconds_until_next_schedule(time_t now_utc);
