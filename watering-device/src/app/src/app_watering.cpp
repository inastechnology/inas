#include "app_watering.h"
#include "hal_soil.h"
#include "hal_output.h"
#include "app_pin.h"

#define SOIL_SENSOR_PIN A2 // Example GPIO pin for soil moisture sensor

static const uint8_t kWateringPins[] = {
    PUMP_PIN,
    VALVE_PIN,
};

static uint8_t _last_moisture = 0;
static uint8_t s_watering_threshold = 40;

static void on_watering_complete(void *arg)
{
    (void)arg;
    Serial.println("Watering completed");
}

void app_watering_init()
{
    if (!hal_soil_init((gpio_num_t)SOIL_SENSOR_PIN, 1895, 1285))
    {
        Serial.println("Failed to initialize soil moisture sensor");
        return;
    }

    hal_output_init(kWateringPins, sizeof(kWateringPins) / sizeof(kWateringPins[0]));
    Serial.println("Watering system initialized successfully");
}

void app_watering_deinit()
{
    hal_output_deinit();
    hal_soil_deinit();
}

void app_watering_loop()
{
    hal_output_loop();
}

void app_watering_set_threshold(uint8_t threshold_percent)
{
    s_watering_threshold = constrain(threshold_percent, 0, 100);
}

uint8_t app_watering_get_threshold()
{
    return s_watering_threshold;
}

bool app_watering_start(int duration_sec, uint32_t channel_mask, bool force_watering)
{
    if (!app_watering_start_async(duration_sec, channel_mask, force_watering))
    {
        return false;
    }

    while (app_watering_is_in_progress())
    {
        app_watering_loop();
        delay(50);
    }

    return true;
}

bool app_watering_start_async(int duration_sec, uint32_t channel_mask, bool force_watering)
{
    if (app_watering_is_in_progress())
    {
        Serial.println("Watering is already in progress");
        return false;
    }

    if (channel_mask == 0)
    {
        Serial.println("No watering channels selected");
        return false;
    }

    uint8_t moisture = hal_soil_read_percent();
    _last_moisture = moisture;
    Serial.printf("Current soil moisture: %u%% threshold=%u%% force_watering=%s\n",
                  moisture,
                  s_watering_threshold,
                  force_watering ? "true" : "false");

    if (force_watering || moisture < s_watering_threshold)
    {
        if (force_watering)
        {
            Serial.printf("Force watering enabled, starting watering on mask 0x%lx...\n",
                          static_cast<unsigned long>(channel_mask));
        }
        else
        {
            Serial.printf("Soil is dry (%u < %u), starting watering on mask 0x%lx...\n",
                          moisture,
                          s_watering_threshold,
                          static_cast<unsigned long>(channel_mask));
        }
        if (!hal_output_start_channels_async(channel_mask, static_cast<uint32_t>(duration_sec) * 1000UL, on_watering_complete))
        {
            Serial.println("Failed to start watering output");
            return false;
        }
        Serial.printf("Watering for %d seconds...\n", duration_sec);
        return true;
    }

    Serial.printf("Soil moisture is sufficient (%u >= %u), no watering needed\n", moisture, s_watering_threshold);
    return false;
}

uint8_t app_watering_get_last_soil_moisture()
{
    return _last_moisture;
}

bool app_watering_is_in_progress()
{
    return hal_output_is_in_progress();
}
