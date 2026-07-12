#include "hal_mosfet_output.h"

#include <Arduino.h>
#include <string.h>

typedef struct
{
    uint8_t pin;
    bool active;
    uint32_t end_at_ms;
} hal_mosfet_output_channel_t;

static hal_mosfet_output_channel_t s_channels[HAL_MOSFET_OUTPUT_MAX_CHANNELS];
static uint8_t s_channel_count = 0;
static bool s_active_high = true;

static int active_level()
{
    return s_active_high ? HIGH : LOW;
}

static int inactive_level()
{
    return s_active_high ? LOW : HIGH;
}

void hal_mosfet_output_init(const uint8_t *pins, uint8_t channel_count, bool active_high)
{
    memset(s_channels, 0, sizeof(s_channels));
    s_channel_count = min(channel_count, static_cast<uint8_t>(HAL_MOSFET_OUTPUT_MAX_CHANNELS));
    s_active_high = active_high;

    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        s_channels[i].pin = pins[i];
        pinMode(s_channels[i].pin, OUTPUT);
        digitalWrite(s_channels[i].pin, inactive_level());
    }
}

void hal_mosfet_output_deinit()
{
    hal_mosfet_output_stop_all();
    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        pinMode(s_channels[i].pin, INPUT);
    }
    s_channel_count = 0;
}

bool hal_mosfet_output_start_channels(uint32_t channel_mask, uint32_t duration_ms)
{
    if (channel_mask == 0 || duration_ms == 0 || s_channel_count == 0 || hal_mosfet_output_is_in_progress())
    {
        return false;
    }

    const uint32_t end_at_ms = millis() + duration_ms;
    bool any_started = false;
    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        if ((channel_mask & (1UL << i)) == 0)
        {
            continue;
        }
        digitalWrite(s_channels[i].pin, active_level());
        s_channels[i].active = true;
        s_channels[i].end_at_ms = end_at_ms;
        any_started = true;
    }
    return any_started;
}

void hal_mosfet_output_loop()
{
    const uint32_t now_ms = millis();
    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        if (!s_channels[i].active)
        {
            continue;
        }
        if (static_cast<int32_t>(s_channels[i].end_at_ms - now_ms) <= 0)
        {
            digitalWrite(s_channels[i].pin, inactive_level());
            s_channels[i].active = false;
            s_channels[i].end_at_ms = 0;
        }
    }
}

void hal_mosfet_output_stop_all()
{
    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        digitalWrite(s_channels[i].pin, inactive_level());
        s_channels[i].active = false;
        s_channels[i].end_at_ms = 0;
    }
}

bool hal_mosfet_output_is_in_progress()
{
    for (uint8_t i = 0; i < s_channel_count; ++i)
    {
        if (s_channels[i].active)
        {
            return true;
        }
    }
    return false;
}
