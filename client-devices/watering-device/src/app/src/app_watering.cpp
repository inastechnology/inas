#include "app_watering.h"
#include "hal_soil.h"
#include "hal_output.h"
#include "app_debug_log.h"
#include "app_pin.h"

static const uint8_t kWateringPins[] = {
    VALVE_PIN,
    PUMP_PIN,
};
static constexpr uint8_t kPumpOutputIndex = (sizeof(kWateringPins) / sizeof(kWateringPins[0])) - 1;
static constexpr uint32_t kPumpOutputMask = (1UL << kPumpOutputIndex);
static constexpr uint32_t kValveChannelMask = kPumpOutputMask - 1;

static uint8_t _last_moisture = 0;
static bool s_last_moisture_valid = false;
static uint8_t s_watering_threshold = 40;

static void on_watering_complete(void *arg)
{
    (void)arg;
    Serial.println("Watering completed");
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING, APP_DEBUG_LOG_INFO, APP_DEBUG_EVENT_WATERING_COMPLETED, 0, 0);
}

void app_watering_init()
{
    if (!hal_soil_init((gpio_num_t)SOIL_SENSOR_PIN, 1895, 1285))
    {
        Serial.println("Failed to initialize soil moisture sensor");
        return;
    }

    hal_output_init(kWateringPins, sizeof(kWateringPins) / sizeof(kWateringPins[0]));
    Serial.printf("Watering output map: valve_mask=0x%lx pump_mask=0x%lx valve_pin=%u pump_pin=%u\n",
                  static_cast<unsigned long>(kValveChannelMask),
                  static_cast<unsigned long>(kPumpOutputMask),
                  static_cast<unsigned int>(VALVE_PIN),
                  static_cast<unsigned int>(PUMP_PIN));
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_WATERING_OUTPUT_MAP,
                        static_cast<int32_t>(kValveChannelMask),
                        static_cast<int32_t>(kPumpOutputMask));
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

uint8_t app_watering_read_soil_moisture()
{
    _last_moisture = hal_soil_read_percent();
    s_last_moisture_valid = true;
    Serial.printf("Soil moisture measured: %u%%\n", _last_moisture);
    return _last_moisture;
}

uint16_t app_watering_read_soil_raw_average(uint8_t sample_count, uint16_t interval_ms)
{
    const uint16_t raw = hal_soil_read_raw_average(sample_count, interval_ms);
    Serial.printf("Soil raw average: %u\n", raw);
    return raw;
}

void app_watering_set_soil_calibration(uint16_t dry_raw, uint16_t wet_raw)
{
    hal_soil_set_calibration(dry_raw, wet_raw);
}

void app_watering_get_soil_calibration(uint16_t *dry_raw, uint16_t *wet_raw)
{
    hal_soil_get_calibration(dry_raw, wet_raw);
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

bool app_watering_run_pattern(uint16_t on_sec,
                              uint16_t off_sec,
                              uint8_t repeat_count,
                              uint32_t channel_mask,
                              bool force_watering,
                              void (*idle_loop)())
{
    if (on_sec == 0 || repeat_count == 0)
    {
        return false;
    }

    bool any_started = false;
    for (uint8_t i = 0; i < repeat_count; i++)
    {
        const bool pulse_force = force_watering || any_started;
        if (!app_watering_start_async(on_sec, channel_mask, pulse_force))
        {
            return any_started;
        }
        any_started = true;

        while (app_watering_is_in_progress())
        {
            app_watering_loop();
            if (idle_loop != nullptr)
            {
                idle_loop();
            }
            delay(50);
        }

        if (off_sec > 0 && i + 1 < repeat_count)
        {
            const uint32_t pause_until_ms = millis() + static_cast<uint32_t>(off_sec) * 1000UL;
            while (static_cast<int32_t>(pause_until_ms - millis()) > 0)
            {
                app_watering_loop();
                if (idle_loop != nullptr)
                {
                    idle_loop();
                }
                delay(50);
            }
        }
    }

    return any_started;
}

bool app_watering_start_async(int duration_sec, uint32_t channel_mask, bool force_watering)
{
    if (app_watering_is_in_progress())
    {
        Serial.println("Watering is already in progress");
        return false;
    }

    const uint32_t valve_mask = channel_mask & kValveChannelMask;
    if (valve_mask == 0)
    {
        Serial.printf("No watering valve channels selected: requested_mask=0x%lx valve_mask=0x%lx\n",
                      static_cast<unsigned long>(channel_mask),
                      static_cast<unsigned long>(kValveChannelMask));
        return false;
    }
    const uint32_t output_mask = valve_mask | kPumpOutputMask;

    uint8_t moisture = s_last_moisture_valid ? _last_moisture : app_watering_read_soil_moisture();
    Serial.printf("Current soil moisture: %u%% threshold=%u%% force_watering=%s requested_mask=0x%lx output_mask=0x%lx\n",
                  moisture,
                  s_watering_threshold,
                  force_watering ? "true" : "false",
                  static_cast<unsigned long>(channel_mask),
                  static_cast<unsigned long>(output_mask));
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                        APP_DEBUG_LOG_INFO,
                        APP_DEBUG_EVENT_WATERING_DECISION,
                        static_cast<int32_t>(moisture) |
                            (static_cast<int32_t>(s_watering_threshold) << 8) |
                            (force_watering ? (1L << 16) : 0),
                        static_cast<int32_t>(output_mask));

    if (force_watering || moisture < s_watering_threshold)
    {
        if (force_watering)
        {
            Serial.printf("Force watering enabled, starting watering on valve mask 0x%lx with pump...\n",
                          static_cast<unsigned long>(valve_mask));
        }
        else
        {
            Serial.printf("Soil is dry (%u < %u), starting watering on valve mask 0x%lx with pump...\n",
                          moisture,
                          s_watering_threshold,
                          static_cast<unsigned long>(valve_mask));
        }
        if (!hal_output_start_channels_async(output_mask, static_cast<uint32_t>(duration_sec) * 1000UL, on_watering_complete))
        {
            Serial.println("Failed to start watering output");
            APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                                APP_DEBUG_LOG_ERROR,
                                APP_DEBUG_EVENT_WATERING_OUTPUT_START_FAILED,
                                duration_sec,
                                static_cast<int32_t>(output_mask));
            return false;
        }
        Serial.printf("Watering for %d seconds...\n", duration_sec);
        APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                            APP_DEBUG_LOG_INFO,
                            APP_DEBUG_EVENT_WATERING_STARTED,
                            duration_sec,
                            static_cast<int32_t>(output_mask));
        return true;
    }

    Serial.printf("Soil moisture is sufficient (%u >= %u), no watering needed\n", moisture, s_watering_threshold);
    APP_DEBUG_LOG_EVENT(APP_DEBUG_FILE_WATERING,
                        APP_DEBUG_LOG_WARNING,
                        APP_DEBUG_EVENT_WATERING_SKIPPED_MOISTURE,
                        moisture,
                        s_watering_threshold);
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
