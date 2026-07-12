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
    uint8_t app_watering_read_soil_moisture();
    uint16_t app_watering_read_soil_raw_average(uint8_t sample_count = 20, uint16_t interval_ms = 40);
    void app_watering_set_soil_calibration(uint16_t dry_raw, uint16_t wet_raw);
    void app_watering_get_soil_calibration(uint16_t *dry_raw, uint16_t *wet_raw);
    bool app_watering_start(int duration_sec = 10, uint32_t channel_mask = 0x1, bool force_watering = false);
    bool app_watering_start_async(int duration_sec = 10, uint32_t channel_mask = 0x1, bool force_watering = false);
    bool app_watering_run_pattern(uint16_t on_sec,
                                  uint16_t off_sec,
                                  uint8_t repeat_count,
                                  uint32_t channel_mask,
                                  bool force_watering,
                                  void (*idle_loop)() = nullptr);
    bool app_watering_is_in_progress();
    uint8_t app_watering_get_last_soil_moisture();
#ifdef __cplusplus
}
#endif
