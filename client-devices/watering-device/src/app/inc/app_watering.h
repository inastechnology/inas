#pragma once
#include <Arduino.h>

#ifdef __cplusplus
extern "C"
{
#endif

    void app_watering_init();
    void app_watering_deinit();
    void app_watering_loop();
    void app_watering_set_threshold(uint8_t threshold_percent);
    uint8_t app_watering_get_threshold();
    bool app_watering_start(int duration_sec = 10, uint32_t channel_mask = 0x1, bool force_watering = false);
    bool app_watering_start_async(int duration_sec = 10, uint32_t channel_mask = 0x1, bool force_watering = false);
    bool app_watering_is_in_progress();
    uint8_t app_watering_get_last_soil_moisture();
#ifdef __cplusplus
}
#endif
