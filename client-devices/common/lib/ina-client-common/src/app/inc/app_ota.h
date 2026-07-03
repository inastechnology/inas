#pragma once

#include <stddef.h>
#include <stdint.h>

void app_ota_init();
void app_ota_mark_waiting();
void app_ota_finish_waiting();
bool app_ota_apply_offer_json(const uint8_t *payload, size_t length);
bool app_ota_is_offer_received();
bool app_ota_should_update();
bool app_ota_build_request_payload(char *payload_out, size_t payload_size, uint32_t seq_id);
bool app_ota_publish_pending_boot_status(uint32_t seq_id);
bool app_ota_publish_request_failed_status(uint32_t seq_id);
bool app_ota_publish_offer_timeout_status(uint32_t seq_id, uint32_t wait_ms);
bool app_ota_handle_offer(uint32_t seq_id);
