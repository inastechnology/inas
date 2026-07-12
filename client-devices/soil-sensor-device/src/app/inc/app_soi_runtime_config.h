#pragma once

#include <Arduino.h>
#include <stdint.h>

#ifndef APP_SOI_MOISTURE_PIN
#define APP_SOI_MOISTURE_PIN A0
#endif

#ifndef APP_SOI_MOISTURE_DRY_RAW
#define APP_SOI_MOISTURE_DRY_RAW 3200
#endif

#ifndef APP_SOI_MOISTURE_WET_RAW
#define APP_SOI_MOISTURE_WET_RAW 1500
#endif

#ifndef APP_SOI_MOISTURE_SAMPLE_COUNT
#define APP_SOI_MOISTURE_SAMPLE_COUNT 20
#endif

#ifndef APP_SOI_MOISTURE_SAMPLE_INTERVAL_MS
#define APP_SOI_MOISTURE_SAMPLE_INTERVAL_MS 40
#endif

#ifndef APP_SOI_SLEEP_SEC
#define APP_SOI_SLEEP_SEC 900
#endif

constexpr uint32_t APP_SOI_MIN_SLEEP_SEC = 60UL;
constexpr uint32_t APP_SOI_MAX_SLEEP_SEC = 24UL * 60UL * 60UL;
constexpr uint32_t APP_SOI_DEFAULT_OTA_CHECK_INTERVAL_SEC = 6UL * 60UL * 60UL;
constexpr uint32_t APP_SOI_MIN_OTA_CHECK_INTERVAL_SEC = 60UL * 60UL;
constexpr uint32_t APP_SOI_MAX_OTA_CHECK_INTERVAL_SEC = 24UL * 60UL * 60UL;

constexpr const char *APP_SOI_CALIBRATION_MODE_NORMAL = "normal";
constexpr const char *APP_SOI_CALIBRATION_MODE_CAPTURE_DRY = "capture_dry";
constexpr const char *APP_SOI_CALIBRATION_MODE_CAPTURE_WET = "capture_wet";
constexpr const char *APP_SOI_CALIBRATION_MODE_RESET = "reset";

typedef struct
{
    bool calibrated;
    char mode[16];
    char request_id[40];
    char last_request_id[40];
    uint16_t dry_raw;
    uint16_t wet_raw;
    uint16_t min_delta_raw;
    uint16_t drift_tolerance_raw;
    uint8_t sample_count;
    uint16_t sample_interval_ms;
} app_soi_soil_calibration_config_t;

typedef struct
{
    bool valid;
    bool received_from_mqtt;
    char ntp_server[256];
    int32_t timezone_offset_sec;
    uint32_t ota_check_interval_sec;
    uint32_t sleep_sec;
    app_soi_soil_calibration_config_t soil_calibration;
} app_soi_runtime_config_t;

void app_soi_runtime_config_init();
void app_soi_runtime_config_mark_waiting();
bool app_soi_runtime_config_apply_json(const uint8_t *payload, size_t length);
bool app_soi_runtime_config_load_saved();
bool app_soi_runtime_config_save_current();
bool app_soi_runtime_config_update_soil_calibration(uint16_t dry_raw,
                                                    uint16_t wet_raw,
                                                    bool calibrated,
                                                    const char *last_request_id);
bool app_soi_runtime_config_is_valid();
bool app_soi_runtime_config_is_received();
const app_soi_runtime_config_t &app_soi_runtime_config_get();
