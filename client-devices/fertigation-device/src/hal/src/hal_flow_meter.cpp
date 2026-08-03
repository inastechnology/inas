#include "hal_flow_meter.h"

#include <Arduino.h>

#ifndef APP_FGT_FLOW_PULSE_PIN
#define APP_FGT_FLOW_PULSE_PIN -1
#endif

#ifndef APP_FGT_FLOW_PULSES_PER_LITER
#define APP_FGT_FLOW_PULSES_PER_LITER 450
#endif

static volatile uint32_t s_pulse_count = 0;
static hal_flow_meter_config_t s_config = {};
static bool s_initialized = false;

static void IRAM_ATTR on_flow_pulse()
{
    ++s_pulse_count;
}

hal_flow_meter_config_t hal_flow_meter_default_config()
{
    hal_flow_meter_config_t config = {};
    config.pulse_pin = APP_FGT_FLOW_PULSE_PIN;
    config.pulses_per_liter = APP_FGT_FLOW_PULSES_PER_LITER;
    config.pullup_enabled = true;
    return config;
}

bool hal_flow_meter_init(const hal_flow_meter_config_t *config)
{
    s_config = config != nullptr ? *config : hal_flow_meter_default_config();
    if (s_config.pulse_pin < 0 || s_config.pulses_per_liter == 0)
    {
        return false;
    }
    s_pulse_count = 0;
    pinMode(static_cast<uint8_t>(s_config.pulse_pin), s_config.pullup_enabled ? INPUT_PULLUP : INPUT);
    attachInterrupt(digitalPinToInterrupt(s_config.pulse_pin), on_flow_pulse, RISING);
    s_initialized = true;
    return true;
}

void hal_flow_meter_deinit()
{
    if (!s_initialized)
    {
        return;
    }
    detachInterrupt(digitalPinToInterrupt(s_config.pulse_pin));
    pinMode(static_cast<uint8_t>(s_config.pulse_pin), INPUT);
    s_initialized = false;
}

void hal_flow_meter_reset()
{
    noInterrupts();
    s_pulse_count = 0;
    interrupts();
}

uint32_t hal_flow_meter_total_pulses()
{
    noInterrupts();
    const uint32_t value = s_pulse_count;
    interrupts();
    return value;
}

uint32_t hal_flow_meter_total_ml()
{
    if (!s_initialized || s_config.pulses_per_liter == 0)
    {
        return 0;
    }
    const uint64_t scaled = static_cast<uint64_t>(hal_flow_meter_total_pulses()) * 1000ULL;
    return static_cast<uint32_t>(scaled / s_config.pulses_per_liter);
}
