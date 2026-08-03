#pragma once

#include <stdint.h>

typedef struct
{
    int adc_pin;
    uint8_t sample_count;
    float divider_ratio;
    bool initialized;
} hal_battery_monitor_t;

typedef struct
{
    uint32_t adc_millivolts;
    float battery_volts;
} hal_battery_sample_t;

bool hal_battery_monitor_open(hal_battery_monitor_t *monitor);
bool hal_battery_monitor_read(const hal_battery_monitor_t *monitor,
                              hal_battery_sample_t *sample);
