#include "hal_output.h"

#include <string.h>

typedef struct
{
    uint8_t pin;
    bool active;
    uint32_t end_at_ms;
} hal_output_channel_state_t;

static hal_output_channel_state_t s_channels[HAL_OUTPUT_MAX_CHANNELS];
static uint8_t s_channel_count = 0;
static void (*s_on_complete)(void *) = nullptr;

void hal_output_init(const uint8_t *pins, uint8_t channel_count)
{
    memset(s_channels, 0, sizeof(s_channels));
    s_channel_count = min(channel_count, static_cast<uint8_t>(HAL_OUTPUT_MAX_CHANNELS));

    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        s_channels[i].pin = pins[i];
        pinMode(s_channels[i].pin, OUTPUT);
        digitalWrite(s_channels[i].pin, LOW);
    }
}

void hal_output_deinit(void)
{
    hal_output_stop_all();

    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        pinMode(s_channels[i].pin, INPUT);
    }

    s_channel_count = 0;
    s_on_complete = nullptr;
}

bool hal_output_start_channels_async(uint32_t channel_mask, uint32_t duration_ms, void (*on_complete)(void *))
{
    if (duration_ms == 0 || channel_mask == 0 || s_channel_count == 0)
    {
        return false;
    }

    if (hal_output_is_in_progress())
    {
        return false;
    }

    const uint32_t end_at_ms = millis() + duration_ms;
    bool any_channel_started = false;

    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        if ((channel_mask & (1UL << i)) == 0)
        {
            continue;
        }
        digitalWrite(s_channels[i].pin, HIGH);
        s_channels[i].active = true;
        s_channels[i].end_at_ms = end_at_ms;
        any_channel_started = true;
    }

    if (!any_channel_started)
    {
        return false;
    }

    s_on_complete = on_complete;
    return true;
}

void hal_output_stop_all()
{
    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        digitalWrite(s_channels[i].pin, LOW);
        s_channels[i].active = false;
        s_channels[i].end_at_ms = 0;
    }
}

void hal_output_loop()
{
    bool was_in_progress = hal_output_is_in_progress();
    bool any_active = false;
    const uint32_t now_ms = millis();

    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        if (!s_channels[i].active)
        {
            continue;
        }

        const int32_t remaining_ms = static_cast<int32_t>(s_channels[i].end_at_ms - now_ms);
        if (remaining_ms <= 0)
        {
            digitalWrite(s_channels[i].pin, LOW);
            s_channels[i].active = false;
            s_channels[i].end_at_ms = 0;
            continue;
        }

        any_active = true;
    }

    if (was_in_progress && !any_active && s_on_complete != nullptr)
    {
        void (*on_complete)(void *) = s_on_complete;
        s_on_complete = nullptr;
        on_complete(nullptr);
    }
}

bool hal_output_is_in_progress(void)
{
    for (uint8_t i = 0; i < s_channel_count; i++)
    {
        if (s_channels[i].active)
        {
            return true;
        }
    }
    return false;
}
