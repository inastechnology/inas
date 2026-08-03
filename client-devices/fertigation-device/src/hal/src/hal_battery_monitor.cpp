#include "hal_battery_monitor.h"

#include <Arduino.h>

#ifndef APP_FGT_BATTERY_ADC_PIN
#define APP_FGT_BATTERY_ADC_PIN A0
#endif

#ifndef APP_FGT_BATTERY_ADC_SAMPLES
#define APP_FGT_BATTERY_ADC_SAMPLES 16
#endif

#ifndef APP_FGT_BATTERY_DIVIDER_RATIO
#define APP_FGT_BATTERY_DIVIDER_RATIO 2.0F
#endif

bool hal_battery_monitor_open(hal_battery_monitor_t *monitor)
{
    if (monitor == nullptr || APP_FGT_BATTERY_ADC_SAMPLES == 0)
    {
        return false;
    }

    *monitor = {};
    monitor->adc_pin = APP_FGT_BATTERY_ADC_PIN;
    monitor->sample_count = APP_FGT_BATTERY_ADC_SAMPLES;
    monitor->divider_ratio = APP_FGT_BATTERY_DIVIDER_RATIO;
    pinMode(monitor->adc_pin, INPUT);
    monitor->initialized = true;
    return true;
}

bool hal_battery_monitor_read(const hal_battery_monitor_t *monitor,
                              hal_battery_sample_t *sample)
{
    if (monitor == nullptr || sample == nullptr || !monitor->initialized ||
        monitor->sample_count == 0 || monitor->divider_ratio <= 0.0F)
    {
        return false;
    }

    uint32_t accumulated_millivolts = 0;
    for (uint8_t i = 0; i < monitor->sample_count; ++i)
    {
        accumulated_millivolts += analogReadMilliVolts(monitor->adc_pin);
    }

    sample->adc_millivolts = accumulated_millivolts / monitor->sample_count;
    sample->battery_volts =
        monitor->divider_ratio * static_cast<float>(sample->adc_millivolts) / 1000.0F;
    return true;
}
