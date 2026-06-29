#include "hal_soil.h"

/* ---- ローカル状態 ---- */
static gpio_num_t s_pin = GPIO_NUM_NC;
static uint16_t s_dry_raw = 3200; // デフォルト: 乾いた空気中
static uint16_t s_wet_raw = 1500; // デフォルト: 水に浸漬
static bool s_ready = false;

/* ---- 初期化 ---- */
bool hal_soil_init(gpio_num_t adc_pin, uint16_t dry_raw, uint16_t wet_raw)
{
    if (adc_pin == GPIO_NUM_NC || dry_raw <= wet_raw)
        return false;

    s_pin = adc_pin;
    s_dry_raw = dry_raw;
    s_wet_raw = wet_raw;

    /* ADC 設定（ESP32-S3／Arduino core）*/
    analogSetPinAttenuation(s_pin, ADC_11db); // 0-3.1 V レンジ
    analogReadResolution(12);                 // 0-4095 に統一
    s_ready = true;

    Serial.printf("Soil sensor initialized on pin %d\n", s_pin);
    Serial.printf("Dry raw value: %d, Wet raw value: %d\n", s_dry_raw, s_wet_raw);
    Serial.printf("Ready to read soil moisture.\n");
    return true;
}

void hal_soil_deinit(void)
{
    s_ready = false;
    s_pin = GPIO_NUM_NC; // 無効化
    s_dry_raw = 3200;    // デフォルト値に戻す
    s_wet_raw = 1500;    // デフォルト値に戻す
}

/* ---- 読み取り ---- */
uint16_t hal_soil_read_raw(void)
{
    return s_ready ? analogRead(s_pin) : 0;
}

uint8_t hal_soil_read_percent(void)
{
    uint32_t sum_of_raw = 0;
    const int num_samples = 20; // 平均化のためのサンプル
    for (int i = 0; i < num_samples; ++i)
    {
        sum_of_raw += hal_soil_read_raw();
        delay(40); // サンプリング間隔
    }
    uint16_t raw = sum_of_raw / num_samples; // 平均値を計算
    Serial.printf("Soil raw value: %d\n", raw);
    raw = constrain(raw, s_wet_raw, s_dry_raw); // 範囲クランプ
    Serial.printf("Constrained raw value: %d\n", raw);
    return map(raw, s_dry_raw, s_wet_raw, 0, 100); // 乾 0 % ←→ 湿 100 %
}

/* ---- キャリブレーション操作 ---- */
void hal_soil_set_calibration(uint16_t dry_raw, uint16_t wet_raw)
{
    if (dry_raw > wet_raw)
    {
        s_dry_raw = dry_raw;
        s_wet_raw = wet_raw;
    }
}
void hal_soil_get_calibration(uint16_t *dry_raw, uint16_t *wet_raw)
{
    if (dry_raw)
        *dry_raw = s_dry_raw;
    if (wet_raw)
        *wet_raw = s_wet_raw;
}
