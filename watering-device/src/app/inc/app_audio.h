#pragma once

#include "esp_err.h"

void app_audio_init();
void app_audio_deinit();

bool app_audio_report(uint32_t seqId);