#pragma once

#include <stdint.h>

typedef struct
{
    int output_pins[5];
    int input_pins[4];
    bool initialized;
} hal_direct_gpio_t;

bool hal_direct_gpio_open(hal_direct_gpio_t *io);
void hal_direct_gpio_close(hal_direct_gpio_t *io);
bool hal_direct_gpio_write_outputs(hal_direct_gpio_t *io, uint16_t output_mask, uint16_t enabled_mask);
bool hal_direct_gpio_read_inputs(hal_direct_gpio_t *io, uint16_t *value_out);
bool hal_direct_gpio_all_outputs_off(hal_direct_gpio_t *io);
