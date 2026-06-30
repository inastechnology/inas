#pragma once

#include <stdint.h>

enum app_debug_log_level_t : uint8_t
{
    APP_DEBUG_LOG_INFO = 1,
    APP_DEBUG_LOG_WARNING = 2,
    APP_DEBUG_LOG_ERROR = 3,
};

enum app_debug_log_file_id_t : uint8_t
{
    APP_DEBUG_FILE_APP = 1,
    APP_DEBUG_FILE_NETWORK = 2,
    APP_DEBUG_FILE_RUNTIME_CONFIG = 3,
    APP_DEBUG_FILE_WATERING = 4,
};

enum app_debug_log_event_t : uint8_t
{
    APP_DEBUG_EVENT_BOOT = 1,
    APP_DEBUG_EVENT_LITTLEFS_MOUNTED = 2,
    APP_DEBUG_EVENT_CONFIG_LOADED = 3,
    APP_DEBUG_EVENT_RUNTIME_CONFIG_INIT = 4,
    APP_DEBUG_EVENT_NETWORK_START = 5,
    APP_DEBUG_EVENT_NETWORK_UNAVAILABLE = 6,
    APP_DEBUG_EVENT_RUNTIME_CONFIG_REQUEST = 7,
    APP_DEBUG_EVENT_RUNTIME_CONFIG_ACTIVE = 8,
    APP_DEBUG_EVENT_TIME_SYNC_NTP_FAILED_RTC = 9,
    APP_DEBUG_EVENT_TIME_SYNC_OFFLINE_RTC = 10,
    APP_DEBUG_EVENT_TIME_SYNC_UNAVAILABLE = 11,
    APP_DEBUG_EVENT_TIME_SYNC_OK = 12,
    APP_DEBUG_EVENT_SCHEDULE_CHECK = 13,
    APP_DEBUG_EVENT_WATERING_DUE_RESULT = 14,
    APP_DEBUG_EVENT_SLEEP_PLANNED = 15,
    APP_DEBUG_EVENT_STATUS_SENT = 16,
    APP_DEBUG_EVENT_STATUS_FAILED = 17,
    APP_DEBUG_EVENT_STATUS_SKIPPED = 18,
    APP_DEBUG_EVENT_DEBUG_LOG_PUBLISH_ENABLED = 19,

    APP_DEBUG_EVENT_MQTT_DNS_FAILED = 30,
    APP_DEBUG_EVENT_MQTT_CONNECTED = 31,
    APP_DEBUG_EVENT_MQTT_FAILED = 32,
    APP_DEBUG_EVENT_WIFI_FAILED = 33,
    APP_DEBUG_EVENT_WIFI_CONNECTED = 34,
    APP_DEBUG_EVENT_WIFI_RECONNECT_FAILED = 35,
    APP_DEBUG_EVENT_WIFI_RECONNECTED = 36,

    APP_DEBUG_EVENT_RUNTIME_CONFIG_UPDATED = 50,

    APP_DEBUG_EVENT_WATERING_OUTPUT_MAP = 70,
    APP_DEBUG_EVENT_WATERING_DECISION = 71,
    APP_DEBUG_EVENT_WATERING_OUTPUT_START_FAILED = 72,
    APP_DEBUG_EVENT_WATERING_STARTED = 73,
    APP_DEBUG_EVENT_WATERING_SKIPPED_MOISTURE = 74,
    APP_DEBUG_EVENT_WATERING_COMPLETED = 75,
};

void app_debug_log_reset();
void app_debug_log_event(uint8_t file_id,
                         uint16_t line,
                         app_debug_log_level_t level,
                         uint8_t event_code,
                         int32_t arg0 = 0,
                         int32_t arg1 = 0);
uint16_t app_debug_log_event_count();
uint16_t app_debug_log_dropped_count();
bool app_debug_log_publish(uint32_t seq_id);

#define APP_DEBUG_LOG_EVENT(file_id, level, event_code, arg0, arg1) \
    app_debug_log_event((file_id), static_cast<uint16_t>(__LINE__), (level), (event_code), (arg0), (arg1))
