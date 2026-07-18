#pragma once

#include <stdint.h>

typedef struct
{
    int pulse_pin;
    uint32_t pulses_per_liter;
    bool pullup_enabled;
} hal_flow_meter_config_t;

hal_flow_meter_config_t hal_flow_meter_default_config();
bool hal_flow_meter_init(const hal_flow_meter_config_t *config);
void hal_flow_meter_deinit();
void hal_flow_meter_reset();
uint32_t hal_flow_meter_total_pulses();
uint32_t hal_flow_meter_total_ml();
