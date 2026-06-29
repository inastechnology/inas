#pragma once

#include <stdint.h>
#include "esp_err.h"

void app_sensor_init();
void app_sensor_deinit();

bool app_sensor_report(uint32_t seqId);
