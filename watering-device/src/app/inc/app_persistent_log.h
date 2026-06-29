#pragma once

#include "esp_err.h"

typedef enum
{
    APP_PLOG_TYPE_REBOOT_COUNT = 0,
    APP_PLOG_TYPE_WIFI_CONNECTION_FAIL_COUNT,
    APP_PLOG_TYPE_MQTT_SEND_FAIL_COUNT,
    APP_PLOG_TYPE_MAX
} app_persistent_log_type_t;

typedef enum
{
    APP_PLOG_TYPE_INFO = 0,
    APP_PLOG_TYPE_WARNING,
    APP_PLOG_TYPE_ERROR,
    APP_PLOG_TYPE_MAX
} app_persistent_log_level_t;

#pragma pack(push, 1)
typedef struct
{
    uint8_t level;            // app_persistent_log_level_t(cast to uint8_t. enum is different size by compiler)
    uint8_t file_type;        // file type(cast to uint8_t)
    uint16_t line;            // line number(cast to uint16_t)
    uint32_t abs_time;        // absolute time(cast to uint32_t)
    uint32_t param[4];        // parameter
} app_persistent_log_entry_t; // 48 bytes

#pragma pack(pop)
typedef struct
{
    uint64_t reboot_count;
    uint64_t wifi_connection_fail_count;
    uint32_t wifi_latest_connect_elapsed_time_ms[10];
    uint64_t mqtt_send_fail_count;
    app_persistent_log_entry_t log_entry[0x80];

} app_persistent_log_t; // 8 + 8 + 40 + 8 + 48 * 0x80 = 6208 bytes

void app_persistent_log_init();
void app_persistent_log_deinit();
