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
bool app_runtime_config_is_valid();
bool app_runtime_config_is_received();
const app_runtime_config_t &app_runtime_config_get();
bool app_runtime_config_find_due_schedule(time_t now_utc,
                                          time_t last_executed_schedule_utc,
                                          app_schedule_entry_t *schedule_out,
                                          time_t *schedule_epoch_utc_out);
uint32_t app_runtime_config_seconds_until_next_schedule(time_t now_utc);
