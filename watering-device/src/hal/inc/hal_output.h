#pragma once
#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#ifdef __cplusplus
extern "C"
{
#endif

    #define HAL_OUTPUT_MAX_CHANNELS 4

    /** 出力chの初期化
     *  @param pins GPIOピン配列
     *  @param channel_count ch数
     */
    void hal_output_init(const uint8_t *pins, uint8_t channel_count);

    /** MOSFET 出力の終了処理
     *  - 割り込みを無効化
     *  - EventGroup を削除
     *  - MOSFET ピンを LOW にする
     */
    void hal_output_deinit(void);

    /** 指定されたchを同時に HIGH にする
     *  @param channel_mask bit0=ch0, bit1=ch1...
     *  @param duration_ms  出力時間 [ms]
     *  @param on_complete 完了時呼ばれるハンドラ
     */
    bool hal_output_start_channels_async(uint32_t channel_mask, uint32_t duration_ms, void (*on_complete)(void *) = nullptr);

    /** 状態更新。loop内から定期的に呼び出す */
    void hal_output_loop(void);

    /** すべての出力を停止する */
    void hal_output_stop_all(void);

    /** MOSFET 出力が進行中かどうかを返す
     *  @return 出力中なら true
     */
    bool hal_output_is_in_progress(void);

#ifdef __cplusplus
}
#endif
