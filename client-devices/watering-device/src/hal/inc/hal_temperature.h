#pragma once

#include "esp_err.h"

typedef enum
{
    HAL_TEMP_C = 0,
    HAL_TEMP_F = 1,
    MAX_TEMP_TYPE
} hal_temp_type_t;

void hal_temperature_init();

float hal_temperature_get(hal_temp_type_t type = HAL_TEMP_C);