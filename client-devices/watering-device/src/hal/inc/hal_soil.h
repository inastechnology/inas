#pragma once
#include <Arduino.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /** 初期化 & キャリブレーション
     *  @param adc_pin   アナログ入力に使う GPIO
     *  @param dry_raw   “完全に乾いた状態” の ADC 値
     *  @param wet_raw   “十分に湿った状態” の ADC 値
     *  @return 初期化 OK なら true
     *
     *  ※ dry_raw は wet_raw より大きい値にしてください。
     */
    bool hal_soil_init(gpio_num_t adc_pin,
                       uint16_t dry_raw,
                       uint16_t wet_raw);

    /** 初期化を解除 */
    void hal_soil_deinit(void);

    /** 1 回だけ読み取り（RAW 0-4095） */
    uint16_t hal_soil_read_raw(void);

    /** 0-100 %（水分量）の整数値を返す */
    uint8_t hal_soil_read_percent(void);

    /* キャリブレーション値の後変更用 */
    void hal_soil_set_calibration(uint16_t dry_raw, uint16_t wet_raw);
    void hal_soil_get_calibration(uint16_t *dry_raw, uint16_t *wet_raw);

#ifdef __cplusplus
}
#endif
