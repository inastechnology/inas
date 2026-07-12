#ifndef __HAL_POWER_SWITCH_H__
#define __HAL_POWER_SWITCH_H__

#include <stdint.h>

#ifndef APP_SENSOR_12V_POWER_PIN
#define APP_SENSOR_12V_POWER_PIN -1
#endif

#ifndef APP_SENSOR_12V_POWER_ACTIVE_HIGH
#define APP_SENSOR_12V_POWER_ACTIVE_HIGH 1
#endif

#ifndef APP_SENSOR_12V_POWER_SETTLE_MS
#define APP_SENSOR_12V_POWER_SETTLE_MS 800
#endif

#ifdef __cplusplus
extern "C"
{
#endif

typedef struct
{
    int pin;
    bool active_high;
    uint32_t settle_ms;
} hal_power_switch_config_t;

hal_power_switch_config_t hal_power_switch_default_config();
bool hal_power_switch_init(const hal_power_switch_config_t *config);
void hal_power_switch_deinit();
bool hal_power_switch_is_configured();
bool hal_power_switch_is_enabled();
void hal_power_switch_set_enabled(bool enabled);
bool hal_power_switch_enable_and_wait(uint32_t settle_ms_override);

#ifdef __cplusplus
}
#endif

#endif // __HAL_POWER_SWITCH_H__
