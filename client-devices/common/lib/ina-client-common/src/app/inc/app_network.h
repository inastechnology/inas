#pragma once

#include "esp_err.h"
#include <stdint.h>

typedef enum
{
    APP_MSG_TYPE_TEST = 0,
    APP_MSG_TYPE_STATUS,
    APP_MSG_TYPE_IMAGE,
    APP_MSG_TYPE_AUDIO,
    APP_MSG_TYPE_TASKREQ,
    APP_MSG_TYPE_DEBUG_LOG,
    APP_MSG_TYPE_OTA_STATUS,
    MAX_APP_MSG_TYPE
} app_msg_type_t;

bool app_network_start();
void app_network_stop();
void app_network_loop();
void app_network_flush(uint32_t duration_ms);
bool app_network_is_connected();
bool app_network_send(app_msg_type_t kind, const uint8_t *const data, uint16_t data_len, int seqId = 0, bool retain = false);
bool app_network_send_large(app_msg_type_t kind, const uint8_t *const data, unsigned int data_len, int seqId = 0, bool retain = false);
bool app_network_reconnect();
bool app_network_request_runtime_config();
bool app_network_wait_for_runtime_config(uint32_t timeout_ms);
bool app_network_request_ota_update(uint32_t seq_id);
bool app_network_wait_for_ota_offer(uint32_t timeout_ms);
void app_network_set_setup_portal_enabled(bool enabled);
bool app_network_is_setup_portal_enabled();
