#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

/** 割り込み側で立てられる EventGroup のビットを待機
 *  @param flag     待ち受けるビット（複数可）
 *  @param timeout  FreeRTOS tick 単位（portMAX_DELAY で無限待ち）
 */
#ifdef __cplusplus
extern "C"
{
#endif

    void app_notifier_wait(EventBits_t flag, TickType_t timeout);

#ifdef __cplusplus
}
#endif
