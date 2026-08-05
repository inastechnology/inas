#pragma once

#include <Arduino.h>
#include <stdint.h>
#include <time.h>

#include "fgt_state_machine.h"
#include "fgt_timed_output_sequence.h"
#include "hal_rs485_sensor_protocol.h"

constexpr uint8_t APP_FGT_MAX_SCHEDULES = 4;
constexpr uint32_t APP_FGT_MIN_SLEEP_SEC = 60UL;
constexpr uint32_t APP_FGT_MAX_SLEEP_SEC = 24UL * 60UL * 60UL;
constexpr uint32_t APP_FGT_DEFAULT_SLEEP_SEC = 300UL;
constexpr uint32_t APP_FGT_MIN_OTA_CHECK_INTERVAL_SEC = 60UL * 60UL;
constexpr uint32_t APP_FGT_MAX_OTA_CHECK_INTERVAL_SEC = 24UL * 60UL * 60UL;
constexpr uint32_t APP_FGT_DEFAULT_OTA_CHECK_INTERVAL_SEC = 6UL * 60UL * 60UL;

typedef struct
{
    bool enabled;
    uint8_t hour;
    uint8_t minute;
} app_fgt_schedule_entry_t;

typedef struct
{
    hal_rs485_soil_sensor_config_t soil;
    hal_rs485_par_sensor_config_t par;
    uint32_t power_settle_ms;
    uint32_t flow_pulses_per_liter;
} app_fgt_sensor_config_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint32_t sleep_sec;
    uint32_t ota_check_interval_sec;
    bool debug_log_on_wake;
    bool enabled;
    uint32_t recovery_ack;
    bool timed_outputs_enabled;
    fgt::TimedProgram timed_program;
    fgt::Recipe recipe;
    fgt::Limits limits;
    app_fgt_sensor_config_t sensors;
    uint8_t schedule_count;
    app_fgt_schedule_entry_t schedules[APP_FGT_MAX_SCHEDULES];
} app_fgt_runtime_config_t;

void app_fgt_runtime_config_init();
void app_fgt_runtime_config_mark_waiting();
bool app_fgt_runtime_config_apply_json(const uint8_t *payload, size_t length);
bool app_fgt_runtime_config_load_saved();
bool app_fgt_runtime_config_save_current();
bool app_fgt_runtime_config_is_valid();
bool app_fgt_runtime_config_is_received();
const app_fgt_runtime_config_t &app_fgt_runtime_config_get();
bool app_fgt_runtime_config_find_due_schedule(time_t now_utc,
                                              time_t last_executed_schedule_utc,
                                              app_fgt_schedule_entry_t *schedule_out,
                                              time_t *schedule_epoch_utc_out);
uint32_t app_fgt_runtime_config_seconds_until_next_schedule(time_t now_utc);
