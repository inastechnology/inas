#ifndef __HAL_MOSFET_OUTPUT_H__
#define __HAL_MOSFET_OUTPUT_H__

#include <stdint.h>

#ifndef HAL_MOSFET_OUTPUT_MAX_CHANNELS
#define HAL_MOSFET_OUTPUT_MAX_CHANNELS 4
#endif

#ifdef __cplusplus
extern "C"
{
#endif

void hal_mosfet_output_init(const uint8_t *pins, uint8_t channel_count, bool active_high);
void hal_mosfet_output_deinit();
bool hal_mosfet_output_start_channels(uint32_t channel_mask, uint32_t duration_ms);
void hal_mosfet_output_loop();
void hal_mosfet_output_stop_all();
bool hal_mosfet_output_is_in_progress();

#ifdef __cplusplus
}
#endif

#endif // __HAL_MOSFET_OUTPUT_H__
