#pragma once

#include "esp_err.h"

void hal_tds_init();
void hal_tds_deinit();
float hal_tds_read(float temperature);