#pragma once

#include "esp_err.h"

void app_camera_init();

void app_camera_deinit();

bool app_camera_report(uint32_t seqId);