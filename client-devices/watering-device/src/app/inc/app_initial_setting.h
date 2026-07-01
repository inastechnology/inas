#pragma once

#include <stdint.h>

typedef enum
{
    APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED = 0,
    APP_INITIAL_SETTING_PORTAL_REASON_BUTTON,
    APP_INITIAL_SETTING_PORTAL_REASON_CONNECTION_RESET,
    APP_INITIAL_SETTING_PORTAL_REASON_WIFI_FAILURE,
    APP_INITIAL_SETTING_PORTAL_REASON_MQTT_FAILURE,
} app_initial_setting_portal_reason_t;

void app_initial_setting_start_portal(app_initial_setting_portal_reason_t reason = APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED,
                                      uint32_t recovery_timeout_ms = 0);
bool app_initial_setting_handle_setup_portal_request();
