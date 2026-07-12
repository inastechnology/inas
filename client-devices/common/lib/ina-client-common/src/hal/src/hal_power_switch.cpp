#include "hal_power_switch.h"

#include <Arduino.h>

static hal_power_switch_config_t s_config = {};
static bool s_initialized = false;
static bool s_enabled = false;

static int inactive_level()
{
    return s_config.active_high ? LOW : HIGH;
}

static int active_level()
{
    return s_config.active_high ? HIGH : LOW;
}

hal_power_switch_config_t hal_power_switch_default_config()
{
    hal_power_switch_config_t config = {};
    config.pin = APP_SENSOR_12V_POWER_PIN;
    config.active_high = APP_SENSOR_12V_POWER_ACTIVE_HIGH != 0;
    config.settle_ms = APP_SENSOR_12V_POWER_SETTLE_MS;
    return config;
}

bool hal_power_switch_init(const hal_power_switch_config_t *config)
{
    s_config = config != nullptr ? *config : hal_power_switch_default_config();
    s_enabled = false;

    if (s_config.pin < 0)
    {
        s_initialized = true;
        Serial.println("12V sensor power switch disabled: APP_SENSOR_12V_POWER_PIN is not set");
        return true;
    }

    pinMode(static_cast<uint8_t>(s_config.pin), OUTPUT);
    digitalWrite(static_cast<uint8_t>(s_config.pin), inactive_level());
    s_initialized = true;
    Serial.printf("12V sensor power switch initialized: pin=%d active_high=%s settle=%lu ms\n",
                  s_config.pin,
                  s_config.active_high ? "true" : "false",
                  static_cast<unsigned long>(s_config.settle_ms));
    return true;
}

void hal_power_switch_deinit()
{
    if (s_initialized && s_config.pin >= 0)
    {
        digitalWrite(static_cast<uint8_t>(s_config.pin), inactive_level());
        pinMode(static_cast<uint8_t>(s_config.pin), INPUT);
    }
    s_initialized = false;
    s_enabled = false;
}

bool hal_power_switch_is_configured()
{
    return s_initialized && s_config.pin >= 0;
}

bool hal_power_switch_is_enabled()
{
    return s_enabled;
}

void hal_power_switch_set_enabled(bool enabled)
{
    if (!s_initialized)
    {
        hal_power_switch_init(nullptr);
    }
    if (s_config.pin >= 0)
    {
        digitalWrite(static_cast<uint8_t>(s_config.pin), enabled ? active_level() : inactive_level());
    }
    s_enabled = enabled;
}

bool hal_power_switch_enable_and_wait(uint32_t settle_ms_override)
{
    if (!s_initialized && !hal_power_switch_init(nullptr))
    {
        return false;
    }

    hal_power_switch_set_enabled(true);
    const uint32_t wait_ms = settle_ms_override > 0 ? settle_ms_override : s_config.settle_ms;
    if (wait_ms > 0)
    {
        delay(wait_ms);
    }
    return true;
}
