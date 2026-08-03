#include "hal_direct_gpio.h"

#include <Arduino.h>

#ifndef APP_FGT_WATER_OUTPUT_PIN
#define APP_FGT_WATER_OUTPUT_PIN 1
#endif
#ifndef APP_FGT_NUTRIENT_A_OUTPUT_PIN
#define APP_FGT_NUTRIENT_A_OUTPUT_PIN 2
#endif
#ifndef APP_FGT_NUTRIENT_B_OUTPUT_PIN
#define APP_FGT_NUTRIENT_B_OUTPUT_PIN 21
#endif
#ifndef APP_FGT_MIXER_OUTPUT_PIN
#define APP_FGT_MIXER_OUTPUT_PIN 22
#endif
#ifndef APP_FGT_IRRIGATION_OUTPUT_PIN
#define APP_FGT_IRRIGATION_OUTPUT_PIN 23
#endif

static constexpr uint16_t kOutputMask = 0x001F;

bool hal_direct_gpio_open(hal_direct_gpio_t *io)
{
    if (io == nullptr)
    {
        return false;
    }
    *io = {};
    const int outputs[] = {
        APP_FGT_WATER_OUTPUT_PIN,
        APP_FGT_NUTRIENT_A_OUTPUT_PIN,
        APP_FGT_NUTRIENT_B_OUTPUT_PIN,
        APP_FGT_MIXER_OUTPUT_PIN,
        APP_FGT_IRRIGATION_OUTPUT_PIN,
    };
    for (size_t i = 0; i < 5; ++i)
    {
        io->output_pins[i] = outputs[i];
        pinMode(outputs[i], OUTPUT);
        digitalWrite(outputs[i], LOW);
    }
    io->initialized = true;
    return true;
}

void hal_direct_gpio_close(hal_direct_gpio_t *io)
{
    if (io == nullptr)
    {
        return;
    }
    hal_direct_gpio_all_outputs_off(io);
    io->initialized = false;
}

bool hal_direct_gpio_write_outputs(hal_direct_gpio_t *io, uint16_t output_mask, uint16_t enabled_mask)
{
    if (io == nullptr || !io->initialized || output_mask != kOutputMask ||
        (enabled_mask & ~output_mask) != 0)
    {
        return false;
    }
    for (size_t i = 0; i < 5; ++i)
    {
        digitalWrite(io->output_pins[i], (enabled_mask & (1U << i)) != 0 ? HIGH : LOW);
    }
    return true;
}

bool hal_direct_gpio_read_inputs(hal_direct_gpio_t *io, uint16_t *value_out)
{
    if (io == nullptr || !io->initialized || value_out == nullptr)
    {
        return false;
    }
    *value_out = 0;
    return true;
}

bool hal_direct_gpio_all_outputs_off(hal_direct_gpio_t *io)
{
    if (io == nullptr || !io->initialized)
    {
        return false;
    }
    for (int pin : io->output_pins)
    {
        digitalWrite(pin, LOW);
    }
    return true;
}
