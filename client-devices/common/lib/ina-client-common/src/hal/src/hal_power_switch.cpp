#include "hal_power_switch.h"

#include <Arduino.h>

static hal_power_switch_t s_default_switch = {};

static int inactive_level(const hal_power_switch_config_t &config)
{
    return config.active_high ? LOW : HIGH;
}

static int active_level(const hal_power_switch_config_t &config)
{
    return config.active_high ? HIGH : LOW;
}

hal_power_switch_config_t hal_power_switch_default_config()
{
    hal_power_switch_config_t config = {};
    config.pin = APP_SENSOR_12V_POWER_PIN;
    config.active_high = APP_SENSOR_12V_POWER_ACTIVE_HIGH != 0;
    config.settle_ms = APP_SENSOR_12V_POWER_SETTLE_MS;
    return config;
}

bool hal_power_switch_open(hal_power_switch_t *power_switch, const hal_power_switch_config_t *config)
{
    if (power_switch == nullptr)
    {
        return false;
    }
    if (power_switch->initialized)
    {
        hal_power_switch_close(power_switch);
    }

    power_switch->config = config != nullptr ? *config : hal_power_switch_default_config();
    power_switch->enabled = false;

    if (power_switch->config.pin < 0)
    {
        power_switch->initialized = true;
        Serial.println("Power switch disabled: pin is not set");
        return true;
    }

    pinMode(static_cast<uint8_t>(power_switch->config.pin), OUTPUT);
    digitalWrite(static_cast<uint8_t>(power_switch->config.pin), inactive_level(power_switch->config));
    power_switch->initialized = true;
    Serial.printf("Power switch initialized: pin=%d active_high=%s settle=%lu ms\n",
                  power_switch->config.pin,
                  power_switch->config.active_high ? "true" : "false",
                  static_cast<unsigned long>(power_switch->config.settle_ms));
    return true;
}

void hal_power_switch_close(hal_power_switch_t *power_switch)
{
    if (power_switch == nullptr)
    {
        return;
    }

    if (power_switch->initialized && power_switch->config.pin >= 0)
    {
        digitalWrite(static_cast<uint8_t>(power_switch->config.pin), inactive_level(power_switch->config));
        pinMode(static_cast<uint8_t>(power_switch->config.pin), INPUT);
    }
    power_switch->initialized = false;
    power_switch->enabled = false;
}

bool hal_power_switch_configured(const hal_power_switch_t *power_switch)
{
    return power_switch != nullptr && power_switch->initialized && power_switch->config.pin >= 0;
}

bool hal_power_switch_enabled(const hal_power_switch_t *power_switch)
{
    return power_switch != nullptr && power_switch->enabled;
}

bool hal_power_switch_set(hal_power_switch_t *power_switch, bool enabled)
{
    if (power_switch == nullptr || !power_switch->initialized)
    {
        return false;
    }
    if (power_switch->config.pin >= 0)
    {
        digitalWrite(static_cast<uint8_t>(power_switch->config.pin),
                     enabled ? active_level(power_switch->config) : inactive_level(power_switch->config));
    }
    power_switch->enabled = enabled;
    return true;
}

bool hal_power_switch_enable_wait(hal_power_switch_t *power_switch, uint32_t settle_ms_override)
{
    if (power_switch == nullptr || !power_switch->initialized)
    {
        return false;
    }

    if (!hal_power_switch_set(power_switch, true))
    {
        return false;
    }
    const uint32_t wait_ms = settle_ms_override > 0 ? settle_ms_override : power_switch->config.settle_ms;
    if (wait_ms > 0)
    {
        delay(wait_ms);
    }
    return true;
}

bool hal_power_switch_init(const hal_power_switch_config_t *config)
{
    return hal_power_switch_open(&s_default_switch, config);
}

void hal_power_switch_deinit()
{
    hal_power_switch_close(&s_default_switch);
}

bool hal_power_switch_is_configured()
{
    return hal_power_switch_configured(&s_default_switch);
}

bool hal_power_switch_is_enabled()
{
    return hal_power_switch_enabled(&s_default_switch);
}

void hal_power_switch_set_enabled(bool enabled)
{
    if (!s_default_switch.initialized)
    {
        hal_power_switch_init(nullptr);
    }
    hal_power_switch_set(&s_default_switch, enabled);
}

bool hal_power_switch_enable_and_wait(uint32_t settle_ms_override)
{
    if (!s_default_switch.initialized && !hal_power_switch_init(nullptr))
    {
        return false;
    }
    return hal_power_switch_enable_wait(&s_default_switch, settle_ms_override);
}
