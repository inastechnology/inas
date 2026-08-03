#pragma once

#include <stdint.h>

class AsyncWebServer;

typedef enum
{
    APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED = 0,
    APP_INITIAL_SETTING_PORTAL_REASON_BUTTON,
    APP_INITIAL_SETTING_PORTAL_REASON_CONNECTION_RESET,
    APP_INITIAL_SETTING_PORTAL_REASON_WIFI_FAILURE,
    APP_INITIAL_SETTING_PORTAL_REASON_MQTT_FAILURE,
} app_initial_setting_portal_reason_t;

typedef struct
{
    const char *label;
    const char *description;
    const char *path;
    void (*begin)();
    void (*register_routes)(AsyncWebServer *server);
    void (*loop)();
    void (*end)();
} app_initial_setting_extension_t;

void app_initial_setting_set_extension(const app_initial_setting_extension_t *extension);
void app_initial_setting_start_portal(app_initial_setting_portal_reason_t reason = APP_INITIAL_SETTING_PORTAL_REASON_UNCONFIGURED,
                                      uint32_t recovery_timeout_ms = 0);
bool app_initial_setting_handle_setup_portal_request();
