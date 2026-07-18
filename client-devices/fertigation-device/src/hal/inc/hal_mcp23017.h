#pragma once

#include <stdint.h>

typedef struct
{
    uint8_t address;
    int sda_pin;
    int scl_pin;
    uint32_t clock_hz;
} hal_mcp23017_config_t;

typedef struct
{
    hal_mcp23017_config_t config;
    uint16_t direction_mask;
    uint16_t pullup_mask;
    uint16_t output_latch;
    bool initialized;
} hal_mcp23017_t;

hal_mcp23017_config_t hal_mcp23017_default_config();
bool hal_mcp23017_open(hal_mcp23017_t *device, const hal_mcp23017_config_t *config);
void hal_mcp23017_close(hal_mcp23017_t *device);
bool hal_mcp23017_configure(hal_mcp23017_t *device, uint16_t output_mask, uint16_t input_pullup_mask);
bool hal_mcp23017_write_outputs(hal_mcp23017_t *device, uint16_t output_mask, uint16_t enabled_mask);
bool hal_mcp23017_read_gpio(hal_mcp23017_t *device, uint16_t *value_out);
bool hal_mcp23017_all_outputs_off(hal_mcp23017_t *device);
